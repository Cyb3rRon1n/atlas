from datetime import datetime, timedelta

from atlas.alerts import AlertStore, issue, report, report_event
from atlas.web.alerts_page import render_alerts_page
from atlas.web.home_page import attention_items

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
    watch = AlertStore(temp_db).listing(datetime.utcnow())["watch"]
    assert [(a["title"], a["detail"], a["href"]) for a in watch] == [
        ("Can't read sw1", "sw1: no answer from 192.0.2.2", "/cabling")]
