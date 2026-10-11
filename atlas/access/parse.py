"""
Traefik's default (common + extras) access-log line ->
dict(ip, time, method, path, status, service). Lines that don't match are skipped.

1.2.3.4 - - [11/Oct/2026:02:23:12 +0000] "GET /health HTTP/1.1" 200 7 "-" "-" 148676 "jellyfin@docker" "http://..." 9ms
"""

import ipaddress
import re
from datetime import datetime

LINE = re.compile(r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] "(?P<method>[A-Z]+) (?P<path>\S*)[^"]*" (?P<status>\d{3}) '
                  r'\S+ "[^"]*" "[^"]*" \d+ "(?P<router>[^"]*)"')


def parse_line(line):

    m = LINE.match(line)
    if not m:
        return None
    try:
        when = datetime.strptime(m["time"], "%d/%b/%Y:%H:%M:%S %z").replace(tzinfo=None)
        ipaddress.ip_address(m["ip"])
    except ValueError:
        return None

    return {"ip": m["ip"], "time": when, "method": m["method"], "path": m["path"], "status": int(m["status"]),
            "service": m["router"].split("@")[0] or "-"}


def is_private(ip):

    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return a.is_private or a.is_loopback or a.is_link_local


def read_new(path, offset):
    """
    Lines appended since `offset` (bytes). A smaller file than the offset means it
    was rotated/truncated, so start over. Returns (lines, new_offset).
    """

    with open(path, "rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        if size < offset:
            offset = 0
        handle.seek(offset)
        data = handle.read()

    end = data.rfind(b"\n") + 1   # leave a half-written last line for next time
    return data[:end].decode("utf-8", "replace").splitlines(), offset + end
