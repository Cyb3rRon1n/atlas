from datetime import datetime, timedelta

from atlas.posture.model import build_posture, node_details
from atlas.posture.store import PostureStore


NOW = datetime(2026, 10, 8, 13, 42, 0)


def seed(store):
    d = lambda **o: {**{"source": "sonarr", "band": "direct", "dest_ip": "203.0.113.75", "dest_port": 443,
                       "proto": "tcp", "asn": 64500, "org": "EXAMPLE-NET", "cc": "US", "bytes_out": 5000,
                       "bytes_in": 120000, "new_conn": True}, **o}
    store.record_flows([d(), d(source="jellyfin", dest_ip="198.51.100.10", asn=64501, org="EXAMPLE-CDN",
                            bytes_in=10, bytes_out=900000),
                        d(source="gluetun", band="vpn", dest_ip="198.51.100.44", asn=64502, org="EXAMPLE-VPN",
                          bytes_out=800000, bytes_in=9000000)], NOW - timedelta(minutes=10))
    store.mark_known("jellyfin", "AS64501")
    store.set_status("tunnel", True, {"connections": 4}, NOW)
    store.set_status("gluetun", True, {"exit_ip": "198.51.100.9", "country": "NL"}, NOW)
    store.set_status("public_ip", True, {"ip": "192.0.2.10"}, NOW)
    store.set_status("crowdsec", True, {"active": 37}, NOW)
    store.set_status("conntrack", True, {"flows": 330}, NOW)
    store.save_routes([
        {"name": "atlas", "hosts": ["atlas.example.test"], "entrypoints": ["tunnel"], "protection": "authelia", "provider": "docker"},
        {"name": "jellyfin", "hosts": ["jellyfin.example.test"], "entrypoints": ["tunnel"], "protection": "public", "provider": "docker"},
    ], NOW)


def strip(result):
    return {item["key"]: item for item in result["strip"]}


def test_strip_states(temp_db):
    store = PostureStore(temp_db)
    seed(store)
    s = strip(build_posture(store, NOW))
    assert (s["ingress"]["state"], s["ingress"]["value"]) == ("ok", "Tunnel up")
    assert (s["vpn"]["state"], s["vpn"]["value"]) == ("ok", "Verified")
    assert (s["exposure"]["value"], s["exposure"]["detail"]) == ("2 routes", "1 without Authelia")
    assert s["blocked"]["value"] == "37"
    assert (s["new"]["state"], s["new"]["value"]) == ("review", "2")   # sonarr + gluetun; jellyfin marked known


def test_vpn_leak_and_unknown(temp_db):
    store = PostureStore(temp_db)
    seed(store)
    store.set_status("gluetun", True, {"exit_ip": "192.0.2.10", "country": "US"}, NOW)
    assert strip(build_posture(store, NOW))["vpn"]["state"] == "warn"
    store.set_status("gluetun", False, {"error": "timeout"}, NOW)
    assert strip(build_posture(store, NOW))["vpn"]["state"] == "unknown"


def test_nodes_edges_and_bands(temp_db):
    store = PostureStore(temp_db)
    seed(store)
    result = build_posture(store, NOW)
    ids = {n["id"] for n in result["nodes"]}
    assert {"in:internet", "in:tunnel", "in:traefik", "src:sonarr", "src:jellyfin", "out:router",
            "dst:AS64500", "dst:AS64501", "vpn:gluetun", "vpn:exit"} <= ids
    assert "src:gluetun" not in ids
    new_edge = next(e for e in result["edges"] if e["target"] == "dst:AS64500")
    assert new_edge["state"] == "review" and new_edge["bytes"] == 125000
    assert next(e for e in result["edges"] if e["target"] == "dst:AS64501")["state"] == "ok"
    assert [b["id"] for b in result["bands"]] == ["inbound", "direct", "vpn"]
    assert all(isinstance(n["x"], int) and isinstance(n["y"], int) for n in result["nodes"])


def test_stale_sources_grey_out_bands(temp_db):
    store = PostureStore(temp_db)
    seed(store)
    store.set_status("conntrack", False, {"error": "Operation not permitted"}, NOW)
    bands = {b["id"]: b for b in build_posture(store, NOW)["bands"]}
    assert bands["direct"]["stale"] and not bands["inbound"]["stale"]


def test_window_live_uses_current_hour_only(temp_db):
    store = PostureStore(temp_db)
    seed(store)
    old = NOW - timedelta(hours=3)
    store.record_flows([{"source": "radarr", "band": "direct", "dest_ip": "203.0.113.9", "dest_port": 443,
                         "proto": "tcp", "asn": 64500, "org": "EXAMPLE-NET", "cc": "US", "bytes_out": 1,
                         "bytes_in": 1, "new_conn": True}], old)
    assert "src:radarr" in {n["id"] for n in build_posture(store, NOW, "24h")["nodes"]}
    assert "src:radarr" not in {n["id"] for n in build_posture(store, NOW, "live")["nodes"]}


def test_node_details_for_destination(temp_db):
    store = PostureStore(temp_db)
    seed(store)
    details = node_details(store, "dst:AS64500", NOW, resolve=lambda ip: "edge.example.test")
    assert details["org"] == "EXAMPLE-NET" and details["known"] is False
    assert details["sources"] == [{"source": "sonarr", "bytes": 125000}]
    assert details["ips"][0] == {"ip": "203.0.113.75", "rdns": "edge.example.test"}
    assert node_details(store, "dst:AS99999", NOW) is None
    assert node_details(store, "bogus", NOW) is None
