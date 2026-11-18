"""
IP -> city/country/lat/lon from DB-IP's free "IP to City Lite" database (CC BY 4.0,
https://db-ip.com), read locally with maxminddb - no visitor IP ever leaves the host.
Refreshed monthly; a missing file just means unknown locations.
"""

from datetime import datetime, timedelta
from pathlib import Path

import requests

URL = "https://download.db-ip.com/free/dbip-city-lite-{month}.mmdb.gz"


class GeoDB:

    def __init__(self, path):
        self.reader = None
        if Path(path).exists():
            import maxminddb
            self.reader = maxminddb.open_database(str(path))

    def lookup(self, ip):
        if not self.reader:
            return None
        try:
            r = self.reader.get(ip) or {}
        except ValueError:
            return None
        loc = r.get("location") or {}
        if not r:
            return None
        return {"cc": (r.get("country") or {}).get("iso_code", ""),
                "country": ((r.get("country") or {}).get("names") or {}).get("en", ""),
                "city": ((r.get("city") or {}).get("names") or {}).get("en", ""),
                "region": (((r.get("subdivisions") or [{}])[0]).get("names") or {}).get("en", ""),
                "lat": loc.get("latitude"), "lon": loc.get("longitude")}


def refresh(path, now, max_age=timedelta(days=31), get=requests.get):
    """Download this (or last) month's file if ours is missing or older than max_age. True when replaced."""

    import gzip
    import maxminddb

    path = Path(path)
    if path.exists() and now - datetime.fromtimestamp(path.stat().st_mtime) < max_age:
        return False

    last_error = None
    for month in (now.strftime("%Y-%m"), (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")):
        response = get(URL.format(month=month), timeout=120)
        if response.status_code != 200:
            last_error = f"{response.status_code} for {month}"
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(gzip.decompress(response.content))
        try:
            maxminddb.open_database(str(tmp)).get("1.1.1.1")
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        tmp.replace(path)
        return True

    raise RuntimeError(f"DB-IP download failed: {last_error}")
