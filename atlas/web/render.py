"""
Pure HTML-rendering functions for the read-only web view (`atlas web`).
Every function here takes already-fetched data (from KnowledgeQueries/
build_trends_payload) and returns a plain HTML string - no I/O, no
database access, so these are unit-testable the same way format_change()/
_trend_summary() already are elsewhere in this codebase. No form, no
POST route, no write path anywhere in this module - view only, per the
roadmap's own scoping for this feature.
"""

from html import escape


PAGE_STYLE = """
  body { font-family: system-ui, sans-serif; background: #0d1117; color: #e6edf3;
         margin: 0; padding: 2rem; line-height: 1.5; }
  a { color: #58a6ff; text-decoration: none; }
  a:hover { text-decoration: underline; }
  nav { margin-bottom: 1.5rem; }
  nav a { margin-right: 1.25rem; font-weight: 600; }
  h1 { margin-top: 0; }
  h2 { border-bottom: 1px solid #30363d; padding-bottom: 0.3rem; }
  table { border-collapse: collapse; width: 100%; margin: 0.75rem 0 1.5rem; }
  th, td { text-align: left; padding: 0.4rem 0.8rem; border-bottom: 1px solid #21262d; }
  th { color: #8b949e; font-weight: 600; font-size: 0.85rem; text-transform: uppercase; }
  .muted { color: #8b949e; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px;
          padding: 1rem 1.5rem; margin-bottom: 1.5rem; }
  code, pre { background: #010409; border: 1px solid #30363d; border-radius: 4px;
              padding: 0.15rem 0.4rem; font-size: 0.85rem; }
  pre { padding: 0.75rem; overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
"""


def _esc(value):
    return escape(str(value))


def render_page(title, body_html):

    return (
        "<!doctype html>\n"
        "<html><head><meta charset=\"utf-8\">"
        f"<title>Atlas - {_esc(title)}</title>"
        f"<style>{PAGE_STYLE}</style></head><body>"
        "<nav>"
        "<a href=\"/\">Overview</a>"
        "<a href=\"/history\">History</a>"
        "<a href=\"/trends\">Trends</a>"
        "<a href=\"/map\">Map</a>"
        "</nav>"
        f"<h1>{_esc(title)}</h1>"
        f"{body_html}"
        "</body></html>"
    )


def _kv_table(data):

    if not data:
        return "<p class=\"muted\">No data.</p>"

    rows = "".join(
        f"<tr><td>{_esc(key)}</td><td>{_esc(value)}</td></tr>"
        for key, value in data.items()
    )

    return f"<table><tbody>{rows}</tbody></table>"


def _list_of_dicts_table(items):

    if not items:
        return "<p class=\"muted\">None found.</p>"

    columns = []

    for item in items:
        for key in item.keys():
            if key not in columns:
                columns.append(key)

    header = "".join(f"<th>{_esc(column)}</th>" for column in columns)

    body_rows = "".join(
        "<tr>" + "".join(f"<td>{_esc(item.get(column, ''))}</td>" for column in columns) + "</tr>"
        for item in items
    )

    return f"<table><thead><tr>{header}</tr></thead><tbody>{body_rows}</tbody></table>"


def render_overview_page(environment, analysis):
    """
    environment is KnowledgeQueries().latest_environment()'s return
    value (or None if atlas discover has never run); analysis is
    KnowledgeQueries().latest_analysis()'s (or None).
    """

    if environment is None:

        return render_page(
            "Overview",
            "<p class=\"muted\">No inventory found. Run <code>atlas discover</code> first.</p>"
        )

    sections = []

    for title, key in (
        ("System", "system"), ("Hardware", "hardware"),
        ("Storage", "storage"), ("Network", "network")
    ):

        data = environment.get(key) or {}

        # collect_storage() (atlas/discovery/storage.py) always returns a
        # list - one row per mounted filesystem - never a dict, unlike every
        # other category here. _kv_table() unconditionally called .items()
        # on whatever it was given, so this crashed the whole page with an
        # AttributeError on any real host with any storage at all (found by
        # actually running `atlas discover` + `atlas web` together, not by
        # a unit test - the existing render tests seed data without a real
        # `storage` key).
        table = _list_of_dicts_table(data) if isinstance(data, list) else _kv_table(data)

        sections.append(
            f"<div class=\"card\"><h2>{_esc(title)}</h2>{table}</div>"
        )

    # atlas discover's containers/virtualization categories are each
    # keyed by plugin name (see atlas.plugins.AtlasPlugin.category and
    # the per-category merge in atlas.cli.main.discover()) - every
    # entry is {"available": bool, "containers"/"guests": [...]}, not
    # the resource itself. Flatten each plugin's list into rows,
    # tagging each with its source plugin.
    containers = environment.get("containers") or {}

    container_rows = [
        {"plugin": plugin_name, **container}
        for plugin_name, result in containers.items()
        if isinstance(result, dict)
        for container in result.get("containers", [])
    ]

    if container_rows:

        sections.append(
            f"<div class=\"card\"><h2>Containers</h2>{_list_of_dicts_table(container_rows)}</div>"
        )

    virtualization = environment.get("virtualization") or {}

    if isinstance(virtualization.get("guests"), list):

        # atlas proxmox scan's shape - {"nodes": [...], "guests": [...]}
        # - not plugin-sourced, so no "plugin" column to add.
        guests = virtualization["guests"]

    else:

        guests = [
            {"plugin": plugin_name, **guest}
            for plugin_name, result in virtualization.items()
            if isinstance(result, dict)
            for guest in result.get("guests", [])
        ]

    if guests:

        sections.append(
            f"<div class=\"card\"><h2>Virtualization Guests</h2>{_list_of_dicts_table(guests)}</div>"
        )

    if analysis:

        recommendations = "".join(
            f"<li>{_esc(rec)}</li>" for rec in analysis.get("recommendations") or []
        )

        sections.append(
            "<div class=\"card\"><h2>Latest AI Analysis</h2>"
            f"<p class=\"muted\">{_esc(analysis.get('provider'))} / "
            f"{_esc(analysis.get('model'))} - {_esc(analysis.get('created_at'))}</p>"
            f"<p>{_esc(analysis.get('summary'))}</p>"
            f"<ul>{recommendations}</ul></div>"
        )

    timestamp = environment.get("timestamp")

    header = f"<p class=\"muted\">Latest snapshot: {_esc(timestamp)}</p>" if timestamp else ""

    return render_page("Overview", header + "".join(sections))


def render_history_page(events):
    """
    events is KnowledgeQueries().recent_events()'s return value - a
    list of EventRecord ORM objects, same as `atlas history` prints.
    """

    if not events:

        return render_page(
            "History",
            "<p class=\"muted\">No historical events found.</p>"
        )

    rows = "".join(
        "<tr>"
        f"<td>{_esc(event.created_at)}</td>"
        f"<td>{_esc(event.event_type)}</td>"
        f"<td>{_esc(event.source)}</td>"
        f"<td><pre>{_esc(event.payload)}</pre></td>"
        "</tr>"
        for event in events
    )

    body = (
        "<table><thead><tr><th>Time</th><th>Event</th><th>Source</th>"
        f"<th>Payload</th></tr></thead><tbody>{rows}</tbody></table>"
    )

    return render_page("History", body)


def _trend_summary_row(metric_name, summary):

    return (
        "<tr>"
        f"<td>{_esc(metric_name)}</td>"
        f"<td>{summary['latest']:.1f}%</td>"
        f"<td>{summary['min']:.1f}%</td>"
        f"<td>{summary['max']:.1f}%</td>"
        f"<td>{summary['avg']:.1f}%</td>"
        f"<td>{summary['samples']}</td>"
        "</tr>"
    )


def _trend_table(summaries):

    if not summaries:
        return "<p class=\"muted\">No data.</p>"

    rows = "".join(
        _trend_summary_row(metric_name, summary) for metric_name, summary in summaries.items()
    )

    return (
        "<table><thead><tr><th>Metric</th><th>Latest</th><th>Min</th>"
        f"<th>Max</th><th>Avg</th><th>Samples</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def render_trends_page(payload):
    """
    payload is build_trends_payload()'s return value - the exact same
    {"host", "containers", "guests"} shape `atlas trends --json`
    prints, so this page and the CLI can never disagree.
    """

    if not payload["host"] and not payload["containers"] and not payload["guests"]:

        return render_page(
            "Trends",
            "<p class=\"muted\">No monitoring history found. Run "
            "<code>atlas monitor</code> and/or <code>atlas proxmox scan</code> "
            "a few times to build history.</p>"
        )

    sections = [f"<div class=\"card\"><h2>Host</h2>{_trend_table(payload['host'])}</div>"]

    for container_name, summaries in payload["containers"].items():

        sections.append(
            f"<div class=\"card\"><h2>{_esc(container_name)}</h2>{_trend_table(summaries)}</div>"
        )

    for vmid, guest_payload in payload["guests"].items():

        name = guest_payload.get("name", "")
        metrics = {k: v for k, v in guest_payload.items() if k != "name"}

        sections.append(
            f"<div class=\"card\"><h2>{_esc(name)} ({_esc(vmid)})</h2>{_trend_table(metrics)}</div>"
        )

    return render_page("Trends", "".join(sections))


def _status_color(ok):

    return {True: "#3fb950", False: "#f85149"}.get(ok, "#8b949e")


def _svg_box(x, y, width, height, title, subtitle, color, detail=""):

    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="8" fill="#161b22" '
        f'stroke="{color}" stroke-width="2"/>'
        f'<text x="{x + width / 2}" y="{y + 22}" text-anchor="middle" fill="#e6edf3" '
        f'font-size="14" font-weight="600">{_esc(title)[:24]}</text>'
        f'<text x="{x + width / 2}" y="{y + 40}" text-anchor="middle" fill="#8b949e" '
        f'font-size="11">{_esc(subtitle)[:30]}</text>'
        + (f'<text x="{x + width / 2}" y="{y + 56}" text-anchor="middle" fill="{color}" '
           f'font-size="11">{_esc(detail)[:30]}</text>' if detail else "")
    )


def render_map_svg(topology):
    """
    Layered overview: Internet -> LAN -> one column per machine, with that
    machine's container networks / Proxmox guests hanging underneath.
    """

    docker = topology.get("docker") or {}
    proxmox = topology.get("proxmox") or {}
    brain = topology.get("brain") or {}

    public_count = sum(len(c["public"]) for members in docker.get("networks", {}).values() for c in members)

    def guest_state(guest):
        # A stopped template is normal (grey), a stopped VM/LXC is down (red).
        return None if guest.get("template") else guest["status"] == "running"

    guests = proxmox.get("guests", []) if proxmox.get("enabled") else []
    guest_children = [(g["name"], f"{g['type']} {g['vmid']}" + (" template" if g.get("template") else ""),
                       guest_state(g)) for g in guests[:6]]
    guest_detail = (f"Proxmox: {sum(g['status'] == 'running' for g in guests)}/"
                    f"{sum(not g.get('template') for g in guests)} guests up")

    columns = [{
        "title": topology.get("host", "this host"),
        "subtitle": "atlas runs here",
        "ok": docker.get("available"),
        "detail": f"{sum(len(m) for m in docker.get('networks', {}).values())} containers",
        "children": [
            (name, f"{len(members)} containers",
             all(m["status"] == "running" and m["health"] != "unhealthy" for m in members))
            for name, members in list(docker.get("networks", {}).items())[:6]
        ]
    }]

    placed_proxmox = placed_brain = False

    for host in topology.get("lan", []):

        column = {
            "title": host["name"], "subtitle": host["address"], "ok": host["reachable"],
            "detail": "ports " + ",".join(map(str, host["open_ports"])) if host["open_ports"] else "unreachable",
            "children": []
        }

        # The same machine is one box: Proxmox guests hang under their host,
        # the AI endpoint is a label on the machine that serves it.
        if guests and host["address"] == proxmox.get("host"):
            column["detail"], column["children"], placed_proxmox = guest_detail, guest_children, True

        if brain and host["address"] == brain.get("address"):
            column["subtitle"], placed_brain = f"{host['address']} - AI: {brain.get('model', '')}", True

        columns.append(column)

    if guests and not placed_proxmox:
        columns.insert(1, {"title": "Proxmox", "subtitle": proxmox.get("host", ""), "ok": True,
                           "detail": guest_detail, "children": guest_children})

    if brain and not placed_brain:
        columns.append({"title": "AI brain", "subtitle": brain.get("address", ""), "ok": brain.get("reachable"),
                        "detail": brain.get("model", ""), "children": []})

    box_w, gap, host_y, child_h = 190, 20, 150, 46
    width = max(len(columns) * (box_w + gap) + gap, 600)
    depth = max((len(c["children"]) for c in columns), default=0)
    height = host_y + 70 + depth * (child_h + 10) + 30
    lan_y = 110

    parts = [
        _svg_box(width / 2 - 110, 10, 220, 46, "Internet",
                 f"{public_count} public routes via Traefik" if public_count else "no public routes", "#58a6ff"),
        f'<line x1="{width / 2}" y1="56" x2="{width / 2}" y2="{lan_y}" stroke="#30363d" stroke-width="2"/>',
        f'<rect x="{gap}" y="{lan_y}" width="{width - 2 * gap}" height="8" rx="4" fill="#30363d"/>',
        f'<text x="{gap + 6}" y="{lan_y - 6}" fill="#8b949e" font-size="11">LAN</text>',
    ]

    for index, column in enumerate(columns):

        x = gap + index * (box_w + gap)
        color = _status_color(column["ok"])
        parts.append(f'<line x1="{x + box_w / 2}" y1="{lan_y + 8}" x2="{x + box_w / 2}" y2="{host_y}" '
                     f'stroke="#30363d" stroke-width="2"/>')
        parts.append(_svg_box(x, host_y, box_w, 64, column["title"], column["subtitle"], color, column["detail"]))

        for row, (name, subtitle, ok) in enumerate(column["children"]):
            y = host_y + 80 + row * (child_h + 10)
            parts.append(f'<line x1="{x + 14}" y1="{y - 16 if row else host_y + 64}" x2="{x + 14}" '
                         f'y2="{y + child_h / 2}" stroke="#30363d"/>')
            parts.append(_svg_box(x + 24, y, box_w - 24, child_h, name, subtitle, _status_color(ok)))

    return (f'<svg viewBox="0 0 {width} {height}" width="100%" style="max-width:{width}px" '
            f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Network map">{"".join(parts)}</svg>')


def render_map_page(topology):

    if not topology:
        return render_page("Network Map", "<p class=\"muted\">No map yet. Run: <code>atlas map</code></p>")

    docker = topology.get("docker") or {}
    responsibility = topology.get("responsibility") or {}

    network_sections = "".join(
        f"<h3>{_esc(name)} <span class=\"muted\">({len(members)})</span></h3>"
        + _list_of_dicts_table([
            {"container": m["name"], "status": m["status"], "health": m["health"] or "-",
             "public hostnames": ", ".join(m["public"]) or "-"}
            for m in members
        ])
        for name, members in docker.get("networks", {}).items()
    )

    body = (
        f"<p class=\"muted\">Snapshot {_esc(topology.get('generated_at', ''))} - refreshed by "
        "<code>atlas map</code>. Green = up/reachable, red = down, grey = unknown.</p>"
        f"<div class=\"card\">{render_map_svg(topology)}</div>"
        "<div class=\"card\"><h2>What atlas is responsible for</h2>"
        + _kv_table({
            "Containers on this host": responsibility.get("containers", "") + " - proposed as a plan, you confirm each step",
            "Proxmox guests": (responsibility.get("proxmox_guests") or "not connected")
            + (" - proposed as a plan, you confirm each step" if responsibility.get("proxmox_guests") else ""),
            "Other LAN machines": responsibility.get("lan_hosts", ""),
        })
        + "</div>"
        f"<div class=\"card\"><h2>This host: {_esc(topology.get('host', ''))}</h2>{network_sections or '<p class=muted>Docker unavailable.</p>'}</div>"
        "<div class=\"card\"><h2>Proxmox guests</h2>"
        + _list_of_dicts_table((topology.get("proxmox") or {}).get("guests", []))
        + "</div><div class=\"card\"><h2>LAN machines</h2>"
        + _list_of_dicts_table([
            {**host, "open_ports": ", ".join(map(str, host["open_ports"])) or "-"}
            for host in topology.get("lan", [])
        ])
        + "</div>"
    )

    return render_page("Network Map", body)
