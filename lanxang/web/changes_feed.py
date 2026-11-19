"""
"What changed" at the top of Activity: the last 24 hours (or 7 days) in plain words, newest first: problems that
started or cleared, one-off findings (a new open port, a certificate), new devices, Proxmox guests added, removed
or stopped, and container limits crossed. Built from what atlas already saved; nothing is measured here.
"""

import json
from datetime import timedelta

from lanxang.web.icons import icon
from lanxang.web.render import _esc, event_label, segmented, when

WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7)}
CHANGE_EVENTS = ("atlas.proxmox.changes_detected", "atlas.monitoring.changes_detected")


def collect(now, window, sources):
    """[(at, mark, text, href)] newest first; mark is an icons.py name ("device" for a new device). sources: {"alerts": f(now, days), "devices": f(),
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
            mark = "alert" if row["level"] == "problem" else "search" if row.get("event") else "info"
            text = row["title"] + (f" — {row['detail']}" if row.get("detail") else "")
            found.append((row["opened_at"], mark, text, row.get("href") or "/alerts"))
        if row.get("resolved_at") and row["resolved_at"] >= since and not row.get("event"):
            found.append((row["resolved_at"], "check", f"Cleared: {row['title']}", "/alerts"))

    for device in safely(sources["devices"]) or []:
        seen = [s["first_seen"] for s in device.get("sightings") or [] if s.get("first_seen")]
        first = min(seen) if seen else None
        if first and first >= since.isoformat():
            where = f" ({device['ip']})" if device.get("ip") and device["ip"] != device["name"] else ""
            found.append((_parse(first), "device", f"New device: {device['name']}{where}", "/devices"))

    from lanxang.monitoring.changes import format_change as container_change
    from lanxang.proxmox.changes import format_change as proxmox_change
    shown = set()
    for at, event_type, payload in sorted(safely(sources["changes"], since) or [], key=lambda item: item[0]):
        key = (event_type, json.dumps(payload, sort_keys=True))
        if key in shown:                                 # the same list again (before the fix, every Proxmox scan
            continue                                     # said the whole cluster was added): once is enough
        shown.add(key)
        proxmox = event_type.startswith("atlas.proxmox")
        changes = payload.get("changes") if isinstance(payload, dict) else None
        for change in (changes if isinstance(changes, list) else [])[:20]:
            try:
                text = (proxmox_change if proxmox else container_change)(change)
            except Exception:                            # one odd row (a bare string, a missing key) never blanks
                text = change if isinstance(change, str) else event_label(event_type)    # the page
            if text:
                found.append((at, "server" if proxmox else "box", text.lstrip("!✓?+-~ ").strip(), "/overview"))

    return sorted(found, key=lambda item: item[0], reverse=True)


def _parse(text):

    from datetime import datetime
    return datetime.fromisoformat(str(text).replace("Z", "")[:19])


def group(items):
    """Back-to-back new devices fold into one entry: [(at, mark, text, href, [(at, text, href)...] or None)]."""

    rows = []
    for at, mark, text, href in items:
        if mark == "device" and rows and rows[-1][1] == "device":
            rows[-1][4].append((at, text, href))
        else:
            rows.append((at, mark, text, href, [(at, text, href)] if mark == "device" else None))
    return rows


def render(items, now, window):
    """The section's HTML: a 24 h / 7 days switch and one line per change (a run of new devices is one line)."""

    switch = segmented(WINDOWS, window, "/history?changes={key}")
    lines = []
    for at, mark, text, href, members in group(items):
        mark = icon("laptop" if mark == "device" else mark)
        if members and len(members) > 1:
            listed = "".join(f'<li><a href="{_esc(h)}">{_esc(t.removeprefix("New device: "))}</a></li>' for _, t, h in members)
            line = f'<details><summary>{len(members)} new devices</summary><ul class="group">{listed}</ul></details>'
        else:
            line = f'<a href="{_esc(href)}">{_esc(text)}</a>'
        lines.append(f'<li><span class="time">{when(at, now)}</span><span class="mark">{mark}</span>{line}</li>')
    rows = "".join(lines[:60])
    more = f'<p class="muted">and {len(lines) - 60} more</p>' if len(lines) > 60 else ""
    return (STYLE + f'<section class="changes"><div class="changes-head"><h2>What changed</h2>{switch}</div>'
            + (f"<ul>{rows}</ul>{more}" if rows else '<p class="muted">Nothing changed — all quiet.</p>')
            + f'<p class="muted">Times are {_esc(_zone())}. Everything Lanxang recorded is below.</p></section>')


def _zone():

    from lanxang.web import render

    zone = render.DISPLAY.time_zone if render.DISPLAY else "browser"
    return "in your local time" if zone == "browser" else f"in {zone}"


STYLE = """<style>
.changes { margin:0 0 1.4rem; }
.changes-head { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin:.8rem 0 .4rem; padding-bottom:.3rem;
                border-bottom:1px solid var(--line); } .changes-head h2 { margin:0; padding:0; border:0; }
.changes ul { list-style:none; padding:0; margin:.4rem 0; }
.changes li { display:flex; gap:10px; padding:5px 0; border-bottom:1px solid var(--line); align-items:baseline; }
.changes .time { color:var(--muted); font-size:.8125rem; flex:none; width:8.5em; font-variant-numeric:tabular-nums; }
.changes .mark { flex:none; } .changes .mark .ic { margin:0; }
.changes details > summary { cursor:pointer; } .changes ul.group { margin:.3rem 0 0; }
.changes ul.group li { border:0; padding:2px 0; }
.changes li a { color:inherit; text-decoration:none; } .changes li a:hover { text-decoration:underline; }
</style>"""
