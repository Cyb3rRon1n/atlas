"""
IPv4 -> (ASN, country, organisation) from the free iptoasn.com table, looked up
locally (bisect over sorted ranges) so no destination IP ever leaves the host.
Refreshed at most weekly; a missing file just means unknown owners.
"""

import bisect
import gzip
import ipaddress
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import requests


@dataclass(frozen=True)
class AsnInfo:
    asn: int
    cc: str
    org: str


def parse_ip2asn(lines):

    rows = []

    for line in lines:
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 5 or parts[2] == "0":
            continue
        try:
            start, end = int(ipaddress.IPv4Address(parts[0])), int(ipaddress.IPv4Address(parts[1]))
            asn = int(parts[2])
        except ValueError:
            continue
        # ~500k rows repeat a few thousand org/cc strings - intern them so they are stored once.
        rows.append((start, end, asn, sys.intern(parts[3]), sys.intern(parts[4])))

    return sorted(rows)


class AsnTable:

    def __init__(self, rows):
        self.rows = rows
        self.starts = [row[0] for row in rows]

    def __len__(self):
        return len(self.rows)

    def lookup(self, ip):
        try:
            value = int(ipaddress.IPv4Address(ip))
        except ValueError:
            return None
        index = bisect.bisect_right(self.starts, value) - 1
        if index < 0 or value > self.rows[index][1]:
            return None
        _, _, asn, cc, org = self.rows[index]
        return AsnInfo(asn=asn, cc=cc, org=org)


def load_table(path):
    path = Path(path)
    if not path.exists():
        return AsnTable([])
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        return AsnTable(parse_ip2asn(handle))


def refresh(path, url, now, max_age=timedelta(days=7), get=requests.get):

    path = Path(path)

    if path.exists() and now - datetime.fromtimestamp(path.stat().st_mtime) < max_age:
        return False

    response = get(url, timeout=60)
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp" + path.suffix)   # keeps .gz so load_table opens it the same way
    tmp.write_bytes(response.content)
    try:
        if not len(load_table(tmp)):
            raise ValueError("downloaded ASN table has no usable rows")
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)
    return True


RESOLVE = None      # socket.getaddrinfo unless a test swaps it


def remember_download(url, note, table=None, store=None, resolve=None, asn_path="inventory/ip2asn-v4.tsv.gz"):
    """Mark the owner of one of atlas's own download servers (this table, the IP-location file, the MAC maker
    list) as known for the host, so atlas's own updates never show up as a new destination to review.
    Best effort: returns the keys marked, [] when anything fails."""

    import socket
    from urllib.parse import urlsplit

    from lanxang.posture.store import PostureStore, asn_key

    try:
        host = urlsplit(url).hostname
        ips = {info[4][0] for info in (resolve or RESOLVE or socket.getaddrinfo)(host, 443, socket.AF_INET, socket.SOCK_STREAM)}
        table = table if table is not None else load_table(asn_path)
        keys = sorted({asn_key(getattr(table.lookup(ip), "asn", None), ip) for ip in ips})
        store = store or PostureStore()
        for key in keys:
            store.mark_known("host", key, note)
        return keys
    except Exception:
        return []
