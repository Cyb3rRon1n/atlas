"""Preferences > Time & date: the display: settings, the save endpoint, and every place a time is written."""

import json
import os
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer

import pytest
from pydantic import ValidationError

from lanxang.clock import stamp
from lanxang.config.models import AtlasConfig, DisplayConfig
from lanxang.web import render
from lanxang.web.render import TIME_SCRIPT, friendly_time, render_page, when

NOW = datetime(2026, 11, 17, 12, 0)                    # naive UTC; 07:00 in New York (EST)
THEN = datetime(2026, 10, 28, 19, 5)                   # 20 days before; 15:05 in New York (EDT)
NY = "America/New_York"


def test_defaults_and_validation():
    assert DisplayConfig().model_dump() == {"clock": "24h", "time_zone": "browser", "date_format": "iso"}
    assert AtlasConfig().display == DisplayConfig()
    assert DisplayConfig(time_zone=" Asia/Vientiane ").time_zone == "Asia/Vientiane"
    for bad in ({"clock": "13h"}, {"date_format": "ymd"}):
        with pytest.raises(ValidationError):
            DisplayConfig(**bad)
    for zone in ("Mars/Base", "America", "../etc/passwd"):          # never breaks loading: falls back to browser
        assert DisplayConfig(time_zone=zone).time_zone == "browser"


def test_unknown_saved_zone_still_loads(isolated_cwd):
    from lanxang.config.loader import load_config

    (isolated_cwd / "inventory").mkdir()
    (isolated_cwd / "inventory" / "settings.yaml").write_text("display:\n  time_zone: Mars/Base\n  clock: 12h\n")
    shown = load_config().display
    assert shown.time_zone == "browser" and shown.clock == "12h"


def test_zone_data_gone_falls_back_to_utc():
    shown = DisplayConfig.model_construct(clock="24h", time_zone="Mars/Base", date_format="iso")   # skips validation
    assert stamp(THEN, shown) == "2026-10-28 19:05 UTC"


def test_unparseable_times_in_messages():
    from types import SimpleNamespace

    from lanxang.clock import stamp_text
    from lanxang.monitoring import dnsfilter, heartbeat

    assert stamp_text("garbage", SHOWN) == "garbage" and stamp_text(None) == "never"
    assert stamp_text("2026-10-28T19:05:00", SHOWN, date=False) == "3:05 PM EDT"

    class Store:
        def __init__(self, statuses):
            self.saved = statuses
        def statuses(self):
            return self.saved
        def set_status(self, *a, **k):
            pass

    settings = AtlasConfig(display=SHOWN.model_dump(), uptime={"heartbeats": [{"name": "Backup"}]},
                           dns_filter={"enabled": True, "url": "http://192.0.2.2"})
    sent = []
    beat = Store({"ping:Backup": {"detail": {"at": "garbage", "failed": True}}})
    import lanxang.alerts as alerts
    original = alerts.report, alerts.allowed
    alerts.report, alerts.allowed = (lambda *a, **k: None), (lambda *a, **k: True)
    try:
        heartbeat.run(settings, beat, NOW, send=sent.append)
        dns = Store({"dns": {"detail": {"off_since": "garbage", "alerted": False}}})
        dnsfilter.run(settings, dns, NOW, get=lambda config: {"kind": "Pi-hole", "blocking": False}, send=sent.append)
    finally:
        alerts.report, alerts.allowed = original
    assert any("at garbage" in text for text in sent) and any("off since garbage" in text for text in sent)


@pytest.mark.parametrize("clock", ["24h", "12h"])
@pytest.mark.parametrize("dates", ["iso", "dmy", "mdy"])
@pytest.mark.parametrize("zone", ["UTC", NY])
def test_server_text_for_every_combination(clock, dates, zone):
    shown = DisplayConfig(clock=clock, date_format=dates, time_zone=zone)
    day = {"iso": "2026-10-28", "dmy": "28/10/2026", "mdy": "10/28/2026"}[dates]
    hour = {("24h", "UTC"): "19:05 UTC", ("12h", "UTC"): "7:05 PM UTC",
            ("24h", NY): "15:05 EDT", ("12h", NY): "3:05 PM EDT"}[clock, zone]
    assert stamp(THEN, shown) == f"{day} {hour}"
    assert stamp(THEN, shown, date=False) == hour
    assert friendly_time(THEN, NOW, display=shown) == day
    assert friendly_time(THEN, NOW, clock=True, display=shown) == hour
    assert friendly_time(THEN, NOW, clock="day", display=shown) == f"Wed {day}"


def test_zone_moves_the_day_boundary():
    late = datetime(2026, 11, 17, 2, 30)              # still the 16th in New York
    assert friendly_time(late, NOW, display=DisplayConfig(time_zone=NY, clock="12h")) == "yesterday 9:30 PM EST"
    assert friendly_time(late, NOW) == "today 02:30 UTC"            # browser: the server's fallback says UTC


def test_pages_carry_the_setting(monkeypatch):
    assert '<html lang="en" data-clock="24h" data-datefmt="iso" data-tz="browser">' in render_page("Home", "")
    monkeypatch.setattr(render, "DISPLAY", DisplayConfig(clock="12h", date_format="mdy", time_zone=NY))
    html = render_page("Home", when(THEN, NOW))
    assert '<html lang="en" data-clock="12h" data-datefmt="mdy" data-tz="America/New_York">' in html
    assert 'title="10/28/2026 3:05 PM EDT">10/28/2026</time>' in html


def test_panel_time_section():
    panel = render_page("Home", "").split('<div id="prefs"')[1].split("<script>")[0]
    section = panel.split("<h3>Time &amp; date</h3>")[1].split("<h3>")[0]
    assert "alert messages" in section and 'id="pref-time-status"' in section and 'role="status"' in section
    for pref, values in (("clock", ["24h", "12h"]), ("date_format", ["iso", "dmy", "mdy"]),
                         ("zone", ["browser", "UTC", "other"])):
        group = section.split(f'data-spref="{pref}">')[1].split("</div>")[0]
        assert [v.split('"')[0] for v in group.split('data-v="')[1:]] == values
    assert 'list="pref-zones"' in section and "data-pref=" not in section       # never kept in localStorage
    assert "/api/settings/display/save" in render.TIME_PREFS_SCRIPT


# --- the save endpoint, through a real server -------------------------------------------------------------------

@pytest.fixture
def server(temp_db, isolated_cwd):
    from lanxang.web.server import AtlasWebHandler

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), AtlasWebHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join()
        httpd.server_close()


def _post(base, body, origin=True):
    headers = {"Content-Type": "application/json", **({"Origin": base} if origin else {})}
    request = urllib.request.Request(base + "/api/settings/display/save", data=json.dumps(body).encode(),
                                     headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        with error:
            return error.code, json.loads(error.read())


def test_save_good_values_then_pages_use_them(server):
    from lanxang.config import local
    from lanxang.config.loader import load_config

    status, data = _post(server, {"clock": "12h", "date_format": "mdy", "time_zone": NY})
    assert status == 200 and data["message"] == "Saved."
    assert data["display"] == {"clock": "12h", "time_zone": NY, "date_format": "mdy"}
    assert local.read_settings()["display"] == {"clock": "12h", "time_zone": NY, "date_format": "mdy"}
    assert load_config().display.time_zone == NY
    with urllib.request.urlopen(server + "/alerts", timeout=5) as response:
        assert 'data-clock="12h" data-datefmt="mdy" data-tz="America/New_York"' in response.read().decode()


def test_save_rejects_bad_values_and_keeps_the_old_ones(server):
    from lanxang.config import local

    assert _post(server, {"time_zone": "UTC"})[0] == 200
    status, data = _post(server, {"time_zone": "Mars/Base"})
    assert status == 400 and "unknown time zone" in data["error"]
    assert _post(server, {"time_zone": "America"})[0] == 400
    assert _post(server, {"clock": "25h"})[0] == 400
    assert _post(server, {"clock": 12})[0] == 400
    assert _post(server, {})[0] == 400
    assert local.read_settings()["display"] == {"time_zone": "UTC"}


def test_save_needs_same_origin(server):
    from lanxang.config import local

    status, data = _post(server, {"clock": "12h"}, origin=False)
    assert status == 403 and "cross-origin" in data["error"]
    assert "display" not in local.read_settings()


def test_config_file_wins(server, isolated_cwd):
    (isolated_cwd / "lanxang.yaml").write_text("display:\n  clock: 24h\n")
    status, data = _post(server, {"clock": "12h"})
    assert status == 400 and "lanxang.yaml" in data["error"]
    assert _post(server, {"clock": "24h", "date_format": "dmy"})[0] == 200     # unchanged pinned value is fine


# --- messages ---------------------------------------------------------------------------------------------------

SHOWN = DisplayConfig(clock="12h", date_format="mdy", time_zone=NY)


def test_test_alert_text():
    from lanxang import notify

    assert notify.test_text(SHOWN, THEN).endswith("• sent 10/28/2026 3:05 PM EDT")
    assert notify.test_text(None, THEN).endswith("• sent 2026-10-28 19:05 UTC")             # browser -> UTC


def test_device_alert_text():
    from lanxang.devices.notify import format_message

    item = [{"id": 1, "device": "Den TV", "ip": "192.0.2.5", "last_seen": THEN.isoformat()}]
    assert "last seen 10/28/2026 3:05 PM EDT" in format_message("offline", item, SHOWN)
    assert "last seen 2026-10-28 19:05 UTC" in format_message("offline", item)


def test_weekly_summary_text():
    from lanxang.monitoring import summary

    empty = {key: (lambda *a: None) for key in ("internet_rows", "uptime_summary", "devices", "alerts", "statuses", "disks")}
    text = summary.build(AtlasConfig(display=SHOWN.model_dump()), NOW, empty)
    assert text.splitlines()[1] == "11/10/2026 to 11/17/2026, sent 7:00 AM EST"
    assert summary.build(AtlasConfig(), NOW, empty).splitlines()[1] == "2026-11-10 to 2026-11-17, sent 12:00 UTC"


def test_cert_and_dns_alert_text():
    from lanxang.posture import certs

    entry = {"level": "soon", "days": 5, "issuer": "", "error": "", "expires": "2026-11-23T03:00:00+00:00"}
    assert "• 11/22/2026" in certs._text("example.org", entry, SHOWN)        # 22:00 the evening before in New York
    assert "• 2026-11-23" in certs._text("example.org", entry)


# --- the page script, in node -----------------------------------------------------------------------------------

HARNESS = r"""
const [script, attrs, stamps, now] = JSON.parse(process.argv[1]);
const RealDate = Date;
global.Date = class extends RealDate { constructor(...a) { if (a.length) super(...a); else super(now); } };
Date.UTC = RealDate.UTC;
const times = stamps.map(([iso, mode]) => ({getAttribute: () => iso, dataset: {when: mode}, textContent: "", title: ""}));
global.document = {documentElement: {dataset: attrs}, querySelectorAll: () => times};
global.window = global; global.setInterval = () => 0;
eval(script);
console.log(JSON.stringify(times.map((t) => [t.textContent, t.title])));
"""


def run_times(attrs, stamps, browser_tz="UTC"):
    if not shutil.which("node"):
        pytest.skip("node not installed")
    script = TIME_SCRIPT.removeprefix("<script>").removesuffix("</script>")
    out = subprocess.run(["node", "-e", HARNESS, json.dumps([script, attrs, stamps, "2026-11-17T12:00:00Z"])],
                         capture_output=True, text=True, check=True, env={**os.environ, "TZ": browser_tz}
                         ).stdout
    return json.loads(out)


STAMPS = [["2026-10-28T19:05:00Z", "rel"], ["2026-10-28T19:05:00Z", "clock"], ["2026-10-28T19:05:00Z", "day"],
          ["2026-11-17T02:30:00Z", "rel"], ["2026-11-17T11:58:00Z", "rel"]]


@pytest.mark.parametrize("clock", ["24h", "12h"])
@pytest.mark.parametrize("dates", ["iso", "dmy", "mdy"])
@pytest.mark.parametrize("zone", ["UTC", NY])
def test_page_script_matches_the_server(clock, dates, zone):
    shown = DisplayConfig(clock=clock, date_format=dates, time_zone=zone)
    got = run_times({"clock": clock, "datefmt": dates, "tz": zone}, STAMPS, browser_tz="Asia/Tokyo")
    for (iso, mode), (text, title) in zip(STAMPS, got):
        moment = datetime.fromisoformat(iso[:-1])
        server = friendly_time(moment, NOW, {"rel": False, "clock": True, "day": "day"}[mode], shown)
        assert text == server.removesuffix(" UTC").removesuffix(" EST").removesuffix(" EDT")
        assert title == stamp(moment, shown).rsplit(" ", 1)[0] + " " + zone


def test_page_script_browser_zone_uses_the_viewers_clock():
    got = run_times({"clock": "12h", "datefmt": "dmy", "tz": "browser"}, STAMPS[:2], browser_tz=NY)
    assert got == [["28/10/2026", "28/10/2026 3:05 PM"], ["3:05 PM", "28/10/2026 3:05 PM"]]
    assert run_times({}, STAMPS[:1])[0] == ["2026-10-28", "2026-10-28 19:05"]          # no attributes: defaults
