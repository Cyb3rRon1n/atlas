"""
Server-rendered pages for the device inventory: Triage, Devices, one device, Coverage.
Pure functions (data in, HTML out) like render.py. Every action is a button whose
data-* attributes say what to POST; ACTIONS_SCRIPT does the fetch and never puts
data into innerHTML.
"""

import json

from atlas.devices.store import CONNECTIONS, KINDS, STATES
from atlas.web.render import ask_chips, _esc, render_page


ACTIONS_SCRIPT = """
<script>
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-post]");
  if (!button) return;
  const message = document.getElementById("msg");
  const body = JSON.parse(button.dataset.body || "{}");
  if (button.dataset.nameFrom) body.name = document.getElementById(button.dataset.nameFrom).value;
  if (button.dataset.intoFrom) body.into = parseInt(document.getElementById(button.dataset.intoFrom).value, 10);
  if (button.dataset.form) {
    const formEl = document.getElementById(button.dataset.form);
    const field = (name) => formEl.elements.namedItem(name);
    const original = JSON.parse(formEl.dataset.original || "{}");
    const fields = {name: field("name").value, kind: field("kind").value, state: field("state").value,
      notes: field("notes").value, important: field("important").checked,
      tags: field("tags").value.split(",").map((tag) => tag.trim()).filter(Boolean),
      connection: field("connection").value, uplink_id: field("uplink").value};
    for (const key of Object.keys(fields)) {
      const value = key === "tags" ? fields[key].join(",") : fields[key];
      const originalValue = key === "tags" ? (original[key] || []).join(",")
        : key === "uplink_id" ? String(original.uplink_id ?? "") : original[key];
      if (value === originalValue) delete fields[key];
    }
    if ("uplink_id" in fields) fields.uplink_id = fields.uplink_id === "" ? null : parseInt(fields.uplink_id, 10);
    if (Object.keys(fields).length === 0) { message.textContent = "Nothing changed."; return; }
    Object.assign(body, fields);
  }
  try {
    const response = await fetch(button.dataset.post, {method: "POST", credentials: "same-origin",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const expired = response.status === 401 || response.status === 403 || response.redirected;
      message.textContent = data.error || ("Failed: " + response.status + (expired ? " (session expired? reload the page)" : ""));
      return;
    }
    if (button.dataset.after === "goto" && data.device_id) { location.href = "/devices/" + data.device_id; return; }
    location.reload();
  } catch (error) { message.textContent = "Request failed: " + error; }
});
const filter = document.getElementById("filter");
if (filter) filter.addEventListener("input", () => {
  const needle = filter.value.toLowerCase();
  document.querySelectorAll("[data-row]").forEach((row) => {
    row.style.display = row.textContent.toLowerCase().includes(needle) ? "" : "none";
  });
});
</script>
"""


def _button(label, url, body=None, css="", **data):

    extra = "".join(f' data-{key.replace("_", "-")}="{_esc(value)}"' for key, value in data.items())

    return (f'<button class="{css}" data-post="{_esc(url)}" data-body="{_esc(json.dumps(body or {}))}"'
            f"{extra}>{_esc(label)}</button>")


def _sources(device):

    return ", ".join(sorted({sighting["source"] for sighting in device["sightings"]}))


def _status(device):

    return f'<span class="status-{_esc(device["status"])}">{_esc(device["status"])}</span>'


def device_tabs(current):
    return [("/devices", "Devices", current == "devices"), ("/triage", "Triage", current == "triage"),
            ("/coverage", "Coverage", current == "coverage")]


def _page(title, body, tabs=None):

    return render_page(title, f'<p id="msg"></p>{body}{ACTIONS_SCRIPT}', active="devices", tabs=tabs)


def render_triage_page(triage):

    if not triage["new"] and not triage["quiet"]:
        return _page("Triage", '<p class="muted">Nothing to triage - every device is known or ignored.</p>',
                      device_tabs("triage"))

    new_rows = "".join(
        f"<tr><td><input id=\"name-{device['id']}\" value=\"{_esc(device['name'])}\"></td>"
        f"<td>{_esc(device['ip'] or '-')}</td><td>{_esc(_sources(device))}</td>"
        f"<td>{_esc(device['last_seen'] or '-')}</td><td>"
        + _button("Keep", f"/api/devices/{device['id']}", {"state": "known"}, "primary", name_from=f"name-{device['id']}")
        + (_button(f"Merge into {device['suggested_merge_name']}", f"/api/devices/{device['id']}/merge",
                   {"into": device["suggested_merge_id"]}) if device.get("suggested_merge_name") else "")
        + _button("Ignore", f"/api/devices/{device['id']}", {"state": "ignored"})
        + f" <a href=\"/devices/{device['id']}\">details</a></td></tr>"
        for device in triage["new"]
    )

    quiet_rows = "".join(
        f"<tr><td><a href=\"/devices/{device['id']}\">{_esc(device['name'])}</a></td>"
        f"<td>{_esc(device['ip'] or '-')}</td><td>{_esc(device['last_seen'] or '-')}</td><td>"
        + _button("Ignore", f"/api/devices/{device['id']}", {"state": "ignored"}) + "</td></tr>"
        for device in triage["quiet"]
    )

    body = ""

    if new_rows:
        body += ("<div class=\"card\"><h2>New devices</h2><p class=\"muted\">Name it and Keep, merge it into "
                 "the device it duplicates, or Ignore it.</p><table><thead><tr><th>name</th><th>ip</th>"
                 f"<th>seen by</th><th>last seen</th><th></th></tr></thead><tbody>{new_rows}</tbody></table></div>")

    if quiet_rows:
        body += ("<div class=\"card\"><h2>Gone quiet</h2><p class=\"muted\">Known devices no source has seen in "
                 "its last two runs.</p><table><thead><tr><th>name</th><th>ip</th><th>last seen</th><th></th>"
                 f"</tr></thead><tbody>{quiet_rows}</tbody></table></div>")

    return _page("Triage", body, device_tabs("triage"))


DEVICES_CHIPS = ("Which devices are new or unknown on my network?", "Is anything on the LAN acting suspicious?",
                 "Which devices went quiet and might be offline?", "Help me name the unnamed devices.")

KIND_LABELS = {"server": "\U0001F5A5\ufe0f Servers", "container-host": "\U0001F5A5\ufe0f Servers", "vm": "\U0001F4BB Virtual machines",
               "lxc": "\U0001F4BB Virtual machines", "workstation": "\U0001F4BB Computers", "phone": "\U0001F4F1 Phones & tablets",
               "tv": "\U0001F4FA TVs & streaming", "iot": "\U0001F4A1 Smart home", "network": "\U0001F4E1 Network gear",
               "other": "\u2754 Other"}

DEVICES_STYLE = """
<style>
.dsum { font-size:15px; margin:0 0 14px; } .dsum b { font-weight:600; }
.dcard { background:#111821; border:1px solid #222c38; border-radius:14px; padding:14px 16px; margin-bottom:16px; }
.dcard.attn { border-color:var(--orange); background:#1d1810; }
.dcard h2 { margin:0 0 10px; font-size:15px; border:0; padding:0; }
.tiles { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:8px; }
.tile { display:flex; gap:8px; align-items:center; padding:8px 10px; border-radius:8px; background:#1b2430;
        border:1px solid #2f3b4c; color:var(--text); text-decoration:none; font-size:14px; min-width:0; }
.tile:hover { border-color:var(--blue); text-decoration:none; }
.tile .t { flex:1; min-width:0; } .tile .t div { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tile .sub { font-size:12px; color:var(--muted); }
.ddot { width:9px; height:9px; border-radius:50%; flex:none; background:var(--muted); }
.ddot.seen { background:var(--green); } .ddot.quiet { background:var(--orange); }
.attn-row { display:flex; flex-wrap:wrap; gap:8px; align-items:center; padding:6px 0; border-top:1px solid #3a2f1c; }
.attn-row:first-of-type { border-top:0; } .attn-row input { width:180px; }
</style>
"""


def _tile(device):

    sub = " \u00b7 ".join(x for x in (device["ip"], _sources(device)) if x)
    return (f'<a class="tile" data-row href="/devices/{device["id"]}"><span class="ddot {_esc(device["status"])}"></span>'
            f'<span class="t"><div>{_esc(device["name"])}</div><div class="sub">{_esc(sub or "-")}</div></span></a>')


def render_devices_page(devices):

    new = [d for d in devices if d["state"] == "new"]
    quiet = [d for d in devices if d["state"] == "known" and d["status"] == "quiet"]
    ignored = [d for d in devices if d["state"] == "ignored"]
    known = [d for d in devices if d["state"] == "known"]

    rows = "".join(
        f'<div class="attn-row" data-row><span class="ddot {_esc(d["status"])}"></span>'
        f'<input id="name-{d["id"]}" value="{_esc(d["name"])}" aria-label="Name for {_esc(d["ip"] or d["name"])}">'
        f'<span class="muted">{_esc(d["ip"] or "-")} \u00b7 {_esc(_sources(d))}</span>'
        + _button("Keep", f"/api/devices/{d['id']}", {"state": "known"}, "primary", name_from=f"name-{d['id']}")
        + _button("Ignore", f"/api/devices/{d['id']}", {"state": "ignored"})
        + f' <a href="/devices/{d["id"]}">details</a></div>' for d in new)
    rows += "".join(
        f'<div class="attn-row" data-row><span class="ddot quiet"></span><a href="/devices/{d["id"]}">{_esc(d["name"])}</a>'
        f'<span class="muted">gone quiet \u00b7 last seen {_esc(d["last_seen"] or "-")}</span>'
        + _button("Ignore", f"/api/devices/{d['id']}", {"state": "ignored"}) + "</div>" for d in quiet)
    shown = 8   # the rest fold so the page doesn't start with a wall of IPs
    row_list = rows.split('<div class="attn-row"')[1:]
    rows = "".join('<div class="attn-row"' + r for r in row_list[:shown])
    if len(row_list) > shown:
        rows += (f'<details><summary class="muted">Show {len(row_list) - shown} more</summary>'
                 + "".join('<div class="attn-row"' + r for r in row_list[shown:]) + "</details>")
    attention = (f'<section class="dcard attn"><h2>Needs attention ({len(new) + len(quiet)})</h2>'
                 f'<p class="muted">New: give it a name and Keep, or Ignore it. Quiet: known but not seen lately.</p>{rows}</section>'
                 if rows else '<p class="muted">\u2713 Nothing to triage - every device is named or ignored.</p>')

    groups = {}
    for d in known:
        groups.setdefault(KIND_LABELS.get(d["kind"], KIND_LABELS["other"]), []).append(d)
    grouped = "".join(f'<section class="dcard"><h2>{_esc(label)} ({len(items)})</h2><div class="tiles">'
                      + "".join(_tile(d) for d in sorted(items, key=lambda d: d["name"].lower())) + "</div></section>"
                      for label, items in sorted(groups.items(), key=lambda kv: -len(kv[1])))
    hidden = (f'<details class="dcard"><summary>Ignored ({len(ignored)})</summary><div class="tiles" style="margin-top:10px">'
              + "".join(_tile(d) for d in ignored) + "</div></details>") if ignored else ""

    body = (DEVICES_STYLE + ask_chips(DEVICES_CHIPS)
            + f'<p class="dsum"><b>{len(devices)}</b> devices \u00b7 <b>{len(new)}</b> new \u00b7 <b>{len(quiet)}</b> quiet'
              f' \u00b7 <b>{len(ignored)}</b> ignored</p>'
            + attention
            + '<p><input id="filter" placeholder="Filter by name, ip, source..." size="40"></p>'
            + grouped + hidden)

    return _page(f"Devices ({len(devices)})", body, device_tabs("devices"))


def _options(values, selected):

    return "".join(f"<option{' selected' if value == selected else ''}>{_esc(value)}</option>" for value in values)


def render_device_page(device, devices):

    # The form edits the stored value, which is "unknown" whenever the shown one is a guess.
    connection = "unknown" if device["connection_guessed"] else device["connection"]
    original = _esc(json.dumps({
        "name": device["name"], "kind": device["kind"], "state": device["state"],
        "tags": device["tags"], "notes": device["notes"], "important": device["important"],
        "connection": connection, "uplink_id": device["uplink_id"],
    }))

    def is_router(other):
        return any(sighting.get("source") == "lan" and (sighting.get("detail") or {}).get("gateway") is True
                   for sighting in other.get("sightings", []))

    uplinks = "".join(
        f"<option value=\"{other['id']}\"{' selected' if other['id'] == device['uplink_id'] else ''}>{_esc(other['name'])}</option>"
        for other in devices
        if other["id"] != device["id"] and (other["kind"] in ("network", "server")
                                             or other["id"] == device["uplink_id"] or is_router(other))
    )
    guess = "guessed wireless" if device["connection_guessed"] else ""

    form = (
        f"<form id=\"edit\" data-original=\"{original}\" "
        "onsubmit=\"this.querySelector('[data-form]').click(); return false\">"
        f"<label>Name</label><input name=\"name\" value=\"{_esc(device['name'])}\" size=\"40\">"
        f"<label>Kind</label><select name=\"kind\">{_options(KINDS, device['kind'])}</select>"
        f"<label>State</label><select name=\"state\">{_options(STATES, device['state'])}</select>"
        f"<label>Connection</label><select name=\"connection\">{_options(CONNECTIONS, connection)}</select> "
        f"<span class=\"muted\">{_esc(guess)}</span>"
        "<label>Connected to</label><select name=\"uplink\">"
        f"<option value=\"\"{'' if device['uplink_id'] is not None else ' selected'}>router / not set</option>{uplinks}</select>"
        f"<label>Tags (comma separated)</label><input name=\"tags\" value=\"{_esc(', '.join(device['tags']))}\" size=\"40\">"
        f"<label>Notes</label><textarea name=\"notes\">{_esc(device['notes'])}</textarea>"
        f"<label><input type=\"checkbox\" name=\"important\"{' checked' if device['important'] else ''}> "
        "Important - alert me on Signal when it goes quiet</label><p>"
        + _button("Save", f"/api/devices/{device['id']}", {}, "primary", form="edit")
        + "</p></form>"
    )

    several = len(device["sightings"]) > 1
    sighting_rows = "".join(
        f"<tr><td>{_esc(sighting['source'])}</td><td>{_esc(sighting['external_id'])}</td>"
        f"<td>{_esc(sighting['ip'] or '-')}</td><td>{_esc(sighting['mac'] or '-')}</td>"
        f"<td>{_esc(sighting['hostname'] or '-')}</td><td>{_esc(sighting['last_seen'] or '-')}</td><td>"
        + (_button("Split out", f"/api/sightings/{sighting['id']}/split", {}, after="goto") if several else "")
        + "</td></tr>"
        for sighting in device["sightings"]
    )

    others = "".join(f"<option value=\"{other['id']}\">{_esc(other['name'])}</option>"
                     for other in devices if other["id"] != device["id"])
    merge = (f"<p>Merge this device into <select id=\"merge-into\">{others}</select> "
             + _button("Merge", f"/api/devices/{device['id']}/merge", {}, into_from="merge-into", after="goto")
             + "</p>") if others else ""

    body = (
        f"<p>{_status(device)} <span class=\"muted\">- {_esc(device['ip'] or 'no ip')} - last seen "
        f"{_esc(device['last_seen'] or 'never')}</span></p>"
        f"<div class=\"card\"><h2>Details</h2>{form}</div>"
        "<div class=\"card\"><h2>Where atlas saw it</h2><table><thead><tr><th>source</th><th>id</th><th>ip</th>"
        f"<th>mac</th><th>hostname</th><th>last seen</th><th></th></tr></thead><tbody>{sighting_rows}</tbody></table>"
        f"{merge}</div>"
    )

    return _page(device["name"], body)


def render_coverage_page(coverage):

    source_rows = "".join(
        f"<tr><td>{_esc(source['source'])}</td><td>{'ok' if source['ok'] else 'FAILED'}</td>"
        f"<td>{_esc(source['last_run'] or '-')}</td><td>{_esc(source['seen_count'])}</td>"
        f"<td>{_esc(source['last_ok'] or 'never')}</td><td>{_esc(source['error'] or '')}</td></tr>"
        for source in coverage["sources"]
    )

    def listing(devices, empty):
        if not devices:
            return f"<p class=\"muted\">{empty}</p>"
        return "<ul>" + "".join(f"<li><a href=\"/devices/{device['id']}\">{_esc(device['name'])}</a> "
                                f"<span class=\"muted\">{_esc(device['ip'] or '')}</span></li>"
                                for device in devices) + "</ul>"

    body = (
        "<div class=\"card\"><h2>Sources</h2><table><thead><tr><th>source</th><th>last run</th><th>at</th>"
        f"<th>devices seen</th><th>last success</th><th>error</th></tr></thead><tbody>{source_rows}</tbody></table>"
        "<p class=\"muted\">A failed run never makes devices look quiet - they keep their last status.</p></div>"
        f"<div class=\"card\"><h2>Gone quiet</h2>{listing(coverage['quiet'], 'None - everything is being seen.')}</div>"
        "<div class=\"card\"><h2>Known but invisible</h2><p class=\"muted\">In your config, never seen by a scan.</p>"
        f"{listing(coverage['invisible'], 'None.')}</div>"
    )

    return _page("Coverage", body, device_tabs("coverage"))
