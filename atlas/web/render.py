"""
Pure HTML-rendering functions for the web view (`atlas web`).
Every function here takes already-fetched data (from KnowledgeQueries/
build_trends_payload) and returns a plain HTML string - no I/O, no
database access, so these are unit-testable the same way format_change()/
_trend_summary() already are elsewhere in this codebase. These pages are
pure renderers; the write path (device edit/merge/split) lives in api.py
and server.py.
"""

from html import escape

from atlas.devices.store import CONNECTIONS, KINDS, STATES
from atlas.web.chat_assets import CHAT_SCRIPT, CHAT_STYLE, DRAWER_HTML, DRAWER_STYLE


PAGE_STYLE = """
  body { font-family: system-ui, sans-serif; background: #0d1117; color: #e6edf3;
         margin: 0; padding: 2rem; line-height: 1.5; }
  a { color: #58a6ff; text-decoration: none; }
  a:hover { text-decoration: underline; }
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
  button { background: #21262d; color: #e6edf3; border: 1px solid #30363d; border-radius: 6px;
           padding: 0.25rem 0.7rem; margin: 0 0.25rem 0.25rem 0; cursor: pointer; font: inherit; }
  button:hover { border-color: #58a6ff; }
  button.primary { background: #1f6feb; border-color: #1f6feb; }
  input, select, textarea { background: #0d1117; color: #e6edf3; border: 1px solid #30363d;
           border-radius: 6px; padding: 0.25rem 0.5rem; font: inherit; }
  textarea { width: 100%; min-height: 4rem; }
  label { display: block; margin: 0.5rem 0 0.2rem; color: #8b949e; font-size: 0.85rem; }
  .status-seen { color: #3fb950; } .status-quiet { color: #d29922; } .status-invisible { color: #8b949e; }
  #msg { color: #f85149; min-height: 1.2rem; }
"""

SHELL_STYLE = """
:root { --bg:#0e131a; --surface:#151c25; --surface2:#1b2430; --line:#263140; --text:#e7edf3; --muted:#a3b0bd;
        --blue:#5aa7f0; --green:#43c08f; --orange:#f0a23a; --red:#f47a5c; }
body { margin:0; padding:0; background:var(--bg); color:var(--text);
       font-family: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif; }
.topbar { display:flex; flex-wrap:wrap; align-items:center; gap:16px; padding:12px 24px;
          background:#111821; border-bottom:1px solid #222c38; }
.topbar .brand { font-weight:600; letter-spacing:.14em; }
.topbar nav.main { display:flex; flex-wrap:wrap; gap:4px; }
.topbar nav.main a, .topbar .chat-link { padding:10px 14px; border-radius:8px; color:var(--muted); text-decoration:none; }
.topbar nav.main a[aria-current="page"] { background:var(--surface2); color:var(--text); }
.topbar .spacer { flex:1; }
.page { padding:16px 24px 32px; }
.tabs { display:flex; flex-wrap:wrap; gap:4px; margin:0 0 16px; border-bottom:1px solid var(--line); }
.tabs a { padding:10px 14px; color:var(--muted); text-decoration:none; border-bottom:2px solid transparent; }
.tabs a[aria-current="page"] { color:var(--text); border-bottom-color:var(--blue); }
.chips { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 16px; }
.chips button { font:inherit; font-size:13px; padding:6px 12px; border-radius:999px; margin:0; }
"""

PAGE_STYLE += SHELL_STYLE


def _esc(value):
    return escape(str(value))


NAV = [("/", "Home", "home"), ("/posture", "Posture", "posture"), ("/overview", "Hosts", "hosts"),
       ("/devices", "Devices", "devices"), ("/map", "Network", "lan"), ("/history", "History", "history")]

HOSTS_TABS = (("/overview", "Overview"), ("/trends", "Trends"))


def _hosts_tabs(current):

    return [(href, label, href == current) for href, label in HOSTS_TABS]


def render_page(title, body_html, active="", tabs=None, drawer=True):

    here = ' aria-current="page"'   # built outside the f-strings: backslashes in f-string expressions need 3.12
    links = "".join(
        f'<a href="{href}"{here if key == active else ""}>{_esc(label)}</a>'
        for href, label, key in NAV
    )
    tab_html = ""
    if tabs:
        tab_html = '<nav class="tabs" aria-label="Section">' + "".join(
            f'<a href="{href}"{here if current else ""}>{_esc(label)}</a>'
            for href, label, current in tabs) + "</nav>"

    chat_link = (
        '<button id="chat-toggle" class="chat-link" aria-controls="chat-drawer">Chat</button>' if drawer
        else "<a class=\"chat-link\" href=\"/chat\">Chat</a>"
    )
    drawer_html = CHAT_STYLE + DRAWER_STYLE + DRAWER_HTML + CHAT_SCRIPT if drawer else ""

    return (
        "<!doctype html>\n"
        "<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>Atlas - {_esc(title)}</title>"
        f"<style>{PAGE_STYLE}</style></head><body>"
        "<header class=\"topbar\"><span class=\"brand\">ATLAS</span>"
        f"<nav class=\"main\" aria-label=\"Main\">{links}</nav>"
        "<span class=\"spacer\"></span>"
        f"{chat_link}</header>"
        f"<div class=\"shell{' docked' if drawer else ''}\">"
        f"<main class=\"page\"><h1>{_esc(title)}</h1>{tab_html}{body_html}</main>"
        f"{drawer_html}</div>"
        "</body></html>"
    )


def ask_chips(questions):
    """
    One-click questions that fill the docked chat (window.atlasAsk), or open /chat when there is no panel.
    """

    return '<div class="chips" aria-label="Ask Atlas">' + "".join(
        f'<button data-ask="{_esc(q)}">{_esc(q)}</button>' for q in questions) + "</div>" + (
        "<script>document.querySelectorAll('[data-ask]').forEach((b) => b.addEventListener('click', () => {"
        " const q = b.dataset.ask; if (window.atlasAsk) window.atlasAsk(q); else location.href = '/chat?q=' +"
        " encodeURIComponent(q); }));</script>")


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

    overview_tabs = _hosts_tabs("/overview")

    if environment is None:

        return render_page(
            "Overview",
            "<p class=\"muted\">No inventory found. Run <code>atlas discover</code> first.</p>",
            active="hosts", tabs=overview_tabs
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

    return render_page("Overview", header + "".join(sections), active="hosts", tabs=overview_tabs)


def render_history_page(events):
    """
    events is KnowledgeQueries().recent_events()'s return value - a
    list of EventRecord ORM objects, same as `atlas history` prints.
    """


    if not events:

        return render_page(
            "History",
            "<p class=\"muted\">No historical events found.</p>",
            active="history"
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

    return render_page("History", body, active="history")


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

    trends_tabs = _hosts_tabs("/trends")

    if not payload["host"] and not payload["containers"] and not payload["guests"]:

        return render_page(
            "Trends",
            "<p class=\"muted\">No monitoring history found. Run "
            "<code>atlas monitor</code> and/or <code>atlas proxmox scan</code> "
            "a few times to build history.</p>",
            active="hosts", tabs=trends_tabs
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

    return render_page("Trends", "".join(sections), active="hosts", tabs=trends_tabs)


def _count(number, word):

    return f"{number} {word}" + ("" if number == 1 else "s")


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


def _posture_block(posture):

    items = {item["key"]: item for item in posture["strip"]}
    warn = next((item for item in posture["strip"] if item["state"] == "warn"), None)

    if warn:
        state, message = "warn", f"{warn['label']}: {warn['value']}"
    elif items["new"]["state"] == "review" and posture["review"]:
        first = posture["review"][0]
        org = first["org"] or first["asn_key"]
        cc = first["cc"] or "?"
        state, message = "review", f"{first['source']} reached {org} ({cc})"
    elif items["ingress"]["state"] == "unknown":
        state, message = "unknown", "No posture data yet"
    else:
        state, message = "ok", "All good"

    return {"state": state, "tunnel": items["ingress"]["value"], "vpn": items["vpn"]["value"],
            "routes": len(posture["exposure"]), "blocked": items["blocked"]["value"],
            "review_count": len(posture["review"]), "message": message, "link": "/posture"}


def build_summary(topology, devices=(), posture=None):
    """
    One small JSON object for a dashboard tile (e.g. Homepage's customapi
    widget): counts from the latest saved network map and the device
    inventory, plus a single status word. Nothing is queried live.
    """

    counts = {
        "to_triage": sum(device["state"] == "new" or (device["state"] == "known" and device["status"] == "quiet")
                         for device in devices),
        "devices_quiet": sum(device["status"] == "quiet" and device["state"] != "ignored" for device in devices),
    }
    posture_extra = {"posture": _posture_block(posture)} if posture else {}

    if not topology:
        return {"status": "no map yet - run atlas map", **counts, **posture_extra}

    containers = [c for members in ((topology.get("docker") or {}).get("networks") or {}).values() for c in members]
    guests = [g for g in (topology.get("proxmox") or {}).get("guests", []) if not g.get("template")]
    hosts = topology.get("lan", [])

    down_hosts = [h["name"] for h in hosts if not h["reachable"]]
    stopped = [c["name"] for c in containers if c["status"] != "running"]
    unhealthy = [c["name"] for c in containers if c["health"] == "unhealthy"]
    brain = topology.get("brain") or {}

    return {
        "status": "degraded" if (down_hosts or unhealthy) else "ok",
        "generated_at": topology.get("generated_at"),
        "containers_running": len(containers) - len(stopped),
        "containers_total": len(containers),
        "containers_unhealthy": unhealthy,
        "guests_running": sum(g["status"] == "running" for g in guests),
        "guests_total": len(guests),
        "hosts_up": len(hosts) - len(down_hosts),
        "hosts_total": len(hosts),
        "hosts_down": down_hosts,
        "ai_reachable": brain.get("reachable"),
        **counts,
        **posture_extra,
    }
