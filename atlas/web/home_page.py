"""
/ - the summary home: one verdict line and three cards (security posture,
hosts health, recent activity), each linking to its detail tab. Pure
renderers; server.py gathers the data and passes None for any source that
failed, which renders as a muted "unavailable" line instead of a 500.
"""

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


def _card(href, title, state, inner):

    return (f'<a class="hcard {state}" href="{href}"><h2><span class="dot {state}"></span>{_esc(title)}</h2>'
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


def render_home_page(posture, hosts, events):
    """
    posture: render._posture_block() output or None; hosts: build_hosts()
    output; events: interesting_events() pairs.
    """

    attention = sum(state in ("warn", "review") for state in ((posture or {}).get("state"), hosts["state"]))
    verdict = ('<p class="verdict ok">All good</p>' if not attention else
               f'<p class="verdict warn">{attention} thing{"s" if attention > 1 else ""} need'
               f'{"" if attention > 1 else "s"} attention</p>')

    body = (HOME_STYLE + verdict + '<div class="cards">'
            + _posture_card(posture) + _hosts_card(hosts) + _activity_card(events) + "</div>")

    return render_page("Home", body, active="home")
