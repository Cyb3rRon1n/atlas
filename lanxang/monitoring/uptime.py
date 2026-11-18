"""
Uptime checks (lanxang uptime check, once a minute in atlas-scan -> web Servers > Uptime): is each service you
list answering? A web address counts as up when it answers at all below HTTP 500 - a login redirect or a 401
still means the service is running; certificate trouble is the certificate watch's job, so it isn't verified
here. host:port is a plain TCP connect. A check is down after uptime.fail_after failures in a row: one alert
then, and one "back up" with how long it was down. Results are kept 30 days.
"""

import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from sqlalchemy import Integer, delete, func, select
from sqlalchemy.orm import Session

from lanxang.alerts import Text
from lanxang.database import initialize_database
from lanxang.database.engine import engine
from lanxang.database.models import UptimeRecord

KEEP = timedelta(days=30)
WINDOWS = (("24 h", timedelta(hours=24)), ("7 days", timedelta(days=7)), ("30 days", KEEP))


def valid_target(target):
    """The target cleaned up, or ValueError in words a person can act on."""

    target = (target or "").strip()
    if target.startswith(("http://", "https://")):
        if not urllib.parse.urlsplit(target).hostname:
            raise ValueError("That web address has no host name.")
        return target
    host, _, port = target.rpartition(":")
    if not host or not port.isdigit() or not 0 < int(port) < 65536:
        raise ValueError("Enter a web address (https://...) or host:port, like 192.0.2.10:22.")

    return target


def probe(target, timeout=10.0):
    """(ok, milliseconds or None, detail)."""

    start = time.monotonic()
    try:
        if target.startswith(("http://", "https://")):
            request = urllib.request.Request(target, headers={"User-Agent": "atlas-uptime"})
            try:
                with urllib.request.urlopen(request, timeout=timeout, context=ssl._create_unverified_context()) as reply:
                    status = reply.status
            except urllib.error.HTTPError as error:
                status = error.code
            ms = (time.monotonic() - start) * 1000
            return status < 500, ms, f"HTTP {status}"
        host, _, port = target.rpartition(":")
        with socket.create_connection((host.strip("[]"), int(port)), timeout=timeout):
            pass
        return True, (time.monotonic() - start) * 1000, "port open"
    except (OSError, ValueError) as error:
        reason = getattr(error, "reason", None) or error
        return False, None, (str(reason) or type(reason).__name__)[:200]


class UptimeStore:

    def __init__(self, engine_=None):
        self.engine = engine_ or engine
        initialize_database(self.engine)

    def save(self, results, now):

        with Session(self.engine) as session, session.begin():
            session.add_all(UptimeRecord(checked_at=now, name=name, ok=ok, ms=ms, detail=detail)
                            for name, (ok, ms, detail) in results.items())
            session.execute(delete(UptimeRecord).where(UptimeRecord.checked_at < now - KEEP))

    def recent(self, name, n):
        """The newest n results for one check, newest first: [(checked_at, ok, detail)]."""

        with Session(self.engine) as session:
            return [(r.checked_at, r.ok, r.detail) for r in session.scalars(
                select(UptimeRecord).where(UptimeRecord.name == name)
                .order_by(UptimeRecord.checked_at.desc(), UptimeRecord.id.desc()).limit(n))]

    def latest(self, name):
        """(checked_at, ok, ms) of the newest result for one check, or None."""

        with Session(self.engine) as session:
            row = session.scalars(select(UptimeRecord).where(UptimeRecord.name == name)
                                  .order_by(UptimeRecord.checked_at.desc()).limit(1)).first()
            return (row.checked_at, row.ok, row.ms) if row else None

    def history(self, name, since):
        """[(checked_at, ok)] for one check since `since`, oldest first."""

        with Session(self.engine) as session:
            return [(r.checked_at, r.ok) for r in session.scalars(
                select(UptimeRecord).where(UptimeRecord.name == name, UptimeRecord.checked_at >= since)
                .order_by(UptimeRecord.checked_at))]

    def outage_start(self, name, before):
        """When the failures that ended just now began: the first failure after the last success before `before`."""

        with Session(self.engine) as session:
            where = (UptimeRecord.name == name, UptimeRecord.checked_at < before)
            good = session.scalar(select(func.max(UptimeRecord.checked_at)).where(*where, UptimeRecord.ok.is_(True)))
            return session.scalar(select(func.min(UptimeRecord.checked_at)).where(
                *where, UptimeRecord.ok.is_(False), *([UptimeRecord.checked_at > good] if good else [])))

    def summary(self, names, now):
        """{name: {"last": (at, ok, ms, detail) | None, "uptime": {window: % or None}, "points": [(ok, ms)] 24 h,
        "last_failure": (at, detail) | None}}"""

        out = {}
        with Session(self.engine) as session:
            for name in names:
                where = UptimeRecord.name == name
                uptime = {}
                for label, span in WINDOWS:
                    total, good = session.execute(select(func.count(), func.sum(UptimeRecord.ok.cast(Integer)))
                                                  .where(where, UptimeRecord.checked_at >= now - span)).one()
                    uptime[label] = round(100 * (good or 0) / total, 2) if total else None
                rows = session.scalars(select(UptimeRecord).where(where, UptimeRecord.checked_at >= now - WINDOWS[0][1])
                                       .order_by(UptimeRecord.checked_at)).all()
                failure = session.scalars(select(UptimeRecord).where(where, UptimeRecord.ok.is_(False))
                                          .order_by(UptimeRecord.checked_at.desc()).limit(1)).first()
                out[name] = {"last": (rows[-1].checked_at, rows[-1].ok, rows[-1].ms, rows[-1].detail) if rows else None,
                             "uptime": uptime, "points": [(row.ok, row.ms) for row in rows],
                             "last_failure": (failure.checked_at, failure.detail) if failure else None}

        return out


def _down(store, name, fail_after):

    rows = store.recent(name, fail_after)
    return len(rows) == fail_after and not any(ok for _, ok, _ in rows)


def _minutes(span):

    minutes = max(1, round(span.total_seconds() / 60))
    return f"{minutes} min" if minutes < 120 else f"{minutes // 60} h {minutes % 60} min"


def run(settings, store, now, *, check=probe, send=None):
    """One pass over every check. Returns {name: (ok, ms, detail)}."""

    from lanxang import notify
    from lanxang.alerts import allowed, issue, report

    checks, fail_after = settings.uptime.checks, max(1, settings.uptime.fail_after)
    if not checks:
        report("uptime", [], now, store)
        return {}
    was_down = {c.name: _down(store, c.name, fail_after) for c in checks}
    with ThreadPoolExecutor(max_workers=min(16, len(checks))) as pool:      # a slow check never holds up the rest
        results = dict(zip([c.name for c in checks], pool.map(lambda c: check(c.target, c.timeout), checks)))
    store.save(results, now)

    found, texts = [], []
    for c in checks:
        down = _down(store, c.name, fail_after)
        detail = results[c.name][2]
        if down:
            found.append(issue("down", c.name, f"{c.name} is down", f"{c.target}: {detail}", href="/uptime"))
        if down and not was_down[c.name]:
            texts.append(Text(f"**🔴 {c.name} is down**\n• {c.target}\n• {detail}\n\nSee Lanxang → Servers → Uptime.",
                              f"uptime:down:{c.name}"))
        elif was_down[c.name] and not down:
            since = store.outage_start(c.name, now)
            texts.append(Text(f"**✅ {c.name} is back up**\n• {c.target}"
                              + (f"\n• down for about {_minutes(now - since)}" if since else ""), f"uptime:down:{c.name}"))
    report("uptime", found, now, store)

    for text in texts:
        if allowed(store, text, now):
            if send:
                send(text)
            elif notify.configured(settings.notify):
                notify.send(settings.notify, text)

    return results
