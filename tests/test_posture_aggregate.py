from pathlib import Path

from atlas.posture.aggregate import Accountant, inbound_counts, is_public, tunnel_connections
from atlas.posture.collectors.asn import AsnTable, parse_ip2asn
from atlas.posture.collectors.conntrack import parse_conntrack


FIX = Path(__file__).parent / "fixtures" / "posture"
FLOWS = parse_conntrack((FIX / "conntrack.txt").read_text())
ASN = AsnTable(parse_ip2asn((FIX / "ip2asn-v4.tsv").read_text().splitlines()))
SOURCES = {"172.18.0.13": "sonarr", "172.18.0.3": "gluetun", "172.18.0.38": "cloudflared", "172.18.0.9": "traefik"}
HOST = "192.168.10.157"


def test_is_public():
    assert is_public("203.0.113.1") is False   # documentation range is not global
    assert is_public("8.8.8.8") is True
    assert is_public("100.64.0.10") is False and is_public("192.168.10.1") is False


def test_first_pass_counts_outbound_flows_with_owner_and_band(monkeypatch):
    monkeypatch.setattr("atlas.posture.aggregate.is_public", lambda ip: not ip.startswith(("192.168.", "172.", "100.64.", "224.")))
    deltas = Accountant().deltas(FLOWS, SOURCES, HOST, {"gluetun"}, ASN)
    by_source = {d["source"]: d for d in deltas}
    assert set(by_source) == {"sonarr", "host", "cloudflared", "gluetun"}
    sonarr = by_source["sonarr"]
    assert (sonarr["band"], sonarr["dest_ip"], sonarr["dest_port"], sonarr["asn"], sonarr["org"]) == (
        "direct", "203.0.113.75", 443, 64500, "EXAMPLE-NET")
    assert (sonarr["bytes_out"], sonarr["bytes_in"], sonarr["new_conn"]) == (5000, 120000, True)
    assert by_source["gluetun"]["band"] == "vpn"


def test_second_pass_counts_only_growth_and_forgets_closed(monkeypatch):
    monkeypatch.setattr("atlas.posture.aggregate.is_public", lambda ip: not ip.startswith(("192.168.", "172.", "100.64.", "224.")))
    acct = Accountant()
    acct.deltas(FLOWS, SOURCES, HOST, set(), ASN)
    grown = [f.__class__(**{**f.__dict__, "bytes_out": f.bytes_out + 10}) if f.id == 1002 else f for f in FLOWS]
    deltas = acct.deltas(grown, SOURCES, HOST, set(), ASN)
    assert [(d["source"], d["bytes_out"], d["bytes_in"], d["new_conn"]) for d in deltas] == [("sonarr", 10, 0, False)]
    assert acct.deltas([], SOURCES, HOST, set(), ASN) == []
    assert len(acct.deltas(grown, SOURCES, HOST, set(), ASN)) == 4   # reopened ids count as new again


def test_counter_reset_counts_full_value(monkeypatch):
    monkeypatch.setattr("atlas.posture.aggregate.is_public", lambda ip: ip.startswith("203."))
    acct = Accountant()
    acct.deltas(FLOWS, SOURCES, HOST, set(), ASN)
    shrunk = [f.__class__(**{**f.__dict__, "bytes_out": 1, "bytes_in": 2}) for f in FLOWS if f.id == 1002]
    (d,) = acct.deltas(shrunk, SOURCES, HOST, set(), ASN)
    assert (d["bytes_out"], d["bytes_in"]) == (1, 2)


def test_inbound_and_tunnel_counts(monkeypatch):
    assert inbound_counts(FLOWS, HOST, "172.18.0.9") == {"public": 0, "private": 1}
    assert tunnel_connections(FLOWS, "172.18.0.38") == 1
    assert tunnel_connections(FLOWS, None) == 0


def test_missing_asn_table_means_unknown_owners(monkeypatch):
    monkeypatch.setattr("atlas.posture.aggregate.is_public", lambda ip: not ip.startswith(("192.168.", "172.", "100.64.", "224.")))
    deltas = Accountant().deltas(FLOWS, SOURCES, HOST, {"gluetun"}, None)
    assert deltas and all((d["asn"], d["org"], d["cc"]) == (0, "", "") for d in deltas)
