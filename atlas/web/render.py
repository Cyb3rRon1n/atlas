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

        sections.append(
            f"<div class=\"card\"><h2>{_esc(title)}</h2>{_kv_table(data)}</div>"
        )

    containers = environment.get("containers") or {}

    if isinstance(containers, dict) and containers:

        # atlas discover's plugin-sourced containers land as a dict
        # keyed by container name (see atlas.discover's .update(
        # "containers", plugin_data) call) - flatten to a list of
        # {name, ...fields} rows for a normal table.
        container_rows = [
            {"name": name, **(fields if isinstance(fields, dict) else {"status": fields})}
            for name, fields in containers.items()
        ]

        sections.append(
            f"<div class=\"card\"><h2>Containers</h2>{_list_of_dicts_table(container_rows)}</div>"
        )

    guests = (environment.get("virtualization") or {}).get("guests") or []

    if guests:

        sections.append(
            f"<div class=\"card\"><h2>Proxmox Guests</h2>{_list_of_dicts_table(guests)}</div>"
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
