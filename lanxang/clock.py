"""atlas keeps times as naive UTC (the database columns, every comparison). datetime.utcnow() did exactly that but
is deprecated and going away; this is the same value without the warning.

The rest turns a stored time into words for people, following the display: settings (clock, time zone, date
format) - the same ones the pages' time script uses. Server-side text has no viewer, so time_zone "browser" means UTC
here, and says so."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


DATES = {"iso": "{y:04d}-{m:02d}-{d:02d}", "dmy": "{d:02d}/{m:02d}/{y:04d}", "mdy": "{m:02d}/{d:02d}/{y:04d}"}


def _display(display):

    if display is None:
        from lanxang.config.models import DisplayConfig
        return DisplayConfig()
    return display


def local(moment, display=None):
    """A naive-UTC time (or an aware one) in the display's zone: (aware datetime, zone label like 'UTC' or 'EST')."""

    display = _display(display)
    aware = moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment
    if display.time_zone in ("browser", "UTC"):
        return aware.astimezone(timezone.utc), "UTC"
    here = aware.astimezone(ZoneInfo(display.time_zone))
    return here, here.tzname() or display.time_zone


def hhmm(moment, display=None):
    """The clock part only, of an already-local time: '14:32' or '2:32 PM'."""

    if _display(display).clock == "12h":
        return f"{moment.hour % 12 or 12}:{moment.minute:02d} {'AM' if moment.hour < 12 else 'PM'}"
    return f"{moment:%H:%M}"


def day(moment, display=None):
    """The date part only, of an already-local time: '2026-11-19', '19/11/2026' or '11/19/2026'."""

    return DATES[_display(display).date_format].format(y=moment.year, m=moment.month, d=moment.day)


def stamp(moment, display=None, date=True):
    """One time for a message: '2026-11-19 14:32 UTC', '11/19/2026 2:32 PM EST'; date=False: '2:32 PM EST'."""

    here, zone = local(moment, display)
    return (f"{day(here, display)} " if date else "") + f"{hhmm(here, display)} {zone}"


def parse(value):
    """Stored ISO text (or a datetime) as naive UTC; None when empty or unreadable."""

    try:
        moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment.astimezone(timezone.utc).replace(tzinfo=None) if moment.tzinfo else moment
