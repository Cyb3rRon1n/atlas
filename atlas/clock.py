"""atlas keeps times as naive UTC (the database columns, every comparison). datetime.utcnow() did exactly that but
is deprecated and going away; this is the same value without the warning."""

from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)
