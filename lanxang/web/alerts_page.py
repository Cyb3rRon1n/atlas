"""
The Alerts page (/alerts): every problem atlas's checks see, in one place - what needs action, what is only
being watched, and what resolved in the last week. Each row links to the page to investigate it on.
"""

import re
from datetime import datetime

from lanxang.config.local import config_name
from lanxang.web.cabling_page import _ago
from lanxang.web.render import _esc, render_page
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
.alerts li .meta { font-size:12px; color:var(--muted); margin-top:2px; }
.alerts .sev { width:10px; height:10px; border-radius:50%; margin-top:6px; flex:none; }
.alerts .problem .sev { background:var(--red); } .alerts .watch .sev { background:var(--orange); }
.alerts .resolved .sev { background:var(--green); } .alerts .resolved { opacity:.75; }
.alerts .empty { color:var(--muted); }
.alerts .acts { display:flex; gap:6px; flex-wrap:wrap; align-items:center; justify-content:flex-end; }
.alerts .acts button, .alerts .acts select, .alerts .bar button, .alerts .bar select { font-size:12px; }
.alerts .acked { font-size:11px; border:1px solid var(--line2); border-radius:999px; padding:0 6px; margin-left:6px; }
.alerts .bar { display:flex; gap:8px; align-items:center; flex-wrap:wrap; padding:10px 12px; border:1px solid var(--line2);
  border-radius:10px; }
.alerts .bar.paused { border-color:var(--orange); }
.alerts .quiet { margin:.6rem 0; } .alerts .quiet ul { margin:.3rem 0; padding-left:18px; }
.alerts .quiet li { display:list-item; border:0; padding:2px 0; }
.alerts .quiet-form { display:flex; gap:8px; align-items:center; flex-wrap:wrap; font-size:13px; }
.alerts .quiet-form label { display:inline-flex; gap:3px; align-items:center; }
.alerts .quiet button { font-size:12px; }
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

    when = (f"resolved {_ago(alert['resolved_at'], now)}, after {_ago(alert['opened_at'], alert['resolved_at'])[:-4]}"
            if kind == "resolved" else f"since {_ago(alert['opened_at'], now)}")
    link = (f'<a href="{_esc(alert["href"])}">Investigate →</a>' if alert["href"] and kind != "resolved" else "")
    if kind != "resolved":
        pick = f"mute-{alert['id']}"
        what = "this device" if alert["device_id"] is not None else "this alert"
        link = (f'<div class="acts">{link}'
                + ("" if alert["acked_at"] else
                   f'<button data-post="/api/alerts/{alert["id"]}/ack">Acknowledge</button>')
                + f'<select id="{pick}" name="days" aria-label="Mute {what} for"><option value="1">1 day</option>'
                  f'<option value="7">7 days</option><option value="0">always</option></select>'
                  f'<button data-post="/api/alerts/{alert["id"]}/mute" data-pick="{pick}" '
                  f'title="No messages about {what}; it still shows here">Mute {what}</button></div>')
    acked = '<span class="acked">acknowledged</span>' if alert["acked_at"] and kind != "resolved" else ""

    return (f'<li class="{kind}"><span class="sev"></span><div class="body"><b>{_esc(alert["title"])}</b>{acked}'
            + (f'<div class="detail">{_esc(alert["detail"])}</div>' if alert["detail"] else "")
            + f'<div class="meta">{_esc(SOURCES.get(alert["source"], alert["source"]))} · {_esc(when)}</div>'
            f'</div>{link}</li>')


def _section(title, rows, now, kind, empty):

    items = "".join(_row(alert, now, kind) for alert in rows)
    return f'<h2>{_esc(title)} <span class="muted">({len(rows)})</span></h2>' + (
        f"<ul>{items}</ul>" if rows else f'<p class="empty">{_esc(empty)}</p>')


def _clock(moment, now):

    return moment.strftime("%H:%M UTC") if moment.date() == now.date() else moment.strftime("%b %d %H:%M UTC")


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
                                      f' <button data-post="/api/alerts/quiet-hours/{i}/remove">Remove</button>')
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
        f'<div class="acts"><button data-post="/api/alerts/quiet/{rule["id"]}/remove">Unmute</button></div></li>'
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
            + _section("Needs action", listing["open"], now, "problem", "Nothing needs you right now.")
            + _section("Watching", listing["watch"], now, "watch", "Nothing being watched.")
            + _section("Resolved in the last 7 days", listing["resolved"], now, "resolved", "Nothing resolved recently.")
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
