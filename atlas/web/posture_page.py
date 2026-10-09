"""
/ - the posture page: status strip, zone map (inbound / outbound direct /
outbound via VPN), details panel and public exposure. Markup only here; data
comes from /api/posture via POSTURE_SCRIPT (Task 10).
"""

from atlas.web.render import render_page


POSTURE_STYLE = """
<style>
#strip { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; margin-bottom:16px; }
#strip .chip { padding:14px 16px; background:var(--surface); border:1px solid var(--line); border-radius:12px;
               color:var(--text); text-align:left; font:inherit; }
#strip .chip .k { font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }
#strip .chip .v { font-size:20px; font-weight:600; margin-top:4px; }
#strip .chip .d { font-size:13px; color:var(--muted); }
#strip .chip.ok .v { color:#7fdcb5; } #strip .chip.warn { border-color:var(--red); } #strip .chip.warn .v { color:#ffb4a2; }
#strip .chip.review { border-color:var(--orange); background:#2b2213; } #strip .chip.review .v { color:#ffd08a; }
#strip .chip.unknown .v { color:var(--muted); }
.posture { display:flex; flex-wrap:wrap; gap:20px; }
.posture .mapcard { flex:999 1 720px; min-width:0; background:#111821; border:1px solid #222c38; border-radius:14px; padding:16px; }
.posture aside { flex:1 1 320px; min-width:0; display:flex; flex-direction:column; gap:16px; }
.posture aside section { background:#111821; border:1px solid #222c38; border-radius:14px; padding:16px; }
.mapbar { display:flex; flex-wrap:wrap; align-items:center; gap:12px; margin-bottom:12px; }
.mapbar .windows { display:flex; gap:4px; padding:3px; border:1px solid var(--line); border-radius:8px; }
.mapbar .windows button { font:inherit; font-size:13px; padding:8px 12px; border:0; border-radius:6px;
                          background:transparent; color:var(--muted); cursor:pointer; }
.mapbar .windows button[aria-pressed="true"] { background:var(--surface2); color:var(--text); }
.legend { margin-left:auto; display:flex; flex-wrap:wrap; gap:14px; font-size:12px; color:var(--muted); }
.legend i { display:inline-block; width:18px; height:3px; margin-right:6px; vertical-align:middle; }
#posture-map { height:560px; border-radius:10px; background:var(--bg); }
#exposure li { display:flex; justify-content:space-between; gap:8px; padding:4px 0; }
.prot-authelia { color:#7fdcb5; } .prot-public { color:#ffd08a; }
@media (max-width: 900px) { #strip { grid-template-columns:repeat(2,minmax(0,1fr)); } #posture-map { height:420px; } }
#posture-panel dl { display:grid; grid-template-columns:auto 1fr; gap:6px 12px; font-size:13px; }
#posture-panel dt { color:var(--muted); }
#posture-panel .big { font-size:18px; margin:4px 0 12px; }
.review-label { color:#ffd08a; font-size:12px; text-transform:uppercase; letter-spacing:.06em; }
#posture-panel button { margin:8px 8px 0 0; }
#posture-off { padding:12px 16px; margin-bottom:16px; border:1px solid var(--orange); border-radius:12px;
               background:#2b2213; color:#ffd08a; }
#review { list-style:none; margin:0; padding:0; }
#review li { padding:8px 0; border-top:1px solid var(--line); font-size:13px; }
#review li:first-child { border-top:0; }
#review button { margin-top:6px; }
</style>
"""


POSTURE_SCRIPT = """
<script>
(() => {
const strip = document.getElementById("strip");
const panel = document.getElementById("posture-panel");
const exposure = document.getElementById("exposure");
const msg = document.getElementById("posture-msg");
const reviewList = document.getElementById("review");
const off = document.getElementById("posture-off");
const DEFAULT_MSG = msg.textContent;
const OFF_TEXT = "Posture collection is off - set posture.enabled: true in atlas.yaml and run `atlas posture watch` (atlas-scan does this).";
off.textContent = OFF_TEXT;
const COLORS = {inbound: "#5aa7f0", direct: "#8b98a6", vpn: "#43c08f"};
let windowName = "24h", cy = null, timer = null;

function el(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
function fmt(n) { const u = ["B","KB","MB","GB","TB"]; let i = 0; while (n >= 1000 && i < 4) { n /= 1000; i++; } return (i ? n.toFixed(1) : n.toFixed(0)) + " " + u[i]; }

function renderStrip(items) {
  strip.replaceChildren(...items.map((item) => {
    const chip = el("div", undefined, "chip " + item.state);
    chip.append(el("div", item.label, "k"), el("div", item.value, "v"), el("div", item.detail, "d"));
    return chip;
  }));
}

function renderExposure(routes) {
  exposure.replaceChildren(...routes.map((r) => {
    const li = el("li");
    li.append(el("span", (r.hosts[0] || r.name)), el("span", r.protection === "authelia" ? "Authelia" : "public · own login", "prot-" + r.protection));
    return li;
  }));
  if (!routes.length) exposure.replaceChildren(el("li", "No routes seen yet.", "muted"));
}

async function markExpected(button, source, asnKey) {
  button.disabled = true;
  try {
    const r = await fetch("/api/posture/known", {method: "POST", credentials: "same-origin",
      headers: {"Content-Type": "application/json"}, body: JSON.stringify({source: source, asn_key: asnKey})});
    if (r.ok) { button.textContent = "Marked expected"; load(); return; }
    button.textContent = "Failed (" + r.status + ") - try again";
  } catch (error) { button.textContent = "Network error - try again"; }
  button.disabled = false;
}

function renderReview(items) {
  if (!items.length) { reviewList.replaceChildren(el("li", "Nothing new to review.", "muted")); return; }
  reviewList.replaceChildren(...items.map((r) => {
    const li = el("li");
    li.append(el("div", r.source + " -> " + (r.org || r.asn_key) + " (" + r.asn_key + ", " + (r.cc || "?") + ")"),
      el("div", "first seen " + new Date(r.first_seen + "Z").toLocaleString(), "muted"));
    const mark = el("button", "Mark expected");
    mark.addEventListener("click", () => markExpected(mark, r.source, r.asn_key));
    li.append(mark);
    return li;
  }));
}

function elements(data) {
  const out = [];
  data.bands.forEach((b) => out.push({group: "nodes", data: {id: "band:" + b.id, label: b.label + (b.stale ? " · no recent data" : "")},
    classes: "band" + (b.stale ? " stale" : ""), position: {x: 560, y: b.y + b.h / 2}, locked: true, grabbable: false, selectable: false,
    style: {width: 1180, height: b.h}}));
  data.nodes.forEach((n) => out.push({group: "nodes", data: {id: n.id, label: n.label + "\\n" + n.sub, band: n.band},
    classes: "box " + n.state + " " + n.band, position: {x: n.x + n.w / 2, y: n.y}, style: {width: n.w}}));
  const max = Math.max(1, ...data.edges.map((e) => e.bytes));
  data.edges.forEach((e) => out.push({group: "edges", data: {id: e.id, source: e.source, target: e.target,
    w: 1.5 + 6 * Math.sqrt(e.bytes / max)}, classes: e.state}));
  return out;
}

const STYLE = [
  {selector: "node.band", style: {"shape": "round-rectangle", "background-opacity": 0.06, "background-color": "#5aa7f0",
    "border-width": 1, "border-style": "dashed", "border-color": "#2c4560", "label": "data(label)", "color": "#a3b0bd",
    "font-size": 11, "text-valign": "top", "text-halign": "center", "text-margin-y": 16, "events": "no"}},
  {selector: "node.band.stale", style: {"background-color": "#8b98a6", "color": "#ffb4a2"}},
  {selector: "node.box", style: {"shape": "round-rectangle", "height": 44, "background-color": "#1b2430",
    "border-width": 1, "border-color": "#2f3b4c", "label": "data(label)", "color": "#e7edf3", "font-size": 11,
    "text-wrap": "wrap", "text-valign": "center", "text-halign": "center"}},
  {selector: "node.box.review", style: {"border-color": "#f0a23a", "background-color": "#2b2213", "color": "#ffd08a"}},
  {selector: "node.box.warn", style: {"border-color": "#f47a5c", "background-color": "#2a1d1a", "color": "#ffb4a2"}},
  {selector: "node.box.unknown", style: {"color": "#a3b0bd", "border-style": "dashed"}},
  {selector: "node.box:selected", style: {"border-color": "#5aa7f0", "border-width": 3}},
  {selector: "edge", style: {"width": "data(w)", "line-color": "#8b98a6", "target-arrow-color": "#8b98a6",
    "target-arrow-shape": "triangle", "curve-style": "taxi", "taxi-direction": "horizontal", "opacity": 0.8}},
  {selector: "edge.review", style: {"line-color": "#f0a23a", "target-arrow-color": "#f0a23a", "line-style": "dashed"}},
  {selector: "edge.warn", style: {"line-color": "#f47a5c", "target-arrow-color": "#f47a5c"}},
];

function draw(data) {
  const els = elements(data);
  els.forEach((e) => { if (e.group === "edges") {
    const src = data.nodes.find((n) => n.id === e.data.source);
    if (src && e.classes === "ok") e.classes = src.band; } });
  if (cy) cy.destroy();
  cy = cytoscape({container: document.getElementById("posture-map"), elements: els, style: STYLE.concat(
    Object.entries(COLORS).map(([band, color]) => ({selector: "edge." + band, style: {"line-color": color, "target-arrow-color": color}}))),
    layout: {name: "preset", fit: true, padding: 24}, userZoomingEnabled: true, wheelSensitivity: 0.2, autoungrabify: true});
  cy.on("tap", "node.box", (event) => select(event.target.id()));
}

async function select(id) {
  panel.replaceChildren(el("h2", "Details"));
  panel.firstChild.style.cssText = "margin:0 0 8px;font-size:15px";
  if (!id.startsWith("dst:") || id === "dst:others") { panel.append(el("p", "Pick a destination box to see who talks to it.", "muted")); return; }
  panel.append(el("p", "Loading...", "muted"));
  let d = null;
  try {
    const response = await fetch("/api/posture/node?id=" + encodeURIComponent(id), {credentials: "same-origin"});
    d = response.ok ? await response.json() : null;
  } catch (error) {
    panel.lastChild.textContent = "Could not load details: " + error;
    return;
  }
  panel.lastChild.remove();
  if (!d) { panel.append(el("p", "No traffic recorded for this in the last 24 h.", "muted")); return; }
  panel.append(el("div", d.known ? "Expected destination" : "Not reviewed yet", d.known ? "muted" : "review-label"));
  panel.append(el("div", d.org || d.asn_key, "big"));
  const dl = el("dl");
  [["Network", d.asn_key], ["Country", d.cc || "?"], ["First seen", d.first_seen ? new Date(d.first_seen + "Z").toLocaleString() : "?"],
   ["Ports", d.ports.join(", ")], ["Top address", d.ips[0] ? d.ips[0].ip + (d.ips[0].rdns ? " (" + d.ips[0].rdns + ")" : "") : "?"]]
    .forEach(([k, v]) => dl.append(el("dt", k), el("dd", v)));
  panel.append(dl, el("h3", "From"));
  const ul = el("ul");
  d.sources.forEach((s) => ul.append(el("li", s.source + " · " + fmt(s.bytes))));
  panel.append(ul);
  const ask = el("button", "Ask Atlas about this", "primary");
  ask.id = "ask-atlas";
  ask.dataset.prefill = "Why is " + d.sources.map((s) => s.source).join(", ") + " talking to " + (d.org || d.asn_key) +
    " (" + d.asn_key + ", " + (d.cc || "?") + ", ports " + d.ports.join(",") + ")? Is this expected?";
  ask.addEventListener("click", () => { const text = ask.dataset.prefill;
    if (window.atlasAsk) window.atlasAsk(text); else location.href = "/chat?q=" + encodeURIComponent(text); });
  panel.append(ask);
  if (!d.known) d.sources.forEach((s) => {
    const mark = el("button", "Mark expected for " + s.source);
    mark.addEventListener("click", () => markExpected(mark, s.source, d.asn_key));
    panel.append(mark);
  });
}

async function load() {
  try {
    const response = await fetch("/api/posture?window=" + windowName, {credentials: "same-origin"});
    if (!response.ok) { msg.textContent = "Could not load posture data (" + response.status + ")."; return; }
    const data = await response.json();
    msg.textContent = DEFAULT_MSG;
    off.hidden = data.enabled !== false;
    renderStrip(data.strip); renderExposure(data.exposure); renderReview(data.review); draw(data);
  } catch (error) { msg.textContent = "Could not load posture data: " + error; }
}

document.querySelectorAll("[data-window]").forEach((b) => b.addEventListener("click", () => {
  windowName = b.dataset.window;
  document.querySelectorAll("[data-window]").forEach((o) => o.setAttribute("aria-pressed", String(o === b)));
  clearInterval(timer);
  if (windowName === "live") timer = setInterval(load, 30000);
  load();
}));

load();
})();
</script>
"""


def render_posture_page():

    body = (
        POSTURE_STYLE
        + '<p id="posture-off" role="status" hidden></p>'
        + '<section id="strip" aria-label="Posture summary"><p class="muted">Loading...</p></section>'
        + '<div class="posture"><section class="mapcard">'
        + '<div class="mapbar"><h2 style="margin:0;font-size:16px">Network posture</h2>'
        + '<div class="windows" role="group" aria-label="Time window">'
        + '<button data-window="live" aria-pressed="false">This hour</button>'
        + '<button data-window="1h" aria-pressed="false">1 h</button>'
        + '<button data-window="24h" aria-pressed="true">24 h</button></div>'
        + '<div class="legend"><span><i style="background:#5aa7f0"></i>Inbound</span>'
        + '<span><i style="background:#8b98a6"></i>Outbound</span>'
        + '<span><i style="background:#43c08f"></i>Via VPN</span>'
        + '<span><i style="background:#f0a23a"></i>New / unreviewed</span></div></div>'
        + '<div id="posture-map" role="img" aria-label="Zone map of inbound, outbound and VPN traffic"></div>'
        + '<p class="muted" id="posture-msg">Click a box for details. Line width = traffic; dashed orange = '
          'a network this container never used before.</p></section>'
        + '<aside><section id="posture-panel"><h2 style="margin:0 0 8px;font-size:15px">Details</h2>'
        + '<p class="muted">Select a destination on the map.</p></section>'
        + '<section><h2 style="margin:0 0 8px;font-size:15px">Public exposure</h2><ul id="exposure" '
          'style="list-style:none;margin:0;padding:0"></ul></section>'
        + '<section><h2 style="margin:0 0 8px;font-size:15px">Needs review</h2><ul id="review"></ul></section>'
        + '</aside></div>'
        + '<script src="/static/cytoscape.min.js?v=3.34.3"></script>'
        + POSTURE_SCRIPT
    )

    return render_page("Posture", body, active="posture",
                       tabs=[("/", "Posture", True), ("/overview", "Host overview", False)])
