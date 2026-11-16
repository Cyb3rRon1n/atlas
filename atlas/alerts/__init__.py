"""
The Alerts page's list: every check reports the problems it sees now (sync) or a one-off finding (event);
the store opens new ones, refreshes ongoing ones and resolves the ones that went away. Sending messages
stays with each check for now; mute, pause and grouping will decide here what gets sent.
"""

from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from atlas.database import initialize_database
from atlas.database.engine import engine
from atlas.database.models import AlertRecord

EVENT_DAYS = 7          # a one-off finding stays under "Needs action" this long
KEEP_DAYS = 30          # resolved alerts are kept this long


def issue(kind, subject, title, detail="", level="problem", href="", device_id=None):
    """One problem as a check reports it to sync()."""

    return {"key": f"{kind}:{subject}", "title": title, "detail": detail, "level": level, "href": href,
            "device_id": device_id}


def _row(record):

    return {name: getattr(record, name) for name in ("id", "key", "source", "level", "title", "detail", "href",
                                                     "device_id", "event", "opened_at", "seen_at", "resolved_at")}


class AlertStore:

    def __init__(self, engine_=None):
        self.engine = engine_ or engine
        initialize_database(self.engine)

    def sync(self, source, issues, now):
        """This check's problems right now: new ones open, ongoing ones refresh, missing ones resolve."""

        current = {f"{source}:{i['key']}": i for i in issues}
        with Session(self.engine) as session:
            open_rows = {row.key: row for row in session.scalars(select(AlertRecord).where(
                AlertRecord.source == source, AlertRecord.event.is_(False), AlertRecord.resolved_at.is_(None)))}
            for key, row in open_rows.items():
                if key not in current:
                    row.resolved_at = now
            for key, found in current.items():
                row = open_rows.get(key)
                if row is None:
                    row = AlertRecord(key=key, source=source, opened_at=now, seen_at=now, event=False,
                                      level=found["level"], title=found["title"])
                    session.add(row)
                row.level, row.title, row.detail = found["level"], found["title"], found.get("detail", "")
                row.href, row.device_id, row.seen_at = found.get("href", ""), found.get("device_id"), now
            session.commit()

    def event(self, source, title, detail="", href="", device_id=None, now=None, level="problem"):
        """A one-off finding (a new open port): shows as open for EVENT_DAYS, then resolves by itself."""

        with Session(self.engine) as session:
            session.add(AlertRecord(key=f"{source}:event", source=source, level=level, title=title, detail=detail,
                                    href=href, device_id=device_id, event=True, opened_at=now, seen_at=now))
            session.commit()

    def listing(self, now, days=7):
        """{"open": [...], "watch": [...], "resolved": [...]} - newest first; old events and rows tidied."""

        with Session(self.engine) as session:
            session.execute(delete(AlertRecord).where(AlertRecord.resolved_at < now - timedelta(days=KEEP_DAYS)))
            for row in session.scalars(select(AlertRecord).where(
                    AlertRecord.event.is_(True), AlertRecord.resolved_at.is_(None),
                    AlertRecord.opened_at < now - timedelta(days=EVENT_DAYS))):
                row.resolved_at = row.opened_at + timedelta(days=EVENT_DAYS)
            session.commit()
            rows = [_row(r) for r in session.scalars(select(AlertRecord).order_by(AlertRecord.opened_at.desc()))]

        live = [r for r in rows if r["resolved_at"] is None]
        return {"open": [r for r in live if r["level"] == "problem"],
                "watch": [r for r in live if r["level"] != "problem"],
                "resolved": [r for r in rows if r["resolved_at"] and r["resolved_at"] >= now - timedelta(days=days)]}


def _store(owner):
    """An AlertStore on the same database as the check's own store; None for a stand-in store (tests)."""

    engine_ = getattr(owner, "engine", None)
    return AlertStore(engine_) if engine_ is not None else None


def report(source, issues, now, owner):
    """sync() on owner's database (the check's own store), never breaking the check calling it."""

    try:
        store = _store(owner)
        if store:
            store.sync(source, issues, now)
    except Exception:
        pass


def report_event(source, title, now, owner, detail="", href="", device_id=None):

    try:
        store = _store(owner)
        if store:
            store.event(source, title, detail, href, device_id, now)
    except Exception:
        pass
