"""Event types are stored data: they stay atlas.* after the rename, so an existing install's history keeps working."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from lanxang.clock import utcnow
from lanxang.database.models import EventRecord
from lanxang.knowledge.queries import KnowledgeQueries
from lanxang.knowledge.store import KnowledgeStore


def _seed(engine, rows):
    with Session(engine) as session, session.begin():
        session.add_all([EventRecord(event_type=kind, source="x", payload=payload, created_at=at)
                         for kind, payload, at in rows])


def test_existing_atlas_history_reads_labels_and_prunes(temp_db):
    from lanxang.web.home_page import build_hosts, interesting_events, render_home_page
    from lanxang.web.render import render_history_page

    now = utcnow()
    _seed(temp_db, [("atlas.discovery.completed", "{}", now - timedelta(days=10)),
                    ("atlas.discovery.completed", "{}", now - timedelta(days=1)),
                    ("atlas.proxmox.scan.completed", '{"nodes": [{"name": "pve1"}]}', now - timedelta(hours=2)),
                    ("atlas.proxmox.changes_detected", "{}", now - timedelta(hours=1))])
    events = KnowledgeQueries().recent_events(50)

    home = render_home_page(None, build_hosts(None, None, None), interesting_events(events))
    history = render_history_page(events)
    for html in (home, history):
        assert "proxmox changes detected" in html and "atlas proxmox" not in html and "lanxang proxmox" not in html

    assert KnowledgeQueries().latest_event_payload("atlas.proxmox.scan.completed") == {"nodes": [{"name": "pve1"}]}
    KnowledgeStore().prune(now)                                   # routine atlas.* rows older than a week go
    with Session(temp_db) as session:
        left = [e.event_type for e in session.scalars(select(EventRecord).order_by(EventRecord.id))]
    assert left == ["atlas.discovery.completed", "atlas.proxmox.scan.completed", "atlas.proxmox.changes_detected"]


def test_new_events_are_still_written_as_atlas(temp_db):
    from lanxang.actions.registry import PLAN_STEP_EVENT_TYPES
    from lanxang.events import types
    from lanxang.knowledge.store import ROUTINE_EVENTS
    from lanxang.web import api, changes_feed
    from lanxang.devices import Sighting
    from lanxang.devices.store import InventoryStore

    names = [types.DISCOVERY_COMPLETED, types.PLUGIN_LOADED, types.REPORT_GENERATED, *PLAN_STEP_EVENT_TYPES.values(),
             *ROUTINE_EVENTS, *changes_feed.CHANGE_EVENTS]
    assert all(name.startswith("atlas.") for name in names)

    store = InventoryStore(temp_db)
    store.record_run("lan", [Sighting("lan", "02:00:00:00:00:01", ip="192.0.2.1", mac="02:00:00:00:00:01")])
    device = store.devices()[0]["id"]
    assert api.handle("POST", f"/api/devices/{device}", {"name": "router"})[0] == 200
    assert KnowledgeQueries().recent_events(1)[0].event_type == "atlas.devices.updated"
