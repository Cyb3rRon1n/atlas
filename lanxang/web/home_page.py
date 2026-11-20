"""
/ - the home briefing, top to bottom: a status line, the problems (only when there are any), the getting-started
steps, what changed since your last visit beside the Ask Lanxang chips, the vitals with a week of history, then the
detail cards, each linking to its tab. Problems before news, news before numbers, numbers before detail. Pure
renderers; server.py gathers the data and passes None for any source that failed, which renders as a muted
"unavailable" line (or leaves the part out) instead of a 500.
"""

import re
from datetime import date, timedelta

from lanxang import clock
from lanxang.health.alerts import container_problem, container_state
from lanxang.web.blocks import bar_chart, check_row, day_strip, status_hero, timeline, trend_tile
from lanxang.web.render import _esc, ask_chips, empty_state, event_label, friendly_time, plural, render_page, when
from lanxang.clock import utcnow


HOME_STYLE = """
<style>
.panel { margin:0 0 16px; padding:12px 16px; border:1px solid var(--line); border-radius:12px; background:var(--surface); }
.panel h2 { margin:0 0 6px; font-size:.9375rem; font-weight:600; border:0; padding:0; }
.panel h2 .muted { font-weight:400; font-size:.8125rem; }
.problems { padding:4px 16px; border-color:var(--warn-line); }
.brief { display:grid; grid-template-columns:minmax(0,3fr) minmax(0,2fr); gap:16px; align-items:start; margin:0 0 16px; }
.brief > .panel { margin:0; } .brief > :only-child { grid-column:1 / -1; }
.brief .chips { margin:0; } .since .more { margin:8px 0 0; font-size:.8125rem; }
.vitals { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:0 0 16px; }
@media (max-width: 700px) { .brief { grid-template-columns:minmax(0,1fr); } .vitals { grid-template-columns:repeat(2,minmax(0,1fr)); } }
.cards { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; align-items:start; }
.cards a.hcard.wide { grid-column:span 2; grid-row:span 2; align-self:stretch; display:flex; flex-direction:column; }
.hcard .summary { font-size:.875rem; line-height:1.45; margin:6px 0 10px; }
@media (max-width: 1100px) { .cards { grid-template-columns:repeat(2,minmax(0,1fr)); } .cards a.hcard.wide { grid-row:auto; } }
@media (max-width: 700px) { .cards { grid-template-columns:1fr; } .cards a.hcard.wide { grid-column:auto; } }
.cards a.hcard.flagged { box-shadow:0 0 0 2px var(--gold); }
.cards a.hcard.flagged.warn { box-shadow:0 0 0 2px var(--red); }
.hcard .tag { margin-left:auto; font-size:.6875rem; font-weight:500; text-transform:uppercase; letter-spacing:.05em; color:var(--warn-text); }
.cards a.hcard { display:block; color:var(--text); text-decoration:none; background:var(--surface);
                 border:1px solid var(--line); border-radius:10px; padding:16px; }
.cards a.hcard:hover { border-color:var(--blue); }
.hcard h2 { margin:0 0 10px; font-size:.9375rem; border:0; padding:0; display:flex; gap:8px; align-items:center; }
.hcard.warn { border-color:var(--red); } .hcard.review { border-color:var(--orange); }
.dot { width:9px; height:9px; border-radius:50%; background:var(--muted); display:inline-block; }
.dot.ok { background:var(--green); } .dot.warn { background:var(--red); } .dot.review { background:var(--orange); }
.hcard dl { display:grid; grid-template-columns:auto 1fr; gap:4px 12px; margin:8px 0 0; font-size:.875rem; }
.hcard dt { color:var(--muted); }
.hcard .host { padding:8px 0; border-top:1px solid var(--line); font-size:.875rem; }
.hcard .host .m { white-space:nowrap; }
.hcard .host:first-of-type { border-top:0; }
.hcard .bad { color:var(--bad-text); font-size:.8125rem; }
.hcard ul { list-style:none; margin:0; padding:0; font-size:.8125rem; }
.hcard li { padding:4px 0; border-top:1px solid var(--line); }
.hcard li:first-child { border-top:0; }
.hcard .row { display:flex; justify-content:space-between; gap:8px; padding:5px 0; border-top:1px solid var(--line); font-size:.875rem; }
.hcard .row:first-of-type { border-top:0; }
.hcard .row.warn span:last-child { color:var(--bad-text); }
.chart { margin:4px 0 12px; } .chart h3 { margin:0 0 4px; font-size:.75rem; font-weight:500; color:var(--muted); }
.chart .lbl { font-size:.75rem; margin-top:4px; }
.sev-high, .sev-critical { color:var(--bad-text); } .sev-medium { color:var(--warn-text); }
</style>
"""


def _pct(used, total):

    return round(used / total * 100) if used is not None and total else None


def build_hosts(topology, local_health, pve_scan, host_issues=None):
    """
    Rows for the hosts card: the host Lanxang runs on (live psutil numbers from
    get_host_health() + containers from the latest topology) and each Proxmox
    node from the latest scan event (guests from the topology).
    """

    topology = topology or {}
    rows = []

    if local_health or topology.get("docker"):
        health = local_health or {}
        containers = [c for members in ((topology.get("docker") or {}).get("networks") or {}).values()
                      for c in members]
        load, cpus = (health.get("load_average") or [None])[0], health.get("cpu_count")
        rows.append({
            "name": topology.get("host") or "this host",
            "cpu": min(100, round(load / cpus * 100)) if load is not None and cpus else None,
            "mem": round(health["memory_percent"]) if "memory_percent" in health else None,
            "disk": round(health["root_disk_percent"]) if "root_disk_percent" in health else None,
            "detail": (f"{sum(c['status'] == 'running' for c in containers)}/{len(containers)} containers running"
                       if containers else ""),
            # stopped cleanly (a game room the idle timer put to sleep) is normal: listed apart, never a problem
            "asleep": [c["name"] for c in containers if container_state(c) == "asleep"],
            "problems": [p for p in map(container_problem, containers) if p]
                        + [i["detail"] for i in host_issues or [] if i["kind"] != "container"],
        })

    guests = [g for g in (topology.get("proxmox") or {}).get("guests", []) if not g.get("template")]

    nodes = (pve_scan or {}).get("nodes", [])
    pve_address = (topology.get("proxmox") or {}).get("host")
    lan_name = next((h["name"] for h in topology.get("lan", []) if pve_address and h.get("address") == pve_address), None)

    for node in nodes:
        online = node.get("status") == "online"
        rows.append({
            # A single-node install is the LAN host at the configured Proxmox address - show the name people use.
            "name": lan_name if lan_name and len(nodes) == 1 else node["name"],
            "cpu": round(node["cpu"] * 100) if "cpu" in node else None,
            "mem": _pct(node.get("mem"), node.get("maxmem")),
            "disk": _pct(node.get("disk"), node.get("maxdisk")),
            "detail": (f"{sum(g['status'] == 'running' for g in guests)}/{len(guests)} guests running"
                       if guests else ""),
            "problems": ([] if online else [f"node {node.get('status')}"])
                        + [f"{g['name']} stopped" for g in guests if g["status"] != "running"],
        })

    down = [h["name"] for h in topology.get("lan", []) if not h.get("reachable")]
    # Unreachable LAN devices are listed but don't flip the card: TVs and laptops are off half the time.
    state = "unknown" if not rows else ("warn" if any(r["problems"] for r in rows) else "ok")

    return {"rows": rows, "down": down, "state": state}


ROUTINE_EVENT_SUFFIXES = (".completed", ".loaded")


def interesting_events(events, limit=8):
    """
    Newest-first (event, repeat count) pairs: routine bookkeeping (scan finished,
    plugin loaded) dropped, and repeats of one event type folded into its newest.
    """

    seen = {}

    for event in events:
        if not event.event_type.endswith(ROUTINE_EVENT_SUFFIXES):
            seen.setdefault(event.event_type, [event, 0])[1] += 1

    return [tuple(pair) for pair in list(seen.values())[:limit]]


WARN_PERCENT = 90

ASK_SHORTCUTS = ("What changed today?", "Is anything unhealthy right now?",
                 "Explain the new outbound destinations that need review.", "How is storage looking?")


def _size(n):

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000


def parse_mdstat(text):
    """
    Linux software-RAID arrays from /proc/mdstat: name, level, state, member
    count, failed members, and whether a redundant array is degraded ([UU_]).
    """

    arrays = []

    for block in re.split(r"\n(?=md\d+ :)", text or ""):
        head = re.match(r"(md\d+) : (\S+) (?:\(\S+\) )?(raid\d+|linear)?\s*(.*)", block)
        if not head:
            continue
        members = re.findall(r"\S+\[\d+\](\(F\))?", head.group(4))
        status = re.search(r"\[([U_]+)\]", block)
        arrays.append({"name": head.group(1), "state": head.group(2), "level": head.group(3) or "?",
                       "disks": len(members), "failed": sum(bool(f) for f in members),
                       "degraded": bool(status and "_" in status.group(1))})

    return arrays


def build_storage(arrays, usage, feeds, pve_scan, topology=None, health=None, nas=None):
    """
    Rows for the storage card. arrays: parse_mdstat() output; usage: {label:
    psutil.disk_usage() result} for configured storage_paths; feeds: status
    feeds from get_host_health() (a RAID card watchdog: temp/state/warn);
    pve_scan: the latest Proxmox scan payload (nodes carry storage/zfs).
    """

    rows = []

    for a in arrays:
        bad = a["state"] != "active" or a["degraded"] or a["failed"]
        detail = f"{a['level'].upper()} · {plural(a['disks'], 'disk')} · {a['state']}"
        if a["degraded"] or a["failed"]:
            detail += f" · DEGRADED ({a['failed']} failed)"
        elif a["level"] == "raid0":
            detail += " · no redundancy"
        rows.append({"name": a["name"], "detail": detail, "warn": bad})

    for label, u in (usage or {}).items():
        rows.append({"name": label, "detail": f"{round(u.percent)}% of {_size(u.total)}",
                     "warn": u.percent >= WARN_PERCENT})

    for name, feed in (feeds or {}).items():
        if not isinstance(feed, dict) or "error" in feed:
            rows.append({"name": name.replace("_", " "), "detail": "feed unreachable", "warn": True})
        elif "temp" in feed:
            rows.append({"name": name.replace("_", " "), "detail": f"{feed['temp']}°C · {feed.get('state', '?')}",
                         "warn": feed.get("state") != "ok"})

    lan = {h.get("address"): h["name"] for h in (topology or {}).get("lan", [])}
    pve_host = lan.get(((topology or {}).get("proxmox") or {}).get("host"))
    nodes = (pve_scan or {}).get("nodes", [])

    nas_nodes = [{"name": nas["name"], "zfs": (nas.get("info") or {}).get("pools") or [],
                  "disks": (nas.get("info") or {}).get("disks") or []}] if nas and nas.get("name") else []
    for node in nodes + nas_nodes:
        host = pve_host if pve_host and len(nodes) == 1 and node in nodes else node["name"]
        for pool in node.get("zfs", []):
            pct = round((pool.get("alloc") or 0) / pool["size"] * 100) if pool.get("size") else 0
            size = f" · {pct}% of {_size(pool['size'])}" if pool.get("size") else ""
            rows.append({"name": f"{host} {pool['name']}", "detail": f"{pool['health']}{size}",
                         "warn": pool["health"] not in ("ONLINE", "NORMAL") or pct >= WARN_PERCENT})
        rows.extend(_disk_rows(host, node.get("disks") or [], health))
    if nas and nas.get("error"):
        rows.append({"name": nas.get("name") or "NAS", "detail": "can't read it — see Setup", "warn": True})

    state = "unknown" if not rows else ("warn" if any(r["warn"] for r in rows) else "ok")

    return {"rows": rows, "state": state}


def _disk_rows(host, disks, health=None):
    """One summary row per node's disks, then one row per disk with a problem (SMART, heat, wear)."""

    from lanxang.config.models import HealthConfig
    from lanxang.monitoring.disks import problems

    if not disks:
        return []
    health = health or HealthConfig()
    bad = [(d, problems(d, health, was_hot=True)) for d in disks]
    bad = [(d, found) for d, found in bad if found]
    temps = [d["temp"] for d in disks if d.get("temp") is not None]
    lives = [d["life"] for d in disks if d.get("life") is not None and d.get("type") != "hdd"]
    parts = [f"{len(disks)} disk{'s' if len(disks) != 1 else ''}",
             f"{len(bad)} need{'s' if len(bad) == 1 else ''} a look" if bad else "all healthy"]
    if temps:
        parts.append(f"warmest {max(temps)}°C")
    if lives:
        parts.append(f"lowest life left {min(lives)}%")
    rows = [{"name": f"{host} disks", "detail": " · ".join(parts), "warn": bool(bad)}]
    for disk, found in bad:
        title, detail = next(iter(found.values()))
        rows.append({"name": f"{host} {disk.get('dev') or '?'}", "detail": f"{title} · {detail}", "warn": True})
    return rows


def _trends_card(trends, display=None):

    if not trends:
        return _card("/posture", "Security trends", "unknown", '<p class="muted">Posture data unavailable.</p>',
                     wide=True)

    hours, days = trends["hours"], trends["new_per_day"]
    if not any(h["direct"] or h["vpn"] for h in hours) and not any(d["count"] for d in days):
        # No traffic counted yet: one short explanation instead of an empty two-row chart card.
        return _card("/posture", "Security trends", "unknown", empty_state(
            "shield", "No traffic data yet", "Charts of outbound traffic and new destinations appear here after "
            "the first scans that see traffic leave this host.",
            extra='<span class="btn primary">Open Exposure →</span>'))   # the card is the link: no <a> in <a>

    display = display or home_display()
    moments = [clock.parse(h["hour"]) for h in hours]
    here = [clock.local(m, display)[0] for m in moments]
    # An x label every 6 hours on the viewer's own clock (00:00, 06:00...); a half-hour zone gets every 6th bar.
    ticks = ({i: clock.hhmm(t, display) for i, t in enumerate(here) if t.hour % 6 == 0 and t.minute == 0}
             or {i: clock.hhmm(t, display) for i, t in enumerate(here) if i % 6 == 0})

    # Separate scales: VPN (torrents) is often 100x direct and would flatten it.
    traffic = "".join(
        f'<div class="lbl">{label} <span class="muted">peak {_size(max(h[key] for h in hours))}/h</span></div>'
        + bar_chart([h[key] for h in hours], [f"{clock.stamp(m, display)} · {label} {_size(h[key])}"
                                              for h, m in zip(hours, moments)],
                    ticks, fmt=_size, height=70, label=f"{label} traffic per hour")
        for key, label in (("direct", "Direct"), ("vpn", "Via VPN")))

    dates = [date.fromisoformat(str(d["day"])[:10]) for d in days]      # display-zone days (build_trends(display))
    new = bar_chart([d["count"] for d in days], [f"{clock.day(x, display)}: {d['count']} new" for x, d in zip(dates, days)],
                    {i: f"{x:%a}" for i, x in enumerate(dates)}, fmt=lambda v: f"{v:g}", height=110,
                    label="New destinations per day")
    total_new = sum(d["count"] for d in days)
    inner = (
        '<div class="chart"><h3>Outbound traffic per hour, last 24 h</h3>' + traffic + "</div>"
        + (f'<div class="chart"><h3>New destinations per day, last 7 days ({total_new} total)</h3>{new}</div>'
           if total_new else '<p class="muted">No new destinations in the last 7 days.</p>')
    )

    return _card("/posture", "Security trends", "review" if days[-1]["count"] else "ok", inner, wide=True)


def _analysis_card(analysis, now):

    from lanxang.web import render

    if not render.AI_ON:
        return ""

    if not analysis:
        return _card("/overview", "Latest AI check-up", "unknown",
                     '<p class="muted">No check-up yet. The scan service runs one daily once the AI model is reachable.</p>')

    recs = [r if isinstance(r, dict) else {"title": str(r), "severity": ""} for r in analysis.get("recommendations") or []]
    worst = "warn" if any(r.get("severity") in ("high", "critical") for r in recs) else "ok"
    summary = (analysis.get("summary") or "")[:220].rsplit(" ", 1)[0] + "\u2026" if len(analysis.get("summary") or "") > 220 else (analysis.get("summary") or "")
    inner = (f'<p class="muted">{when(analysis.get("created_at"), now)} · {_esc(analysis.get("model"))}</p>'
             f'<p class="summary">{_esc(summary)}</p><ul>'
             + "".join(f'<li><span class="sev-{_esc(r.get("severity"))}">{_esc(r.get("severity") or "")}</span> '
                       f'{_esc(r.get("title"))}</li>' for r in recs[:3]) + "</ul>")

    return _card("/overview", "Latest AI check-up", worst, inner)


def _storage_card(storage, flagged=False):

    if not storage["rows"]:
        return _card("/overview", "Storage & RAID", "unknown", '<p class="muted">No storage data yet.</p>')

    inner = "".join(f'<div class="row{" warn" if r["warn"] else ""}"><span>{_esc(r["name"])}</span>'
                    f'<span class="muted">{_esc(r["detail"])}</span></div>' for r in storage["rows"])

    return _card("/overview", "Storage & RAID", storage["state"], inner, flagged=flagged)


def _card(href, title, state, inner, wide=False, flagged=False):

    if flagged and state == "ok":
        state = "warn"

    classes = f"hcard {state}" + (" wide" if wide else "") + (" flagged" if flagged else "")
    tag = '<span class="tag">needs attention</span>' if flagged else ""

    return (f'<a class="{classes}" href="{href}"><h2><span class="dot {state}"></span>{_esc(title)}{tag}</h2>'
            f"{inner}</a>")


STORAGE_SOURCES = {"nas", "nas-disks", "disks"}     # alerts the Storage & RAID card already shows


def attention_items(posture, hosts, storage, access_reviews=(), open_alerts=()):
    """
    One plain-words line per problem behind the verdict: (card, what, why, href, action).
    """

    items = []

    if posture and posture["state"] == "warn":
        items.append(("posture", "Security posture", posture["message"], "/posture", "Open"))

    if posture and posture.get("review_count"):
        n = posture["review_count"]
        items.append(("posture", "Security posture", f"{n} new outbound destination{'s' if n != 1 else ''} need{'' if n != 1 else 's'} review",
                      "/posture#review", "Review"))

    for row in hosts["rows"]:
        if row["problems"]:
            items.append(("hosts", "Hosts", f"{row['name']}: {', '.join(row['problems'][:3])}", "/overview", "Details"))

    covered = {"lan", "host"}        # already listed above through posture / hosts
    if posture and posture.get("internet_unexpected"):
        covered.add("internet_view")
    storage_alerts = [a for a in open_alerts if a["source"] in STORAGE_SOURCES and not a.get("acked_at")]
    for row in storage["rows"]:
        if row["warn"]:
            covered |= STORAGE_SOURCES   # the Storage line says it: one problem, one line
            href = "/alerts" if storage_alerts else "/overview"   # the alert says what to do; a full pool has none
            items.append(("storage", "Storage", f"{row['name']}: {row['detail']}", href, "Details"))

    others = [alert for alert in open_alerts if alert["source"] not in covered and not alert.get("acked_at")]
    if others:
        first = others[0]["title"]
        more = f" and {len(others) - 1} more" if len(others) > 1 else ""
        items.append(("alerts", "Alerts", f"{first}{more}", "/alerts", "Review"))

    for place in access_reviews:
        items.append(("access", "Sign-in", f"{place['user']} signed in from a new place: {place['label']}", "/access", "Review"))

    return items


def _posture_card(posture, flagged=False):

    if not posture:
        return _card("/posture", "Security posture", "unknown", '<p class="muted">Posture data unavailable.</p>')

    internet = posture.get("internet", "")
    rows = (("Status", posture["message"]), ("VPN", posture["vpn"]), ("Public routes", posture["routes"]),
            ("CrowdSec bans", posture["blocked"]), ("Needs review", posture["review_count"])) \
        + ((("Internet", internet),) if internet else ())
    inner = "<dl>" + "".join(f"<dt>{_esc(k)}</dt><dd>{_esc(v)}</dd>" for k, v in rows) + "</dl>"

    return _card("/posture", "Security posture", posture["state"], inner, flagged=flagged)


def _usage(row):

    parts = [f"{label} {row[key]}%" for key, label in (("cpu", "CPU"), ("mem", "RAM"), ("disk", "Disk"))
             if row[key] is not None]

    return " ".join(f'<span class="m">{_esc(part)}</span>' for part in parts)


def _hosts_card(hosts, flagged=False):

    if not hosts["rows"]:
        return _card("/overview", "Host health", "unknown", '<p class="muted">No host data yet.</p>')

    inner = "".join(
        f'<div class="host"><strong>{_esc(row["name"])}</strong> <span class="muted">{_usage(row)}</span>'
        + (f'<br><span class="muted">{_esc(row["detail"])}</span>' if row["detail"] else "")
        + (f'<br><span class="bad">{_esc(", ".join(row["problems"][:4]))}</span>' if row["problems"] else "")
        + (f'<br><span class="muted">Asleep: {_esc(", ".join(row["asleep"]))}</span>' if row.get("asleep") else "")
        + "</div>"
        for row in hosts["rows"]
    )

    if hosts["down"]:
        inner += f'<p class="muted">Unreachable: {_esc(", ".join(hosts["down"]))}</p>'

    return _card("/overview", "Host health", hosts["state"], inner, flagged=flagged)


def _activity_card(events):

    if not events:
        return _card("/history", "Recent activity", "unknown", '<p class="muted">No events yet.</p>')

    inner = "<ul>" + "".join(
        f'<li><span class="muted">{when(e.created_at)}</span> {_esc(event_label(e.event_type))}'
        + (f' <span class="muted">&times;{count}</span>' if count > 1 else "")
        + f' <span class="muted">({_esc(e.source)})</span></li>'
        for e, count in events
    ) + "</ul>"

    return _card("/history", "Recent activity", "ok", inner)


def setup_steps(config, devices):
    """The first-steps checklist: (title, why, href, done, optional) per step."""

    alerts, wiring = config.notify, config.wiring
    new = sum(device["state"] == "new" for device in devices)
    has_alerts = bool(alerts.signal.url or (alerts.ntfy.url and alerts.ntfy.topic) or alerts.webhooks
                      or (alerts.email.host and alerts.email.to) or alerts.apprise)

    return [
        ("Name your devices", f"{new} device{'s' * (new != 1)} still marked new — name them, or mark them known"
         if new else "Lanxang hasn't found any devices yet — the first scan runs within a few minutes",
         "/devices", bool(devices) and not new, False),
        ("Turn on alerts", "Get a message when something new joins, a port opens or a cable goes bad",
         "/settings#ntfy", has_alerts, False),
        ("Map your cabling", "Add a managed switch or a UniFi console to see every port",
         "/settings#switches", wiring.enabled and bool(wiring.switches or wiring.unifi.enabled), True),
        ("Connect Proxmox", "See your VMs and containers under their host", "/settings#proxmox",
         config.proxmox.enabled, True),
    ]


STEP_ICONS = {"/devices": "laptop", "/settings#ntfy": "alert", "/settings#switches": "network",
              "/settings#proxmox": "server"}


def _checklist(steps):
    """Shown until every required step is done; optional ones ride along."""

    if not steps or all(done for *_, done, optional in steps if not optional):
        return ""

    rows = "".join(
        check_row(STEP_ICONS.get(href, "info"), title + (" (optional)" if optional else ""), "" if done else why,
                  None if done else ("Set up", href), "done" if done else "todo")
        for title, why, href, done, optional in steps)

    return f'<section class="panel steps" aria-label="Getting started"><h2>Getting started</h2>{rows}</section>'


def home_display(viewer_zone=None):
    """The display settings Home's server-side times use: render.DISPLAY, with "browser" made the zone the viewer's
    browser reported (as Activity does); without one, UTC, which the page's time script then redoes."""

    from lanxang.web import render

    display = clock._display(render.DISPLAY)
    if display.time_zone == "browser" and viewer_zone:
        display = display.model_copy(update={"time_zone": viewer_zone})
    return display


VISIT_GAP = timedelta(minutes=30)       # away this long and the next Home load is a new visit


def since_window(value, now):
    """
    "Since you were here" from the lanxang-seen cookie ("<since>|<last>", UTC minutes): (since, the value to write
    back). Away more than 30 minutes since the last load starts a new visit (since = that last load); a reload
    within a visit keeps since. No cookie, an unreadable one or a time ahead of now means the last 24 hours; never
    more than 7 days back.
    """

    first, _, last = (value or "").partition("|")
    since, last = clock.parse(first), clock.parse(last)

    if since is None or last is None or since > now or last > now:
        since = now - timedelta(hours=24)
    elif now - last > VISIT_GAP:
        since = last
    since = max(since, now - timedelta(days=7))

    return since, f"{since:%Y-%m-%dT%H:%M}|{now:%Y-%m-%dT%H:%M}"


def day_states(histories, fail_after, now, days=7, display=None):
    """
    One "ok" / "bad" / "none" per day in the display zone (display: home_display()), oldest first, ending today, from
    [(checked_at, ok)] lists (one per check): bad when any check failed fail_after times in a row that day; ok only
    when every check has results that day and none had an outage; otherwise none (a silent check is no data).
    """

    first = clock.local(now, display)[0].date() - timedelta(days=days - 1)
    reported, bad = [0] * days, [False] * days

    for rows in histories:
        by_day = {}
        for at, ok in rows:
            index = (clock.local(at, display)[0].date() - first).days
            if 0 <= index < days:
                by_day.setdefault(index, []).append(ok)
        for index, results in by_day.items():
            run = longest = 0
            for ok in results:
                run = 0 if ok else run + 1
                longest = max(longest, run)
            reported[index] += 1
            bad[index] = bad[index] or longest >= max(1, fail_after)

    return ["bad" if bad[i] else "ok" if histories and reported[i] == len(histories) else "none" for i in range(days)]


def storage_trend(scans, samples=(), fresh_after=None):
    """
    The Storage tile: the largest ZFS pool's used % per Proxmox scan ([(at, payload)] oldest first), else the
    fullest storage_paths label per host sample; None when neither has any. {"name", "points", "size", "stale"}:
    stale when the newest reading is older than fresh_after.
    """

    def pools(payload):
        return {pool["name"]: pool for node in (payload or {}).get("nodes") or [] for pool in node.get("zfs") or []
                if pool.get("size")}

    newest = pools(scans[-1][1]) if scans else {}
    if newest:
        name = max(newest, key=lambda n: newest[n]["size"])
        points = [round((found[name].get("alloc") or 0) / found[name]["size"] * 100, 1)
                  for _, payload in scans for found in [pools(payload)] if name in found]
        return {"name": name, "points": points, "size": newest[name]["size"],
                "stale": bool(fresh_after and scans[-1][0] < fresh_after)}

    paths = ((samples[-1][1] or {}).get("storage") or {}) if samples else {}
    if paths:
        name = max(paths, key=paths.get)
        points = [s["storage"][name] for _, s in samples if name in ((s or {}).get("storage") or {})]
        return {"name": name, "points": points, "size": None,
                "stale": bool(fresh_after and samples[-1][0] < fresh_after)}

    return None


def build_vitals(runs, internet, internet_days, uptime_days, storage, posture, ups):
    """
    The vitals row's trend_tile()s: Devices, Internet, Services, Storage, Security, Power; each is left out when its
    data is None. runs: InventoryStore.runs() for 7 days, oldest first; internet: (up, ms) of a recent internet
    check or None; internet_days / uptime_days: day_states(); storage: storage_trend() (plus "warn" when the Storage & RAID card has a problem); posture: _posture_block();
    ups: the UPS watch's saved detail.
    """

    tiles = []

    if runs is not None:
        # The LAN scan's count of devices seen; with no LAN scan, whichever source ran last.
        lan = [r for r in runs if r["source"] == "lan"] or [r for r in runs if r["source"] == runs[-1]["source"]]
        last = lan[-1] if lan else None
        if last and last["ok"]:
            tiles.append(trend_tile("Devices online", last["seen_count"],
                                    points=[r["seen_count"] for r in lan if r["ok"]], href="/devices"))
        else:
            tiles.append(trend_tile("Devices online", "?", state="unknown", href="/devices",
                                    note="last scan failed" if last else "no scan yet"))

    if internet is not None or internet_days is not None:
        strip = day_strip(internet_days) if internet_days else ""
        if internet is None:
            tiles.append(trend_tile("Internet", "?", state="unknown", href="/uptime", note="no recent result",
                                    strip=strip))
        else:
            up, ms = internet
            tiles.append(trend_tile("Internet", "Up" if up else "Down", f"· {ms:.0f} ms" if up and ms is not None else "",
                                    state="ok" if up else "attention", href="/uptime", strip=strip,
                                    note="" if up else "router or provider — see Uptime"))

    if uptime_days is not None:
        bad = uptime_days.count("bad")
        recent = uptime_days[-1] != "none"           # nothing today: stale, never "All up"
        tiles.append(trend_tile("Services, 7 days", plural(bad, "bad day") if bad and recent else
                                "All up" if recent else "No recent data",
                                state="attention" if bad and recent else "ok" if recent else "unknown", href="/uptime",
                                strip=day_strip(uptime_days)))

    if storage and storage["points"]:
        used, stale = storage["points"][-1], storage.get("stale")
        note = storage["name"] + (f" · of {_size(storage['size'])}" if storage.get("size") else "")
        flagged = storage.get("warn") or used >= WARN_PERCENT       # warn: the Storage & RAID card has a problem
        tiles.append(trend_tile("Storage", f"{used:.0f}", "%", points=storage["points"], href="/overview",
                                state="unknown" if stale else "attention" if flagged else "ok",
                                note=note + (" · old reading" if stale else " · see Storage & RAID" if storage.get("warn") else "")))

    if posture:
        state = {"ok": "ok", "warn": "attention", "review": "attention"}.get(posture["state"], "unknown")
        value = {"ok": "All good", "warn": "Problem", "review": "To review"}.get(posture["state"], "No data")
        bans = f" · {plural(int(posture['blocked']), 'ban')}" if str(posture.get("blocked")).isdigit() else ""
        tiles.append(trend_tile("Security", value, state=state, href="/posture",
                                note=plural(posture["routes"], "public route") + bans))

    for name, info in ((ups or {}).get("upses") or {}).items():
        on_battery = info.get("state") in ("battery", "low")
        charge = f"{info['charge']:.0f}% charged" if info.get("charge") is not None else name
        tiles.append(trend_tile("Power", "On battery" if on_battery else "On mains", href="/uptime", note=charge,
                                state="attention" if on_battery else "ok"))
        break

    return tiles


def _dns_card(dns, names):
    """Pi-hole / AdGuard Home: blocking, totals, the devices that ask the most (named from the inventory)."""

    info = (dns or {}).get("info") or {}
    if not info:
        return ""
    state = "ok" if info.get("blocking") and not dns.get("error") else "warn" if not info.get("blocking") else "review"
    rows = [("Ad blocking", "on" if info.get("blocking") else "OFF"),
            ("DNS questions", f'{info["queries"]:,}' if info.get("queries") is not None else "-"),
            ("Blocked", f'{info["blocked"]:,} ({info["percent"]:.1f}%)' if info.get("blocked") is not None
             and info.get("percent") is not None else "-")]
    if info.get("blocklist"):
        rows.append(("Blocklist", f'{info["blocklist"]:,} domains'))
    inner = "<dl>" + "".join(f"<dt>{_esc(k)}</dt><dd>{_esc(v)}</dd>" for k, v in rows) + "</dl>"
    busiest = [(names.get(c["ip"]) or c.get("name") or c["ip"], c["count"]) for c in info.get("clients") or [] if c.get("ip")]
    if busiest:
        inner += ('<p class="muted" style="margin:10px 0 4px">Asks the most</p>'
                  + "".join(f'<div class="row"><span>{_esc(n)}</span><span class="muted">{c:,}</span></div>'
                            for n, c in busiest[:5]))
    if dns.get("error"):
        inner += f'<p class="bad">{_esc(dns["error"])}</p>'
    return f'<div id="dns" style="display:contents">{_card("/settings#dnsfilter", info.get("kind") or "Ad blocking", state, inner)}</div>'


def _ha_card(ha):
    """Home Assistant: version, devices that dropped out, low batteries, updates waiting."""

    info = (ha or {}).get("info") or {}
    if not info and not (ha or {}).get("error"):
        return ""
    offline, batteries, updates = info.get("offline") or [], info.get("batteries") or [], info.get("updates") or []
    state = "warn" if (ha or {}).get("failures", 0) >= 2 or offline else "review" if batteries or updates else "ok"
    rows = "".join(f'<div class="row warn"><span>{_esc(d["name"])}</span><span class="muted">offline '
                   f'{d["hours"]} h</span></div>' for d in offline[:6])
    rows += "".join(f'<div class="row"><span>{_esc(b["name"])}</span><span class="muted">battery '
                    f'{b["level"]}%</span></div>' if b["level"] is not None else
                    f'<div class="row"><span>{_esc(b["name"])}</span><span class="muted">battery low</span></div>'
                    for b in batteries[:6])
    inner = (f'<p class="muted">Home Assistant {_esc(info.get("version") or "")} · {len(offline)} offline · '
             f'{plural(len(batteries), "low battery", "low batteries")}</p>' + (rows or '<p class="muted">Every device is answering.</p>'))
    if updates:
        inner += (f'<p class="muted" style="margin:10px 0 4px">{len(updates)} update{"s" if len(updates) != 1 else ""} '
                  'waiting</p>' + "".join(f'<div class="row"><span>{_esc(u["title"])}</span><span class="muted">'
                                          f'{_esc(u["latest"] or "")}</span></div>' for u in updates[:4]))
    if (ha or {}).get("error"):
        inner += f'<p class="bad">{_esc(ha["error"])}</p>'
    return f'<div id="homeassistant" style="display:contents">{_card("/settings#homeassistant", "Smart home", state, inner)}</div>'


def _headline(items):

    if not items:
        return "Everything is healthy"
    n = len(items)
    return f"{n} thing{'s' * (n != 1)} need{'s' * (n == 1)} a look — everything else is healthy"


def scan_state(runs):
    """(newest ok run's start or None, True when every source's latest run failed) from InventoryStore.runs()."""

    latest = {run["source"]: run for run in runs or []}          # oldest first: the last one per source wins
    ok = [clock.parse(run["started_at"]) for run in runs or [] if run["ok"]]
    return max(ok, default=None), bool(latest) and not any(run["ok"] for run in latest.values())


def _hero(items, last_scan, scan_minutes, now, scans_failing=False, failed=()):
    """
    Unknown, never healthy, when no scan has worked in the last 3 scan intervals, every source's latest scan failed,
    or (with nothing else to show) a part the verdict rests on couldn't be read.
    """

    if scans_failing:
        good = f"last good scan {friendly_time(last_scan, now)}" if last_scan else "no scan has worked this week"
        return status_hero(len(items), "Scans are failing", good, "unknown")
    if last_scan is None:
        return status_hero(len(items), "No recent scan", "no scan has run yet", "unknown")
    ago = f"last scan {friendly_time(last_scan, now)}"
    if now - last_scan > timedelta(minutes=3 * scan_minutes):
        return status_hero(len(items), "No recent scan", ago, "unknown")
    if not items and failed:
        return status_hero("?", f"Couldn't read {' / '.join(failed)}", ago, "unknown")
    return status_hero(len(items), _headline(items), ago, "attention" if items else "ok")


PROBLEM_ICONS = {"posture": "shield", "hosts": "server", "storage": "box", "alerts": "alert", "access": "key"}


def _problems(items):

    if not items:
        return ""
    return ('<section class="panel problems" aria-label="Needs attention">' + "".join(
        check_row(PROBLEM_ICONS.get(card, "alert"), what, why, (action, href)) for card, what, why, href, action in items)
        + "</section>")


# A changes_feed mark as a timeline title and dot state.
CHANGE_KINDS = {"device": ("New device", "attention"), "check": ("Cleared", "ok"), "alert": ("Problem", "attention"),
                "search": ("Found", "attention"), "server": ("Proxmox", "info"), "box": ("Container", "info")}


def _since(changes, since, now, display):
    """Since you were here (the newest 8 changes_feed items) beside the Ask Lanxang chips; stacked on a phone."""

    chips = ask_chips(ASK_SHORTCUTS)
    ask = f'<section class="panel ask"><h2>Ask Lanxang</h2>{chips}</section>' if chips else ""
    news = ""

    if changes is not None and since is not None:
        if changes:
            rows = []
            for at, mark, text, _ in changes[:8]:
                title, state = CHANGE_KINDS.get(mark, ("Notice", "info"))
                rows.append((at, title, text.removeprefix("New device: ").removeprefix("Cleared: "), state))
            window = "24h" if now - since <= timedelta(hours=24) else "7d"
            news = (f'<section class="panel since"><h2>Since you were here <span class="muted">— {when(since, now)}'
                    f'</span></h2>{timeline(rows, display)}<p class="muted more">{plural(len(changes), "change")} · '
                    f'<a href="/history?changes={window}">see all in Activity →</a></p></section>')
        else:
            news = ('<section class="panel since"><h2>Since you were here</h2>'
                    f'<p class="muted">Nothing changed since {when(since, now)}.</p></section>')

    return f'<div class="brief">{news}{ask}</div>' if news or ask else ""


def render_home_page(posture, hosts, events, storage=None, trends=None, analysis=None, now=None, access_reviews=(),
                     steps=None, open_alerts=(), dns=None, names=None, ha=None, changes=None, since=None, vitals=None,
                     last_scan=None, scan_minutes=15, viewer_zone=None, scans_failing=False, failed=()):
    """
    posture: render._posture_block() output or None; hosts: build_hosts() output; events: interesting_events()
    pairs; storage: build_storage() output; trends: posture.model.build_trends() output or None; analysis:
    KnowledgeQueries().latest_analysis() or None; changes: changes_feed.collect() items since `since` (None leaves
    Since you were here out); vitals: build_vitals() tiles; last_scan, scans_failing: scan_state() of the source runs;
    failed: the parts that couldn't be read (["posture", "alerts"]), so an empty problem list isn't called healthy;
    viewer_zone: the zone the browser reported (lanxang-tz), used when the display time zone is "browser".
    """

    display = home_display(viewer_zone)

    now = now or utcnow()
    storage = storage or {"rows": [], "state": "unknown"}
    items = attention_items(posture, hosts, storage, access_reviews, open_alerts)
    flagged = {card for card, *_ in items}

    body = (HOME_STYLE + _hero(items, last_scan, scan_minutes, now, scans_failing, failed) + _problems(items) + _checklist(steps)
            + _since(changes, since, now, display)
            + (f'<section class="vitals" aria-label="Vitals">{"".join(vitals)}</section>' if vitals else "")
            + '<div class="cards">'
            + _posture_card(posture, "posture" in flagged) + _hosts_card(hosts, "hosts" in flagged)
            + _storage_card(storage, "storage" in flagged) + _dns_card(dns, names or {}) + _ha_card(ha)
            + _trends_card(trends, display) + _analysis_card(analysis, now)
            + _activity_card(events) + "</div>")

    return render_page("Home", body, active="home")
