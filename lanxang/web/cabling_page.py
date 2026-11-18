"""
/cabling - the port-level wired map: a layered diagram (gateway -> switches ->
hosts, real ports on each box, port-to-port labels and speed on every cable),
a faceplate per switch, a port map table with CSV export and the changes since
the previous scan. Server-rendered HTML around one JSON blob; the diagram is
laid out in the browser by vendored ELK.js and drawn as SVG with
createElementNS/textContent only (no innerHTML). Pure renderers: server.py
passes the latest WiringStore row and the diff.
"""

import csv
import io
import json
from datetime import datetime

from lanxang.config.local import config_name
from lanxang.web.icons import icon
from lanxang.web.render import _esc, render_page
from lanxang.wiring import traffic
from lanxang.wiring.build import IDLE
from lanxang.wiring.faceplate import physical_layout
from lanxang.clock import utcnow


INFRA = ("wan", "gateway", "switch", "ap")

CABLING_STYLE = """
<style>
.suggest { margin:0 0 12px; padding:8px 12px; border:1px solid var(--line2); border-radius:10px; }
.cab-head { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-bottom:10px; }
.cab-head .when { color:var(--muted); font-size:14px; }
.chip { font-size:12px; padding:2px 9px; border-radius:999px; border:1px solid var(--line); }
.chip.ok { color:var(--ok-text); border-color:var(--ok-line); } .chip.stale { color:var(--warn-text); border-color:var(--warn-line); }
.chip.error { color:var(--bad-text); border-color:var(--bad-line); }
.cab-btn { background:var(--accent); color:var(--on-accent); border:0; border-radius:6px; padding:6px 12px; cursor:pointer; font:inherit; }
.cab-btn.ghost { background:transparent; border:1px solid var(--line); color:inherit; }
.cab-btn[disabled] { opacity:.6; cursor:wait; }
.warn { margin:6px 0 12px; padding:8px 12px 8px 28px; border:1px solid var(--warn-line); border-radius:8px; color:var(--warn-text); font-size:14px; }
#diagram .frame { overflow:auto; border:1px solid var(--line); border-radius:10px; background:var(--deep); max-height:78vh; }
#wiring-svg { display:block; min-width:100%; }
.legend { display:flex; flex-wrap:wrap; gap:14px; font-size:12px; color:var(--muted); margin:6px 0; }
.legend i { display:inline-block; width:22px; height:3px; vertical-align:middle; margin-right:5px; }
.fp-wrap { overflow-x:auto; padding:8px 0 14px; }
.fp { --pw:62px; --ph:44px; position:relative; }
.fp .port { margin:0; text-align:left; font:inherit; color:inherit; cursor:pointer; overflow:hidden; position:absolute; width:56px; height:38px; box-sizing:border-box; border:1px solid var(--line2); border-radius:6px;
           padding:2px 5px; font-size:11px; background:var(--surface); opacity:.55; }
.fp .port.up { opacity:1; }
.fp .port.poe-cap, .fp .port.poe { border:2px dashed var(--yellow); }
.fp .port.poe { border-style:solid; }
.fp .port.poe-cap::after { content:"PoE"; position:absolute; right:3px; top:1px; font-size:11px; font-weight:700; color:var(--yellow); }
.fp .port.poe::after { content:""; position:absolute; right:4px; top:4px; width:9px; height:11px; background:var(--yellow);
  -webkit-mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='4 2 15 20'%3E%3Cpath d='M13 2 4 14h7l-1 8 9-12h-7z'/%3E%3C/svg%3E") center/contain no-repeat;
  mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='4 2 15 20'%3E%3Cpath d='M13 2 4 14h7l-1 8 9-12h-7z'/%3E%3C/svg%3E") center/contain no-repeat; }
.fp .port.h-bad { border:2px solid var(--red); box-shadow:0 0 0 2px color-mix(in srgb, var(--red) 30%, transparent); }
.fp .port.h-watch { border:2px solid var(--orange); }
#health ul { list-style:none; padding:0; margin:0; } #health li { padding:6px 0; border-top:1px solid var(--line); }
#health li:first-child { border-top:0; } #health .lvl { font-weight:600; margin-right:6px; }
#health .bad .lvl { color:var(--red); } #health .watch .lvl { color:var(--orange); }
.fp .port b { display:block; font-size:12px; }
.fp .port small { display:block; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.fp .port.cage { border-style:dashed; background:transparent; }
.fp .port.standby { border:2px dashed var(--muted); opacity:.7; }
.fp .port.standby::before { content:"standby"; position:absolute; left:4px; bottom:1px; font-size:8px; color:var(--muted); }
.fp .port.vlan-off { opacity:.15; }
.notes { margin:6px 0 12px; padding:6px 12px 6px 28px; color:var(--muted); font-size:14px; }
.lag { border:1px solid var(--line); border-radius:6px; padding:1px 6px; margin-right:6px; }
.fp .s100 { border-color:var(--muted); } .fp .s1g { border-color:var(--blue); } .fp .s25 { border-color:var(--teal); } .fp .s10g { border-color:var(--purple); }
#faceplates details { border:1px solid var(--line); border-radius:10px; padding:8px 12px; margin-bottom:8px; }
#faceplates summary { cursor:pointer; font-weight:600; }
.portmap { width:100%; border-collapse:collapse; font-size:13px; }
.portmap th, .portmap td { text-align:left; padding:4px 8px; border-bottom:1px solid var(--line); }
.portmap td.down { color:var(--bad-text); }
.cab-tools { display:flex; gap:8px; align-items:center; margin:8px 0; }
.cab-tools input { background:var(--deep); color:inherit; border:1px solid var(--line); border-radius:6px; padding:5px 8px; min-width:240px; }
#changes li { font-size:14px; }
.spark { vertical-align:middle; margin-right:6px; } .spark polyline { fill:none; stroke:var(--blue); stroke-width:1.5; }
.spark.busy polyline { stroke:var(--orange); } .spark.hot polyline { stroke:var(--red); }
.portmap td.rate { white-space:nowrap; color:var(--muted); }
.fp .port.sel { outline:3px solid var(--blue); outline-offset:2px; opacity:1; }
.views { display:inline-flex; border:1px solid var(--line2); border-radius:8px; overflow:hidden; margin-left:auto; }
.views button { margin:0; border:0; border-radius:0; padding:7px 14px; background:var(--surface); }
.views button[aria-pressed="true"] { background:var(--accent); color:var(--on-accent); font-weight:600; }
.cab-sum { color:var(--muted); font-size:14px; }
.fp-layout { display:flex; flex-wrap:wrap; gap:20px; align-items:flex-start; }
.fp-layout > div { flex:999 1 400px; min-width:0; }
.pd { flex:1 1 240px; position:sticky; top:12px; border:1px solid var(--line); border-radius:10px; padding:16px 18px;
      background:var(--surface); font-size:14px; }
.pd h3 { margin:0 0 10px; font-size:17px; } .pd .k { font-size:13px; color:var(--muted); margin:0; }
.pd dl { display:grid; grid-template-columns:auto 1fr; gap:6px 14px; margin:0; } .pd dt { color:var(--muted); }
.pd dd { margin:0; overflow-wrap:anywhere; } .pd dd.bad { color:var(--bad-text); font-weight:600; }
</style>
"""

DIAGRAM_SCRIPT = r"""
<script src="/static/elk.bundled.js"></script>
<script>
(function () {
  var NS = "http://www.w3.org/2000/svg";
  var SVG_CSS = ".node{fill:var(--surface);stroke:var(--line2);stroke-width:1.5}.k-gateway{stroke:var(--orange)}.k-switch{stroke:var(--blue)}"
    + ".k-ap{stroke:var(--teal)}.k-bridge{stroke:var(--yellow)}.k-wan{stroke:var(--muted);stroke-dasharray:4 3}.k-unknown{stroke-dasharray:3 3}"
    + ".nm{fill:var(--text);font:600 13px system-ui,sans-serif}.sub{fill:var(--muted);font:11px system-ui,sans-serif}"
    + ".pt{fill:var(--line2)}.pl{fill:var(--text);font:10px ui-monospace,monospace}"
    + ".edge{fill:none;stroke-width:2.5}.s100{stroke:var(--muted)}.s1g{stroke:var(--blue)}.s25{stroke:var(--teal)}.s10g{stroke:var(--purple)}"
    + ".busy{stroke:var(--orange);stroke-width:4}.hot{stroke:var(--red);stroke-width:5}.down{stroke-dasharray:6 4;opacity:.6}.standby{stroke:var(--muted);stroke-dasharray:2 4;opacity:.7}.bundle{stroke-width:4.5}.el{fill:var(--text);font:11px ui-monospace,monospace;paint-order:stroke;"
    + "stroke:var(--deep);stroke-width:4px;stroke-linejoin:round}"
    + ".fc{fill:var(--surface2);stroke:var(--line2)}.fc.up.s100{fill:var(--muted)}.fc.up.s1g{fill:var(--blue)}.fc.up.s25{fill:var(--teal)}"
    + ".fc.up.s10g{fill:var(--purple)}.fc.used{stroke:var(--text);stroke-width:1.6}.fc.cage{fill:none;stroke-dasharray:3 2}.fn{fill:var(--muted);font:10px ui-monospace,monospace;"
    + "text-anchor:middle}.fn.on{fill:var(--deep);font-weight:700}.stub{stroke:var(--text);stroke-width:1.5;opacity:.7}";
  var holder = document.getElementById("wiring-data");
  var svg = document.getElementById("wiring-svg");
  var msg = document.getElementById("msg");
  function say(text) { if (msg) { msg.textContent = text; } }
  function el(tag, attrs, parent, text) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (text !== undefined) { e.textContent = text; }
    if (parent) { parent.appendChild(e); }
    return e;
  }
  function speedClass(s) { return s >= 10000 ? "s10g" : s >= 2500 ? "s25" : s >= 1000 ? "s1g" : "s100"; }
  function rateText(b) {
    var u = [["Gb/s", 1e9], ["Mb/s", 1e6], ["kb/s", 1e3]];
    for (var i = 0; i < u.length; i++) { if (b >= u[i][1]) { return (b / u[i][1]).toFixed(1).replace(/\.0$/, "") + " " + u[i][0]; } }
    return Math.round(b) + " b/s";
  }
  function loadClass(l) { return l >= 0.8 ? " hot" : l >= 0.5 ? " busy" : ""; }
  function speedText(s) { return s >= 1000 ? (s / 1000) + "G" : (s ? s + "M" : "?"); }
  function short(text, n) { text = String(text || ""); return text.length > n ? text.slice(0, n - 1) + "…" : text; }

  if (holder && svg && window.ELK) {
    var data = JSON.parse(holder.textContent);
    var nodes = {}, ends = {}, faces = data.faces || {};
    data.nodes.forEach(function (n) { nodes[n.id] = n; ends[n.id] = []; });
    var edges = data.links.map(function (l, i) {
      var pa = "p" + i + "a", pb = "p" + i + "b";
      ends[l.a].push({id: pa, side: "SOUTH", label: l.a_port, port: l.a_port});
      ends[l.b].push({id: pb, side: "NORTH", label: l.b_port, port: l.b_port});
      return {id: "e" + i, sources: [pa], targets: [pb], link: l};
    });
    // Boxes for switches/gateways/APs draw the device's real port grid (see lanxang/wiring/faceplate.py)
    // and every cable leaves from its port's real position, so the screen reads like the front panel.
    var PW = 23, PS = 20, PH = 16, TOP = 44;
    var portLabel = {}, geometry = {};
    function nodeBox(n) {
      var face = faces[n.id];
      if (!face || !face.ports.length) {
        return {width: Math.max(190, ends[n.id].length * 34), height: 62, face: null};
      }
      var width = Math.max(190, 20 + face.width * PW), height = TOP + face.rows * (PH + 3) + 10;
      var cells = {};
      face.ports.forEach(function (p) {
        p.at = {x: 10 + p.x * PW, y: TOP + p.row * (PH + 3)};
        if (!p.cage) { cells[p.name] = {x: p.at.x, y: p.at.y, cell: p}; }   // a combo SFP cage shares the RJ45 port's cable end
      });
      return {width: width, height: height, face: face, cells: cells};
    }
    var graph = {
      id: "root",
      layoutOptions: {"elk.algorithm": "layered", "elk.direction": "DOWN", "elk.edgeRouting": "ORTHOGONAL",
                      "elk.layered.spacing.nodeNodeBetweenLayers": "80", "elk.spacing.nodeNode": "28",
                      "elk.spacing.edgeEdge": "12"},
      children: data.nodes.map(function (n) {
        var box = nodeBox(n);
        geometry[n.id] = box;
        var spare = 0;
        return {id: n.id, width: box.width, height: box.height,
                layoutOptions: {"elk.portConstraints": box.face ? "FIXED_POS" : "FIXED_SIDE"},
                ports: ends[n.id].map(function (p) {
                  portLabel[p.id] = p;
                  var spec = {id: p.id, width: 8, height: 8, layoutOptions: {"elk.port.side": p.side}};
                  if (box.face) {
                    var cell = box.cells[p.port];
                    // two cables from the same column (odd above even) sit side by side, not on top of each other
                    var cx = cell ? cell.x + PS / 2 + (box.face.rows === 2 ? (cell.cell.row ? 3 : -3) : 0)
                                  : box.width - 14 - (spare++) * 12;   // logical port (LAG): right edge
                    spec.x = cx - 4;
                    spec.y = p.side === "SOUTH" ? box.height : -8;
                    p.cx = cx; p.cell = cell;
                  }
                  return spec;
                })};
      }),
      edges: edges.map(function (e) { return {id: e.id, sources: e.sources, targets: e.targets}; })
    };
    new ELK().layout(graph).then(function (res) {
      svg.setAttribute("viewBox", "-10 -10 " + (res.width + 20) + " " + (res.height + 20));
      svg.setAttribute("width", res.width + 20);
      svg.setAttribute("height", res.height + 20);
      el("style", {}, svg, SVG_CSS);
      var edgeLayer = el("g", {}, svg), nodeLayer = el("g", {}, svg), labelLayer = el("g", {}, svg);
      var byId = {}, dropCount = {};
      edges.forEach(function (e) { byId[e.id] = e.link; });
      (res.edges || []).forEach(function (e) {
        var link = byId[e.id], s = (e.sections || [])[0];
        if (!s) { return; }
        var pts = [s.startPoint].concat(s.bendPoints || []).concat([s.endPoint]);
        el("polyline", {points: pts.map(function (p) { return p.x + "," + p.y; }).join(" "),
                        "class": "edge " + speedClass(link.speed) + loadClass(link.load || 0) + (link.up ? "" : " down")
                                 + (link.standby ? " standby" : "") + (link.lag ? " bundle" : "")}, edgeLayer);
        // Label each cable on its last leg (the drop into its own device): every device has its own
        // drop, so labels never pile up on the shared horizontal runs.
        var end = pts[pts.length - 1];
        var stack = (dropCount[link.b] = (dropCount[link.b] || 0) + 1) - 1;   // several cables into one box: stagger
        var text = (link.a_port || "·") + " ⇄ " + (link.b_port || "·") + " · " + speedText(link.speed)
                   + (link.patch ? " · " + link.patch : "") + (link.lag ? " · " + link.lag : "")
                   + (link.standby && link.up ? " · standby" : "")
                   + (link.bps >= 1e6 ? " · " + rateText(link.bps) : "");
        el("text", {x: end.x + 6, y: end.y - 12 - stack * 14, "class": "el"}, labelLayer, text);
      });
      (res.children || []).forEach(function (c) {
        var n = nodes[c.id], box = geometry[c.id];
        var g = el("g", {transform: "translate(" + c.x + "," + c.y + ")", style: "cursor:pointer"}, nodeLayer);
        var tip = [n.name, n.kind, n.ip, n.mac].filter(Boolean).join(" · ");
        if (n.behind.length) { tip += "\nbehind: " + n.behind.join(", "); }
        el("title", {}, g, tip);
        el("rect", {width: c.width, height: c.height, rx: 8, "class": "node k-" + n.kind}, g);
        el("text", {x: 10, y: 19, "class": "nm"}, g, short(n.name, Math.floor(c.width / 8)));
        var sub = [n.model ? short(n.model.split(" ")[0], 18) : n.kind, n.ip].filter(Boolean).join(" · ") + (n.behind.length ? "  +" + n.behind.length + " behind" : "");
        el("text", {x: 10, y: 34, "class": "sub"}, g, sub);
        if (box.face) {
          var used = {};
          ends[c.id].forEach(function (p) { if (p.cell) { used[p.port] = true; } });
          // Downlinks get a stub from the port square to the bottom edge (drawn first, under the squares); the uplink meets the top edge
          // straight above its (outlined) port - a stub there would run through the box's title.
          ends[c.id].forEach(function (p) {
            if (!p.cell || p.side !== "SOUTH") { return; }
            el("line", {x1: p.cx, y1: p.cell.y + PH, x2: p.cx, y2: c.height, "class": "stub"}, g);
          });
          box.face.ports.forEach(function (p) {
            var cell = p.at;
            var cls = "fc" + (p.cage ? " cage" : p.up ? " up " + speedClass(p.speed) : "") + (used[p.name] && !p.cage ? " used" : "");
            var r = el("rect", {x: cell.x, y: cell.y, width: PS, height: PH, rx: 2, "class": cls}, g);
            el("title", {}, r, p.name + (p.up ? " · " + speedText(p.speed) : " · down"));
            el("text", {x: cell.x + PS / 2, y: cell.y + 11.5, "class": "fn" + (p.up && !p.cage ? " on" : "")}, g, p.cage ? p.label.replace("SFP ", "S") : p.label);
          });
        } else {
          (c.ports || []).forEach(function (p) {
            el("rect", {x: p.x, y: p.y, width: p.width, height: p.height, "class": "pt"}, g);
            var info = portLabel[p.id];
            if (info && info.label && info.side === "SOUTH") {
              el("text", {x: p.x + 4, y: p.y - 3, "text-anchor": "middle", "class": "pl"}, g, short(info.label.replace(/^Port /, "p"), 6));
            }
          });
        }
        g.addEventListener("click", function () {
          var plate = document.getElementById("fp-" + c.id);
          if (plate) { showView("faceplates"); plate.open = true; plate.scrollIntoView({behavior: "smooth"}); }
        });
      });
    }).catch(function (error) { say("Diagram layout failed: " + error); });
  }

  var exportBtn = document.getElementById("wiring-export");
  if (exportBtn) {
    exportBtn.addEventListener("click", function () {
      var root = getComputedStyle(document.documentElement);
      var text = new XMLSerializer().serializeToString(svg).replace(/var\((--[\w-]+)\)/g, function (m, name) {
        return root.getPropertyValue(name).trim() || m; });
      var blob = new Blob([text], {type: "image/svg+xml"});
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "cabling.svg";
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    });
  }

  var refresh = document.getElementById("wiring-refresh");
  if (refresh) {
    refresh.addEventListener("click", function () {
      refresh.disabled = true;
      refresh.textContent = "Scanning…";
      fetch("/api/wiring/refresh", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"})
        .then(function (r) { return r.json().then(function (body) { return [r.ok, body]; }); })
        .then(function (pair) {
          if (pair[0]) { location.reload(); return; }
          say(pair[1].error || "Refresh failed");
          refresh.disabled = false; refresh.textContent = "Refresh map";
        })
        .catch(function (error) { say("Refresh failed: " + error); refresh.disabled = false; refresh.textContent = "Refresh map"; });
    });
  }

  var detail = document.getElementById("port-detail");
  document.addEventListener("click", function (event) {
    var cell = event.target.closest(".fp .port");
    if (!cell || !detail) { return; }
    document.querySelectorAll(".fp .port.sel").forEach(function (other) { other.classList.remove("sel"); });
    cell.classList.add("sel");
    var pairs = JSON.parse(cell.dataset.detail || "[]");
    detail.textContent = "";
    function put(name, cls, parent, text) {
      var e = document.createElement(name);
      if (cls) { e.className = cls; }
      e.textContent = text || "";
      parent.appendChild(e);
      return e;
    }
    put("p", "k", detail, cell.closest(".fp").dataset.box);
    put("h3", "", detail, pairs.length ? pairs[0][1] : "");
    var list = put("dl", "", detail);
    pairs.slice(1).forEach(function (pair) {
      put("dt", "", list, pair[0]);
      put("dd", pair[0] === "Problem" ? "bad" : "", list, pair[1]);
    });
    var box = detail.getBoundingClientRect();
    if (box.top > window.innerHeight || box.bottom < 0) { detail.scrollIntoView({behavior: "smooth", block: "nearest"}); }
  });

  function showView(name) {
    document.querySelectorAll(".views button").forEach(function (button) {
      var on = button.dataset.view === name;
      button.setAttribute("aria-pressed", on ? "true" : "false");
      var section = document.getElementById(button.dataset.view);
      if (section) { section.hidden = !on; }
    });
    try { localStorage.setItem("atlas-cabling-view", name); } catch (e) {}
  }
  document.querySelectorAll(".views button").forEach(function (button) {
    button.addEventListener("click", function () { showView(button.dataset.view); });
  });
  try { var saved = localStorage.getItem("atlas-cabling-view"); if (saved) { showView(saved); } } catch (e) {}

  var vlanPick = document.getElementById("vlan-filter");
  if (vlanPick) {
    vlanPick.addEventListener("change", function () {
      var v = vlanPick.value;
      document.querySelectorAll(".fp .port[data-vlans]").forEach(function (cell) {
        cell.classList.toggle("vlan-off", v !== "" && cell.dataset.vlans.split(" ").indexOf(v) === -1);
      });
    });
  }

  var filter = document.getElementById("portmap-filter");
  if (filter) {
    filter.addEventListener("input", function () {
      var q = filter.value.toLowerCase();
      document.querySelectorAll(".portmap tbody tr").forEach(function (row) {
        row.style.display = row.textContent.toLowerCase().indexOf(q) === -1 ? "none" : "";
      });
    });
  }

  // A device page links to /cabling#fp-<node>: open that front panel.
  var linked = location.hash.indexOf("#fp-") === 0 && document.getElementById(decodeURIComponent(location.hash.slice(1)));
  if (linked) { linked.open = true; linked.scrollIntoView(); }
})();
</script>
"""


def _speed_class(speed):

    return "s10g" if speed >= 10000 else "s25" if speed >= 2500 else "s1g" if speed >= 1000 else "s100"


def _speed_text(speed):

    if not speed:
        return "?"
    return f"{speed / 1000:g}G" if speed >= 1000 else f"{speed}M"


def _ago(taken_at, now):

    minutes = int((now - taken_at).total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 120:
        return f"{minutes} min ago"
    hours = minutes // 60
    return f"{hours} h ago" if hours < 48 else f"{hours // 24} days ago"


def _spark(points, speed):
    """A small 24 h graph of a port's busier direction; the title says now and peak in words."""

    if len(points) < 2:
        return ""
    values = [max(a, b) for _, a, b in points]
    top = max(max(values), 1.0)
    step = 120 / (len(values) - 1)
    line = " ".join(f"{i * step:.1f},{22 - value / top * 20:.1f}" for i, value in enumerate(values))
    load = max(values) / (speed * 1e6) if speed else 0
    tip = (f"now {traffic.text(points[-1][1])} in / {traffic.text(points[-1][2])} out · "
           f"24 h peak {traffic.text(max(values))}" + (f" ({load:.0%} of the link)" if speed else ""))

    return (f'<svg class="spark{" hot" if load >= traffic.HOT else " busy" if load >= traffic.BUSY else ""}" '
            f'width="120" height="24" viewBox="0 0 120 24" role="img" aria-label="{_esc(tip)}">'
            f'<title>{_esc(tip)}</title><polyline points="{line}"/></svg>')


def port_rows(snapshot):
    """One row per cable, upstream side first - shared by the table and the CSV."""

    names = {node["id"]: node["name"] for node in snapshot["nodes"]}

    return [{"switch": names.get(link["a"], link["a"]), "port": link["a_port"], "bps": link.get("bps"),
             "device": names.get(link["b"], link["b"]), "device_port": link["b_port"],
             "speed": link["speed"], "up": link["up"], "via": link["via"],
             "patch": link["patch"] or "", "label": link["label"]}
            for link in snapshot["links"]]


def _csv_safe(value):

    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def cabling_csv(snapshot):

    out = io.StringIO()
    writer = csv.writer(out)
    columns = ["switch", "port", "device", "device_port", "speed", "up", "via", "patch", "label"]
    writer.writerow(columns)
    for row in port_rows(snapshot):
        writer.writerow([_csv_safe(row[column]) for column in columns])

    return out.getvalue()


def _boxes(snapshot, raw):
    """(node id, name, full port table) for every shown switch/gateway/AP - SNMP and UniFi alike."""

    boxes = [(f"s:{switch['name']}", switch["name"], switch["ports"]) for switch in (raw.get("switches") or {}).values()]
    boxes += [(f"u:{device['mac']}", device["name"], device["ports"])
              for device in ((raw.get("unifi") or {}).get("devices") or []) if device.get("ports")]
    shown = {node["id"] for node in snapshot["nodes"]}

    return [box for box in boxes if box[0] in shown]


def faces(snapshot, raw, panels=None):

    panels = panels or {}
    return {node_id: physical_layout(ports, panels.get(name)) for node_id, name, ports in _boxes(snapshot, raw)}


def _poe_text(poe):

    if poe.get("fault"):
        return "PoE fault"
    if poe.get("delivering"):
        watts = f' {poe["watts"]:g} W' if poe.get("watts") is not None else ""
        return f'PoE{watts} {poe.get("class") or ""}'.strip()

    return f'PoE capable, not powering ({poe.get("mode") or "off"})'


def _poe_summary(device, names, ports):
    """' · PoE: Port 4, Port 5 (1 powering, 12 W of 30 W)' - which ports can supply PoE, shown without expanding."""

    poe = [ports[n]["poe"] for n in names if (ports.get(n) or {}).get("poe")]
    if not poe:
        return ""
    powering = sum(1 for p in poe if p.get("delivering"))
    budget, used = device.get("poe_budget_w"), device.get("poe_used_w")
    watts = f", {used or 0:g} W of {budget:g} W" if budget else f", {used:g} W" if used else ""
    listed = ", ".join(n for n in names if (ports.get(n) or {}).get("poe"))

    return f" · PoE: {listed} ({powering or 'none'} powering{watts})"


def _faceplates(snapshot, raw, panels=None):

    health = {}
    for issue in snapshot.get("health") or []:
        health.setdefault((issue["device"], issue["port"]), []).append(issue)
    names = {node["id"]: node["name"] for node in snapshot["nodes"]}
    attached = {}
    for link in snapshot["links"]:
        attached[(link["a"], link["a_port"])] = (names.get(link["b"]), link)
        if link["b_port"]:
            attached[(link["b"], link["b_port"])] = (names.get(link["a"]), link)

    devices = {d.get("name"): d for d in list((raw.get("switches") or {}).values())
               + list((raw.get("unifi") or {}).get("devices") or [])}
    html = []
    for node_id, name, ports in _boxes(snapshot, raw):
        layout = physical_layout(ports, (panels or {}).get(name))
        cells = []
        for cell in layout["ports"]:
            other, link = attached.get((node_id, cell["name"]), (None, None))
            tip = " · ".join(filter(None, [cell["name"], _speed_text(cell["speed"]) if cell["up"] else "down", other,
                                           f"{link['patch']} {link['label']}".strip() if link else ""]))
            # Positioned like the front panel: x in port columns, row 0 = top (odd ports on rack switches).
            if cell["cage"]:
                tip = f'{cell["name"]} SFP cage (combo: shares {cell["name"]} with the RJ45 port)'
            poe = None if cell["cage"] else (ports.get(cell["name"]) or {}).get("poe")
            if poe:
                tip += " · " + _poe_text(poe)
            issues = [] if cell["cage"] else health.get((name, cell["name"]), [])
            state = ("h-bad " if any(i["level"] == "bad" for i in issues) else "h-watch ") if issues else ""
            if issues:
                tip += " · " + " · ".join(f'{i["reason"]}: {i["detail"]}' for i in issues)
            poe_class = ("poe " if poe["delivering"] else "poe-cap ") if poe else ""
            info = {} if cell["cage"] else ports.get(cell["name"]) or {}
            tip += _topology_text(info)
            vlans = _vlans(info)
            standby = "standby " if info.get("stp") in IDLE and cell["up"] else ""
            pairs = _port_detail(cell, other, link, poe, info, issues)
            cells.append(f'<button type="button" class="port {state}{poe_class}{standby}{"cage " if cell["cage"] else ""}{"up " if cell["up"] else ""}{_speed_class(cell["speed"])}" '
                         + (f'data-vlans="{" ".join(map(str, vlans))}" ' if vlans else "") +
                         f'data-detail="{_esc(json.dumps(pairs))}" '
                         f'style="left:calc({cell["x"]:g} * var(--pw));top:calc({cell["row"]} * var(--ph))" '
                         f'title="{_esc(tip)}"><b>{_esc(cell["label"])}</b><small>{_esc(other or "")}</small></button>')
        logical = "".join(
            f'<span class="lag" title="{_esc(port)}">{_esc(port)}'
            f'{" · " + _esc(attached[(node_id, port)][0]) if (node_id, port) in attached else ""}</span>'
            for port in layout["logical"] if (node_id, port) in attached)
        sockets = [cell for cell in layout["ports"] if not cell["cage"]]   # a combo cage is the same port
        up = sum(1 for cell in sockets if cell["up"])
        poe_note = ('<p class="when">Yellow = can supply PoE: solid with ' + icon("bolt") + 'when powering a device, '
                    'dashed when not.</p>' if any(p.get("poe") for p in ports.values()) else "")
        model = (devices.get(name) or {}).get("model") if node_id.startswith("s:") else ""
        html.append(f'<details open id="fp-{_esc(node_id)}"><summary>{_esc(name)} '
                    + (f'<span class="when">· {_esc(model)}</span> ' if model else "") +
                    f'<span class="when">· {up}/{len(sockets)} ports up{_esc(_poe_summary(devices.get(name) or {}, [c["name"] for c in sockets], ports))}</span></summary>'
                    f'<div class="fp-wrap"><div class="fp" data-box="{_esc(name)}" style="width:calc({layout["width"]:g} * var(--pw));'
                    f'height:calc({layout["rows"]} * var(--ph))">{"".join(cells)}</div></div>'
                    + (f'<p class="when">Port-channels: {logical}</p>' if logical else "") + poe_note + '</details>')

    every = sorted({vlan for _, _, ports in _boxes(snapshot, raw) for info in ports.values() for vlan in _vlans(info)})
    pick = ('<div class="cab-tools"><label for="vlan-filter">VLAN</label><select id="vlan-filter"><option value="">all</option>'
            + "".join(f'<option value="{vlan}">{vlan}</option>' for vlan in every) + '</select></div>'
            if len(every) > 1 else "")

    if not html:
        return '<p class="muted">No switch port data yet.</p>'
    return (pick + '<div class="fp-layout"><div>' + "".join(html) + '</div><aside class="pd" id="port-detail" '
            'aria-live="polite"><p class="muted">Pick a port to see what is plugged in and how it is doing.</p></aside></div>')


def _port_detail(cell, other, link, poe, info, issues):
    """[(label, value)] for the port panel; the first pair is its heading."""

    if cell["cage"]:
        return [("Port", f'{cell["name"]} SFP cage'), ("Shares", f'{cell["name"]} with the RJ45 port (combo)')]
    pairs = [("Port", f'Port {cell["label"]}' + (f" \u2192 {other}" if other else "")),
             ("Status", _speed_text(cell["speed"]) if cell["up"] else "down"),
             ("Connected", other or "nothing Lanxang can name")]
    if link and link.get("bps") is not None:
        load = f' ({link["load"] * 100:.0f}% of the link)' if link.get("load") is not None else ""
        pairs.append(("Traffic now", traffic.text(link["bps"]) + load))
    if link and (link.get("patch") or link.get("label")):
        pairs.append(("Patch", f'{link.get("patch") or ""} {link.get("label") or ""}'.strip()))
    if poe:
        pairs.append(("PoE", _poe_text(poe)))
    if info.get("vlan") or info.get("tagged"):
        tagged = ", ".join(map(str, sorted(info.get("tagged") or [])))
        pairs.append(("VLAN", f'{info["vlan"]} untagged' + (f", tagged {tagged}" if tagged else "") if info.get("vlan")
                      else f"tagged {tagged}"))
    if info.get("lag"):
        pairs.append(("Bundle", f'part of {info["lag"]}'))
    if info.get("stp") in IDLE and cell["up"]:
        pairs.append(("Standby", "spanning tree keeps this cable idle so there is no loop"))
    pairs += [("Problem", f'{issue["reason"]}: {issue["detail"]}') for issue in issues]

    return pairs


def _vlans(info):

    return sorted({info["vlan"]} if info.get("vlan") else set()) + sorted(set(info.get("tagged") or []) - {info.get("vlan")})


def _topology_text(info):

    parts = []
    if info.get("lag"):
        parts.append(f'in {info["lag"]}')
    if info.get("stp") in IDLE:
        parts.append(f'spanning tree: {info["stp"]} (standby)')
    if info.get("vlan"):
        parts.append(f'VLAN {info["vlan"]}' + (f', tagged {", ".join(map(str, sorted(info["tagged"])))}'
                                               if info.get("tagged") else ""))
    elif info.get("tagged"):
        parts.append(f'tagged VLANs {", ".join(map(str, sorted(info["tagged"])))}')

    return "".join(" · " + part for part in parts)


def _health(snapshot):
    """The Cable health list, problems first. Snapshots saved before cable health existed show nothing."""

    if "health" not in snapshot:
        return ""
    issues = sorted(snapshot["health"], key=lambda i: (i["level"] != "bad", i["device"], i["port"]))
    if not issues:
        body = '<p class="muted">No problems: every connected port is clean since the last scan.</p>'
    else:
        body = "<ul>" + "".join(
            f'<li class="{i["level"]}"><span class="lvl">{"Problem" if i["level"] == "bad" else "Watch"}</span>'
            f'<b>{_esc(i["device"])} {_esc(i["port"])}</b> · {_esc(i["reason"])}: {_esc(i["detail"])}</li>'
            for i in issues) + "</ul>"

    return ('<section id="health"><h2>Cable health</h2>' + body +
            '<p class="when">Checked on every scan. Growing CRC errors, duplex mismatches and PoE faults send an '
            'alert; a slower link, a link that dropped or a nearly used PoE budget is only shown here. '
            + icon("bolt") + '= port powering a device, dashed outline = port that can supply PoE.</p></section>')


def suggestion_banner(suggested):
    """'N devices could show their ports with a login' - links to the Setup tab's Switches card."""

    if not suggested:
        return ""
    names = ", ".join(entry["name"] for entry in suggested[:3]) + (" and more" if len(suggested) > 3 else "")
    count = len(suggested)

    return (f'<p class="suggest">{icon("key")}{count} device{"s" * (count != 1)} on your network could show '
            f'{"their" if count != 1 else "its"} ports with a login: {_esc(names)}. '
            '<a href="/settings#switches">Add on the Setup tab \u2192</a></p>')


def _summary(snapshot, raw):

    boxes = len(_boxes(snapshot, raw))
    problems = len(snapshot.get("health") or []) + len(snapshot["warnings"])
    return (f"{boxes} switch{'es' * (boxes != 1)} · {len(snapshot['links'])} cables · "
            + (f"{problems} to check" if problems else "nothing to check"))


def render_cabling_page(latest, changes, enabled, now=None, faceplates=None, suggested=(), history=None):

    if not enabled:
        body = ('<p class="muted">The cabling map is off. Add a managed switch or a UniFi console on the '
                f'<a href="/settings#switches">Setup tab</a> (or a <code>wiring:</code> section in {config_name()}), '
                'and copy cabling.example.yaml to cabling.yaml for patch panels.</p>' + suggestion_banner(suggested))
        return render_page("Cabling", CABLING_STYLE + body, active="cabling")

    refresh = '<button class="cab-btn" id="wiring-refresh" type="button">Refresh map</button>'

    if not latest:
        body = (f'<div class="cab-head">{refresh}</div><p id="msg"></p>'
                '<p class="muted">No wiring scan yet - press Refresh map (or run <code>lanxang wiring scan</code>).</p>')
        return render_page("Cabling", CABLING_STYLE + body + DIAGRAM_SCRIPT, active="cabling")

    now = now or utcnow()
    snapshot, sources = latest["snapshot"], latest["sources"]

    chips = []
    for name, source in sources.items():
        state = "ok" if source["ok"] else "stale" if source["stale"] else "error"
        detail = source["error"] or source["note"] or "ok"
        chips.append(f'<span class="chip {state}" title="{_esc(detail)}">{_esc(name)}'
                     f'{" · stale" if state == "stale" else ""}{" · " + _esc(source["note"]) if source["note"] else ""}</span>')

    warnings = "".join(f"<li>{_esc(warning)}</li>" for warning in snapshot["warnings"])
    notes = "".join(f"<li>{_esc(note)}</li>" for note in snapshot.get("notes") or [])
    data = json.dumps({"nodes": snapshot["nodes"], "links": snapshot["links"],
                       "faces": faces(snapshot, latest.get("raw") or {}, faceplates)}).replace("</", "<\\/")

    rows = "".join(
        f'<tr><td>{_esc(row["switch"])}</td><td>{_esc(row["port"])}</td><td>{_esc(row["device"])}</td>'
        f'<td>{_esc(row["device_port"])}</td><td class="{"" if row["up"] else "down"}">'
        f'{_esc(_speed_text(row["speed"]) if row["up"] else "down")}</td><td>{_esc(row["patch"])}</td>'
        f'<td class="rate">{_spark((history or {}).get((row["switch"], row["port"]), []), row["speed"])}'
        f'{_esc(traffic.text(row["bps"])) if row["bps"] is not None else ""}</td>'
        f'<td>{_esc(row["label"])}</td><td>{_esc(row["via"])}</td></tr>'
        for row in port_rows(snapshot))

    panels = "".join(
        f'<tr><td>{_esc(panel["panel"])}-{panel["port"]:02d}</td><td>{_esc(panel["label"])}</td>'
        f'<td>{_esc(panel["switch"])} {_esc(panel["switch_port"])}</td><td>{_esc(panel["device"])}</td>'
        f'<td>{_esc(_speed_text(panel["speed"]) if panel["up"] else "down")}</td></tr>'
        for panel in snapshot["panels"])
    panel_html = (f'<table class="portmap"><thead><tr><th>Panel port</th><th>Label</th><th>Switch port</th>'
                  f'<th>Device</th><th>Link</th></tr></thead><tbody>{panels}</tbody></table>' if panels else
                  '<p class="muted">No patch panels described yet - add them to cabling.yaml '
                  '(see cabling.example.yaml).</p>')

    change_html = ("<ul>" + "".join(f"<li>{_esc(change['text'])}</li>" for change in changes) + "</ul>"
                   if changes else '<p class="muted">No changes since the previous scan.</p>')

    taken = latest["taken_at"]
    body = (
        f'<div class="cab-head">{refresh}<span class="when">Refreshed '
        f'<time datetime="{_esc(taken.isoformat())}Z">{_esc(_ago(taken, now))}</time></span>{"".join(chips)}</div>'
        '<p id="msg"></p>'
        + suggestion_banner(suggested)
        + (f'<ul class="warn">{warnings}</ul>' if warnings else "")
        + (f'<ul class="notes">{notes}</ul>' if notes else "")
        + '<div class="cab-head"><span class="cab-sum">' + _esc(_summary(snapshot, latest.get("raw") or {})) + '</span>'
        '<div class="views" role="group" aria-label="View"><button type="button" data-view="faceplates" '
        'aria-pressed="true">Front panels</button><button type="button" data-view="diagram" aria-pressed="false">'
        'Map</button></div></div>'
        f'<section id="faceplates"><h2>Front panels</h2>{_faceplates(snapshot, latest.get("raw") or {}, faceplates)}</section>'
        + '<section id="diagram" hidden><h2>Map</h2>'
        '<div class="legend"><span><i style="background:var(--muted)"></i>100M</span>'
        '<span><i style="background:var(--blue)"></i>1G</span><span><i style="background:var(--teal)"></i>2.5G</span>'
        '<span><i style="background:var(--purple)"></i>10G</span><span>thick orange = over half full, red = over 80%</span><span>dashed = down</span><span>dotted grey = standby</span>'
        '<span>click a box for its ports</span>'
        '<button class="cab-btn ghost" id="wiring-export" type="button">Export SVG</button></div>'
        f'<div class="frame"><svg id="wiring-svg" xmlns="http://www.w3.org/2000/svg"></svg></div>'
        f'<script type="application/json" id="wiring-data">{data}</script></section>'
        + _health(snapshot) +
        '<section id="portmap"><h2>Port map</h2><div class="cab-tools">'
        '<input id="portmap-filter" type="search" placeholder="Filter: device, port, label…" aria-label="Filter port map">'
        '<a class="cab-btn ghost" href="/cabling.csv" download>CSV</a></div>'
        '<table class="portmap"><thead><tr><th>Switch</th><th>Port</th><th>Device</th><th>Device port</th>'
        f'<th>Link</th><th>Patch</th><th>Traffic (24 h)</th><th>Label</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table></section>'
        f'<section id="patch"><h2>Patch panels</h2>{panel_html}</section>'
        f'<section id="changes"><h2>Changes since the previous scan</h2>{change_html}</section>'
    )

    return render_page("Cabling", CABLING_STYLE + body + DIAGRAM_SCRIPT, active="cabling")
