import socketserver
import threading
from datetime import datetime, timedelta

import pytest

from atlas.alerts import AlertStore
from atlas.config.models import AtlasConfig
from atlas.monitoring import ups
from atlas.posture.store import PostureStore
from atlas.web.uptime_page import render_uptime_page

STATE = {"status": "OL", "charge": "100", "runtime": "2400"}


class Nut(socketserver.StreamRequestHandler):
    """Speaks the part of the NUT protocol atlas uses: LIST UPS, LIST VAR, LOGOUT."""

    def handle(self):
        for raw in self.rfile:
            line = raw.decode().strip()
            if line == "LIST UPS":
                self.wfile.write(b'BEGIN LIST UPS\nUPS rack "Rack UPS"\nEND LIST UPS\n')
            elif line == "LIST VAR rack":
                self.wfile.write(("BEGIN LIST VAR rack\n"
                                  f'VAR rack ups.status "{STATE["status"]}"\nVAR rack battery.charge "{STATE["charge"]}"\n'
                                  f'VAR rack battery.runtime "{STATE["runtime"]}"\nVAR rack ups.load "23"\n'
                                  'VAR rack device.mfr "APC"\nVAR rack device.model "Back-UPS 1500"\n'
                                  "END LIST VAR rack\n").encode())
            elif line.startswith("LIST VAR"):
                self.wfile.write(b"ERR UNKNOWN-UPS\n")
            elif line == "LOGOUT":
                self.wfile.write(b"OK Goodbye\n")
                return


@pytest.fixture
def nut():
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Nut)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def test_fetch_reads_every_ups_and_refuses_an_unknown_one(nut):

    found = ups.fetch("127.0.0.1", nut)
    assert list(found) == ["rack"] and found["rack"]["battery.charge"] == "100"
    info = ups.summarize(found["rack"])
    assert info == {"state": "online", "charge": 100.0, "load": 23.0, "runtime_min": 40, "replace": False,
                    "model": "APC Back-UPS 1500"}
    with pytest.raises(OSError, match="UNKNOWN-UPS"):
        ups.fetch("127.0.0.1", nut, name="garage")


def test_power_cut_low_battery_and_back(nut, temp_db):

    settings = AtlasConfig(ups={"enabled": True, "host": "127.0.0.1", "port": nut})
    store, sent, start = PostureStore(), [], datetime(2026, 1, 1, 20)
    steps = [("OL", "100", "2400"), ("OB DISCHRG", "87", "1500"), ("OB DISCHRG LB", "9", "120"),
             ("OL CHRG", "12", "2400")]
    for minute, (status, charge, runtime) in enumerate(steps):
        STATE.update(status=status, charge=charge, runtime=runtime)
        ups.run(settings, store, start + timedelta(minutes=minute * 10), send=sent.append)
        if minute == 1:
            assert [a["title"] for a in AlertStore().listing(start)["open"]] == \
                ["UPS rack (APC Back-UPS 1500): power cut - running on battery"]

    assert [text.split("\n")[0] for text in sent] == [
        "**⚡ Power cut: UPS rack (APC Back-UPS 1500) is on battery**",
        "**🔋 UPS rack (APC Back-UPS 1500): battery low**",
        "**✅ Power is back: UPS rack (APC Back-UPS 1500)**"]
    assert "87% charged, about 25 min left" in sent[0] and "lasted about 20 min" in sent[2]
    assert AlertStore().listing(start + timedelta(hours=1))["open"] == []


def test_a_blip_reading_the_server_is_not_a_power_change(nut, temp_db):

    settings = AtlasConfig(ups={"enabled": True, "host": "127.0.0.1", "port": nut})
    store, sent, now = PostureStore(), [], datetime(2026, 1, 1, 20)
    STATE.update(status="OL", charge="100", runtime="2400")
    ups.run(settings, store, now, send=sent.append)

    def down(*args):
        raise OSError("connection refused")
    detail = ups.run(settings, store, now + timedelta(minutes=1), get=down, send=sent.append)
    assert detail["error"] == "connection refused" and detail["upses"]["rack"]["state"] == "online"
    ups.run(settings, store, now + timedelta(minutes=2), send=sent.append)
    assert sent == []

    page = render_uptime_page([], {}, now, power=detail)
    assert "On mains" in page and "100% charged" in page and "about 40 min on battery" in page


def test_setup_card_tests_the_ups_server(nut, isolated_cwd, monkeypatch):

    from atlas.web.settings_page import handle_post
    status, body = handle_post("/api/settings/ups/test", {"host": "127.0.0.1", "port": nut, "name": ""})
    assert status == 200 and body["message"].startswith("Connected: rack on mains power, 100% charged")
    status, body = handle_post("/api/settings/ups/test", {"host": "", "port": nut})
    assert status == 400 and "address" in body["error"]
