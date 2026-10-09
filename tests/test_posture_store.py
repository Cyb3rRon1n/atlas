from datetime import datetime, timedelta

from atlas.posture.store import PostureStore, asn_key


NOW = datetime(2026, 10, 8, 13, 42, 10)


def delta(**overrides):
    base = {"source": "sonarr", "band": "direct", "dest_ip": "203.0.113.7", "dest_port": 443, "proto": "tcp",
            "asn": 64500, "org": "EXAMPLE-NET", "cc": "US", "bytes_out": 100, "bytes_in": 900, "new_conn": True}
    return {**base, **overrides}


def test_asn_key_falls_back_to_ip_when_asn_unknown():
    assert asn_key(64500, "203.0.113.7") == "AS64500"
    assert asn_key(0, "203.0.113.7") == "ip:203.0.113.7"


def test_record_flows_accumulates_per_hour_and_reports_first_seen(temp_db):
    store = PostureStore(temp_db)

    new = store.record_flows([delta()], NOW)
    assert new == [{"source": "sonarr", "asn_key": "AS64500", "org": "EXAMPLE-NET", "cc": "US"}]

    again = store.record_flows([delta(bytes_out=50, bytes_in=50, new_conn=False)], NOW + timedelta(minutes=5))
    assert again == []

    rows = store.flows(NOW - timedelta(hours=1))
    assert len(rows) == 1
    assert (rows[0]["bytes_out"], rows[0]["bytes_in"], rows[0]["conns"]) == (150, 950, 1)
    assert rows[0]["hour"] == datetime(2026, 10, 8, 13)


def test_new_hour_gets_its_own_bucket(temp_db):
    store = PostureStore(temp_db)
    store.record_flows([delta()], NOW)
    store.record_flows([delta(new_conn=False)], NOW + timedelta(hours=1))
    assert len(store.flows(NOW - timedelta(hours=2))) == 2


def test_mark_known_hides_from_new_and_flags_seen(temp_db):
    store = PostureStore(temp_db)
    assert store.mark_known("sonarr", "AS64500") == {"ok": True}
    assert store.record_flows([delta()], NOW) == []
    assert store.seen()[0]["known"] is True


def test_mark_known_validates(temp_db):
    store = PostureStore(temp_db)
    assert store.mark_known("", "AS1")["ok"] is False
    assert store.mark_known("sonarr", "nonsense")["ok"] is False


def test_status_roundtrip(temp_db):
    store = PostureStore(temp_db)
    store.set_status("gluetun", True, {"exit_ip": "198.51.100.9"}, NOW)
    store.set_status("gluetun", False, {"error": "timeout"}, NOW + timedelta(seconds=30))
    status = store.statuses()["gluetun"]
    assert status["ok"] is False and status["detail"] == {"error": "timeout"}
    assert status["updated_at"] == NOW + timedelta(seconds=30)


def test_save_routes_reports_change_only_when_set_differs(temp_db):
    store = PostureStore(temp_db)
    routes = [{"name": "atlas", "hosts": ["atlas.example.test"], "entrypoints": ["websecure"],
               "protection": "authelia", "provider": "docker"}]
    assert store.save_routes(routes, NOW) is True
    assert store.save_routes(routes, NOW + timedelta(minutes=1)) is False
    assert store.latest_routes() == routes


def test_prune_drops_old_flow_buckets(temp_db):
    store = PostureStore(temp_db)
    store.record_flows([delta()], NOW - timedelta(days=40))
    store.record_flows([delta(new_conn=False)], NOW)
    assert store.prune(NOW - timedelta(days=30)) == 1
    assert len(store.flows(NOW - timedelta(days=100))) == 1


def test_record_flows_without_seen_tracking_keeps_flows_only(temp_db):
    store = PostureStore(temp_db)
    assert store.record_flows([delta(asn=0, org="", cc="")], NOW, track_seen=False) == []
    assert store.seen() == [] and len(store.flows(NOW - timedelta(hours=1))) == 1


def test_mark_known_accepts_ipv6_and_rejects_junk_ip_keys(temp_db):
    store = PostureStore(temp_db)
    assert store.mark_known("sonarr", "ip:2001:db8::1") == {"ok": True}
    assert store.mark_known("sonarr", "ip:203.0.113.7") == {"ok": True}
    assert store.mark_known("sonarr", "ip:999.1.1.1")["ok"] is False
    assert store.mark_known("sonarr", "ip:2001:db8::zz")["ok"] is False
