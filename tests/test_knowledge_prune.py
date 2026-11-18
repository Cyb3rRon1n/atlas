from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from lanxang.database.models import EnvironmentRecord, EventRecord
from lanxang.knowledge.store import KnowledgeStore


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


def test_routine_discovery_events_go_after_a_week(temp_db):
    from datetime import datetime

    from lanxang.knowledge import store as store_module

    now = datetime(2026, 11, 17, 12)
    rows = [("atlas.discovery.completed", now - timedelta(days=10)), ("atlas.discovery.completed", now - timedelta(days=9)),
            ("atlas.discovery.completed", now - timedelta(days=1)), ("atlas.plugin.loaded", now - timedelta(days=8)),
            ("atlas.host.sample", now - timedelta(days=10))]
    with Session(temp_db) as session:
        session.add_all([EventRecord(event_type=kind, source="x", payload="{}", created_at=at) for kind, at in rows])
        session.commit()
    store_module.KnowledgeStore().prune(now)
    with Session(temp_db) as session:
        left = sorted((e.event_type, (now - e.created_at).days) for e in session.scalars(select(EventRecord)))
    assert left == [("atlas.discovery.completed", 1), ("atlas.host.sample", 10),    # Trends reads host samples
                    ("atlas.plugin.loaded", 8)]                                      # the newest of its type stays
