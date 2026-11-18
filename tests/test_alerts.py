from datetime import datetime, timedelta

from atlas.alerts import AlertStore, issue, report, report_event
from atlas.web.alerts_page import render_alerts_page
from atlas.web.home_page import attention_items
from atlas.clock import utcnow

NOW = datetime(2026, 11, 16, 12, 0)


def test_sync_opens_refreshes_and_resolves(temp_db):
    store = AlertStore(temp_db)
    store.sync("wiring", [issue("loop", "a<->b", "Possible network loop: a<->b", href="/cabling"),
                          issue("source", "sw2", "Can't read sw2", "timeout", "watch")], NOW)
    store.sync("wiring", [issue("loop", "a<->b", "Possible network loop: a<->b", "still", href="/cabling")],
               NOW + timedelta(minutes=15))
    store.sync("lan", [], NOW)                       # another source never touches wiring's rows

    listing = store.listing(NOW + timedelta(minutes=20))
    assert [a["title"] for a in listing["open"]] == ["Possible network loop: a<->b"]
    assert listing["open"][0]["detail"] == "still" and listing["open"][0]["opened_at"] == NOW
    assert listing["watch"] == [] and [a["title"] for a in listing["resolved"]] == ["Can't read sw2"]

    store.sync("wiring", [issue("loop", "a<->b", "again")], NOW + timedelta(hours=1))
    assert len(store.listing(NOW + timedelta(hours=1))["open"]) == 1     # still one open row per problem


def test_events_resolve_by_themselves_and_old_rows_go(temp_db):
    store = AlertStore(temp_db)
    store.event("ports", "New open port on nas", "• 3389 RDP", "/devices", None, NOW)
    assert len(store.listing(NOW + timedelta(days=1))["open"]) == 1
    later = store.listing(NOW + timedelta(days=8))
    assert later["open"] == [] and len(later["resolved"]) == 1
    assert store.listing(NOW + timedelta(days=60))["resolved"] == []


def test_report_skips_stand_in_stores_and_never_raises(temp_db):
    class Fake:
        pass

    report("lan", [issue("x", "y", "z")], NOW, Fake())                  # no engine: nothing written
    report_event("ports", "t", NOW, Fake())
    assert AlertStore(temp_db).listing(NOW)["open"] == []


def test_page_and_home_show_the_same_problems(temp_db):
    store = AlertStore(temp_db)
    store.sync("certs", [issue("cert", "example.org", "Certificate expires in 3 days: example.org", href="/posture")], NOW)
    store.sync("devices", [issue("new", "devices", "2 new devices waiting for a name", level="watch", href="/devices")], NOW)
    store.sync("vpn", [issue("vpn", "qbt", "gone", href="/posture")], NOW)
    store.sync("vpn", [], NOW + timedelta(hours=3))
    listing = store.listing(NOW + timedelta(hours=4))
    page = render_alerts_page(listing, NOW + timedelta(hours=4))
    assert "Needs action <span class=\"muted\">(1)" in page and 'href="/posture">Investigate' in page
    assert "2 new devices waiting" in page and "resolved 60 min ago, after 3 h" in page

    items = attention_items(None, {"rows": []}, {"rows": []}, (), listing["open"])
    assert items == [("alerts", "Alerts", "Certificate expires in 3 days: example.org", "/alerts", "Review")]


def test_cabling_scan_reports_into_alerts(temp_db):
    from atlas.config.models import AtlasConfig
    from atlas.wiring import WiringError
    from atlas.wiring.scan import run_scan
    from atlas.wiring.store import WiringStore

    settings = AtlasConfig(wiring={"enabled": True, "switches": [{"name": "sw1", "host": "192.0.2.2"}]})

    def broken(switch, env, timeout):
        raise WiringError("sw1: no answer from 192.0.2.2")

    run_scan(settings, WiringStore(temp_db), [], env={}, collect=broken, send=lambda text: None)
    watch = AlertStore(temp_db).listing(utcnow())["watch"]
    assert [(a["title"], a["detail"], a["href"]) for a in watch] == [
        ("Can't read sw1", "sw1: no answer from 192.0.2.2", "/cabling")]


def test_ack_mute_pause_and_allowed(temp_db):
    from atlas.alerts import Text

    store = AlertStore(temp_db)
    store.sync("lan", [issue("rogue_dhcp", "192.0.2.9", "Another DHCP server", href="/posture")], NOW)
    store.sync("devices", [issue("offline", 4, "nas is offline", device_id=4)], NOW)
    store.event("ports", "New open port on nas", "", "/devices/4", 4, NOW)
    lan, nas = [a for a in store.listing(NOW)["open"] if a["source"] in ("lan", "devices")]
    port = next(a for a in store.listing(NOW)["open"] if a["source"] == "ports")

    store.ack(lan["id"], NOW)
    store.ack(port["id"], NOW)                                          # a one-off finding is done once seen
    listing = store.listing(NOW)
    assert [a["source"] for a in listing["open"]] == ["devices", "lan"]   # acknowledged sinks
    assert listing["open"][1]["acked_at"] == NOW

    assert store.allowed("lan:rogue_dhcp:192.0.2.9", None, NOW)
    store.mute(lan["id"], 1, NOW)
    store.mute(nas["id"], 0, NOW)                                       # has a device: mutes the device, always
    assert not store.allowed("lan:rogue_dhcp:192.0.2.9", None, NOW)
    assert store.allowed("lan:rogue_dhcp:192.0.2.9", None, NOW + timedelta(days=2))   # 1-day mute expired
    assert not store.allowed("", 4, NOW + timedelta(days=400)) and store.allowed("", 5, NOW)

    store.pause(4, NOW)
    assert not store.allowed("anything", None, NOW) and store.listing(NOW)["paused_until"] == NOW + timedelta(hours=4)
    store.unquiet()
    assert store.allowed("anything", None, NOW)
    rule = store.listing(NOW)["muted"][0]
    store.unquiet(rule["id"])
    assert len(store.listing(NOW)["muted"]) == 0 or store.listing(NOW)["muted"][0]["id"] != rule["id"]


def test_a_muted_problem_is_listed_but_not_sent(temp_db):
    from atlas.config.models import AtlasConfig
    from atlas.devices import lanwatch
    from atlas.posture.store import PostureStore

    posture = PostureStore(temp_db)
    settings = AtlasConfig()
    arp = "IP address       HW type     Flags       HW address            Mask     Device\n" \
          "192.0.2.1        0x1         0x2         aa:aa:aa:aa:aa:01     *        eth0\n"
    route = "Iface\tDestination\tGateway\tFlags\n eth0\t00000000\t010200C0\t0003\n"
    read = lambda path: arp if path.endswith("arp") else route
    offer = lambda timeout: [{"server": "192.0.2.9", "offered": "192.0.2.50", "router": "192.0.2.9"}]
    sent = []

    lanwatch.run(settings, posture, NOW, probe=offer, read=read, send=sent.append)
    assert len(sent) == 1 and sent[0].key == "lan:rogue_dhcp:192.0.2.9"
    store = AlertStore(temp_db)
    store.mute(store.listing(NOW)["open"][0]["id"], 7, NOW)

    later = utcnow()
    posture.set_status("lan", True, {}, later)                         # forget it, so the check alerts again
    lanwatch.run(settings, posture, later, probe=offer, read=read, send=sent.append)
    assert len(sent) == 1 and len(store.listing(later)["open"]) == 1     # still listed, nothing sent


def test_alerts_api_and_page_controls(temp_db, monkeypatch):
    from atlas.web import alerts_page

    store = AlertStore(temp_db)
    monkeypatch.setattr("atlas.alerts.engine", temp_db)
    store.sync("certs", [issue("cert", "example.org", "Certificate expires in 3 days: example.org")], NOW)
    alert_id = store.listing(NOW)["open"][0]["id"]

    assert alerts_page.handle_post(f"/api/alerts/{alert_id}/mute", {"days": "7"})[0] == 400
    assert alerts_page.handle_post(f"/api/alerts/{alert_id}/mute", {"days": 7})[0] == 200
    assert alerts_page.handle_post("/api/alerts/999/ack", {})[0] == 404
    assert alerts_page.handle_post("/api/alerts/pause", {"hours": 999})[0] == 400
    assert alerts_page.handle_post("/api/alerts/pause", {"hours": 4})[0] == 200
    assert alerts_page.handle_post("/api/elsewhere", {}) is None

    now = utcnow()
    page = render_alerts_page(store.listing(now), now)
    assert "Alerts are paused until" in page and "Resume now" in page
    assert "Muted (1)" in page and "Mute this alert" in page and "Acknowledge" in page
    alerts_page.handle_post("/api/alerts/resume", {})
    assert "Pause alerts" in render_alerts_page(store.listing(now), now)


def test_old_alerts_table_gets_the_new_column(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    from atlas.database import initialize_database

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alerts (id INTEGER PRIMARY KEY, key VARCHAR, source VARCHAR, "
                                "level VARCHAR, title VARCHAR, detail VARCHAR, href VARCHAR, device_id INTEGER, "
                                "event BOOLEAN, opened_at DATETIME, seen_at DATETIME, resolved_at DATETIME)"))
    initialize_database(engine)
    assert "acked_at" in {c["name"] for c in inspect(engine).get_columns("alerts")}
