import gzip
from datetime import datetime, timedelta
from pathlib import Path

from atlas.posture.collectors.asn import AsnInfo, AsnTable, load_table, parse_ip2asn, refresh


FIXTURE = Path(__file__).parent / "fixtures" / "posture" / "ip2asn-v4.tsv"


def test_lookup_finds_range_and_skips_unrouted():
    table = AsnTable(parse_ip2asn(FIXTURE.read_text().splitlines()))
    assert table.lookup("203.0.113.75") == AsnInfo(asn=64500, cc="US", org="EXAMPLE-NET")
    assert table.lookup("198.51.100.44") == AsnInfo(asn=64501, cc="NL", org="EXAMPLE-VPN")
    assert table.lookup("203.0.113.200") is None
    assert table.lookup("192.168.10.1") is None
    assert table.lookup("not-an-ip") is None
    assert len(table) == 3


def test_load_table_reads_gzip_and_tolerates_missing(tmp_path):
    path = tmp_path / "ip2asn-v4.tsv.gz"
    assert len(load_table(path)) == 0
    path.write_bytes(gzip.compress(FIXTURE.read_bytes()))
    assert load_table(path).lookup("1.0.0.1").org == "CLOUDFLARENET"


class FakeResponse:
    def __init__(self, content):
        self.content = content
    def raise_for_status(self):
        pass


def test_refresh_downloads_when_missing_or_stale_only(tmp_path):
    path = tmp_path / "inventory" / "ip2asn-v4.tsv.gz"
    calls = []
    get = lambda url, timeout: calls.append(url) or FakeResponse(gzip.compress(FIXTURE.read_bytes()))
    now = datetime.now()

    assert refresh(path, "https://example.test/a.gz", now, get=get) is True
    assert refresh(path, "https://example.test/a.gz", now, get=get) is False
    assert refresh(path, "https://example.test/a.gz", now + timedelta(days=8), get=get) is True
    assert len(calls) == 2 and load_table(path).lookup("1.0.0.1") is not None
