"""
The device inventory: sightings from each source are upserted, linked to a
device by atlas.devices.linking's certain-only rules, and turned into a
status plus queued alerts. Takes an explicit engine (tests pass a temp one);
defaults to this module's `engine`, which tests/conftest.py's temp_db also
patches.
"""

import json
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.database import initialize_database
from atlas.database.engine import engine
from atlas.database.models import DeviceRecord, NotificationRecord, SightingRecord, SourceRunRecord
from atlas.devices.linking import match
from atlas.devices.status import device_status


ROLLUP = timedelta(hours=24)

EDITABLE = {"name", "kind", "tags", "notes", "important", "state"}

GUEST_KINDS = {"qemu": "vm", "lxc": "lxc"}


def _iso(value):

    return value.isoformat() if value else None


class InventoryStore:

    def __init__(self, target_engine=None):

        self.engine = target_engine or engine
        initialize_database(self.engine)

    def import_manual_hosts(self, hosts, now=None):
        """map.hosts become known devices with a locked name - once per address."""

        now = now or datetime.utcnow()
        added = 0

        with Session(self.engine) as session:

            for host in hosts:

                exists = session.scalar(select(SightingRecord.id).where(
                    SightingRecord.source == "manual", SightingRecord.external_id == host.address))

                if exists:
                    continue

                device = DeviceRecord(name=host.name, state="known", notes=host.role,
                                      locked_fields=json.dumps(["name"]), created_at=now, updated_at=now)
                session.add(device)
                session.flush()
                session.add(SightingRecord(source="manual", external_id=host.address, ip=host.address,
                                           device_id=device.id, first_seen=now, last_seen=now))
                added += 1

            session.commit()

        return added

    def _known(self, session):

        rows = session.execute(
            select(SightingRecord, DeviceRecord.name).join(DeviceRecord, SightingRecord.device_id == DeviceRecord.id)
        ).all()

        return [{"device_id": row.device_id, "device_name": name, "source": row.source,
                 "ip": row.ip, "mac": row.mac, "hostname": row.hostname} for row, name in rows]

    def record_run(self, source, sightings, ok=True, error="", now=None):

        now = now or datetime.utcnow()
        result = {"new": [], "linked": 0, "suggested": 0, "seen": len(sightings) if ok else 0, "baseline": False}

        with Session(self.engine) as session:

            # A prior ok run only counts toward baseline if it actually saw something -
            # an empty first run (e.g. from a wrong subnet) shouldn't consume it, so the
            # first real run still gets treated as baseline instead of alerting on everything.
            result["baseline"] = ok and not session.scalar(select(SourceRunRecord.id).where(
                SourceRunRecord.source == source, SourceRunRecord.ok.is_(True),
                SourceRunRecord.seen_count > 0))

            session.add(SourceRunRecord(source=source, started_at=now, ok=ok, error=error, seen_count=result["seen"]))

            if not ok:
                session.commit()
                return result

            for new in sightings:

                row = session.scalar(select(SightingRecord).where(
                    SightingRecord.source == source, SightingRecord.external_id == new.external_id))

                if row is None:

                    # ponytail: O(new x total) re-query per sighting; fine at /24 scale,
                    # cache per run if subnets grow.
                    verdict, device_id = match(new, self._known(session))

                    if verdict == "link":
                        result["linked"] += 1

                    else:
                        device = DeviceRecord(
                            name=(new.hostname or "").split(".")[0] or new.ip or new.external_id,
                            kind=GUEST_KINDS.get(new.detail.get("type"), "other"),
                            suggested_merge_id=device_id if verdict == "suggest" else None,
                            created_at=now, updated_at=now)
                        session.add(device)
                        session.flush()
                        device_id = device.id
                        result["new"].append(device.name)
                        result["suggested"] += verdict == "suggest"

                        if not result["baseline"]:
                            session.add(NotificationRecord(device_id=device.id, kind="new", created_at=now))

                    row = SightingRecord(source=source, external_id=new.external_id, first_seen=now, device_id=device_id)
                    session.add(row)

                row.ip, row.mac, row.hostname = new.ip, new.mac, new.hostname
                row.detail, row.last_seen = json.dumps(new.detail), now
                session.flush()

            session.commit()

        return result

    def set_fields(self, device_id, fields, now=None):
        """Operator edit: applies only EDITABLE fields and locks each one it sets."""

        with Session(self.engine) as session:

            device = session.get(DeviceRecord, device_id)

            if device is None:
                return {"found": False}

            locked = set(json.loads(device.locked_fields))

            for key, value in fields.items():

                if key not in EDITABLE:
                    continue

                setattr(device, key, json.dumps(value) if key == "tags" else value)
                locked.add(key)

            device.locked_fields = json.dumps(sorted(locked))
            device.updated_at = now or datetime.utcnow()
            session.commit()

        return {"found": True}

    def _ok_runs(self, session):

        runs = {}

        for run in session.scalars(select(SourceRunRecord).where(SourceRunRecord.ok.is_(True))
                                   .order_by(SourceRunRecord.started_at.desc())):
            runs.setdefault(run.source, []).append(run.started_at)

        return runs

    def devices(self, now=None):

        with Session(self.engine) as session:

            ok_runs = self._ok_runs(session)
            sightings = {}

            for row in session.scalars(select(SightingRecord)):
                sightings.setdefault(row.device_id, []).append(row)

            output = []

            for device in session.scalars(select(DeviceRecord).order_by(DeviceRecord.name)):

                rows = sightings.get(device.id, [])
                observed = [row for row in rows if row.source != "manual"] or rows
                preferred = sorted(observed, key=lambda row: (row.source != "lan", row.ip is None))

                output.append({
                    "id": device.id, "name": device.name, "kind": device.kind,
                    "tags": json.loads(device.tags), "notes": device.notes, "important": device.important,
                    "state": device.state, "suggested_merge_id": device.suggested_merge_id,
                    "status": device_status([{"source": row.source, "last_seen": row.last_seen} for row in rows], ok_runs),
                    "ip": next((row.ip for row in preferred if row.ip), None),
                    "last_seen": _iso(max((row.last_seen for row in observed), default=None)),
                    "sightings": [{"id": row.id, "source": row.source, "external_id": row.external_id,
                                   "ip": row.ip, "mac": row.mac, "hostname": row.hostname,
                                   "detail": json.loads(row.detail), "first_seen": _iso(row.first_seen),
                                   "last_seen": _iso(row.last_seen)} for row in rows],
                })

        return output

    def queue_offline(self, now=None):
        """One offline alert per episode: skipped if one was queued since it was last seen."""

        now = now or datetime.utcnow()
        queued = []

        candidates = [device for device in self.devices(now)
                      if device["important"] and device["status"] == "quiet" and device["state"] != "ignored"]

        with Session(self.engine) as session:

            for device in candidates:

                since = datetime.fromisoformat(device["last_seen"]) if device["last_seen"] else datetime.min
                already = session.scalar(select(NotificationRecord.id).where(
                    NotificationRecord.device_id == device["id"], NotificationRecord.kind == "offline",
                    NotificationRecord.created_at >= since))

                if not already:
                    session.add(NotificationRecord(device_id=device["id"], kind="offline", created_at=now))
                    queued.append(device["name"])

            session.commit()

        return queued

    def due_notifications(self, now=None):
        """Stale alerts are suppressed (sent_at set with nothing delivered), not just
        skipped: a device deleted, ignored, or no longer in the state the alert was
        about (a "new" device the operator already triaged; an "offline" device
        seen again) shouldn't surface once its cause is gone."""

        now = now or datetime.utcnow()
        devices = {device["id"]: device for device in self.devices(now)}
        due = {}

        with Session(self.engine) as session:

            last_new = session.scalar(select(NotificationRecord.sent_at).where(
                NotificationRecord.kind == "new", NotificationRecord.sent_at.is_not(None))
                .order_by(NotificationRecord.sent_at.desc()))

            for note in session.scalars(select(NotificationRecord).where(NotificationRecord.sent_at.is_(None))
                                        .order_by(NotificationRecord.created_at)):

                device = devices.get(note.device_id)

                if (device is None or device["state"] == "ignored"
                        or (note.kind == "new" and device["state"] != "new")
                        or (note.kind == "offline" and device["status"] != "quiet")):
                    note.sent_at = now
                    continue

                if note.kind == "new" and last_new and now - last_new < ROLLUP:
                    continue

                due.setdefault(note.kind, []).append({
                    "id": note.id, "device": device.get("name", "?"),
                    "ip": device.get("ip"), "last_seen": device.get("last_seen")})

            session.commit()

        return due

    def mark_sent(self, ids, now=None):

        with Session(self.engine) as session:

            for note in session.scalars(select(NotificationRecord).where(NotificationRecord.id.in_(ids))):
                note.sent_at = now or datetime.utcnow()

            session.commit()

    def source_runs(self, limit=20):

        with Session(self.engine) as session:

            return [{"source": run.source, "started_at": _iso(run.started_at), "ok": run.ok,
                     "error": run.error, "seen_count": run.seen_count}
                    for run in session.scalars(select(SourceRunRecord)
                                               .order_by(SourceRunRecord.started_at.desc()).limit(limit))]
