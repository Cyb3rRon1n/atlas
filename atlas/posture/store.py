"""
Posture storage: hourly flow buckets, first-seen networks per source, the
operator's "expected" list, route snapshots and per-collector status. Takes an
explicit engine (tests pass a temp one); defaults to this module's `engine`,
which tests/conftest.py's temp_db also patches.
"""

import json
import re
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from atlas.database import initialize_database
from atlas.database.engine import engine
from atlas.database.models import (PostureFlowRecord, PostureKnownRecord, PostureRouteRecord, PostureSeenRecord,
                                   PostureStatusRecord)


ASN_KEY = re.compile(r"^(AS\d+|ip:[0-9.]+)$")


def asn_key(asn, dest_ip):
    return f"AS{asn}" if asn else f"ip:{dest_ip}"


def _hour(moment):
    return moment.replace(minute=0, second=0, microsecond=0)


def _row(record, *fields):
    return {field: getattr(record, field) for field in fields}


FLOW_FIELDS = ("hour", "source", "band", "dest_ip", "dest_port", "proto", "asn", "org", "cc",
               "bytes_out", "bytes_in", "conns")


class PostureStore:

    def __init__(self, engine_=None):
        self.engine = engine_ or engine
        initialize_database(self.engine)

    def record_flows(self, deltas, now):

        hour = _hour(now)
        new = []

        with Session(self.engine) as session:

            known = {(k.source, k.asn_key) for k in session.scalars(select(PostureKnownRecord))}

            for d in deltas:

                row = session.scalars(select(PostureFlowRecord).where(
                    PostureFlowRecord.hour == hour, PostureFlowRecord.source == d["source"],
                    PostureFlowRecord.dest_ip == d["dest_ip"], PostureFlowRecord.dest_port == d["dest_port"],
                    PostureFlowRecord.proto == d["proto"])).first()

                if row is None:
                    row = PostureFlowRecord(hour=hour, source=d["source"], band=d["band"], dest_ip=d["dest_ip"],
                                            dest_port=d["dest_port"], proto=d["proto"], asn=d["asn"], org=d["org"],
                                            cc=d["cc"], bytes_out=0, bytes_in=0, conns=0)
                    session.add(row)

                row.bytes_out += d["bytes_out"]
                row.bytes_in += d["bytes_in"]
                row.conns += 1 if d["new_conn"] else 0

                key = asn_key(d["asn"], d["dest_ip"])
                seen = session.scalars(select(PostureSeenRecord).where(
                    PostureSeenRecord.source == d["source"], PostureSeenRecord.asn_key == key)).first()

                if seen is None:
                    session.add(PostureSeenRecord(source=d["source"], asn_key=key, org=d["org"], cc=d["cc"],
                                                  first_seen=now, last_seen=now))
                    session.flush()
                    if (d["source"], key) not in known:
                        new.append({"source": d["source"], "asn_key": key, "org": d["org"], "cc": d["cc"]})
                else:
                    seen.last_seen = now

            session.commit()

        return new

    def flows(self, since):
        with Session(self.engine) as session:
            rows = session.scalars(select(PostureFlowRecord).where(PostureFlowRecord.hour >= _hour(since)))
            return [_row(r, *FLOW_FIELDS) for r in rows]

    def seen(self):
        with Session(self.engine) as session:
            known = {(k.source, k.asn_key) for k in session.scalars(select(PostureKnownRecord))}
            return [{**_row(r, "source", "asn_key", "org", "cc", "first_seen", "last_seen"),
                     "known": (r.source, r.asn_key) in known}
                    for r in session.scalars(select(PostureSeenRecord))]

    def mark_known(self, source, key, note=""):

        if not (isinstance(source, str) and source.strip() and len(source) <= 128):
            return {"ok": False, "error": "source must be a container name"}

        if not (isinstance(key, str) and ASN_KEY.match(key)):
            return {"ok": False, "error": "asn_key must look like AS123 or ip:1.2.3.4"}

        with Session(self.engine) as session:
            exists = session.scalars(select(PostureKnownRecord).where(
                PostureKnownRecord.source == source, PostureKnownRecord.asn_key == key)).first()
            if exists is None:
                session.add(PostureKnownRecord(source=source, asn_key=key, note=str(note)[:500]))
                session.commit()

        return {"ok": True}

    def set_status(self, source, ok, detail, now):
        with Session(self.engine) as session:
            row = session.scalars(select(PostureStatusRecord).where(PostureStatusRecord.source == source)).first()
            if row is None:
                row = PostureStatusRecord(source=source, ok=ok, updated_at=now)
                session.add(row)
            row.ok, row.detail, row.updated_at = ok, json.dumps(detail), now
            session.commit()

    def statuses(self):
        with Session(self.engine) as session:
            return {r.source: {"ok": r.ok, "detail": json.loads(r.detail), "updated_at": r.updated_at}
                    for r in session.scalars(select(PostureStatusRecord))}

    def save_routes(self, routes, now):
        encoded = json.dumps(sorted(routes, key=lambda r: r["name"]), sort_keys=True)
        with Session(self.engine) as session:
            last = session.scalars(select(PostureRouteRecord).order_by(PostureRouteRecord.id.desc())).first()
            if last is not None and last.routes == encoded:
                return False
            session.add(PostureRouteRecord(snapshot_at=now, routes=encoded))
            session.commit()
            return True

    def latest_routes(self):
        with Session(self.engine) as session:
            last = session.scalars(select(PostureRouteRecord).order_by(PostureRouteRecord.id.desc())).first()
            return json.loads(last.routes) if last else []

    def prune(self, before):
        with Session(self.engine) as session:
            result = session.execute(delete(PostureFlowRecord).where(PostureFlowRecord.hour < _hour(before)))
            session.commit()
            return result.rowcount
