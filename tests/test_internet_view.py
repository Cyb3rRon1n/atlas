from datetime import datetime, timedelta

import requests

from lanxang.alerts import AlertStore
from lanxang.config.models import AtlasConfig
from lanxang.posture.internet_view import lookup, run
from lanxang.posture.model import build_posture
from lanxang.posture.store import PostureStore

NOW = datetime(2026, 11, 19, 12, 0)
IP = "203.0.113.7"
URL = "https://internetdb.shodan.io/{ip}"
ON = AtlasConfig(posture={"internet_view": True})


class Reply:

    def __init__(self, status=200, data=None, bad_json=False):
        self.status_code, self.data, self.bad_json = status, data, bad_json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        if self.bad_json:
            raise ValueError("not JSON")
        return self.data


def shodan(ports, vulns=()):
    calls = []

    def get(url, timeout):
        calls.append(url)
        return Reply(200, {"ip": IP, "ports": list(ports), "vulns": list(vulns), "cpes": [], "hostnames": []})

    get.calls = calls
    return get


def failing(url, timeout):
    raise requests.Timeout("timed out")


def home(temp_db, ip=IP, now=NOW):
    store = PostureStore(temp_db)
    store.set_status("public_ip", True, {"ip": ip}, now)
    return store


def open_alerts(temp_db):
    return [a for a in AlertStore(temp_db).listing(NOW + timedelta(days=5))["open"] if a["source"] == "internet_view"]


def test_lookup_parses_ports_and_vulns():
    got = lookup(IP, URL, get=shodan([443, 22], ["CVE-2023-0001"]))
    assert got["ok"] and got["known"] and got["ports"] == [22, 443] and got["vulns"] == ["CVE-2023-0001"]


def test_lookup_404_means_nothing_known():
    got = lookup(IP, URL, get=lambda url, timeout: Reply(404, {"detail": "No information available"}))
    assert got == {"ok": True, "known": False, "ports": [], "vulns": [], "cpes": [], "hostnames": []}


def test_lookup_error_is_not_ok():
    assert lookup(IP, URL, get=failing)["ok"] is False
    bad = lookup(IP, URL, get=lambda url, timeout: Reply(200, bad_json=True))
    assert bad["ok"] is False and bad["error"]
    assert lookup(IP, URL, get=lambda url, timeout: Reply(500))["ok"] is False


def test_run_marks_expected_and_alerts_once_on_unexpected(temp_db):
    store, sent, get = home(temp_db), [], shodan([443, 22])
    texts, detail = run(ON, store, NOW, get=get, send=sent.append)
    assert get.calls == [f"https://internetdb.shodan.io/{IP}"]
    assert detail["ports"] == [{"port": 22, "expected": False}, {"port": 443, "expected": True}]
    assert len(sent) == 1 and "Port 22 is open to the internet" in sent[0] and "seen by Shodan" in sent[0]
    alerts = open_alerts(temp_db)
    assert [a["key"] for a in alerts] == ["internet_view:internet_port:22"]
    assert store.statuses()["internet_view"]["ok"] is False
    assert run(ON, store, NOW + timedelta(hours=2), get=get, send=sent.append) == ([], detail)   # not due
    assert len(get.calls) == 1 and len(sent) == 1


def test_run_alerts_on_cves(temp_db):
    store, sent = home(temp_db), []
    run(ON, store, NOW, get=shodan([443], ["CVE-2023-0001"]), send=sent.append)
    assert sent == ["**⚠️ CVE-2023-0001 reported on your public IP**"]
    assert [a["key"] for a in open_alerts(temp_db)] == ["internet_view:internet_cve:CVE-2023-0001"]


def test_run_clears_when_the_port_closes(temp_db):
    store, sent = home(temp_db), []
    run(ON, store, NOW, get=shodan([443, 22]), send=sent.append)
    texts, detail = run(ON, store, NOW + timedelta(days=1), get=shodan([443]), send=sent.append)
    assert texts == ["**✓ Port 22 no longer seen from the internet**"]
    assert open_alerts(temp_db) == [] and store.statuses()["internet_view"]["ok"] is True


def test_failed_lookup_keeps_alerts_and_last_ports(temp_db):
    store, sent = home(temp_db), []
    run(ON, store, NOW, get=shodan([22]), send=sent.append)
    texts, detail = run(ON, store, NOW + timedelta(days=1), get=failing, send=sent.append)
    assert texts == [] and len(sent) == 1
    assert detail["ok"] is False and "timed out" in detail["error"]
    assert detail["ports"] == [{"port": 22, "expected": False}] and detail["known"] is True
    assert [a["key"] for a in open_alerts(temp_db)] == ["internet_view:internet_port:22"]
    assert store.statuses()["internet_view"]["ok"] is False


def test_404_clears_alerts(temp_db):
    store = home(temp_db)
    run(ON, store, NOW, get=shodan([22]), send=lambda text: None)
    texts, detail = run(ON, store, NOW + timedelta(days=1), get=lambda url, timeout: Reply(404, {}),
                        send=lambda text: None)
    assert detail["ok"] is True and detail["known"] is False and detail["ports"] == []
    assert open_alerts(temp_db) == []


def test_no_public_ip_skips(temp_db):
    store, get = PostureStore(temp_db), shodan([22])
    assert run(ON, store, NOW, get=get) == ([], {})
    assert get.calls == [] and "internet_view" not in store.statuses()


def test_new_ip_looks_up_again_inside_24h(temp_db):
    store, get = home(temp_db), shodan([443])
    run(ON, store, NOW, get=get, send=lambda text: None)
    store.set_status("public_ip", True, {"ip": "203.0.113.8"}, NOW)
    texts, detail = run(ON, store, NOW + timedelta(hours=1), get=get, send=lambda text: None)
    assert len(get.calls) == 2 and get.calls[1].endswith("203.0.113.8") and detail["ip"] == "203.0.113.8"


def test_force_looks_up_inside_24h(temp_db):
    store, get = home(temp_db), shodan([443])
    run(ON, store, NOW, get=get, send=lambda text: None)
    run(ON, store, NOW + timedelta(hours=1), get=get, send=lambda text: None, force=True)
    assert len(get.calls) == 2


def test_off_by_default_does_nothing(temp_db):
    store, get = home(temp_db), shodan([22])
    assert AtlasConfig().posture.internet_view is False
    assert AtlasConfig().posture.expected_ports == [80, 443]
    assert run(AtlasConfig(), store, NOW, get=get, force=True) == ([], {})
    assert get.calls == [] and "internet_view" not in store.statuses()


def test_build_posture_includes_internet(temp_db):
    store = home(temp_db)
    assert build_posture(store, NOW)["internet"] is None
    run(ON, store, NOW, get=shodan([443, 22]), send=lambda text: None)
    internet = build_posture(store, NOW)["internet"]
    assert [p["port"] for p in internet["ports"]] == [22, 443] and internet["ip"] == IP
    assert internet["ports"][0]["label"].startswith("22 (SSH)")


def posture(internet):
    strip = [{"key": key, "state": "ok", "value": "v", "label": key, "detail": ""}
             for key in ("ingress", "vpn", "exposure", "blocked", "new")]
    return {"strip": strip, "exposure": [], "review": [], "internet": internet}


def test_posture_block_internet_line():
    from lanxang.web.home_page import _posture_card
    from lanxang.web.render import _posture_block

    one = {"ports": [{"port": 22, "expected": False}, {"port": 443, "expected": True}]}
    block = _posture_block(posture(one))
    assert block["internet"] == "1 unexpected port"
    card = _posture_card(block)
    assert 'class="hcard warn"' in card and "<dt>Internet</dt><dd>1 unexpected port</dd>" in card
    assert 'class="hcard ok"' in _posture_card(_posture_block(posture({"ports": [{"port": 443, "expected": True}]})))
    fine = {"ports": [{"port": 80, "expected": True}, {"port": 443, "expected": True}]}
    assert _posture_block(posture(fine))["internet"] == "2 ports open, all expected"
    assert _posture_block(posture(None))["internet"] == ""
    assert "Internet" not in _posture_card(_posture_block(posture(None)))


def test_posture_page_has_internet_box():
    from lanxang.web.posture_page import render_posture_page

    html = render_posture_page()
    assert "What the internet sees" in html and "Shodan's last scan, not a live test" in html


def test_setup_card_turns_it_on_with_expected_ports(isolated_cwd, monkeypatch):
    from lanxang.config import local
    from lanxang.web import settings_page

    monkeypatch.setattr(local, "save_settings", lambda settings: saved.update(settings))
    saved = {}
    status, payload = settings_page.handle_post("/api/settings/internet/save", {"expected_ports": "80, 443, 8443"})
    assert status == 200, payload
    assert saved["posture"] == {"internet_view": True, "expected_ports": ["80", "443", "8443"]}
    html = settings_page.render_settings_page()
    assert "Sends your home IP to Shodan once a day." in html


def test_turning_it_off_resolves_alerts_and_clears_the_view(temp_db):
    store = home(temp_db)
    run(ON, store, NOW, get=shodan([22]), send=lambda text: None)
    assert open_alerts(temp_db)
    get = shodan([22])
    assert run(AtlasConfig(), store, NOW + timedelta(hours=1), get=get) == ([], {})
    assert get.calls == [] and open_alerts(temp_db) == []
    assert "internet_view" not in store.statuses() and build_posture(store, NOW)["internet"] is None


def test_setup_turn_off_clears_it(temp_db, isolated_cwd, monkeypatch):
    from lanxang.config import local
    from lanxang.web import settings_page

    store = home(temp_db)
    run(ON, store, NOW, get=shodan([22]), send=lambda text: None)
    monkeypatch.setattr(local, "save_settings", lambda settings: None)
    assert settings_page.handle_post("/api/settings/internet/off", {})[0] == 200
    assert open_alerts(temp_db) == [] and "internet_view" not in store.statuses()


def test_first_failure_knows_nothing(temp_db):
    texts, detail = run(ON, home(temp_db), NOW, get=failing)
    assert detail["ok"] is False and detail["known"] is None and detail["ports"] == []


def test_cve_cleared_text(temp_db):
    store, sent = home(temp_db), []
    run(ON, store, NOW, get=shodan([443], ["CVE-2023-0001"]), send=sent.append)
    run(ON, store, NOW + timedelta(days=1), get=failing, send=sent.append)
    assert len(sent) == 1                                   # a failure says nothing
    run(ON, store, NOW + timedelta(days=2), get=shodan([443]), send=sent.append)
    assert sent[-1] == "**✓ CVE-2023-0001 no longer reported on your public IP**" and open_alerts(temp_db) == []


def test_posture_block_flags_unexpected_and_failed_checks():
    from lanxang.web.home_page import _posture_card, attention_items
    from lanxang.web.render import _posture_block

    block = _posture_block(posture({"ok": True, "ports": [{"port": 22, "expected": False}]}))
    assert block["internet_unexpected"] == 1 and block["state"] == "warn" and block["message"] != "All good"
    assert "1 unexpected port" in block["message"]
    alert = {"source": "internet_view", "title": "Port 22 is open to the internet", "acked_at": None}
    items = attention_items(block, {"rows": []}, {"rows": []}, (), [alert])
    assert [i[0] for i in items] == ["posture"]             # one problem, one line
    failed = _posture_block(posture({"ok": False, "ports": [{"port": 443, "expected": True}]}))
    assert failed["internet"] == "1 port open, all expected (last check failed)" and failed["state"] == "ok"
    assert _posture_block(posture({"ok": False, "ports": []}))["internet"] == "Last check failed"
    assert 'class="hcard ok"' in _posture_card(failed)


def test_posture_page_box_has_privacy_note():
    from lanxang.web.posture_page import render_posture_page

    assert "Sends your home IP to Shodan once a day." in render_posture_page()
