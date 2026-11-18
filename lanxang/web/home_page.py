"""
/ - the summary home: one verdict line and three cards (security posture,
hosts health, recent activity), each linking to its detail tab. Pure
renderers; server.py gathers the data and passes None for any source that
failed, which renders as a muted "unavailable" line instead of a 500.
"""

import re
from datetime import datetime

from lanxang.health.alerts import container_problem, container_state
from lanxang.web.render import _esc, ask_chips, render_page
from lanxang.clock import utcnow


HOME_STYLE = """
<style>
.steps { margin:0 0 16px; padding:12px 16px; border:1px solid var(--line2); border-radius:12px; }
.steps h2 { margin:0 0 6px; font-size:15px; border:0; padding:0; }
.steps ol { list-style:none; margin:0; padding:0; }
.steps li { display:flex; gap:10px; align-items:baseline; padding:4px 0; }
.steps li .what { flex:1; } .steps li.done { opacity:.6; }
.steps .tick { width:1em; color:var(--ok-text); }
.verdict { font-size:20px; font-weight:600; margin:0 0 16px; }
.verdict.ok { color:var(--ok-text); }
.attention { margin:0 0 16px; padding:12px 16px; border:1px solid var(--orange); border-radius:12px; background:var(--warn-bg); }
.attention h2 { margin:0 0 6px; font-size:15px; border:0; padding:0; color:var(--warn-text); }
.attention ul { list-style:none; margin:0; padding:0; }
.attention li { display:flex; align-items:center; gap:10px; padding:6px 0; border-top:1px solid var(--warn-line); font-size:14px; }
.attention li:first-child { border-top:0; }
.attention li .what { flex:1; } .attention li .what b { font-weight:600; }
.attention li a { white-space:nowrap; }
.cards { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; align-items:start; }
.cards a.hcard.wide { grid-column:span 2; grid-row:span 2; align-self:stretch; display:flex; flex-direction:column; }
.cards a.hcard.wide .chart:last-child { flex:1; display:flex; flex-direction:column; }
.cards a.hcard.wide .chart:last-child svg { flex:1; min-height:100px; max-height:170px; height:auto !important; }
.hcard .summary { font-size:14px; line-height:1.45; margin:6px 0 10px; }
@media (max-width: 1100px) { .cards { grid-template-columns:repeat(2,minmax(0,1fr)); } .cards a.hcard.wide { grid-row:auto; } }
@media (max-width: 700px) { .cards { grid-template-columns:1fr; } .cards a.hcard.wide { grid-column:auto; } }
.cards a.hcard.flagged { box-shadow:0 0 0 2px var(--gold); }
.cards a.hcard.flagged.warn { box-shadow:0 0 0 2px var(--red); }
.hcard .tag { margin-left:auto; font-size:11px; font-weight:500; text-transform:uppercase; letter-spacing:.05em; color:var(--warn-text); }
.cards a.hcard { display:block; color:var(--text); text-decoration:none; background:var(--surface);
                 border:1px solid var(--line); border-radius:10px; padding:16px; }
.cards a.hcard:hover { border-color:var(--blue); }
.hcard h2 { margin:0 0 10px; font-size:15px; border:0; padding:0; display:flex; gap:8px; align-items:center; }
.hcard.warn { border-color:var(--red); } .hcard.review { border-color:var(--orange); }
.dot { width:9px; height:9px; border-radius:50%; background:var(--muted); display:inline-block; }
.dot.ok { background:var(--green); } .dot.warn { background:var(--red); } .dot.review { background:var(--orange); }
.hcard dl { display:grid; grid-template-columns:auto 1fr; gap:4px 12px; margin:8px 0 0; font-size:14px; }
.hcard dt { color:var(--muted); }
.hcard .host { padding:8px 0; border-top:1px solid var(--line); font-size:14px; }
.hcard .host .m { white-space:nowrap; }
.hcard .host:first-of-type { border-top:0; }
.hcard .bad { color:var(--bad-text); font-size:13px; }
.hcard ul { list-style:none; margin:0; padding:0; font-size:13px; }
.hcard li { padding:4px 0; border-top:1px solid var(--line); }
.hcard li:first-child { border-top:0; }
.hcard .row { display:flex; justify-content:space-between; gap:8px; padding:5px 0; border-top:1px solid var(--line); font-size:14px; }
.hcard .row:first-of-type { border-top:0; }
.hcard .row.warn span:last-child { color:var(--bad-text); }
.chart { margin:4px 0 12px; } .chart h3 { margin:0 0 4px; font-size:12px; font-weight:500; color:var(--muted); }
.chart svg { width:100%; height:70px; display:block; }
.chart .lbl { font-size:12px; margin-top:4px; }
.sev-high, .sev-critical { color:var(--bad-text); } .sev-medium { color:var(--warn-text); }
.kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(128px,1fr)); gap:12px; margin:0 0 24px; }
.kpis a { display:block; border:1px solid var(--line); border-radius:10px; padding:14px 16px; background:var(--surface);
          color:var(--text); text-decoration:none; }
.kpis a:hover { border-color:var(--blue); }
.kpis .k { font-size:13px; color:var(--muted); }
.kpis .v { display:block; font-size:24px; font-weight:600; margin:2px 0; font-variant-numeric:tabular-nums; }
.kpis .s { font-size:13px; color:var(--muted); } .kpis .bad .v { color:var(--red); } .kpis .warn .v { color:var(--orange); } .kpis .good .v { color:var(--green); }
.issues { border:1px solid var(--line); border-radius:10px; overflow-x:auto; background:var(--surface); margin:0 0 24px; }
.issues table { margin:0; font-size:14px; } .issues td { vertical-align:top; } .issues tr:last-child td { border-bottom:0; }
.sev { display:inline-flex; align-items:center; gap:6px; font-weight:600; font-size:13px; white-space:nowrap; }
.sev i { width:8px; height:8px; border-radius:2px; display:block; }
.sev.problem { color:var(--red); } .sev.problem i { background:var(--red); }
.sev.review { color:var(--orange); } .sev.review i { background:var(--orange); }
h2.sect { font-size:16px; border:0; padding:0; margin:0 0 10px; }
</style>
"""


def _pct(used, total):

    return round(used / total * 100) if used is not None and total else None


def build_hosts(topology, local_health, pve_scan, host_issues=None):
    """
    Rows for the hosts card: the host Atlas runs on (live psutil numbers from
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


def _event_label(event_type):

    return event_type.removeprefix("lanxang.").replace(".", " ").replace("_", " ")


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
        detail = f"{a['level'].upper()} · {a['disks']} disks · {a['state']}"
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


def _bars_svg(series, colors, labels, height=70):
    """
    Stacked bars, one per point: series is a list of {key: value} dicts, colors
    {key: css color}. Each bar carries a <title> tooltip from labels.
    """

    peak = max((sum(point.values()) for point in series), default=0) or 1
    width = 100 / len(series)
    bars = []

    for i, (point, label) in enumerate(zip(series, labels)):
        y = height
        for key, color in colors.items():
            h = point.get(key, 0) / peak * (height - 4)
            if h:
                y -= h
                bars.append(f'<rect x="{i * width + width * 0.12:.2f}" y="{y:.2f}" width="{width * 0.76:.2f}" '
                            f'height="{h:.2f}" style="fill:{color}"><title>{_esc(label)}</title></rect>')

    return (f'<svg viewBox="0 0 100 {height}" preserveAspectRatio="none" role="img" style="height:{height}px">'
            f'{"".join(bars)}</svg>')


def _trends_card(trends):

    if not trends:
        return _card("/posture", "Security trends", "unknown", '<p class="muted">Posture data unavailable.</p>',
                     wide=True)

    hours, days = trends["hours"], trends["new_per_day"]
    # Separate scales: VPN (torrents) is often 100x direct and would flatten it.
    traffic = "".join(
        f'<div class="lbl">{label} <span class="muted">peak {_size(max(h[key] for h in hours))}/h</span></div>'
        + _bars_svg([{key: h[key]} for h in hours], {key: color},
                    [f"{h['hour'][11:16]} UTC · {label} {_size(h[key])}" for h in hours], height=56)
        for key, label, color in (("direct", "Direct", "var(--muted)"), ("vpn", "Via VPN", "var(--green)")))
    new = _bars_svg([{"n": d["count"]} for d in days], {"n": "var(--orange)"},
                    [f"{d['day']}: {d['count']} new" for d in days], height=110)
    total_new = sum(d["count"] for d in days)
    inner = (
        '<div class="chart"><h3>Outbound traffic per hour, last 24 h</h3>' + traffic + "</div>"
        + f'<div class="chart"><h3>New destinations per day, last 7 days ({total_new} total)</h3>{new}</div>'
    )

    return _card("/posture", "Security trends", "review" if days[-1]["count"] else "ok", inner, wide=True)


def _age(created_at, now):

    try:
        hours = (now - datetime.fromisoformat(str(created_at)[:19])).total_seconds() / 3600
    except ValueError:
        return str(created_at)

    return f"{hours:.0f} h ago" if hours < 48 else f"{hours / 24:.0f} days ago"


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
    inner = (f'<p class="muted">{_esc(_age(analysis.get("created_at"), now))} · {_esc(analysis.get("model"))}</p>'
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

    rows = (("Status", posture["message"]), ("VPN", posture["vpn"]), ("Public routes", posture["routes"]),
            ("CrowdSec bans", posture["blocked"]), ("Needs review", posture["review_count"]))
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
        f'<li><span class="muted">{_esc(str(e.created_at)[:16])}</span> {_esc(_event_label(e.event_type))}'
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


def _checklist(steps):
    """Shown until every required step is done; optional ones ride along."""

    if not steps or all(done for *_, done, optional in steps if not optional):
        return ""

    rows = []
    for title, why, href, done, optional in steps:
        extra = ' <span class="muted">(optional)</span>' if optional else ""
        if done:
            rows.append(f'<li class="done"><span class="tick">\u2713</span><span class="what"><b>{_esc(title)}</b>'
                        f'{extra}</span></li>')
        else:
            rows.append(f'<li><span class="tick">\u25cb</span><span class="what"><b>{_esc(title)}</b>{extra} '
                        f'\u2014 {_esc(why)}</span><a href="{href}">Set up \u2192</a></li>')

    return ('<section class="steps" aria-label="Getting started"><h2>Getting started</h2><ol>' + "".join(rows)
            + "</ol></section>")


def build_stats(devices=None, hosts=None, storage=None, posture=None, uptime=None, ups=None, internet=None,
                dns=None, ha=None):
    """The number tiles along the top of Home: [(label, value, sub, href, tone)]; a source that's missing is left out.
    devices: InventoryStore().devices(); uptime: [7-day % per check]; ups: the UPS watch's saved detail."""

    tiles = []
    if devices is not None:
        live = [d for d in devices if d["state"] != "ignored"]
        online = sum(d.get("status") != "quiet" for d in live)
        new = sum(d["state"] == "new" for d in live)
        tiles.append(("Devices", f"{online} / {len(live)}", f"online · {new} new" if new else "online, all named",
                      "/devices", "warn" if new else ""))
    if internet:                                  # (up, ms) from the newest internet check
        up, ms = internet
        tiles.append(("Internet", "Up" if up else "Down", f"{ms:.0f} ms" if up and ms is not None else
                      "router or provider — see Uptime" if not up else "", "/uptime", "good" if up else "bad"))
    info = (dns or {}).get("info") or {}
    if info:                                      # Pi-hole / AdGuard Home
        on = info.get("blocking")
        share = f'{info["percent"]:.0f}% of queries blocked' if info.get("percent") is not None else ""
        tiles.append(("Ad blocking", "On" if on else "Off", share if on else "every device sees ads", "/#dns",
                      "good" if on else "bad"))
    home = (ha or {}).get("info") or {}
    if ha and (home or ha.get("error")):          # Home Assistant
        lost, low = len(home.get("offline") or []), len(home.get("batteries") or [])
        problems = ([f"{lost} offline"] if lost else []) + ([f"{low} low batteries"] if low else [])
        tiles.append(("Smart home", "Down" if ha.get("failures", 0) >= 2 else "Fine" if not problems else
                      f"{lost + low} to check", ", ".join(problems) or (f"{len(home.get('updates') or [])} updates "
                      "waiting" if home.get("updates") else "all devices answering"), "/#homeassistant",
                      "bad" if ha.get("failures", 0) >= 2 or lost else "warn" if low else "good"))
    if hosts and hosts["rows"]:
        fine = sum(not row["problems"] for row in hosts["rows"])
        tiles.append(("Servers", f"{fine} / {len(hosts['rows'])}", "healthy" if fine == len(hosts["rows"]) else
                      "need a look", "/overview", "" if fine == len(hosts["rows"]) else "bad"))
    if uptime is not None:
        known = [u for u in uptime if u is not None]
        tiles.append(("Uptime, 7 days", f"{min(known):g}%" if known else "–",
                      f"{len(uptime)} check{'s' * (len(uptime) != 1)}" if uptime else "no checks yet — add one",
                      "/uptime", "bad" if known and min(known) < 99 else ""))
    if posture:
        tiles.append(("Public routes", str(posture["routes"]), f"{posture['review_count']} to review"
                      if posture.get("review_count") else "nothing to review", "/posture",
                      "bad" if posture["state"] == "warn" else ""))
    for name, info in ((ups or {}).get("upses") or {}).items():
        on_battery = info.get("state") in ("battery", "low")
        charge = f"{info['charge']:.0f}% charged" if info.get("charge") is not None else name
        tiles.append(("Power", "On battery" if on_battery else "On mains", charge, "/uptime",
                      "bad" if on_battery else "good"))
        break
    if storage and storage["rows"] and not ups:
        bad = sum(bool(row["warn"]) for row in storage["rows"])
        tiles.append(("Storage", "Problem" if bad else "Healthy", f"{len(storage['rows'])} checked", "/overview",
                      "bad" if bad else "good"))

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
             f'{len(batteries)} low batteries</p>' + (rows or '<p class="muted">Every device is answering.</p>'))
    if updates:
        inner += (f'<p class="muted" style="margin:10px 0 4px">{len(updates)} update{"s" if len(updates) != 1 else ""} '
                  'waiting</p>' + "".join(f'<div class="row"><span>{_esc(u["title"])}</span><span class="muted">'
                                          f'{_esc(u["latest"] or "")}</span></div>' for u in updates[:4]))
    if (ha or {}).get("error"):
        inner += f'<p class="bad">{_esc(ha["error"])}</p>'
    return f'<div id="homeassistant" style="display:contents">{_card("/settings#homeassistant", "Smart home", state, inner)}</div>'


def _kpis(stats):

    if not stats:
        return ""
    return ('<nav class="kpis" aria-label="At a glance">' + "".join(
        f'<a class="{tone}" href="{href}"><span class="k">{_esc(label)}</span><span class="v">{_esc(value)}</span>'
        f'<span class="s">{_esc(sub)}</span></a>' for label, value, sub, href, tone in stats) + "</nav>")


def _headline(items):

    if not items:
        return "\u2713 Everything is healthy"
    n = len(items)
    return f"{n} thing{'s' * (n != 1)} need{'s' * (n == 1)} a look — everything else is healthy"


def _issues(items):

    rows = []
    for card, what, why, href, action in items:
        problem = card in ("hosts", "storage") or (card == "posture" and action == "Open")
        sev = ('<span class="sev problem"><i></i>Problem</span>' if problem else
               '<span class="sev review"><i></i>Review</span>')
        rows.append(f'<tr><td>{sev}</td><td><b>{_esc(what)}</b></td><td>{_esc(why)}</td>'
                    f'<td><a href="{href}">{_esc(action)} \u2192</a></td></tr>')

    return ('<section aria-label="Needs attention"><h2 class="sect">Needs attention</h2><div class="issues"><table>'
            '<thead><tr><th>Severity</th><th>Area</th><th>What</th><th></th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div></section>")


def render_home_page(posture, hosts, events, storage=None, trends=None, analysis=None, now=None, access_reviews=(),
                     steps=None, open_alerts=(), stats=None, dns=None, names=None, ha=None):
    """
    posture: render._posture_block() output or None; hosts: build_hosts()
    output; events: interesting_events() pairs; storage: build_storage()
    output; trends: posture.model.build_trends() output or None; analysis:
    KnowledgeQueries().latest_analysis() or None; stats: build_stats() tiles.
    """

    storage = storage or {"rows": [], "state": "unknown"}
    items = attention_items(posture, hosts, storage, access_reviews, open_alerts)
    flagged = {card for card, *_ in items}

    body = (HOME_STYLE + _checklist(steps) + _kpis(stats) + (_issues(items) if items else "")
            + ask_chips(ASK_SHORTCUTS) + '<div class="cards">'
            + _posture_card(posture, "posture" in flagged) + _hosts_card(hosts, "hosts" in flagged)
            + _storage_card(storage, "storage" in flagged) + _dns_card(dns, names or {}) + _ha_card(ha)
            + _trends_card(trends) + _analysis_card(analysis, now or utcnow())
            + _activity_card(events) + "</div>")

    return render_page("Home", body, active="home", heading=_headline(items))
