"""
Quiet hours: a weekly schedule when no alert messages go out (the Sunday update window, the night). Problems still
show on the Alerts page; only the messages are held, the same as Pause. Times are in notify.timezone (an IANA name
like America/Detroit; UTC when empty or unknown). A window that ends before it starts runs over midnight and
belongs to the day it starts.
"""

from datetime import timedelta, timezone

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def minutes(hhmm):
    """"06:30" -> 390, or ValueError."""

    hours, _, mins = str(hhmm).partition(":")
    value = int(hours) * 60 + int(mins)
    if not (0 <= int(hours) < 24 and 0 <= int(mins) < 60):
        raise ValueError(hhmm)
    return value


def local(now, tz):

    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        zone = ZoneInfo(tz) if tz else timezone.utc
    except (ZoneInfoNotFoundError, ValueError):
        zone = timezone.utc
    return now.replace(tzinfo=timezone.utc).astimezone(zone)


def active(windows, tz, now):
    """The window (start, end, days) covering now (naive UTC), or None."""

    here = local(now, tz)
    at = here.hour * 60 + here.minute
    today, yesterday = DAYS[here.weekday()], DAYS[(here - timedelta(days=1)).weekday()]
    for window in windows:
        start, end = minutes(window.start), minutes(window.end)
        days = window.days or DAYS
        if start < end and start <= at < end and today in days:
            return window
        if start >= end and ((at >= start and today in days) or (at < end and yesterday in days)):
            return window
    return None


def describe(window):

    days = window.days or DAYS
    named = "every day" if set(days) == set(DAYS) else ", ".join(d.capitalize() for d in DAYS if d in days)
    return f"{named} {window.start}-{window.end}"
