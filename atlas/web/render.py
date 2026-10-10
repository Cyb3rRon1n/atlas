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

MAP_STYLE = """
  .map-wrap { display: flex; gap: 1rem; align-items: flex-start; }
  #graph { flex: 1; min-width: 0; height: 70vh; min-height: 420px; background: #0d1117; border: 1px solid #30363d; border-radius: 8px; }
  #panel { flex: 0 0 320px; background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1rem; }
  #panel h2 { margin-top: 0; }
  #panel input, #panel select, #panel textarea { width: 100%; box-sizing: border-box; }
  #panel input[type=checkbox] { width: auto; }
  .map-legend span { margin-right: 1rem; }
  @media (max-width: 900px) { .map-wrap { flex-direction: column; } #panel { width: 100%; box-sizing: border-box; } }
"""

PAGE_STYLE += MAP_STYLE

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
"""

PAGE_STYLE += SHELL_STYLE


def _esc(value):
    return escape(str(value))


NAV = [("/", "Home", "home"), ("/posture", "Posture", "posture"), ("/overview", "Hosts", "hosts"),
       ("/devices", "Devices", "devices"), ("/map", "LAN map", "lan"), ("/history", "History", "history")]

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


MAP_SCRIPT = """
<script>
const panel = document.getElementById("panel");
const message = document.getElementById("panel-msg");
const graphMsg = document.getElementById("graph-msg");
let current = null;
let cy = null;
let graph = null;

const STYLE = [
  {selector: "node", style: {"label": "data(label)", "color": "#e6edf3", "font-size": 11, "text-wrap": "wrap",
    "text-valign": "bottom", "text-margin-y": 4, "background-color": "#8b949e", "width": 22, "height": 22,
    "border-width": 2, "border-color": "#30363d"}},
  {selector: ".fixed", style: {"shape": "round-rectangle", "background-color": "#1f6feb", "width": 60, "height": 24,
    "text-valign": "center", "text-margin-y": 0}},
  {selector: ".host", style: {"shape": "round-rectangle", "background-opacity": 0.08, "text-valign": "top",
    "padding": 12, "border-width": 2}},
  {selector: ".network", style: {"shape": "round-rectangle", "width": 16, "height": 16}},
  {selector: ".status-seen", style: {"background-color": "#3fb950", "border-color": "#3fb950"}},
  {selector: ".status-quiet", style: {"background-color": "#d29922", "border-color": "#d29922"}},
  {selector: ".status-invisible", style: {"background-color": "#8b949e", "border-color": "#8b949e"}},
  {selector: ".alert", style: {"background-color": "#f85149", "border-color": "#f85149"}},
  {selector: ".important", style: {"border-width": 4}},
  {selector: ".router, .infra", style: {"shape": "diamond"}},
  {selector: ".conn-unknown", style: {"border-style": "dotted"}},
  {selector: ".conn-wireless", style: {"opacity": 0.6}},
  {selector: ".state-new", style: {"border-style": "dashed", "border-color": "#58a6ff"}},
  {selector: ".state-ignored", style: {"opacity": 0.4}},
  {selector: "edge", style: {"width": 1.5, "line-color": "#30363d", "curve-style": "bezier", "opacity": 0.12}},
  {selector: ":selected", style: {"border-color": "#58a6ff", "border-width": 4}},
];

function arrange(cy) {
  // Layered tree from the Internet node: every device under whatever it hangs off (BFS over edges, so
  // uplink cycles can't loop), leaves wrapped in a grid under their parent (columns scale with leaf
  // count via gridCols, capped to fit the canvas width), branches side by side. Compound hosts are laid
  // out inside first, then treated as one wide node.
  const CW = 150, CH = 70, GAP = 50;
  const rank = (n) => n.hasClass("alert") ? 0 : n.hasClass("important") ? 1 : n.hasClass("state-known") ? 2 : 3;
  const order = (a, b) => rank(a) - rank(b) || String(a.data("label")).localeCompare(String(b.data("label")), undefined, {numeric: true});
  const top = cy.nodes().filter((n) => !n.isChild()).sort(order);
  const byId = {}, out = {}, kids = {}, own = {}, block = {};
  top.forEach((n) => { byId[n.id()] = n; out[n.id()] = []; });
  cy.edges().forEach((e) => { if (out[e.data("source")] && byId[e.data("target")]) out[e.data("source")].push(byId[e.data("target")]); });
  top.forEach((n) => {
    if (!n.isParent()) { own[n.id()] = {w: CW, h: CH}; return; }
    const inner = n.children().sort(order), cols = Math.min(inner.length, 4) || 1;
    inner.forEach((kid, i) => kid.position({x: (i % cols) * CW, y: Math.floor(i / cols) * CH}));
    const box = n.boundingBox({includeLabels: true});
    own[n.id()] = {w: box.w + GAP, h: box.h + GAP, box};
  });
  const visited = new Set();
  const grow = (root) => {
    visited.add(root.id());
    const queue = [root];
    while (queue.length) {
      const n = queue.shift();
      kids[n.id()] = [];
      out[n.id()].sort(order).forEach((m) => {
        if (!visited.has(m.id())) { visited.add(m.id()); kids[n.id()].push(m); queue.push(m); }
      });
    }
  };
  const isLeaf = (n) => !n.isParent() && !kids[n.id()].length;
  // Leaf grids scale with their count (about 30 leaves -> ~9 columns) so a flat LAN stays wide, not tall,
  // but never wider than the canvas; a few leaves just sit in one row.
  const maxCols = Math.max(4, Math.floor((cy.width() - 40) / CW));
  const gridCols = (count) => Math.min(count, Math.max(4, Math.min(Math.ceil(Math.sqrt(count * 2.5)), maxCols)));
  const measure = (n) => {
    const leaves = kids[n.id()].filter(isLeaf), branches = kids[n.id()].filter((m) => !isLeaf(m));
    const cols = gridCols(leaves.length);
    let rowW = cols * CW, rowH = cols ? Math.ceil(leaves.length / cols) * CH : 0;
    branches.forEach((m) => { const b = measure(m); rowW += b.w; rowH = Math.max(rowH, b.h); });
    return block[n.id()] = {w: Math.max(own[n.id()].w, rowW), h: own[n.id()].h + rowH, leaves, branches, cols, rowW};
  };
  const place = (n, x, y) => {
    const b = block[n.id()], o = own[n.id()];
    if (o.box) {
      const dx = x + b.w / 2 - (o.box.x1 + o.box.x2) / 2, dy = y + GAP / 2 - o.box.y1;
      n.descendants().filter((d) => !d.isParent())
        .forEach((d) => { const p = d.position(); d.position({x: p.x + dx, y: p.y + dy}); });
    } else if (o.w) n.position({x: x + b.w / 2, y: y + CH / 2});
    let left = x + (b.w - b.rowW) / 2;
    const below = y + o.h;
    b.leaves.forEach((m, i) => m.position({x: left + (i % b.cols) * CW + CW / 2, y: below + Math.floor(i / b.cols) * CH + CH / 2}));
    left += b.cols * CW;
    b.branches.forEach((m) => { place(m, left, below); left += block[m.id()].w; });
  };
  let bottom = 0;
  if (byId.internet) {
    grow(byId.internet);
    measure(byId.internet);
    place(byId.internet, 0, 0);
    bottom = block.internet.h + GAP;
  }
  // Unreachable from the Internet (an uplink loop, a stale edge): one final row, each loop rooted at its
  // first member, under an invisible root.
  const rest = {id: () => "_rest", isParent: () => false};
  kids._rest = [];
  top.forEach((n) => { if (!visited.has(n.id())) { grow(n); kids._rest.push(n); } });
  own._rest = {w: 0, h: 0};  // zero-size stand-in node: measure/place lay out its children and draw nothing for it
  measure(rest);
  place(rest, 0, bottom);
  cy.fit(undefined, 20);
}

async function load() {
  const params = [];
  if (document.getElementById("show-ignored").checked) params.push("ignored=1");
  if (document.getElementById("show-wireless").checked) params.push("wireless=1");
  try {
    const response = await fetch("/api/graph" + (params.length ? "?" + params.join("&") : ""), {credentials: "same-origin"});
    if (!response.ok || response.redirected) {
      graphMsg.textContent = "Couldn't load the map (status " + response.status + ") - session expired? reload the page";
      return;
    }
    graph = await response.json();
    graphMsg.textContent = "";
    document.getElementById("hidden-wireless").textContent = graph.hidden_wireless + " wireless hidden";
    if (cy) cy.destroy();
    cy = cytoscape({container: document.getElementById("graph"), elements: {nodes: graph.nodes, edges: graph.edges}, style: STYLE,
      layout: {name: "preset"}});
    arrange(cy);
    cy.on("tap", "node.device", (event) => openPanel(event.target.data("device_id")));
    cy.on("dbltap", "node.host", (event) => {
      const children = event.target.children();
      children.style("display", children.first().style("display") === "none" ? "element" : "none");
    });
  } catch (error) {
    graphMsg.textContent = "Couldn't load the map (network error) - session expired? reload the page";
  }
}

function field(name) { return document.getElementById("panel-" + name); }

function storedConnection(device) { return device.connection_guessed ? "unknown" : device.connection; }

function option(value, label) {
  const element = document.createElement("option");
  element.value = value;
  element.textContent = label;
  return element;
}

function fillUplinks(device) {
  // Anything a device can plug into: router / network gear on the map, plus servers.
  const choices = graph.nodes.filter((node) => node.data.device_id !== undefined && node.data.device_id !== device.id &&
      (node.classes.split(" ").some((c) => c === "router" || c === "infra") || node.data.kind === "server"))
    .sort((a, b) => a.data.label.localeCompare(b.data.label));
  const options = [option("", "router / not set"), ...choices.map((node) => option(String(node.data.device_id), node.data.label))];
  // Keep a current uplink that isn't on the map (hidden, ignored) selectable, so saving doesn't clear it.
  // The fallback is "device #N", not a name: the map only has nodes for what it shows, and fetching the
  // name would cost another request for a rare case.
  if (device.uplink_id !== null && !choices.some((node) => node.data.device_id === device.uplink_id))
    options.push(option(String(device.uplink_id), "device #" + device.uplink_id));
  field("uplink").replaceChildren(...options);
  field("uplink").value = device.uplink_id === null ? "" : String(device.uplink_id);
}

async function openPanel(deviceId, keepMessage) {
  try {
    const response = await fetch("/api/devices/" + deviceId, {credentials: "same-origin"});
    if (!response.ok || response.redirected) {
      graphMsg.textContent = "Couldn't load the map (status " + response.status + ") - session expired? reload the page";
      return;
    }
    current = await response.json();
  } catch (error) {
    graphMsg.textContent = "Couldn't load the map (network error) - session expired? reload the page";
    return;
  }
  graphMsg.textContent = "";
  panel.hidden = false;
  if (!keepMessage) message.textContent = "";
  document.getElementById("panel-title").textContent = current.name;
  document.getElementById("panel-meta").textContent =
    current.status + " - " + (current.ip || "no ip") + " - seen by " +
    [...new Set(current.sightings.map((s) => s.source))].join(", ");
  field("name").value = current.name;
  field("kind").value = current.kind;
  field("state").value = current.state;
  field("tags").value = current.tags.join(", ");
  field("notes").value = current.notes;
  field("important").checked = current.important;
  field("connection").value = storedConnection(current);
  field("guess").textContent = current.connection_guessed ? "guessed wireless" : "";
  fillUplinks(current);
  document.getElementById("panel-link").href = "/devices/" + current.id;
  document.getElementById("panel-ask").href = "/chat?device=" + current.id;
  cy.resize();
  cy.fit(undefined, 20);
}

document.getElementById("panel-save").addEventListener("click", async () => {
  if (!current) return;
  const id = current.id;
  const body = {name: field("name").value, kind: field("kind").value, state: field("state").value,
    notes: field("notes").value, important: field("important").checked,
    tags: field("tags").value.split(",").map((tag) => tag.trim()).filter(Boolean),
    connection: field("connection").value,
    uplink_id: field("uplink").value === "" ? null : parseInt(field("uplink").value, 10)};
  for (const key of Object.keys(body)) {
    const value = key === "tags" ? body[key].join(",") : body[key];
    const currentValue = key === "tags" ? current[key].join(",") : key === "connection" ? storedConnection(current) : current[key];
    if (value === currentValue) delete body[key];
  }
  if (Object.keys(body).length === 0) {
    message.textContent = "Nothing changed.";
    return;
  }
  try {
    const response = await fetch("/api/devices/" + id, {method: "POST", credentials: "same-origin",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      message.textContent = data.error || ("Failed: " + response.status +
        ((response.status === 401 || response.status === 403 || response.redirected) ? " (session expired? reload the page)" : ""));
      return;
    }
    message.textContent = "Saved.";
    await load();
    openPanel(id, true);
  } catch (error) { message.textContent = "Request failed: " + error; }
});
document.getElementById("panel-close").addEventListener("click", () => {
  panel.hidden = true;
  current = null;
  cy.resize();
  cy.fit(undefined, 20);
});
document.getElementById("show-ignored").addEventListener("change", load);
document.getElementById("show-wireless").addEventListener("change", load);
load();
</script>
"""


def _map_block():

    options = lambda values: "".join(f"<option>{_esc(value)}</option>" for value in values)

    return (
        "<p class=\"map-legend muted\"><span style=\"color:#3fb950\">● seen</span>"
        "<span style=\"color:#d29922\">● quiet</span><span style=\"color:#f85149\">● important &amp; quiet</span>"
        "<span style=\"color:#8b949e\">● never seen</span><span>◆ router / network gear</span>"
        "<span>dashed = new, needs triage</span><span>dotted = connection unknown</span>"
        "<span>click a device to edit - double-click a host to fold it</span><span id=\"hidden-wireless\"></span>"
        "<label style=\"display:inline\"><input type=\"checkbox\" id=\"show-ignored\"> show ignored</label> "
        "<label style=\"display:inline\"><input type=\"checkbox\" id=\"show-wireless\"> show wireless</label></p>"
        "<p id=\"graph-msg\" class=\"muted\"></p>"
        "<div class=\"map-wrap\"><div id=\"graph\"></div>"
        "<aside id=\"panel\" hidden><h2 id=\"panel-title\"></h2><p class=\"muted\" id=\"panel-meta\"></p>"
        "<label>Name</label><input id=\"panel-name\">"
        f"<label>Kind</label><select id=\"panel-kind\">{options(KINDS)}</select>"
        f"<label>State</label><select id=\"panel-state\">{options(STATES)}</select>"
        f"<label>Connection</label><select id=\"panel-connection\">{options(CONNECTIONS)}</select>"
        "<span class=\"muted\" id=\"panel-guess\"></span>"
        "<label>Connected to</label><select id=\"panel-uplink\"></select>"
        "<label>Tags (comma separated)</label><input id=\"panel-tags\">"
        "<label>Notes</label><textarea id=\"panel-notes\"></textarea>"
        "<label><input type=\"checkbox\" id=\"panel-important\"> Important - alert when it goes quiet</label>"
        "<p><button class=\"primary\" id=\"panel-save\">Save</button><button id=\"panel-close\">Close</button></p>"
        "<p id=\"panel-msg\" class=\"muted\"></p>"
        "<p><a id=\"panel-ask\" href=\"#\">Ask atlas about this device</a></p>"
        "<p><a id=\"panel-link\" href=\"#\">Full page - merge, split, every sighting</a></p></aside></div>"
        "<script src=\"/static/cytoscape.min.js?v=3.34.3\"></script>"
        + MAP_SCRIPT
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
        "detail": _count(sum(len(m) for m in docker.get('networks', {}).values()), "container"),
        "children": [
            (name, _count(len(members), "container"),
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
                 f"{_count(public_count, 'public route')} via Traefik" if public_count else "no public routes", "#58a6ff"),
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
        return render_page("Network Map", "<p class=\"muted\">No map yet for this host's containers - run "
                            "<code>atlas map</code>. Devices below come from the inventory.</p>" + _map_block(),
                            active="lan")

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
        + _map_block()
        + f"<noscript><div class=\"card\">{render_map_svg(topology)}</div></noscript>"
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

    return render_page("Network Map", body, active="lan")


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
