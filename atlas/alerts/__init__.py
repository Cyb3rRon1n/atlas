"""
The Alerts page's list: every check reports the problems it sees now (sync) or a one-off finding (event);
the store opens new ones, refreshes ongoing ones and resolves the ones that went away. Each check still
writes its own messages, tagged with the problem they are about (Text); before sending, it asks allowed()
whether that problem or its device is muted, or alerts are paused. The page always shows everything.
"""

from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from atlas.database import initialize_database
from atlas.database.engine import engine
from atlas.database.models import AlertQuietRecord, AlertRecord
from atlas.clock import utcnow

EVENT_DAYS = 7          # a one-off finding stays under "Needs action" this long
KEEP_DAYS = 30          # resolved alerts are kept this long


class Text(str):
    """An alert message that knows which problem it is about: key as in sync() ("lan:rogue_dhcp:192.0.2.9")."""

    def __new__(cls, text, key, device_id=None):
        self = super().__new__(cls, text)
        self.key, self.device_id = key, device_id
        return self


def issue(kind, subject, title, detail="", level="problem", href="", device_id=None):
    """One problem as a check reports it to sync()."""

    return {"key": f"{kind}:{subject}", "title": title, "detail": detail, "level": level, "href": href,
            "device_id": device_id}


def _row(record):

    return {name: getattr(record, name) for name in ("id", "key", "source", "level", "title", "detail", "href",
                                                     "device_id", "event", "opened_at", "seen_at", "resolved_at",
                                                     "acked_at")}


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

    def ack(self, alert_id, now):
        """Seen it: an ongoing problem stays listed (marked acknowledged); a one-off finding is done."""

        with Session(self.engine) as session:
            row = session.get(AlertRecord, alert_id)
            if row is None:
                return False
            row.acked_at = now
            if row.event and row.resolved_at is None:
                row.resolved_at = now
            session.commit()
        return True

    def mute(self, alert_id, days, now):
        """No messages about this problem - or its whole device when it has one - for days (0 = always)."""

        with Session(self.engine) as session:
            row = session.get(AlertRecord, alert_id)
            if row is None:
                return False
            if row.device_id is not None:
                rule = AlertQuietRecord(device_id=row.device_id, label=f"device: {row.title}")
            else:
                rule = AlertQuietRecord(key=row.key, label=row.title)
            rule.until, rule.created_at = (now + timedelta(days=days)) if days else None, now
            session.add(rule)
            session.commit()
        return True

    def pause(self, hours, now):

        with Session(self.engine) as session:
            session.execute(delete(AlertQuietRecord).where(AlertQuietRecord.key == "*"))
            session.add(AlertQuietRecord(key="*", label="all alerts", until=now + timedelta(hours=hours), created_at=now))
            session.commit()

    def unquiet(self, rule_id=None):
        """Remove one mute, or (no id) end a pause."""

        with Session(self.engine) as session:
            where = AlertQuietRecord.id == rule_id if rule_id is not None else AlertQuietRecord.key == "*"
            session.execute(delete(AlertQuietRecord).where(where))
            session.commit()

    def quiet(self, now):
        """Active mutes and pause; expired ones are removed."""

        with Session(self.engine) as session:
            session.execute(delete(AlertQuietRecord).where(AlertQuietRecord.until.is_not(None),
                                                           AlertQuietRecord.until <= now))
            session.commit()
            return [{"id": r.id, "key": r.key, "device_id": r.device_id, "label": r.label, "until": r.until}
                    for r in session.scalars(select(AlertQuietRecord).order_by(AlertQuietRecord.created_at))]

    def allowed(self, key, device_id, now):
        """Should a message about this problem go out now?"""

        for rule in self.quiet(now):
            if rule["key"] == "*" or (key and rule["key"] == key) or \
                    (device_id is not None and rule["device_id"] == device_id):
                return False
        return True

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
        live.sort(key=lambda r: r["acked_at"] is not None)          # acknowledged ones sink, order kept
        quiet = self.quiet(now)
        return {"open": [r for r in live if r["level"] == "problem"],
                "paused_until": next((q["until"] for q in quiet if q["key"] == "*"), None),
                "muted": [q for q in quiet if q["key"] != "*"],
                "watch": [r for r in live if r["level"] != "problem"],
                "resolved": [r for r in rows if r["resolved_at"] and r["resolved_at"] >= now - timedelta(days=days)]}


def _store(owner):
    """An AlertStore on the same database as the check's own store; None for a stand-in store (tests)."""

    engine_ = getattr(owner, "engine", None)
    return AlertStore(engine_) if engine_ is not None else None


def allowed(owner, text, now=None):
    """True when a message may go out: Text tagged as muted, or any message while paused or in quiet hours, is held.
    Fails open - a broken alert database must never silence a real problem."""

    from datetime import datetime

    now = now or utcnow()
    try:
        from atlas.alerts.quiet import active
        from atlas.config import load_config
        notify = load_config().notify
        if notify.quiet_hours and active(notify.quiet_hours, notify.timezone, now):
            return False
    except Exception:
        pass                                     # a bad schedule never silences anything
    try:
        store = _store(owner)
        return store is None or store.allowed(getattr(text, "key", ""), getattr(text, "device_id", None), now)
    except Exception:
        return True


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
