"""
Server-rendered pages for the device inventory: Triage, Devices, one device, Coverage.
Pure functions (data in, HTML out) like render.py. Every action is a button whose
data-* attributes say what to POST; ACTIONS_SCRIPT does the fetch and never puts
data into innerHTML.
"""

import json
from datetime import datetime
from urllib.parse import quote, urlencode

from atlas.devices.store import CONNECTIONS, KINDS, STATES
from atlas.web.icons import icon
from atlas.web.cabling_page import _ago
from atlas.web.render import section_tabs, ask_chips, _esc, render_page


ACTIONS_SCRIPT = """
<script>
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-post]");
  if (!button) return;
  const message = document.getElementById("msg");
  const body = JSON.parse(button.dataset.body || "{}");
  if (button.dataset.nameFrom) body.name = document.getElementById(button.dataset.nameFrom).value;
  if (button.dataset.kindFrom) body.kind = document.getElementById(button.dataset.kindFrom).value;
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
    const row = button.closest(".attn-row");
    if (row) { doneInPlace(row, button); return; }      // triage: no reload, so open lists stay open
    keepPlace();
    location.reload();
  } catch (error) { message.textContent = "Request failed: " + error; }
});
function doneInPlace(row, button) {
  const ignored = button.textContent.trim() === "Ignore";
  const typed = (row.querySelector("input[id^=name-]") || {}).value;
  const name = (ignored ? row.dataset.label : typed || row.dataset.label) || "the device";
  const more = row.closest("details");
  const note = document.createElement("div");
  note.className = "muted done-note";
  note.textContent = "\u2713 " + (ignored ? "Ignored " : "Saved ") + name.trim()
    + " - it moves to its group next time the page loads.";
  row.replaceWith(note);
  const heading = document.querySelector(".attn h2");
  if (heading) heading.textContent = heading.textContent.replace(/\((\d+)\)/, (_, n) => "(" + Math.max(0, n - 1) + ")");
  if (more) {
    const left = more.querySelectorAll(".attn-row").length;
    more.querySelector("summary").textContent = left ? "Show " + left + " more" : "All handled";
  }
}
const PLACE = "atlas-devices-place";
function keepPlace() {
  try { sessionStorage.setItem(PLACE, JSON.stringify({path: location.pathname, y: scrollY,
          open: [...document.querySelectorAll("details")].map((d) => d.open)})); } catch (error) {}
}
try {                                                    // after a reload: reopen the lists, scroll back
  const place = JSON.parse(sessionStorage.getItem(PLACE) || "null");
  sessionStorage.removeItem(PLACE);
  if (place && place.path === location.pathname) {
    document.querySelectorAll("details").forEach((d, i) => { if (place.open[i]) d.open = true; });
    scrollTo(0, place.y);
  }
} catch (error) {}
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


def _when(iso, now=None):
    """'2026-11-17T01:33:24.388' -> '5 min ago' (the exact time stays in the tooltip); '-' when never."""

    if not iso:
        return "-"
    try:
        seen = datetime.fromisoformat(str(iso).replace("Z", ""))
    except ValueError:
        return _esc(iso)
    return f'<time datetime="{_esc(iso)}" title="{_esc(str(iso)[:16].replace("T", " "))} UTC">{_ago(seen, now or datetime.utcnow())}</time>'


def _sources(device):

    return ", ".join(sorted({sighting["source"] for sighting in device["sightings"]}))


def _status(device):

    return f'<span class="status-{_esc(device["status"])}">{_esc(device["status"])}</span>'


def device_tabs(current):
    return section_tabs(current)


def _page(title, body, tabs=None):

    return render_page(title, f'<p id="msg"></p>{body}{ACTIONS_SCRIPT}', active="devices", tabs=tabs)


def render_triage_page(triage, hints=None):

    if not triage["new"] and not triage["quiet"]:
        return _page("Triage", '<p class="muted">Nothing to triage - every device is known or ignored.</p>',
                      device_tabs("triage"))

    hints = hints or {}
    new_rows = "".join(
        f"<tr><td><div class=\"attn-row\">{_name_and_kind(device, hints.get(device['id']))}"
        f"{_clues(device, hints.get(device['id']))}</div></td>"
        f"<td>{_esc(_sources(device))}</td>"
        f"<td>{_when(device['last_seen'])}</td><td>"
        + _button("Keep", f"/api/devices/{device['id']}", {"state": "known"}, "primary", name_from=f"name-{device['id']}",
                  kind_from=f"kind-{device['id']}")
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
                 "the device it duplicates, or Ignore it.</p><table><thead><tr><th>name and clues</th>"
                 f"<th>seen by</th><th>last seen</th><th></th></tr></thead><tbody>{new_rows}</tbody></table></div>")

    if quiet_rows:
        body += ("<div class=\"card\"><h2>Gone quiet</h2><p class=\"muted\">Known devices no source has seen in "
                 "its last two runs.</p><table><thead><tr><th>name</th><th>ip</th><th>last seen</th><th></th>"
                 f"</tr></thead><tbody>{quiet_rows}</tbody></table></div>")

    return _page("Triage", body, device_tabs("triage"))


DEVICES_CHIPS = ("Which devices are new or unknown on my network?", "Is anything on the LAN acting suspicious?",
                 "Which devices went quiet and might be offline?", "Help me name the unnamed devices.")

KIND_LABELS = {"server": ("server", "Servers"), "container-host": ("server", "Servers"), "vm": ("laptop", "Virtual machines"),
               "lxc": ("laptop", "Virtual machines"), "workstation": ("laptop", "Computers"), "phone": ("phone", "Phones & tablets"),
               "tv": ("tv", "TVs & streaming"), "iot": ("bulb", "Smart home"), "network": ("antenna", "Network gear"),
               "other": ("help", "Other")}

KIND_NAMES = {"server": "Server", "vm": "Virtual machine", "lxc": "Container (LXC)", "container-host": "Container host",
              "workstation": "Computer", "phone": "Phone or tablet", "tv": "TV or streamer", "iot": "Smart home",
              "network": "Network gear", "other": "Other"}

DEVICES_STYLE = """
<style>
.dsum { font-size:15px; margin:0 0 14px; } .dsum b { font-weight:600; }
.dcard { background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:14px 16px; margin-bottom:16px; }
.dcard.attn { border-color:var(--orange); background:var(--warn-bg); }
.dcard h2 { margin:0 0 10px; font-size:15px; border:0; padding:0; }
.tiles { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:8px; }
.tile { display:flex; gap:8px; align-items:center; padding:8px 10px; border-radius:8px; background:var(--surface2);
        border:1px solid var(--line2); color:var(--text); text-decoration:none; font-size:14px; min-width:0; }
.tile:hover { border-color:var(--blue); text-decoration:none; }
.tile .t { flex:1; min-width:0; } .tile .t div { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tile .sub { font-size:12px; color:var(--muted); }
.ddot { width:9px; height:9px; border-radius:50%; flex:none; background:var(--muted); }
.ddot.seen { background:var(--green); } .ddot.quiet { background:var(--orange); }
.attn-row { display:flex; flex-wrap:wrap; gap:8px; align-items:center; padding:6px 0; border-top:1px solid var(--warn-line); }
.attn-row:first-of-type { border-top:0; } .attn-row input { width:180px; }
.attn-row select { max-width:170px; }
.clues { flex-basis:100%; margin:-2px 0 2px 18px; font-size:13px; color:var(--muted); }
.clues b { color:var(--text); font-weight:600; }
</style>
"""


def _tile(device):

    sub = " \u00b7 ".join(x for x in (device["ip"], _sources(device)) if x)
    return (f'<a class="tile" data-row href="/devices/{device["id"]}"><span class="ddot {_esc(device["status"])}"></span>'
            f'<span class="t"><div>{_esc(device["name"])}</div><div class="sub">{_esc(sub or "-")}</div></span></a>')


def _name_and_kind(device, hint):
    """The name box (filled with the suggestion while the name is still just the IP) and a kind picker."""

    name = device["name"]
    if hint and hint["name"] and name in (device.get("ip"), "", None):
        name = hint["name"]
    kind = (hint or {}).get("kind") or device["kind"]
    options = "".join(f'<option value="{k}"{" selected" if k == kind else ""}>{_esc(KIND_NAMES.get(k, k))}</option>'
                      for k in KINDS)
    label = _esc(device["ip"] or device["name"])
    return (f'<input id="name-{device["id"]}" value="{_esc(name)}" aria-label="Name for {label}">'
            f'<select id="kind-{device["id"]}" aria-label="Kind of device for {label}">{options}</select>')


def _clues(device, hint):
    """One muted line: what atlas knows that helps say what this device is."""

    parts = []
    found = (hint or {}).get("clues") or {}
    if found.get("maker"):
        parts.append(f'made by <b>{_esc(found["maker"])}</b>')
    elif found.get("private"):
        parts.append("<b>private Wi-Fi address</b> (phones, tablets and laptops hide their maker this way)")
    said = " ".join(filter(None, (found.get("announced"), f'({found["model"]})' if found.get("model") else None)))
    if said:
        parts.append(f"says it is <b>{_esc(said)}</b>")
    if found.get("services"):
        parts.append("offers " + _esc(", ".join(found["services"][:4])))
    if found.get("unifi_name") and found["unifi_name"] != device["name"]:
        parts.append(f'UniFi calls it <b>{_esc(found["unifi_name"])}</b>')
    wifi = found.get("wifi") or {}
    if wifi:
        how = ", ".join(filter(None, (wifi.get("band"), f'{wifi["signal"]} dBm' if wifi.get("signal") else None)))
        parts.append("on Wi-Fi" + (f' <b>{_esc(wifi["ssid"])}</b>' if wifi.get("ssid") else "")
                     + (f' via {_esc(wifi["ap"])}' if wifi.get("ap") else "") + (f" ({_esc(how)})" if how else ""))
    if found.get("guest"):
        parts.append("<b>guest network</b>")
    if found.get("hostname") and found["hostname"] not in (device["name"], found.get("unifi_name")):
        parts.append(f'calls itself <b>{_esc(found["hostname"])}</b>')
    if found.get("place"):
        parts.append(f'on <b>{_esc(found["place"])}</b>')
    if found.get("ports"):
        parts.append("open: " + _esc(", ".join(found["ports"][:4])))
    parts.append(_esc(device["ip"] or "no IP"))
    first = min((s["first_seen"] for s in device["sightings"] if s.get("first_seen")), default=None)
    if first:
        parts.append(f"first seen {_esc(first[:10])}")
    return '<div class="clues">' + " \u00b7 ".join(parts) + "</div>"


def render_devices_page(devices, hints=None):
    """hints: atlas.devices.identify.for_devices() - suggested names, kinds and clues for the new devices."""

    new = [d for d in devices if d["state"] == "new"]
    quiet = [d for d in devices if d["state"] == "known" and d["status"] == "quiet"]
    ignored = [d for d in devices if d["state"] == "ignored"]
    known = [d for d in devices if d["state"] == "known"]

    hints = hints or {}
    rows = "".join(
        f'<div class="attn-row" data-row data-label="{_esc(d["ip"] or d["name"])}"><span class="ddot {_esc(d["status"])}"></span>'
        + _name_and_kind(d, hints.get(d["id"]))
        + _button("Keep", f"/api/devices/{d['id']}", {"state": "known"}, "primary", name_from=f"name-{d['id']}",
                  kind_from=f"kind-{d['id']}")
        + _button("Ignore", f"/api/devices/{d['id']}", {"state": "ignored"})
        + f' <a href="/devices/{d["id"]}">details</a>' + _clues(d, hints.get(d["id"])) + '</div>' for d in new)
    rows += "".join(
        f'<div class="attn-row" data-row data-label="{_esc(d["name"])}"><span class="ddot quiet"></span><a href="/devices/{d["id"]}">{_esc(d["name"])}</a>'
        f'<span class="muted">gone quiet \u00b7 last seen {_when(d["last_seen"])}</span>'
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
    grouped = "".join(f'<section class="dcard"><h2>{icon(label[0])}{_esc(label[1])} ({len(items)})</h2><div class="tiles">'
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


def _open_ports(ports):

    from atlas.devices.ports import port_label

    if not ports:
        return ('<div class="card"><h2>Open ports</h2><p class="muted">Not checked yet: atlas ports check '
                'runs on devices that are online during a scan.</p></div>')
    items = "".join(f"<li>{_esc(port_label(port))}</li>" for port in ports["open"])

    return ('<div class="card"><h2>Open ports</h2>'
            + (f"<ul>{items}</ul>" if items else '<p class="muted">None of the common service ports answer.</p>')
            + f'<p class="muted">Last seen at {_esc(ports["ip"])}. A newly opened port sends an alert.</p></div>')


def wiring_node(device, snapshot):
    """The wired-map node (latest wiring scan) that is this device - matched by IP or a sighting's MAC - or None."""

    from atlas.wiring import normalize_mac

    macs = {normalize_mac(s.get("mac")) for s in device["sightings"]} - {None}
    ips = {device["ip"]} | {s.get("ip") for s in device["sightings"]}
    for node in (snapshot or {}).get("nodes") or []:
        if node.get("kind") != "unknown" and ((node.get("ip") and node["ip"] in ips)
                                              or normalize_mac(node.get("mac")) in macs):
            return node
    # A gateway's LAN MAC often differs from the base MAC its controller reports: match the LAN scan's default gateway.
    gateways = [n for n in (snapshot or {}).get("nodes") or [] if n.get("kind") == "gateway"]
    if len(gateways) == 1 and any(s.get("source") == "lan" and (s.get("detail") or {}).get("gateway") is True
                                  for s in device["sightings"]):
        return gateways[0]

    return None


def _wired(node):

    if not node:
        return ""
    model = f"{_esc(node['model'])} - " if node.get("model") else ""

    box = node["id"].startswith(("s:", "u:"))          # switches/gateways/APs get a front panel there
    href = f"/cabling#fp-{quote(node['id'])}" if box else "/cabling"

    return (f"<p class=\"muted\">{model}<a href=\"{_esc(href)}\">"
            f"{'front panel' if box else 'where it plugs in'} on the Cabling page</a></p>")


def render_device_page(device, devices, ports=None, wiring=None, suggestion=None):

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
        f"<td>{_esc(sighting['hostname'] or '-')}</td><td>{_when(sighting['last_seen'])}</td><td>"
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
        f"{_when(device['last_seen']) if device['last_seen'] else 'never'}</span></p>"
        + _wired(wiring_node(device, wiring)) + _login_hint(suggestion) +
        f"<div class=\"card\"><h2>Details</h2>{form}</div>"
        + _open_ports(ports) +
        "<div class=\"card\"><h2>Where atlas saw it</h2><table><thead><tr><th>source</th><th>id</th><th>ip</th>"
        f"<th>mac</th><th>hostname</th><th>last seen</th><th></th></tr></thead><tbody>{sighting_rows}</tbody></table>"
        f"{merge}</div>"
    )

    return _page(device["name"], body)


def _login_hint(suggestion):

    if not suggestion:
        return ""
    query = urlencode({"add": suggestion["ip"], "name": suggestion["suggested_name"] or ""})

    return (f'<div class="card"><h2>Could show its ports</h2><p>This looks like a managed switch or router '
            f'({_esc("; ".join(suggestion["why"]))}). With a read-only SNMPv3 login atlas can draw every port. '
            f'<a href="/settings?{query}#switches">Add it on the Setup tab \u2192</a></p></div>')


def render_coverage_page(coverage):

    source_rows = "".join(
        f"<tr><td>{_esc(source['source'])}</td><td>{'ok' if source['ok'] else 'FAILED'}</td>"
        f"<td>{_when(source['last_run'])}</td><td>{_esc(source['seen_count'])}</td>"
        f"<td>{_when(source['last_ok']) if source['last_ok'] else 'never'}</td><td>{_esc(source['error'] or '')}</td></tr>"
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
