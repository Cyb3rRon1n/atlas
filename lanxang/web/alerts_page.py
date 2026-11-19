"""
The Alerts page (/alerts): every problem atlas's checks see, in one place - what needs action, what is only
being watched, and what resolved in the last week. Each row links to the page to investigate it on.
"""

import re
from datetime import datetime

from lanxang.config.local import config_name
from lanxang.web.icons import icon
from lanxang.web.render import _esc, empty_state, render_page, when
from lanxang.clock import utcnow

SOURCES = {"lan": "LAN watch", "host": "Host health", "certs": "Certificates", "wiring": "Cabling",
           "ports": "Open ports", "devices": "Devices", "vpn": "VPN"}

STYLE = """<style>
.alerts h2 { margin-top:1.4rem; }
.alerts ul { list-style:none; margin:0; padding:0; }
.alerts li { display:flex; gap:12px; align-items:flex-start; padding:10px 12px; border:1px solid var(--line2);
  border-radius:10px; margin:6px 0; }
.alerts li .body { flex:1; min-width:0; }
.alerts li .detail { color:var(--muted); overflow-wrap:anywhere; }
.alerts li .meta { font-size:.75rem; color:var(--muted); margin-top:2px; }
.alerts .sev { display:inline-flex; align-items:center; flex:none; min-width:6.5rem; margin-top:1px;
  font-size:.75rem; font-weight:600; }
.alerts .problem .sev { color:var(--bad-text); } .alerts .watch .sev { color:var(--warn-text); }
.alerts .resolved .sev { color:var(--ok-text); } .alerts .resolved { opacity:.75; }
.alerts .none { margin-top:1.2rem; }
.alerts .acts { display:flex; gap:6px; flex-wrap:wrap; align-items:center; justify-content:flex-end; }
.alerts .acked { font-size:.6875rem; border:1px solid var(--line2); border-radius:999px; padding:0 6px; margin-left:6px; }
.alerts .bar { display:flex; gap:8px; align-items:center; flex-wrap:wrap; padding:10px 12px; border:1px solid var(--line2);
  border-radius:10px; }
.alerts .bar.paused { border-color:var(--orange); }
.alerts .quiet { margin:.6rem 0; } .alerts .quiet ul { margin:.3rem 0; padding-left:18px; }
.alerts .quiet li { display:list-item; border:0; padding:2px 0; }
.alerts .quiet-form { display:flex; gap:8px; align-items:center; flex-wrap:wrap; font-size:.8125rem; }
.alerts .quiet-form label { display:inline-flex; gap:3px; align-items:center; }
@media (max-width: 640px) { .alerts li { flex-wrap:wrap; } .alerts .acts { width:100%; justify-content:flex-start; } }
</style>"""

SCRIPT = """<script>
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-post]");
  if (!button) return;
  event.preventDefault();
  const body = {};
  const pick = button.dataset.pick && document.getElementById(button.dataset.pick);
  if (pick) body[pick.name] = Number(pick.value);
  button.disabled = true;
  const response = await fetch(button.dataset.post, {method: "POST", credentials: "same-origin",
    headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  if (response.ok) location.reload();
  else { button.disabled = false; const data = await response.json().catch(() => ({}));
         alertError.textContent = data.error || ("Failed: " + response.status); }
});
const alertError = document.getElementById("alert-error");
document.getElementById("quiet-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  const body = {start: form.start.value, end: form.end.value,
                days: [...form.querySelectorAll("input[name=day]:checked")].map((box) => box.value),
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || ""};
  const response = await fetch("/api/alerts/quiet-hours/add", {method: "POST", credentials: "same-origin",
    headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  if (response.ok) location.reload();
  else { const data = await response.json().catch(() => ({})); alertError.textContent = data.error || ("Failed: " + response.status); }
});
</script>"""

ACTION = re.compile(r"^/api/alerts/(?:(\d+)/(ack|mute)|(pause|resume)|quiet/(\d+)/remove)$")
QUIET_REMOVE = re.compile(r"^/api/alerts/quiet-hours/(\d+)/remove$")


def _row(alert, now, kind):

    said = (f"resolved {when(alert['resolved_at'], now)}, after {_lasted(alert['opened_at'], alert['resolved_at'])}"
            if kind == "resolved" else f"since {when(alert['opened_at'], now)}")
    link = (f'<a class="btn primary sm" href="{_esc(alert["href"])}">Investigate</a>' if alert["href"] and kind != "resolved" else "")
    if kind != "resolved":
        pick = f"mute-{alert['id']}"
        what = "this device" if alert["device_id"] is not None else "this alert"
        link = (f'<div class="acts">{link}'
                + ("" if alert["acked_at"] else
                   f'<button class="sm" data-post="/api/alerts/{alert["id"]}/ack">Acknowledge</button>')
                + f'<select class="sm" id="{pick}" name="days" aria-label="Mute {what} for"><option value="1">1 day</option>'
                  f'<option value="7">7 days</option><option value="0">always</option></select>'
                  f'<button class="sm" data-post="/api/alerts/{alert["id"]}/mute" data-pick="{pick}" '
                  f'title="No messages about {what}; it still shows here">Mute {what}</button></div>')
    acked = '<span class="acked">acknowledged</span>' if alert["acked_at"] and kind != "resolved" else ""

    mark, word = SEVERITY[kind]
    return (f'<li class="{kind}"><span class="sev">{icon(mark)}{word}</span><div class="body"><b>{_esc(alert["title"])}</b>{acked}'
            + (f'<div class="detail">{_esc(alert["detail"])}</div>' if alert["detail"] else "")
            + f'<div class="meta">{_esc(SOURCES.get(alert["source"], alert["source"]))} · <span{_opened(alert)}>{said}</span></div>'
            f'</div>{link}</li>')


# Status is never colour alone: each row's mark is an icon plus a word.
SEVERITY = {"problem": ("alert", "Problem"), "watch": ("search", "Watching"), "resolved": ("check", "Resolved")}


def _lasted(start, end):
    """How long an alert was open: '12 min', '3 h', '2 days'."""

    minutes = max(0, int((end - start).total_seconds() // 60))
    return f"{minutes} min" if minutes < 120 else f"{minutes // 60} h" if minutes < 48 * 60 else f"{minutes // 1440} days"


def _sections(listing, now):
    """Only the sections that have rows get a heading; the empty ones share one muted line, or one empty state."""

    parts = (("Needs action", "open", "problem", "nothing needs action"), ("Watching", "watch", "watch", "nothing watched"),
             ("Resolved in the last 7 days", "resolved", "resolved", "nothing resolved this week"))
    if not any(listing[key] for _, key, _, _ in parts):
        return empty_state("check", "All clear", "Nothing needs you, nothing is being watched, and nothing resolved "
                           "in the last 7 days.")
    html, none = "", []
    for title, key, kind, empty in parts:
        rows = listing[key]
        if rows:
            html += (f'<h2>{_esc(title)} <span class="muted">({len(rows)})</span></h2><ul>'
                     + "".join(_row(alert, now, kind) for alert in rows) + "</ul>")
        else:
            none.append(empty)
    return html + (f'<p class="none muted">{_esc(" · ".join(none).capitalize())}.</p>' if none else "")


def _opened(alert):
    """A tooltip with when the alert opened, in the display: settings."""

    from lanxang.clock import parse, stamp
    from lanxang.web import render

    moment = parse(alert["opened_at"]) if alert.get("opened_at") else None
    return f' title="Opened {_esc(stamp(moment, render.DISPLAY))}"' if moment else ""


def _clock(moment, now):

    from lanxang.clock import local, stamp
    from lanxang.web import render

    shown = render.DISPLAY
    return stamp(moment, shown, date=local(moment, shown)[0].date() != local(now, shown)[0].date())


def _quiet_hours(notify, now):
    """The weekly quiet-hours list and a small form to add one (times in the browser's time zone)."""

    from lanxang.alerts.quiet import DAYS, active, describe

    if notify is None:
        return ""
    from lanxang.config import local
    locked = local.locked(("notify", "quiet_hours"))
    windows = notify.quiet_hours
    zone = notify.timezone or "UTC"
    on = windows and active(windows, notify.timezone, now)
    items = "".join(
        f'<li>{_esc(describe(w))}' + ("" if locked else
                                      f' <button class="danger" data-post="/api/alerts/quiet-hours/{i}/remove">Remove</button>')
        + "</li>" for i, w in enumerate(windows))
    boxes = "".join(f'<label><input type="checkbox" name="day" value="{d}" checked>{d.capitalize()}</label>'
                    for d in DAYS)
    form = ("" if locked else
            f'<form id="quiet-form" class="quiet-form">{boxes}<input name="start" type="time" value="23:00" '
            'aria-label="From" required> to <input name="end" type="time" value="07:00" aria-label="Until" required>'
            '<button type="submit">Add quiet hours</button></form>')
    return (f'<details class="quiet"{" open" if windows else ""}><summary>Quiet hours'
            + (f" — on now" if on else f" ({len(windows)})" if windows else "") + '</summary>'
            '<p class="muted">No messages go out in these windows (problems still show here), e.g. while the '
            f'Sunday updates run. Times are {_esc(zone)}.</p>'
            + (f"<ul>{items}</ul>" if items else "") + form + "</details>")


def _controls(listing, now, notify=None):

    paused = listing.get("paused_until")
    if paused:
        bar = (f'<div class="bar paused">⏸ Alerts are paused until {_esc(_clock(paused, now))}. Problems still '
               'show here; nothing is sent. <button data-post="/api/alerts/resume">Resume now</button></div>')
    else:
        bar = ('<div class="bar">Doing maintenance? <select id="pause-hours" name="hours" aria-label="Pause for">'
               '<option value="1">1 hour</option><option value="4">4 hours</option><option value="24">24 hours</option>'
               '</select><button data-post="/api/alerts/pause" data-pick="pause-hours">Pause alerts</button></div>')
    rules = listing.get("muted") or []
    muted = "".join(
        f'<li class="watch"><span class="sev"></span><div class="body"><b>{_esc(rule["label"])}</b><div class="meta">'
        f'muted {"until " + _esc(_clock(rule["until"], now)) if rule["until"] else "always"}</div></div>'
        f'<div class="acts"><button class="sm" data-post="/api/alerts/quiet/{rule["id"]}/remove">Unmute</button></div></li>'
        for rule in rules)

    return bar + _quiet_hours(notify, now) + '<p id="alert-error" class="bad" role="status"></p>' + (
        f'<details><summary>Muted ({len(rules)})</summary><ul>{muted}</ul></details>' if rules else "")


def handle_post(path, body):
    """(status, payload) for the Alerts page's buttons, or None when the path isn't ours."""

    from lanxang.alerts import AlertStore

    if path == "/api/alerts/quiet-hours/add" or QUIET_REMOVE.match(path):
        return _quiet_post(path, body if isinstance(body, dict) else {})
    match = ACTION.match(path)
    if not match:
        return None
    alert_id, action, global_action, rule_id = match.groups()
    body = body if isinstance(body, dict) else {}
    store, now = AlertStore(), utcnow()

    if global_action == "pause":
        hours = body.get("hours")
        if not isinstance(hours, (int, float)) or isinstance(hours, bool) or not 0 < hours <= 24 * 7:
            return 400, {"error": "pause for 1 hour to 7 days"}
        store.pause(hours, now)
        return 200, {"ok": True}
    if global_action == "resume":
        store.unquiet()
        return 200, {"ok": True}
    if rule_id:
        store.unquiet(int(rule_id))
        return 200, {"ok": True}
    if action == "ack":
        return (200, {"ok": True}) if store.ack(int(alert_id), now) else (404, {"error": "no such alert"})
    days = body.get("days")
    if not isinstance(days, int) or isinstance(days, bool) or not 0 <= days <= 365:
        return 400, {"error": "mute for 1 to 365 days, or 0 for always"}
    return (200, {"ok": True}) if store.mute(int(alert_id), days, now) else (404, {"error": "no such alert"})


def render_alerts_page(listing, now, notify=None):

    body = (STYLE + '<div class="alerts"><p class="muted">Everything Lanxang\'s checks found, in one place. Problems '
            'also send an alert to your channels; watched items only show here. An item resolves by itself when '
            'the check stops seeing it. <b>Acknowledge</b> says you\'ve seen it; <b>Mute</b> stops messages about '
            'it (or its device) but keeps it listed.</p>' + _controls(listing, now, notify)
            + _sections(listing, now)
            + "</div>" + SCRIPT)

    return render_page("Alerts", body, active="alerts")


def _quiet_post(path, body):

    from lanxang.alerts.quiet import DAYS, minutes
    from lanxang.config import local

    if local.locked(("notify", "quiet_hours")):
        return 400, {"error": f"Quiet hours are set in {config_name()} — edit them there."}
    saved = list(((local.read_settings().get("notify") or {}).get("quiet_hours")) or [])
    removing = QUIET_REMOVE.match(path)
    if removing:
        index = int(removing.group(1))
        if index >= len(saved):
            return 404, {"error": "No such quiet hours."}
        del saved[index]
        local.save_settings({"notify": {"quiet_hours": saved or None}})
        return 200, {"ok": True}
    start, end = str(body.get("start") or ""), str(body.get("end") or "")
    try:
        minutes(start), minutes(end)
    except (ValueError, TypeError):
        return 400, {"error": "Enter a start and end time, like 23:00 and 07:00."}
    if start == end:
        return 400, {"error": "Start and end are the same time."}
    days = [d for d in DAYS if d in (body.get("days") or [])]
    if not days:
        return 400, {"error": "Pick at least one day."}
    patch = {"quiet_hours": saved + [{"start": start, "end": end, "days": [] if len(days) == 7 else days}]}
    zone = str(body.get("timezone") or "")
    if zone and not local.locked(("notify", "timezone")):
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(zone)
            patch["timezone"] = zone
        except Exception:
            pass
    local.save_settings({"notify": patch})
    return 200, {"ok": True}
