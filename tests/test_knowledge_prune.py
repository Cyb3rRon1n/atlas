from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.database.models import EnvironmentRecord, EventRecord
from atlas.knowledge.store import KnowledgeStore


def test_prune_keeps_recent_rows_and_the_newest_event_of_each_type(temp_db):
    now = datetime(2026, 11, 16)
    old, recent = now - timedelta(days=120), now - timedelta(days=3)
    with Session(temp_db) as session, session.begin():
        session.add_all([EventRecord(event_type="scan", source="x", payload="{}", created_at=old),
                         EventRecord(event_type="scan", source="x", payload="{}", created_at=recent),
                         EventRecord(event_type="proxmox", source="x", payload="{}", created_at=old),
                         EventRecord(event_type="proxmox", source="x", payload="{}", created_at=old + timedelta(hours=1)),
                         EnvironmentRecord(data="{}", created_at=now - timedelta(days=8)),
                         EnvironmentRecord(data="{}", created_at=recent)])

    KnowledgeStore().prune(now)

    with Session(temp_db) as session:
        events = [(e.event_type, e.created_at) for e in session.scalars(select(EventRecord).order_by(EventRecord.id))]
        environments = [e.created_at for e in session.scalars(select(EnvironmentRecord))]
    assert events == [("scan", recent), ("proxmox", old + timedelta(hours=1))]   # newest proxmox kept though old
    assert environments == [recent]
