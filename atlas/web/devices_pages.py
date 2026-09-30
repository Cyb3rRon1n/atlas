"""
Server-rendered pages for the device inventory: Triage, Devices, one device, Coverage.
Pure functions (data in, HTML out) like render.py. Every action is a button whose
data-* attributes say what to POST; ACTIONS_SCRIPT does the fetch and never puts
data into innerHTML.
"""

import json

from atlas.devices.store import KINDS, STATES
from atlas.web.render import _esc, render_page


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
      tags: field("tags").value.split(",").map((tag) => tag.trim()).filter(Boolean)};
    for (const key of Object.keys(fields)) {
      const value = key === "tags" ? fields[key].join(",") : fields[key];
      const originalValue = key === "tags" ? (original[key] || []).join(",") : original[key];
      if (value === originalValue) delete fields[key];
    }
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
  document.querySelectorAll("tr[data-row]").forEach((row) => {
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


def _page(title, body):

    return render_page(title, f'<p id="msg"></p>{body}{ACTIONS_SCRIPT}')


def render_triage_page(triage):

    if not triage["new"] and not triage["quiet"]:
        return _page("Triage", '<p class="muted">Nothing to triage - every device is known or ignored.</p>')

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

    return _page("Triage", body)


def render_devices_page(devices):

    rows = "".join(
        f"<tr data-row><td><a href=\"/devices/{device['id']}\">{_esc(device['name'])}</a></td>"
        f"<td>{_status(device)}</td><td>{_esc(device['state'])}</td><td>{_esc(device['kind'])}</td>"
        f"<td>{_esc(device['ip'] or '-')}</td><td>{_esc(', '.join(device['tags']))}</td>"
        f"<td>{_esc(_sources(device))}</td><td>{_esc(device['last_seen'] or '-')}</td></tr>"
        for device in devices
    )

    body = ("<p><input id=\"filter\" placeholder=\"Filter by name, ip, tag, state...\" size=\"40\"></p>"
            "<div class=\"card\"><table><thead><tr><th>name</th><th>status</th><th>state</th><th>kind</th>"
            "<th>ip</th><th>tags</th><th>seen by</th><th>last seen</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>")

    return _page(f"Devices ({len(devices)})", body)


def _options(values, selected):

    return "".join(f"<option{' selected' if value == selected else ''}>{_esc(value)}</option>" for value in values)


def render_device_page(device, devices):

    original = _esc(json.dumps({
        "name": device["name"], "kind": device["kind"], "state": device["state"],
        "tags": device["tags"], "notes": device["notes"], "important": device["important"],
    }))

    form = (
        f"<form id=\"edit\" data-original=\"{original}\" "
        "onsubmit=\"this.querySelector('[data-form]').click(); return false\">"
        f"<label>Name</label><input name=\"name\" value=\"{_esc(device['name'])}\" size=\"40\">"
        f"<label>Kind</label><select name=\"kind\">{_options(KINDS, device['kind'])}</select>"
        f"<label>State</label><select name=\"state\">{_options(STATES, device['state'])}</select>"
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

    return _page("Coverage", body)
