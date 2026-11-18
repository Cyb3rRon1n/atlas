import socket
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from lanxang.alerts import AlertStore
from lanxang.config.models import AtlasConfig
from lanxang.monitoring import uptime
from lanxang.monitoring.uptime import UptimeStore, probe, run, valid_target
from lanxang.web import uptime_page


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response({"/ok": 200, "/login": 401, "/broken": 503}.get(self.path, 404))
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_probe_counts_any_answer_below_500_as_up(server):

    assert probe(f"http://{server}/ok")[0] is True
    assert probe(f"http://{server}/login")[::2] == (True, "HTTP 401")       # a login wall still means it's running
    assert probe(f"http://{server}/broken")[::2] == (False, "HTTP 503")
    assert probe(server)[::2] == (True, "port open")
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    ok, ms, detail = probe(f"127.0.0.1:{port}", timeout=2)
    assert ok is False and ms is None and detail


def test_valid_target():

    assert valid_target(" https://media.example.org/health ") == "https://media.example.org/health"
    assert valid_target("192.0.2.10:22") == "192.0.2.10:22"
    for bad in ("media.example.org", "https://", "192.0.2.10:99999", ""):
        with pytest.raises(ValueError):
            valid_target(bad)


def settings():
    return AtlasConfig(uptime={"checks": [{"name": "Media", "target": "https://media.example.org"}], "fail_after": 2})


def test_down_after_two_failures_then_back_up_with_duration(temp_db):

    store, sent, start = UptimeStore(), [], datetime(2026, 1, 1, 12)
    answers = iter([True, False, False, False, True])
    check = lambda target, timeout: (True, 40.0, "HTTP 200") if next(answers) else (False, None, "timed out")

    for minute in range(5):
        run(settings(), store, start + timedelta(minutes=minute), check=check, send=sent.append)
        open_titles = [a["title"] for a in AlertStore().listing(start + timedelta(minutes=minute))["open"]]
        assert ("Media is down" in open_titles) == (minute in (2, 3))

    assert len(sent) == 2
    assert sent[0].startswith("**🔴 Media is down**") and "timed out" in sent[0]
    assert sent[1].startswith("**✅ Media is back up**") and "down for about 3 min" in sent[1]

    info = store.summary(["Media"], start + timedelta(minutes=5))["Media"]
    assert info["uptime"]["24 h"] == 40.0 and info["last_failure"][1] == "timed out"


def test_muted_check_is_listed_but_not_sent(temp_db):

    store, sent, start = UptimeStore(), [], datetime(2026, 1, 1, 12)
    AlertStore().pause(1, start)
    for minute in range(2):
        run(settings(), store, start + timedelta(minutes=minute), check=lambda t, timeout: (False, None, "refused"),
            send=sent.append)
    assert sent == []
    assert [a["title"] for a in AlertStore().listing(start)["open"]] == ["Media is down"]


def test_page_shows_state_and_suggestions(temp_db):

    store, now = UptimeStore(), datetime(2026, 1, 1, 12)
    for minute in range(3):
        store.save({"Media": (minute != 2, 30.0 + minute if minute != 2 else None, "HTTP 200" if minute != 2 else "refused")},
                   now - timedelta(minutes=3 - minute))
    checks = settings().uptime.checks
    html = uptime_page.render_uptime_page(checks, store.summary(["Media"], now), now, 2,
                                          [("Photos", "https://photos.example.org")])
    assert "Failed once" in html and "66.67%" in html and 'class="ms"' in html
    assert 'data-fill="https://photos.example.org"' in html and 'data-remove="Media"' in html
    assert 'href="/uptime" aria-current="page">Uptime<' in html


def test_add_and_remove_from_the_page(isolated_cwd):

    post = uptime_page.handle_post
    assert post("/api/uptime/add", {"name": "Media", "target": "https://media.example.org"}) == (200, {"ok": True})
    assert post("/api/uptime/add", {"name": "Media", "target": "192.0.2.1:22"})[0] == 400
    assert "host:port" in post("/api/uptime/add", {"name": "SSH", "target": "nope"})[1]["error"]
    assert post("/api/uptime/add", {"name": "NAS", "target": "192.0.2.5:445"})[0] == 200

    from lanxang.config.loader import load_config
    assert [c.name for c in load_config().uptime.checks] == ["Media", "NAS"]
    assert post("/api/uptime/remove", {"name": "Media"})[0] == 200
    assert [c.name for c in load_config().uptime.checks] == ["NAS"]
    assert post("/api/uptime/remove", {"name": "Media"})[0] == 404

    (isolated_cwd / "atlas.yaml").write_text("uptime:\n  checks: []\n")
    assert "atlas.yaml" in post("/api/uptime/add", {"name": "X", "target": "192.0.2.1:22"})[1]["error"]
