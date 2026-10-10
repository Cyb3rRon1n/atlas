"""
/posture - the posture page: status strip, zone map (inbound / outbound direct /
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
.posture aside .pcard { background:#111821; border:1px solid #222c38; border-radius:14px; padding:16px; }
.ptabs { display:flex; flex-wrap:wrap; gap:4px; margin-bottom:12px; border-bottom:1px solid var(--line); }
.ptabs button { font:inherit; font-size:13px; padding:8px 10px; border:0; margin:0; border-radius:0; background:transparent;
                color:var(--muted); border-bottom:2px solid transparent; cursor:pointer; }
.ptabs button[aria-selected="true"] { color:var(--text); border-bottom-color:var(--blue); }
#posture-panel > h2:first-child { display:none; }
.pcard [role=tabpanel] { max-height:600px; overflow-y:auto; }
.mapbar { display:flex; flex-wrap:wrap; align-items:center; gap:12px; margin-bottom:12px; }
.mapbar .windows { display:flex; gap:4px; padding:3px; border:1px solid var(--line); border-radius:8px; }
.mapbar .windows button { font:inherit; font-size:13px; padding:8px 12px; border:0; border-radius:6px;
                          background:transparent; color:var(--muted); cursor:pointer; }
.mapbar .windows button[aria-pressed="true"] { background:var(--surface2); color:var(--text); }
.legend { margin-left:auto; display:flex; flex-wrap:wrap; gap:14px; font-size:12px; color:var(--muted); }
.legend i { display:inline-block; width:18px; height:3px; margin-right:6px; vertical-align:middle; }
#posture-map { display:flex; flex-direction:column; gap:12px; }
.lane { border:1px dashed #2c4560; border-radius:10px; padding:10px 12px; background:rgba(90,167,240,.04); }
.lane.stale { border-color:var(--red); }
.lane h3 { margin:0 0 8px; font-size:12px; font-weight:500; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }
.lane .cols { display:flex; flex-wrap:wrap; align-items:center; gap:8px; }
.lane .col { display:flex; flex-direction:column; gap:6px; min-width:0; }
.lane .col.list { flex:1 1 220px; }
.lane .arrow { color:var(--muted); font-size:18px; }
.lane.inbound .arrow { color:#5aa7f0; } .lane.vpn .arrow { color:#43c08f; }
#posture-map .box { position:relative; display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 8px; text-align:left; font:inherit;
       font-size:14px; padding:7px 10px; margin:0; background:#1b2430; border:1px solid #2f3b4c; border-radius:8px;
       color:var(--text); cursor:pointer; overflow:hidden; }   /* #id beats chat.css's global .ok/.bad colours */
.box .sub { color:var(--muted); font-size:12px; }
.box .bar { position:absolute; left:0; bottom:0; height:3px; background:#8b98a6; }
.box.review { border-color:#f0a23a; background:#2b2213; } .box.review .bar { background:#f0a23a; }
.box.warn { border-color:#f47a5c; background:#2a1d1a; } .box.unknown { border-style:dashed; color:var(--muted); }
.box.selected { outline:2px solid var(--blue); }
.box .badge { margin-left:auto; font-size:11px; color:#ffd08a; text-transform:uppercase; letter-spacing:.05em; }
#exposure li { display:flex; justify-content:space-between; gap:8px; padding:4px 0; }
.prot-authelia { color:#7fdcb5; } .prot-public { color:#ffd08a; }
@media (max-width: 900px) { #strip { grid-template-columns:repeat(2,minmax(0,1fr)); }  }
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
function showTab(id) {
  document.querySelectorAll("[data-tab]").forEach((b) => {
    const on = b.dataset.tab === id;
    b.setAttribute("aria-selected", String(on));
    document.getElementById(b.dataset.tab).hidden = !on;
  });
}
document.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
const exposure = document.getElementById("exposure");
const msg = document.getElementById("posture-msg");
const reviewList = document.getElementById("review");
const off = document.getElementById("posture-off");
const DEFAULT_MSG = msg.textContent;
const OFF_TEXT = "Posture collection is off - set posture.enabled: true in atlas.yaml and run `atlas posture watch` (atlas-scan does this).";
off.textContent = OFF_TEXT;
let windowName = "24h", timer = null;

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

let reviewShown = false;
if (location.hash === "#review") {   // home page's "Review ->" link
  reviewShown = true; showTab("review-tab");
  document.querySelector(".pcard").scrollIntoView({block: "start"});
}
function renderReview(items) {
  document.getElementById("review-count").textContent = items.length ? "(" + items.length + ")" : "";
  if (items.length && !reviewShown) { reviewShown = true; showTab("review-tab"); }
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

// Lanes: each band is a row of columns (nodes grouped by their x), arrows between columns. Plain HTML
// at normal text size - no canvas, so nothing is ever scaled down to fit.
function lanes(data) {
  const bytes = {};
  data.edges.forEach((e) => { bytes[e.target] = (bytes[e.target] || 0) + e.bytes;
                              if (e.source.startsWith("src:")) bytes[e.source] = (bytes[e.source] || 0) + e.bytes; });
  return data.bands.map((band) => {
    const lane = el("section", undefined, "lane " + band.id + (band.stale ? " stale" : ""));
    lane.append(el("h3", band.label + (band.stale ? " · no recent data" : "")));
    const row = el("div", undefined, "cols");
    const byX = {};
    data.nodes.filter((n) => n.band === band.id).forEach((n) => (byX[n.x] = byX[n.x] || []).push(n));
    Object.keys(byX).map(Number).sort((a, b) => a - b).forEach((x, i) => {
      if (i) row.append(el("span", "\u2192", "arrow"));
      const nodes = byX[x].sort((a, b) => a.y - b.y);
      const col = el("div", undefined, "col" + (nodes.length > 1 ? " list" : ""));
      const max = Math.max(1, ...nodes.map((n) => bytes[n.id] || 0));
      nodes.forEach((n) => {
        const box = el("button", undefined, "box " + n.state);
        box.dataset.id = n.id;
        box.append(el("span", n.label, "name"), el("span", n.sub, "sub"));
        if (bytes[n.id] && nodes.length > 1) {
          const bar = el("span", undefined, "bar");
          bar.style.width = Math.max(4, 100 * bytes[n.id] / max) + "%";
          box.append(bar);
        }
        if (n.state === "review" && n.id.startsWith("dst:")) box.append(el("span", "review", "badge"));
        box.addEventListener("click", () => {
          document.querySelectorAll("#posture-map .box.selected").forEach((o) => o.classList.remove("selected"));
          box.classList.add("selected");
          select(n.id);
        });
        col.append(box);
      });
      row.append(col);
    });
    lane.append(row);
    return lane;
  });
}

function draw(data) {
  document.getElementById("posture-map").replaceChildren(...lanes(data));
}

async function select(id) {
  if (id === "dst:review-more") { showTab("review-tab"); return; }
  showTab("posture-panel");
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
        + '<div id="posture-map" aria-label="Inbound, outbound and VPN traffic"></div>'
        + '<p class="muted" id="posture-msg">Click a destination for details. Bars = share of traffic; orange = '
          'a network this container never used before.</p></section>'
        + '<aside><div class="pcard"><div class="ptabs" role="tablist" aria-label="Posture details">'
        + '<button role="tab" data-tab="posture-panel" aria-selected="true">Details</button>'
        + '<button role="tab" data-tab="exposure-tab" aria-selected="false">Public exposure</button>'
        + '<button role="tab" data-tab="review-tab" aria-selected="false">Needs review '
          '<span id="review-count"></span></button></div>'
        + '<section id="posture-panel" role="tabpanel"><p class="muted">Select a destination on the map.</p></section>'
        + '<section id="exposure-tab" role="tabpanel" hidden><ul id="exposure" '
          'style="list-style:none;margin:0;padding:0"></ul></section>'
        + '<section id="review-tab" role="tabpanel" hidden><ul id="review"></ul></section>'
        + '</div></aside></div>'
        + POSTURE_SCRIPT
    )

    return render_page("Posture", body, active="posture")
