"""
Access storage: hourly hits per (IP, service), one geolocated row per IP, app
sign-ins, and collector bookmarks. Takes an explicit engine (tests pass a temp
one); defaults to the app engine.
"""

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from atlas.database import initialize_database
from atlas.database.engine import engine
from atlas.database.models import AccessHitRecord, AccessIpRecord, AccessLoginRecord, AccessStateRecord

DENIED = (401, 403, 429)


def _hour(moment):
    return moment.replace(minute=0, second=0, microsecond=0)


class AccessStore:

    def __init__(self, engine_=None):
        self.engine = engine_ or engine
        initialize_database(self.engine)

    def get_state(self, key, default=""):
        with Session(self.engine) as session:
            row = session.get(AccessStateRecord, key)
            return row.value if row else default

    def set_state(self, key, value):
        with Session(self.engine) as session:
            session.merge(AccessStateRecord(key=key, value=str(value)))
            session.commit()

    def record_hits(self, entries):
        """entries: parse.parse_line() dicts. Returns the IPs seen, so the caller can geolocate new ones."""

        buckets = {}
        for e in entries:
            b = buckets.setdefault((_hour(e["time"]), e["ip"], e["service"]), [0, 0, 0, e["time"]])
            b[0] += 1
            b[1] += e["status"] in DENIED
            b[2] += e["status"] >= 500
            b[3] = max(b[3], e["time"])

        with Session(self.engine) as session:
            for (hour, ip, service), (n, denied, errors, _) in buckets.items():
                row = session.scalars(select(AccessHitRecord).where(
                    AccessHitRecord.hour == hour, AccessHitRecord.ip == ip, AccessHitRecord.service == service)).first()
                if row is None:
                    row = AccessHitRecord(hour=hour, ip=ip, service=service, requests=0, denied=0, errors=0)
                    session.add(row)
                row.requests += n
                row.denied += denied
                row.errors += errors
            session.commit()

        last = {}
        for (_, ip, _), b in buckets.items():
            last[ip] = max(last.get(ip, b[3]), b[3])
        return last

    def touch_ips(self, last_seen, locate):
        """Upsert IP rows; `locate(ip)` -> dict of geo/asn fields, called only for IPs not stored yet."""

        with Session(self.engine) as session:
            for ip, when in last_seen.items():
                row = session.get(AccessIpRecord, ip)
                if row is None:
                    session.add(AccessIpRecord(ip=ip, first_seen=when, last_seen=when, **(locate(ip) or {})))
                else:
                    row.last_seen = max(row.last_seen, when)
            session.commit()

    def record_logins(self, logins):
        """logins: dicts with app, external_id, time, user, ip, ok, client. Already-stored events are skipped."""

        added = 0
        with Session(self.engine) as session:
            for item in logins:
                exists = session.scalars(select(AccessLoginRecord.id).where(
                    AccessLoginRecord.app == item["app"], AccessLoginRecord.external_id == item["external_id"])).first()
                if not exists:
                    session.add(AccessLoginRecord(**item))
                    added += 1
            session.commit()
        return added

    def summary(self, since):
        """Everything the Access page needs for one time window."""

        with Session(self.engine) as session:
            ips = {r.ip: r for r in session.scalars(select(AccessIpRecord))}
            hits = session.execute(select(AccessHitRecord.ip, AccessHitRecord.service, func.sum(AccessHitRecord.requests),
                                          func.sum(AccessHitRecord.denied), func.max(AccessHitRecord.hour))
                                   .where(AccessHitRecord.hour >= _hour(since))
                                   .group_by(AccessHitRecord.ip, AccessHitRecord.service)).all()
            logins = session.scalars(select(AccessLoginRecord).where(AccessLoginRecord.time >= since)
                                     .order_by(AccessLoginRecord.time.desc())).all()

            def where(ip):
                r = ips.get(ip)
                return {"cc": r.cc, "country": r.country, "region": r.region, "city": r.city, "lat": r.lat, "lon": r.lon,
                        "org": r.org, "asn": r.asn, "first_seen": r.first_seen} if r else {}

            visitors = {}
            for ip, service, n, denied, last in hits:
                v = visitors.setdefault(ip, {"ip": ip, "requests": 0, "denied": 0, "services": {}, "last": last, **where(ip)})
                v["requests"] += n
                v["denied"] += denied
                v["services"][service] = v["services"].get(service, 0) + n
                v["last"] = max(v["last"], last)

            return {"visitors": sorted(visitors.values(), key=lambda v: -v["requests"]),
                    "logins": [{"app": l.app, "time": l.time, "user": l.user, "ip": l.ip, "ok": l.ok, "client": l.client,
                                **where(l.ip)} for l in logins]}

    def prune(self, before):
        with Session(self.engine) as session:
            n = session.execute(delete(AccessHitRecord).where(AccessHitRecord.hour < _hour(before))).rowcount
            n += session.execute(delete(AccessLoginRecord).where(AccessLoginRecord.time < before)).rowcount
            n += session.execute(delete(AccessIpRecord).where(AccessIpRecord.last_seen < before)).rowcount
            session.commit()
            return n
