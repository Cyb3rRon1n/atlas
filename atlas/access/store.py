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
from atlas.database.models import AccessHitRecord, AccessIpRecord, AccessLoginRecord, AccessPlaceRecord, AccessStateRecord

DENIED = (401, 403, 429)
LEARN_DAYS = 14


def place_of(ip_row):
    """(key, label) for a geolocated IP: country + provider is stable per person; city is too noisy on mobile."""

    # ponytail: IPv6 has no ASN here (the iptoasn table is IPv4-only) - a provider's /32 is stable enough;
    # load ip2asn-v6 if names are wanted
    v6 = ":" in ip_row.ip and "IPv6 " + ":".join(ip_row.ip.split(":")[:2]) + "::/32"
    provider = ip_row.org or (f"AS{ip_row.asn}" if ip_row.asn else "") or v6 or ip_row.city or "unknown provider"
    place = ", ".join(p for p in (ip_row.city, ip_row.region, ip_row.cc or ip_row.country) if p) or "unknown place"
    return f"{ip_row.cc or ip_row.country or '?'}/{provider}", f"{place} \u00b7 {provider}"


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

    def classify_logins(self, now, home_ips=()):
        """
        Give every successful sign-in a place. A user's first LEARN_DAYS (from their first stored sign-in)
        learn places automatically; after that a new place becomes a review item. Returns new review rows.
        """

        from datetime import timedelta
        new = []
        with Session(self.engine) as session:
            ips = {r.ip: r for r in session.scalars(select(AccessIpRecord))}
            firsts = {r.key[11:]: r.value for r in session.scalars(
                select(AccessStateRecord).where(AccessStateRecord.key.like("user_first:%")))}
            for login in session.scalars(select(AccessLoginRecord).where(AccessLoginRecord.ok.is_(True))
                                         .order_by(AccessLoginRecord.time)):
                row = ips.get(login.ip)
                if row is None or login.ip in home_ips or row.country == "Home network":
                    continue
                first = firsts.get(login.user)
                if not first:   # same session - a second one would lock SQLite mid-write
                    first = firsts[login.user] = login.time.isoformat()
                    session.merge(AccessStateRecord(key=f"user_first:{login.user}", value=first))
                key, label = place_of(row)
                place = session.scalars(select(AccessPlaceRecord).where(AccessPlaceRecord.user == login.user,
                                                                          AccessPlaceRecord.place_key == key)).first()
                if place is None:
                    learning = login.time < datetime.fromisoformat(first) + timedelta(days=LEARN_DAYS)
                    place = AccessPlaceRecord(user=login.user, place_key=key, label=label, first_seen=login.time,
                                              last_seen=login.time, ip=login.ip, app=login.app,
                                              status="learned" if learning else "review", alerted=False)
                    session.add(place)
                    session.flush()
                    if place.status == "review":
                        new.append({"user": place.user, "label": label, "app": login.app, "ip": login.ip, "time": login.time})
                elif login.time > place.last_seen:
                    place.last_seen, place.ip = login.time, login.ip
            session.commit()
        return new

    def places(self, status=None):
        with Session(self.engine) as session:
            q = select(AccessPlaceRecord).order_by(AccessPlaceRecord.last_seen.desc())
            if status:
                q = q.where(AccessPlaceRecord.status == status)
            return [{c: getattr(r, c) for c in ("id", "user", "place_key", "label", "status", "first_seen", "last_seen",
                                                 "ip", "app", "alerted")} for r in session.scalars(q)]

    def confirm_place(self, user, place_key):
        with Session(self.engine) as session:
            row = session.scalars(select(AccessPlaceRecord).where(AccessPlaceRecord.user == user,
                                                                    AccessPlaceRecord.place_key == place_key)).first()
            if row is None:
                return {"ok": False, "error": "no such sign-in place"}
            row.status = "confirmed"
            session.commit()
            return {"ok": True}

    def unalerted_reviews(self):
        return [p for p in self.places("review") if not p["alerted"]]

    def mark_alerted(self, ids):
        with Session(self.engine) as session:
            for r in session.scalars(select(AccessPlaceRecord).where(AccessPlaceRecord.id.in_(ids))):
                r.alerted = True
            session.commit()

    def prune(self, before):
        with Session(self.engine) as session:
            n = session.execute(delete(AccessHitRecord).where(AccessHitRecord.hour < _hour(before))).rowcount
            n += session.execute(delete(AccessLoginRecord).where(AccessLoginRecord.time < before)).rowcount
            n += session.execute(delete(AccessIpRecord).where(AccessIpRecord.last_seen < before)).rowcount
            session.commit()
            return n
