"""
The weekly summary: one message on Sunday evening (notify.timezone) with how the week went - internet outages,
service uptime, new devices, open alerts, heartbeats, disks. Sent from `lanxang scan` once its time has come, so it
also tells you atlas itself is alive. Off with notify.weekly_summary: false. Quiet hours hold it like any alert.
"""

from datetime import timedelta

from lanxang.alerts import Text
from lanxang.clock import utcnow

SEND_AT_HOUR = 18                     # Sunday, local time


def due(now, tz, last_sent):
    """True from Sunday 18:00 local until it has gone out (at most once in 6 days)."""

    from datetime import datetime

    from lanxang.alerts.quiet import local

    here = local(now, tz)
    if here.weekday() != 6 or here.hour < SEND_AT_HOUR:
        return False
    return not last_sent or now - datetime.fromisoformat(last_sent) >= timedelta(days=6)


def _minutes(total):
    return f"{total} min" if total < 120 else f"{total // 60} h {total % 60} min"


def build(settings, now, sources):
    """The message text. sources: {"uptime_summary", "internet_rows", "devices", "alerts", "statuses", "disks"}."""

    from lanxang.monitoring import internet
    from lanxang.monitoring.disks import problems

    week = now - timedelta(days=7)
    lines = []

    def safely(read, *args):
        try:
            return read(*args)
        except Exception:
            return None

    if settings.internet.enabled:
        rows = safely(sources["internet_rows"], week)
        if rows:
            found = internet.outages(rows, max(1, settings.uptime.fail_after))
            total = sum(round(((end or now) - start).total_seconds() / 60) for start, end, _ in found)
            lines.append("🌐 Internet: no outages" if not found else
                         f"🌐 Internet: {len(found)} outage{'s' if len(found) != 1 else ''}, {_minutes(total)} in all")

    checks = [c.name for c in settings.uptime.checks]
    summary = safely(sources["uptime_summary"], checks) or {}
    week_pct = {name: (info.get("uptime") or {}).get("7 days") for name, info in summary.items()}
    week_pct = {name: pct for name, pct in week_pct.items() if pct is not None}
    if week_pct:
        below = [f"{name} {pct:g}%" for name, pct in sorted(week_pct.items(), key=lambda item: item[1]) if pct < 100]
        lines.append(f"🖥️ Services: all {len(week_pct)} up the whole week" if not below else
                     f"🖥️ Services: {len(week_pct) - len(below)} of {len(week_pct)} up all week; " + ", ".join(below[:4]))

    devices = safely(sources["devices"])
    if devices:
        def first(device):
            return min((s["first_seen"] for s in device.get("sightings") or [] if s.get("first_seen")), default="")
        new = [d for d in devices if first(d) >= week.isoformat()]
        waiting = sum(d.get("state") == "new" for d in devices)
        text = f"📱 Devices: {len(devices)}"
        if new:
            text += f", {len(new)} new this week ({', '.join(d['name'] for d in new[:3])}{'...' if len(new) > 3 else ''})"
        if waiting:
            text += f"; {waiting} waiting for you to name or ignore"
        lines.append(text)

    alerts = safely(sources["alerts"])
    if alerts is not None:
        bad = [a for a in alerts if a.get("level") == "problem"]
        lines.append("✅ Alerts: nothing open" if not alerts else
                     f"🔔 Alerts: {len(bad)} problem{'s' if len(bad) != 1 else ''} open"
                     + (f" ({', '.join(a['title'] for a in bad[:2])})" if bad else "")
                     + (f", {len(alerts) - len(bad)} to watch" if len(alerts) > len(bad) else ""))

    statuses = safely(sources["statuses"]) or {}
    beats = ((statuses.get("heartbeats") or {}).get("detail")) or {}
    judged = {name: b["state"] for name, b in beats.items() if b.get("state") in ("ok", "late", "failed")}
    if judged:
        late = [name for name, state in judged.items() if state != "ok"]
        lines.append(f"💾 Heartbeats: all {len(judged)} on time" if not late else
                     f"💾 Heartbeats: {len(judged) - len(late)} of {len(judged)} on time; not: {', '.join(late)}")

    disks = [d for _, group in (safely(sources["disks"], statuses) or []) for d in group]
    if disks:
        flagged = [d for d in disks if problems(d, settings.health, was_hot=True)]
        temps = [d["temp"] for d in disks if d.get("temp") is not None]
        lines.append(f"💽 Disks: {len(disks)}, " + (f"{len(flagged)} need a look" if flagged else "all healthy")
                     + (f", warmest {max(temps)}°C" if temps else ""))

    home = ((statuses.get("homeassistant") or {}).get("detail")) or {}
    if home and settings.homeassistant.enabled:
        info = home.get("info") or {}
        lost, low, waiting = info.get("offline") or [], info.get("batteries") or [], info.get("updates") or []
        parts = ([f"{len(lost)} device{'s' if len(lost) != 1 else ''} offline ({', '.join(d['name'] for d in lost[:3])})"]
                 if lost else []) + ([f"{len(low)} low batter{'ies' if len(low) != 1 else 'y'}"] if low else []) \
            + ([f"{len(waiting)} update{'s' if len(waiting) != 1 else ''} waiting"] if waiting else [])
        lines.append("🏠 Smart home: " + ("not answering" if home.get("failures", 0) >= 2 else
                                          ", ".join(parts) or "every device answering"))

    upses = (((statuses.get("ups") or {}).get("detail")) or {}).get("upses") or {}
    for name, ups in list(upses.items())[:2]:
        charge = f", {ups['charge']:.0f}% charged" if ups.get("charge") is not None else ""
        lines.append(f"🔋 UPS {name}: {ups.get('state', '?')}{charge}")

    from lanxang.clock import day, local, stamp

    span = (f"{day(local(week, settings.display)[0], settings.display)} to "
            f"{day(local(now, settings.display)[0], settings.display)}, sent {stamp(now, settings.display, date=False)}")
    return f"**📋 Lanxang: your week**\n{span}\n" + "\n".join(f"• {line}" for line in lines or ["nothing to report yet"])


def _sources():

    from lanxang.monitoring import internet
    from lanxang.monitoring.uptime import UptimeStore
    from lanxang.web.metrics import _sources as metric_sources

    base, uptime = metric_sources(), UptimeStore()

    def internet_rows(since):
        router = dict(uptime.history(internet.ROUTER, since))
        return [(at, ok, router.get(at)) for at, ok in uptime.history(internet.INTERNET, since)]

    from datetime import datetime
    return {**base, "uptime_summary": lambda names: uptime.summary(names, utcnow()),
            "internet_rows": internet_rows}


def run(settings, store, now, *, send=None, sources=None):
    """Send the summary when it's due. Returns the text sent, or None."""

    from lanxang import notify
    from lanxang.alerts import allowed

    if not settings.notify.weekly_summary:
        return None
    last = (((store.statuses().get("summary") or {}).get("detail")) or {}).get("sent_at")
    if not due(now, settings.notify.timezone, last):
        return None
    text = Text(build(settings, now, sources or _sources()), "summary:weekly")
    if not allowed(store, text, now):
        return None                                    # quiet hours or paused: tried again on the next scan
    if send:
        send(text)
    elif notify.configured(settings.notify):
        notify.send(settings.notify, text)
    else:
        return None
    store.set_status("summary", True, {"sent_at": now.isoformat(timespec="seconds")}, now)
    return text
