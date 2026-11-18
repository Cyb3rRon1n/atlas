"""
"What changed" at the top of Activity: the last 24 hours (or 7 days) in plain words, newest first - problems that
started or cleared, one-off findings (a new open port, a certificate), new devices, Proxmox guests added, removed
or stopped, and container limits crossed. Built from what atlas already saved; nothing is measured here.
"""

import json
from datetime import timedelta

from lanxang.web.render import _esc

WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7)}
CHANGE_EVENTS = ("lanxang.proxmox.changes_detected", "lanxang.monitoring.changes_detected")


def collect(now, window, sources):
    """[(at, mark, text, href)] newest first. sources: {"alerts": f(now, days), "devices": f(),
    "changes": f(since) -> [(at, event type, payload)] of the change events}."""

    since = now - WINDOWS[window]
    found = []

    def safely(read, *args):
        try:
            return read(*args)
        except Exception:
            return None

    listing = safely(sources["alerts"], now, 7) or {}
    for row in (listing.get("open") or []) + (listing.get("watch") or []) + (listing.get("resolved") or []):
        if row["opened_at"] >= since:
            mark = "⚠️" if row["level"] == "problem" else "🔎" if row.get("event") else "👀"
            text = row["title"] + (f" - {row['detail']}" if row.get("detail") else "")
            found.append((row["opened_at"], mark, text, row.get("href") or "/alerts"))
        if row.get("resolved_at") and row["resolved_at"] >= since and not row.get("event"):
            found.append((row["resolved_at"], "✅", f"Cleared: {row['title']}", "/alerts"))

    for device in safely(sources["devices"]) or []:
        seen = [s["first_seen"] for s in device.get("sightings") or [] if s.get("first_seen")]
        first = min(seen) if seen else None
        if first and first >= since.isoformat():
            where = f" ({device['ip']})" if device.get("ip") and device["ip"] != device["name"] else ""
            found.append((_parse(first), "📱", f"New device: {device['name']}{where}", "/devices"))

    from lanxang.monitoring.changes import format_change as container_change
    from lanxang.proxmox.changes import format_change as proxmox_change
    shown = set()
    for at, event_type, payload in sorted(safely(sources["changes"], since) or [], key=lambda item: item[0]):
        key = (event_type, json.dumps(payload, sort_keys=True))
        if key in shown:                                 # the same list again (before the fix, every Proxmox scan
            continue                                     # said the whole cluster was added): once is enough
        shown.add(key)
        proxmox = event_type.startswith("lanxang.proxmox")
        for change in ((payload or {}).get("changes") or [])[:20]:
            text = (proxmox_change if proxmox else container_change)(change).lstrip("!✓?+-~ ").strip()
            found.append((at, "🖥️" if proxmox else "📦", text, "/overview"))

    return sorted(found, key=lambda item: item[0], reverse=True)


def _parse(text):

    from datetime import datetime
    return datetime.fromisoformat(str(text).replace("Z", "")[:19])


def render(items, now, window):
    """The section's HTML: a 24 h / 7 days switch and one line per change."""

    def when(at):
        return at.strftime("%H:%M") if at.date() == now.date() else at.strftime("%a %d %b %H:%M")

    current = ' aria-current="page"'
    switch = "".join(f'<a href="/history?changes={key}"{current if key == window else ""}>{label}</a>'
                     for key, label in (("24h", "Last 24 hours"), ("7d", "Last 7 days")))
    rows = "".join(f'<li><span class="time">{_esc(when(at))}</span><span>{mark}</span>'
                   f'<a href="{_esc(href)}">{_esc(text)}</a></li>' for at, mark, text, href in items[:60])
    more = f'<p class="muted">and {len(items) - 60} more</p>' if len(items) > 60 else ""
    return (STYLE + f'<section class="changes"><h2>What changed <span class="switch">{switch}</span></h2>'
            + (f"<ul>{rows}</ul>{more}" if rows else '<p class="muted">Nothing changed - all quiet.</p>')
            + "<p class=\"muted\">Times are UTC. Everything atlas recorded is below.</p></section>")


STYLE = """<style>
.changes { margin:0 0 1.4rem; } .changes h2 { display:flex; gap:12px; align-items:baseline; flex-wrap:wrap; }
.changes .switch { font-size:13px; font-weight:400; display:inline-flex; gap:10px; }
.changes .switch a[aria-current] { font-weight:600; text-decoration:none; color:inherit; }
.changes ul { list-style:none; padding:0; margin:.4rem 0; }
.changes li { display:flex; gap:10px; padding:5px 0; border-bottom:1px solid var(--line); align-items:baseline; }
.changes .time { color:var(--muted); font-size:13px; min-width:9.5em; font-variant-numeric:tabular-nums; }
.changes li a { color:inherit; text-decoration:none; } .changes li a:hover { text-decoration:underline; }
</style>"""
