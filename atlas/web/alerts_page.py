"""
The Alerts page (/alerts): every problem atlas's checks see, in one place - what needs action, what is only
being watched, and what resolved in the last week. Each row links to the page to investigate it on.
"""

from atlas.web.cabling_page import _ago
from atlas.web.render import _esc, render_page

SOURCES = {"lan": "LAN watch", "host": "Host health", "certs": "Certificates", "wiring": "Cabling",
           "ports": "Open ports", "devices": "Devices", "vpn": "VPN"}

STYLE = """<style>
.alerts h2 { margin-top:1.4rem; }
.alerts ul { list-style:none; margin:0; padding:0; }
.alerts li { display:flex; gap:12px; align-items:flex-start; padding:10px 12px; border:1px solid #30363d;
  border-radius:10px; margin:6px 0; }
.alerts li .body { flex:1; min-width:0; }
.alerts li .detail { color:#8b949e; overflow-wrap:anywhere; }
.alerts li .meta { font-size:12px; color:#8b949e; margin-top:2px; }
.alerts .sev { width:10px; height:10px; border-radius:50%; margin-top:6px; flex:none; }
.alerts .problem .sev { background:#f85149; } .alerts .watch .sev { background:#d29922; }
.alerts .resolved .sev { background:#3fb950; } .alerts .resolved { opacity:.75; }
.alerts .empty { color:#8b949e; }
</style>"""


def _row(alert, now, kind):

    when = (f"resolved {_ago(alert['resolved_at'], now)}, after {_ago(alert['opened_at'], alert['resolved_at'])[:-4]}"
            if kind == "resolved" else f"since {_ago(alert['opened_at'], now)}")
    link = (f'<a href="{_esc(alert["href"])}">Investigate →</a>' if alert["href"] and kind != "resolved" else "")

    return (f'<li class="{kind}"><span class="sev"></span><div class="body"><b>{_esc(alert["title"])}</b>'
            + (f'<div class="detail">{_esc(alert["detail"])}</div>' if alert["detail"] else "")
            + f'<div class="meta">{_esc(SOURCES.get(alert["source"], alert["source"]))} · {_esc(when)}</div>'
            f'</div>{link}</li>')


def _section(title, rows, now, kind, empty):

    items = "".join(_row(alert, now, kind) for alert in rows)
    return f'<h2>{_esc(title)} <span class="muted">({len(rows)})</span></h2>' + (
        f"<ul>{items}</ul>" if rows else f'<p class="empty">{_esc(empty)}</p>')


def render_alerts_page(listing, now):

    body = (STYLE + '<div class="alerts"><p class="muted">Everything atlas\'s checks found, in one place. Problems '
            'also send an alert to your channels; watched items only show here. An item resolves by itself when '
            'the check stops seeing it.</p>'
            + _section("Needs action", listing["open"], now, "problem", "Nothing needs you right now.")
            + _section("Watching", listing["watch"], now, "watch", "Nothing being watched.")
            + _section("Resolved in the last 7 days", listing["resolved"], now, "resolved", "Nothing resolved recently.")
            + "</div>")

    return render_page("Alerts", body, active="alerts")
