"""
/ - the summary home: one verdict line and three cards (security posture,
hosts health, recent activity), each linking to its detail tab. Pure
renderers; server.py gathers the data and passes None for any source that
failed, which renders as a muted "unavailable" line instead of a 500.
"""

import re
from datetime import datetime

from atlas.web.render import _esc, render_page


HOME_STYLE = """
<style>
.verdict { font-size:20px; font-weight:600; margin:0 0 16px; }
.verdict.ok { color:#7fdcb5; } .verdict.warn { color:#ffb4a2; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:16px; }
.cards a.hcard { display:block; color:var(--text); text-decoration:none; background:#111821;
                 border:1px solid #222c38; border-radius:14px; padding:16px; }
.cards a.hcard:hover { border-color:var(--blue); }
.hcard h2 { margin:0 0 10px; font-size:15px; border:0; padding:0; display:flex; gap:8px; align-items:center; }
.hcard.warn { border-color:var(--red); } .hcard.review { border-color:var(--orange); }
.dot { width:9px; height:9px; border-radius:50%; background:var(--muted); display:inline-block; }
.dot.ok { background:var(--green); } .dot.warn { background:var(--red); } .dot.review { background:var(--orange); }
.hcard dl { display:grid; grid-template-columns:auto 1fr; gap:4px 12px; margin:8px 0 0; font-size:14px; }
.hcard dt { color:var(--muted); }
.hcard .host { padding:8px 0; border-top:1px solid var(--line); font-size:14px; }
.hcard .host:first-of-type { border-top:0; }
.hcard .bad { color:#ffb4a2; font-size:13px; }
.hcard ul { list-style:none; margin:0; padding:0; font-size:13px; }
.hcard li { padding:4px 0; border-top:1px solid var(--line); }
.hcard li:first-child { border-top:0; }
.cards a.hcard.wide { grid-column:span 2; }
@media (max-width: 1100px) { .cards a.hcard.wide { grid-column:auto; } }
.hcard .row { display:flex; justify-content:space-between; gap:8px; padding:5px 0; border-top:1px solid var(--line); font-size:14px; }
.hcard .row:first-of-type { border-top:0; }
.hcard .row.warn span:last-child { color:#ffb4a2; }
.chips { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 16px; }
.chips button { font:inherit; font-size:13px; padding:6px 12px; border-radius:999px; margin:0; }
.chart { margin:4px 0 12px; } .chart h3 { margin:0 0 4px; font-size:12px; font-weight:500; color:var(--muted); }
.chart svg { width:100%; height:70px; display:block; }
.chart .lbl { font-size:12px; margin-top:4px; }
.sev-high, .sev-critical { color:#ffb4a2; } .sev-medium { color:#ffd08a; }
</style>
"""


def _pct(used, total):

    return round(used / total * 100) if used is not None and total else None


def build_hosts(topology, local_health, pve_scan):
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
            "problems": [f"{c['name']} unhealthy" for c in containers if c.get("health") == "unhealthy"]
                        + [f"{c['name']} stopped" for c in containers if c["status"] != "running"],
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

    return event_type.removeprefix("atlas.").replace(".", " ").replace("_", " ")


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


def build_storage(arrays, usage, feeds, pve_scan, topology=None):
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

    for node in nodes:
        host = pve_host if pve_host and len(nodes) == 1 else node["name"]
        for pool in node.get("zfs", []):
            pct = round(pool["alloc"] / pool["size"] * 100) if pool.get("size") else 0
            rows.append({"name": f"{host} {pool['name']}", "detail": f"{pool['health']} · {pct}% of {_size(pool['size'])}",
                         "warn": pool["health"] != "ONLINE" or pct >= WARN_PERCENT})

    state = "unknown" if not rows else ("warn" if any(r["warn"] for r in rows) else "ok")

    return {"rows": rows, "state": state}


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
                            f'height="{h:.2f}" fill="{color}"><title>{_esc(label)}</title></rect>')

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
                    [f"{h['hour'][11:16]} UTC · {label} {_size(h[key])}" for h in hours], height=34)
        for key, label, color in (("direct", "Direct", "#8b98a6"), ("vpn", "Via VPN", "#43c08f")))
    new = _bars_svg([{"n": d["count"]} for d in days], {"n": "#f0a23a"},
                    [f"{d['day']}: {d['count']} new" for d in days])
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

    if not analysis:
        return _card("/overview", "Latest AI check-up", "unknown",
                     '<p class="muted">No check-up yet. atlas-scan runs one daily once the AI model is reachable.</p>')

    recs = [r if isinstance(r, dict) else {"title": str(r), "severity": ""} for r in analysis.get("recommendations") or []]
    worst = "warn" if any(r.get("severity") in ("high", "critical") for r in recs) else "ok"
    summary = (analysis.get("summary") or "")[:280]
    inner = (f'<p class="muted">{_esc(_age(analysis.get("created_at"), now))} · {_esc(analysis.get("model"))}</p>'
             f"<p>{_esc(summary)}</p><ul>"
             + "".join(f'<li><span class="sev-{_esc(r.get("severity"))}">{_esc(r.get("severity") or "")}</span> '
                       f'{_esc(r.get("title"))}</li>' for r in recs[:3]) + "</ul>")

    return _card("/overview", "Latest AI check-up", worst, inner)


def _storage_card(storage):

    if not storage["rows"]:
        return _card("/overview", "Storage & RAID", "unknown", '<p class="muted">No storage data yet.</p>')

    inner = "".join(f'<div class="row{" warn" if r["warn"] else ""}"><span>{_esc(r["name"])}</span>'
                    f'<span class="muted">{_esc(r["detail"])}</span></div>' for r in storage["rows"])

    return _card("/overview", "Storage & RAID", storage["state"], inner)


def _chips():

    return '<div class="chips" aria-label="Ask Atlas">' + "".join(
        f'<button data-ask="{_esc(q)}">{_esc(q)}</button>' for q in ASK_SHORTCUTS) + "</div>" + (
        "<script>document.querySelectorAll('[data-ask]').forEach((b) => b.addEventListener('click', () => {"
        " const q = b.dataset.ask; if (window.atlasAsk) window.atlasAsk(q); else location.href = '/chat?q=' +"
        " encodeURIComponent(q); }));</script>")


def _card(href, title, state, inner, wide=False):

    return (f'<a class="hcard {state}{" wide" if wide else ""}" href="{href}"><h2><span class="dot {state}"></span>{_esc(title)}</h2>'
            f"{inner}</a>")


def _posture_card(posture):

    if not posture:
        return _card("/posture", "Security posture", "unknown", '<p class="muted">Posture data unavailable.</p>')

    rows = (("Status", posture["message"]), ("VPN", posture["vpn"]), ("Public routes", posture["routes"]),
            ("CrowdSec bans", posture["blocked"]), ("Needs review", posture["review_count"]))
    inner = "<dl>" + "".join(f"<dt>{_esc(k)}</dt><dd>{_esc(v)}</dd>" for k, v in rows) + "</dl>"

    return _card("/posture", "Security posture", posture["state"], inner)


def _usage(row):

    parts = [f"{label} {row[key]}%" for key, label in (("cpu", "CPU"), ("mem", "RAM"), ("disk", "Disk"))
             if row[key] is not None]

    return " · ".join(parts)


def _hosts_card(hosts):

    if not hosts["rows"]:
        return _card("/overview", "Hosts health", "unknown", '<p class="muted">No host data yet.</p>')

    inner = "".join(
        f'<div class="host"><strong>{_esc(row["name"])}</strong> <span class="muted">{_esc(_usage(row))}</span>'
        + (f'<br><span class="muted">{_esc(row["detail"])}</span>' if row["detail"] else "")
        + (f'<br><span class="bad">{_esc(", ".join(row["problems"][:4]))}</span>' if row["problems"] else "")
        + "</div>"
        for row in hosts["rows"]
    )

    if hosts["down"]:
        inner += f'<p class="muted">Unreachable: {_esc(", ".join(hosts["down"]))}</p>'

    return _card("/overview", "Hosts health", hosts["state"], inner)


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


def render_home_page(posture, hosts, events, storage=None, trends=None, analysis=None, now=None):
    """
    posture: render._posture_block() output or None; hosts: build_hosts()
    output; events: interesting_events() pairs; storage: build_storage()
    output; trends: posture.model.build_trends() output or None; analysis:
    KnowledgeQueries().latest_analysis() or None.
    """

    storage = storage or {"rows": [], "state": "unknown"}
    states = ((posture or {}).get("state"), hosts["state"], storage["state"])
    attention = sum(state in ("warn", "review") for state in states)
    verdict = ('<p class="verdict ok">All good</p>' if not attention else
               f'<p class="verdict warn">{attention} thing{"s" if attention > 1 else ""} need'
               f'{"" if attention > 1 else "s"} attention</p>')

    body = (HOME_STYLE + verdict + _chips() + '<div class="cards">'
            + _posture_card(posture) + _hosts_card(hosts) + _storage_card(storage)
            + _trends_card(trends) + _analysis_card(analysis, now or datetime.utcnow())
            + _activity_card(events) + "</div>")

    return render_page("Home", body, active="home")
