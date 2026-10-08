from datetime import datetime, timedelta
from pathlib import Path

from atlas.config.models import PostureConfig
from atlas.posture.collect import Collector
from atlas.posture.collectors.asn import AsnTable, parse_ip2asn
from atlas.posture.collectors.conntrack import parse_conntrack
from atlas.posture.store import PostureStore
from posture_fakes import Container, Response, make_client


FIX = Path(__file__).parent / "fixtures" / "posture"
NOW = datetime(2026, 10, 8, 13, 0, 0)


def client():
    return make_client([Container("cloudflared", "c1", "stack_default", {"stack_default": "172.18.0.38"}),
                        Container("traefik", "t1", "stack_default", {"stack_default": "172.18.0.9"}),
                        Container("crowdsec", "cs", "stack_default", {"stack_default": "172.18.0.7"})])


def fake_get(url, headers=None, timeout=None):
    if url.endswith("/v1/publicip/ip"):
        return Response(data={"public_ip": "198.51.100.9", "country": "NL"})
    if url.endswith("/v1/decisions"):
        return Response(data=[{"value": "203.0.113.5"}])
    return Response(text="192.0.2.10")


def make(temp_db, read=None):
    settings = PostureConfig(enabled=True, host_ip="192.168.10.157", gluetun_api_key="g", crowdsec_api_key="c")
    flows = parse_conntrack((FIX / "conntrack.txt").read_text())
    table = AsnTable(parse_ip2asn((FIX / "ip2asn-v4.tsv").read_text().splitlines()))
    return Collector(settings, PostureStore(temp_db), client(), read_flows=read or (lambda: flows),
                     get=fake_get, asn_table=table)


def test_run_once_records_statuses_and_flows(temp_db, monkeypatch):
    monkeypatch.setattr("atlas.posture.aggregate.is_public", lambda ip: ip.startswith(("203.", "198.")))
    collector = make(temp_db)
    result = collector.run_once(NOW)
    statuses = collector.store.statuses()
    assert {"conntrack", "tunnel", "inbound", "routes", "gluetun", "public_ip", "crowdsec", "asn"} <= set(statuses)
    assert statuses["tunnel"]["detail"] == {"connections": 1}
    assert statuses["gluetun"]["detail"]["exit_ip"] == "198.51.100.9"
    assert statuses["public_ip"]["detail"] == {"ip": "192.0.2.10"}
    assert statuses["crowdsec"]["detail"] == {"active": 1}
    assert result["deltas"] == 4 and {n["source"] for n in result["new"]} == {"sonarr", "host", "cloudflared", "gluetun"}


def test_conntrack_failure_is_recorded_not_raised(temp_db):
    def broken():
        raise RuntimeError("Operation not permitted")
    collector = make(temp_db, read=broken)
    collector.run_once(NOW)
    status = collector.store.statuses()["conntrack"]
    assert status["ok"] is False and "not permitted" in status["detail"]["error"]


def test_public_ip_is_fetched_at_most_every_10_minutes(temp_db):
    calls = []
    collector = make(temp_db)
    collector.get = lambda url, headers=None, timeout=None: calls.append(url) or fake_get(url, headers, timeout)
    collector.run_once(NOW)
    collector.run_once(NOW + timedelta(minutes=5))
    collector.run_once(NOW + timedelta(minutes=11))
    assert sum(url == "https://api.ipify.org" for url in calls) == 2


def test_missing_keys_mark_sources_unconfigured(temp_db):
    collector = make(temp_db)
    collector.settings = PostureConfig(enabled=True, host_ip="192.168.10.157")
    collector.run_once(NOW)
    assert collector.store.statuses()["gluetun"]["detail"] == {"error": "not configured (posture.gluetun_api_key)"}


def test_unexpected_exception_from_a_source_is_recorded_not_raised(temp_db):
    def broken_get(url, headers=None, timeout=None):
        if url.endswith("/v1/publicip/ip"):
            raise KeyError("boom")
        return fake_get(url, headers, timeout)
    collector = make(temp_db)
    collector.get = broken_get
    result = collector.run_once(NOW)
    status = collector.store.statuses()["gluetun"]
    assert status["ok"] is False and "boom" in status["detail"]["error"]
    assert isinstance(result, dict)


def test_unexpected_exception_from_public_ip_is_recorded_not_raised(temp_db):
    def broken_get(url, headers=None, timeout=None):
        if url == "https://api.ipify.org":
            raise KeyError("boom")
        return fake_get(url, headers, timeout)
    collector = make(temp_db)
    collector.get = broken_get
    result = collector.run_once(NOW)
    status = collector.store.statuses()["public_ip"]
    assert status["ok"] is False and "boom" in status["detail"]["error"]
    assert isinstance(result, dict)


class BrokenListClient:
    """Wraps a real fake client but makes containers.list() raise, simulating
    a Docker API/socket error - containers.get() (used by _service/container_ip)
    still works, since the collector's per-source isolation should mean those
    aren't affected by the top-of-run_once Docker lookups failing."""

    def __init__(self, inner):
        self._inner = inner
        outer = self
        class containers:
            @staticmethod
            def list():
                raise RuntimeError("Cannot connect to the Docker daemon")
            @staticmethod
            def get(name):
                return outer._inner.containers.get(name)
        self.containers = containers


def test_docker_lookup_failure_at_top_of_run_once_is_recorded_not_raised(temp_db):
    collector = make(temp_db)
    collector.client = BrokenListClient(collector.client)
    result = collector.run_once(NOW)
    statuses = collector.store.statuses()
    assert isinstance(result, dict)
    assert "conntrack" in statuses and statuses["conntrack"]["ok"] is True
    assert "tunnel" in statuses and "inbound" in statuses
