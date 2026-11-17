import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer

from atlas.config.models import AtlasConfig, Heartbeat
from atlas.monitoring import heartbeat
from atlas.web.uptime_page import handle_post, render_uptime_page

KEY = bytes(32)


def test_token_is_per_name_and_find_checks_it():
    beats = [Heartbeat(name="Nightly backup"), Heartbeat(name="Photos sync")]
    one = heartbeat.token("Nightly backup", KEY)
    assert len(one) == 32 and one != heartbeat.token("Photos sync", KEY) and one != heartbeat.token("Nightly backup",
                                                                                                    b"x" * 32)
    assert heartbeat.find(one, beats, KEY).name == "Nightly backup"
    assert heartbeat.find("0" * 32, beats, KEY) is None and heartbeat.find("", beats, KEY) is None


def test_late_failed_and_back_alert_once_each(temp_db):
    from atlas.posture.store import PostureStore

    store, sent = PostureStore(temp_db), []
    settings = AtlasConfig(uptime={"heartbeats": [{"name": "Backup", "every_minutes": 60, "grace_minutes": 15}]})
    t = datetime(2026, 11, 17, 0, 0)

    def check(minutes):
        return heartbeat.run(settings, store, t + timedelta(minutes=minutes), send=sent.append)["Backup"]["state"]

    assert check(0) == "waiting" and check(500) == "waiting" and not sent      # nothing before the first ping
    heartbeat.ping(store, "Backup", t + timedelta(minutes=500))
    assert check(501) == "ok" and check(570) == "ok"
    assert check(576) == "late" and check(600) == "late"                       # 60 + 15 minutes after the ping
    heartbeat.ping(store, "Backup", t + timedelta(minutes=610))
    assert check(611) == "ok"
    heartbeat.ping(store, "Backup", t + timedelta(minutes=620), failed=True)
    assert check(621) == "failed" and check(622) == "failed"
    assert [text.split("**")[1] for text in sent] == ["⏰ Backup hasn't checked in", "✅ Backup checked in again",
                                                     "❌ Backup reported a failure"]
    assert not store.statuses()["heartbeats"]["ok"]


def test_ping_address_needs_no_sign_in_and_rejects_bad_tokens(temp_db, isolated_cwd):
    from atlas.posture.store import PostureStore
    from atlas.web.auth import Auth
    from atlas.web.server import AtlasWebHandler

    (isolated_cwd / "atlas.yaml").write_text("uptime:\n  heartbeats:\n    - name: Backup\n")
    handler = type("Handler", (AtlasWebHandler,), {"auth": Auth(isolated_cwd / "auth.json")})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_port}"

    def get(path):
        try:
            with urllib.request.urlopen(base + path) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    try:
        token = heartbeat.token("Backup")
        assert (isolated_cwd / "inventory/heartbeat.key").stat().st_mode & 0o777 == 0o600
        assert get(f"/ping/{token}") == 200
        assert PostureStore().statuses()["ping:Backup"]["detail"]["failed"] is False
        assert get(f"/ping/{token}/fail") == 200
        assert PostureStore().statuses()["ping:Backup"]["detail"]["failed"] is True
        assert get("/ping/" + "0" * 32) == 404 and get(f"/ping/{token}/other") == 404
        with urllib.request.urlopen(base + "/uptime") as response:                # the rest still needs sign-in
            assert "/login" in response.url or "/setup" in response.url
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_uptime_page_adds_lists_and_removes_heartbeats(isolated_cwd):
    assert handle_post("/api/uptime/heartbeat/add", {"name": "Backup", "every": 1440}) == (200, {"ok": True})
    assert handle_post("/api/uptime/heartbeat/add", {"name": "Backup", "every": 1440})[0] == 400
    assert handle_post("/api/uptime/heartbeat/add", {"name": "x", "every": 7})[0] == 400
    from atlas.config.loader import load_config
    beats = load_config().uptime.heartbeats
    assert [(b.name, b.every_minutes, b.grace_minutes) for b in beats] == [("Backup", 1440, 60)]
    now = datetime(2026, 11, 17, 12)
    html = render_uptime_page([], {}, now, beats=[(beats[0], {"state": "late", "at": "2026-11-16T02:00:00"}, "ab12")])
    assert "Late" in html and 'data-ping="/ping/ab12"' in html and "every day" in html and "34 h ago" in html
    assert handle_post("/api/uptime/heartbeat/remove", {"name": "Backup"}) == (200, {"ok": True})
    assert load_config().uptime.heartbeats == []
