"""
Wired-map snapshots: insert-only rows pruned to the newest `keep`, plus a pure
diff between two snapshots ("nas moved: core-switch gi5 -> gi7"). Takes an
explicit engine (tests pass a temp one), like PostureStore.
"""

import json

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from atlas.database import initialize_database
from atlas.database.engine import engine
from atlas.database.models import WiringSnapshotRecord


class WiringStore:

    def __init__(self, engine_=None):
        self.engine = engine_ or engine
        initialize_database(self.engine)

    def save(self, snapshot, raw, sources, taken_at, keep):

        with Session(self.engine) as session, session.begin():
            record = WiringSnapshotRecord(taken_at=taken_at, data=json.dumps({"snapshot": snapshot, "raw": raw}),
                                          errors=json.dumps(sources))
            session.add(record)
            session.flush()
            keep_ids = select(WiringSnapshotRecord.id).order_by(
                WiringSnapshotRecord.taken_at.desc(), WiringSnapshotRecord.id.desc()).limit(max(keep, 1))
            session.execute(delete(WiringSnapshotRecord).where(WiringSnapshotRecord.id.not_in(keep_ids)))
            return record.id

    def latest(self, n=2):

        with Session(self.engine) as session:
            rows = session.scalars(select(WiringSnapshotRecord).order_by(
                WiringSnapshotRecord.taken_at.desc(), WiringSnapshotRecord.id.desc()).limit(n)).all()
            result = []
            for row in rows:
                data = json.loads(row.data)
                result.append({"taken_at": row.taken_at, "snapshot": data["snapshot"], "raw": data["raw"],
                               "sources": json.loads(row.errors)})
            return result


def diff_snapshots(previous, current):

    if not previous:
        return []

    def attachments(snapshot):
        names = {node["id"]: node["name"] for node in snapshot["nodes"]}
        hosts = {node["id"] for node in snapshot["nodes"] if node["kind"] in ("host", "unknown", "bridge")}
        return ({link["b"]: (names.get(link["a"], link["a"]), link["a_port"], names.get(link["b"], link["b"]))
                 for link in snapshot["links"] if link["b"] in hosts},
                {link["id"]: link for link in snapshot["links"]})

    (old_at, old_links), (new_at, new_links) = attachments(previous), attachments(current)
    changes = []

    for host, (switch, port, name) in new_at.items():
        if host not in old_at:
            changes.append({"type": "added", "text": f"{name} appeared on {switch} {port}"})
        elif old_at[host][:2] != (switch, port):
            changes.append({"type": "moved",
                            "text": f"{name} moved: {old_at[host][0]} {old_at[host][1]} → {switch} {port}"})

    for host, (switch, port, name) in old_at.items():
        if host not in new_at:
            changes.append({"type": "removed", "text": f"{name} gone from {switch} {port}"})

    for link_id, link in new_links.items():
        old = old_links.get(link_id)
        if not old:
            continue
        if old["speed"] != link["speed"]:
            changes.append({"type": "speed", "text": f"{link['a_port']}: {old['speed']}M → {link['speed']}M"})
        if old["up"] != link["up"]:
            state = "up" if link["up"] else "down"
            changes.append({"type": state, "text": f"{link['a_port']} went {state}"})

    return changes
