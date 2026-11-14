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

from atlas.web.render import _esc, render_page


INFRA = ("wan", "gateway", "switch", "ap")

CABLING_STYLE = """
<style>
.cab-head { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-bottom:10px; }
.cab-head .when { color:var(--muted); font-size:14px; }
.chip { font-size:12px; padding:2px 9px; border-radius:999px; border:1px solid var(--line); }
.chip.ok { color:#7fdcb5; border-color:#2f6b55; } .chip.stale { color:#ffd08a; border-color:#6b5530; }
.chip.error { color:#ff9b9b; border-color:#6b3030; }
.cab-btn { background:#1f6feb; color:#fff; border:0; border-radius:6px; padding:6px 12px; cursor:pointer; font:inherit; }
.cab-btn.ghost { background:transparent; border:1px solid var(--line); color:inherit; }
.cab-btn[disabled] { opacity:.6; cursor:wait; }
.warn { margin:6px 0 12px; padding:8px 12px 8px 28px; border:1px solid #6b5530; border-radius:8px; color:#ffd08a; font-size:14px; }
#diagram .frame { overflow:auto; border:1px solid var(--line); border-radius:10px; background:#0b1016; max-height:78vh; }
#wiring-svg { display:block; min-width:100%; }
.legend { display:flex; flex-wrap:wrap; gap:14px; font-size:12px; color:var(--muted); margin:6px 0; }
.legend i { display:inline-block; width:22px; height:3px; vertical-align:middle; margin-right:5px; }
.fp { display:grid; grid-template-columns:repeat(auto-fill,minmax(74px,1fr)); gap:6px; margin:8px 0 14px; }
.fp span { border:1px solid #2f3b4c; border-radius:6px; padding:4px 6px; font-size:11px; background:#111821; opacity:.55; min-height:36px; }
.fp span.up { opacity:1; }
.fp span b { display:block; font-size:12px; }
.fp span small { display:block; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.fp .s100 { border-color:#8b98a5; } .fp .s1g { border-color:#5aa7f0; } .fp .s25 { border-color:#3ccfb4; } .fp .s10g { border-color:#b48cf2; }
#faceplates details { border:1px solid var(--line); border-radius:10px; padding:8px 12px; margin-bottom:8px; }
#faceplates summary { cursor:pointer; font-weight:600; }
.portmap { width:100%; border-collapse:collapse; font-size:13px; }
.portmap th, .portmap td { text-align:left; padding:4px 8px; border-bottom:1px solid #222c38; }
.portmap td.down { color:#ff9b9b; }
.cab-tools { display:flex; gap:8px; align-items:center; margin:8px 0; }
.cab-tools input { background:#0d1117; color:inherit; border:1px solid var(--line); border-radius:6px; padding:5px 8px; min-width:240px; }
#changes li { font-size:14px; }
</style>
"""

DIAGRAM_SCRIPT = r"""
<script src="/static/elk.bundled.js"></script>
<script>
(function () {
  var NS = "http://www.w3.org/2000/svg";
  var SVG_CSS = ".node{fill:#151d27;stroke:#3a4a5e;stroke-width:1.5}.k-gateway{stroke:#f0a35a}.k-switch{stroke:#5aa7f0}"
    + ".k-ap{stroke:#3ccfb4}.k-bridge{stroke:#e5c45a}.k-wan{stroke:#8b98a5;stroke-dasharray:4 3}.k-unknown{stroke-dasharray:3 3}"
    + ".nm{fill:#e6edf3;font:600 13px system-ui,sans-serif}.sub{fill:#8b98a5;font:11px system-ui,sans-serif}"
    + ".pt{fill:#3a4a5e}.pl{fill:#c9d1d9;font:10px ui-monospace,monospace}"
    + ".edge{fill:none;stroke-width:2.5}.s100{stroke:#8b98a5}.s1g{stroke:#5aa7f0}.s25{stroke:#3ccfb4}.s10g{stroke:#b48cf2}"
    + ".down{stroke-dasharray:6 4;opacity:.6}.el{fill:#e6edf3;font:11px ui-monospace,monospace;paint-order:stroke;"
    + "stroke:#0b1016;stroke-width:4px;stroke-linejoin:round}";
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
  function speedText(s) { return s >= 1000 ? (s / 1000) + "G" : (s ? s + "M" : "?"); }
  function short(text, n) { text = String(text || ""); return text.length > n ? text.slice(0, n - 1) + "…" : text; }

  if (holder && svg && window.ELK) {
    var data = JSON.parse(holder.textContent);
    var nodes = {}, ends = {};
    data.nodes.forEach(function (n) { nodes[n.id] = n; ends[n.id] = []; });
    var edges = data.links.map(function (l, i) {
      var pa = "p" + i + "a", pb = "p" + i + "b";
      ends[l.a].push({id: pa, side: "SOUTH", label: l.a_port});
      ends[l.b].push({id: pb, side: "NORTH", label: l.b_port});
      return {id: "e" + i, sources: [pa], targets: [pb], link: l};
    });
    var portLabel = {};
    var graph = {
      id: "root",
      layoutOptions: {"elk.algorithm": "layered", "elk.direction": "DOWN", "elk.edgeRouting": "ORTHOGONAL",
                      "elk.layered.spacing.nodeNodeBetweenLayers": "80", "elk.spacing.nodeNode": "28",
                      "elk.spacing.edgeEdge": "14"},
      children: data.nodes.map(function (n) {
        return {id: n.id, width: Math.max(190, ends[n.id].length * 34), height: 62,
                layoutOptions: {"elk.portConstraints": "FIXED_SIDE"},
                ports: ends[n.id].map(function (p) {
                  portLabel[p.id] = p;
                  return {id: p.id, width: 8, height: 8, layoutOptions: {"elk.port.side": p.side}};
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
      var byId = {};
      edges.forEach(function (e) { byId[e.id] = e.link; });
      (res.edges || []).forEach(function (e) {
        var link = byId[e.id], s = (e.sections || [])[0];
        if (!s) { return; }
        var pts = [s.startPoint].concat(s.bendPoints || []).concat([s.endPoint]);
        el("polyline", {points: pts.map(function (p) { return p.x + "," + p.y; }).join(" "),
                        "class": "edge " + speedClass(link.speed) + (link.up ? "" : " down")}, edgeLayer);
        // Label each cable on its last leg (the drop into its own device): every device has its own
        // drop, so labels never pile up on the shared horizontal runs.
        var end = pts[pts.length - 1];
        var text = (link.a_port || "·") + " ⇄ " + (link.b_port || "·") + " · " + speedText(link.speed)
                   + (link.patch ? " · " + link.patch : "");
        el("text", {x: end.x + 6, y: end.y - 12, "class": "el"}, labelLayer, text);
      });
      (res.children || []).forEach(function (c) {
        var n = nodes[c.id];
        var g = el("g", {transform: "translate(" + c.x + "," + c.y + ")", style: "cursor:pointer"}, nodeLayer);
        var tip = [n.name, n.kind, n.ip, n.mac].filter(Boolean).join(" · ");
        if (n.behind.length) { tip += "\nbehind: " + n.behind.join(", "); }
        el("title", {}, g, tip);
        el("rect", {width: c.width, height: c.height, rx: 8, "class": "node k-" + n.kind}, g);
        el("text", {x: 10, y: 19, "class": "nm"}, g, short(n.name, Math.floor(c.width / 8)));
        var sub = [n.kind, n.ip].filter(Boolean).join(" · ") + (n.behind.length ? "  +" + n.behind.length + " behind" : "");
        el("text", {x: 10, y: 34, "class": "sub"}, g, sub);
        (c.ports || []).forEach(function (p) {
          el("rect", {x: p.x, y: p.y, width: p.width, height: p.height, "class": "pt"}, g);
          var info = portLabel[p.id];
          if (info && info.label && info.side === "SOUTH") {
            el("text", {x: p.x + 4, y: p.y - 3, "text-anchor": "middle", "class": "pl"}, g, short(info.label.replace(/^Port /, "p"), 6));
          }
        });
        g.addEventListener("click", function () {
          var plate = document.getElementById("fp-" + c.id);
          if (plate) { plate.open = true; plate.scrollIntoView({behavior: "smooth"}); }
        });
      });
    }).catch(function (error) { say("Diagram layout failed: " + error); });
  }

  var exportBtn = document.getElementById("wiring-export");
  if (exportBtn) {
    exportBtn.addEventListener("click", function () {
      var blob = new Blob([new XMLSerializer().serializeToString(svg)], {type: "image/svg+xml"});
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

  var filter = document.getElementById("portmap-filter");
  if (filter) {
    filter.addEventListener("input", function () {
      var q = filter.value.toLowerCase();
      document.querySelectorAll(".portmap tbody tr").forEach(function (row) {
        row.style.display = row.textContent.toLowerCase().indexOf(q) === -1 ? "none" : "";
      });
    });
  }
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


def port_rows(snapshot):
    """One row per cable, upstream side first - shared by the table and the CSV."""

    names = {node["id"]: node["name"] for node in snapshot["nodes"]}

    return [{"switch": names.get(link["a"], link["a"]), "port": link["a_port"],
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


def _faceplates(snapshot, raw):

    names = {node["id"]: node["name"] for node in snapshot["nodes"]}
    attached = {}
    for link in snapshot["links"]:
        attached[(link["a"], link["a_port"])] = (names.get(link["b"]), link)
        if link["b_port"]:
            attached[(link["b"], link["b_port"])] = (names.get(link["a"]), link)

    boxes = []
    for switch in (raw.get("switches") or {}).values():
        boxes.append((f"s:{switch['name']}", switch["name"], switch["ports"]))
    for device in ((raw.get("unifi") or {}).get("devices") or []):
        if device.get("ports"):
            boxes.append((f"u:{device['mac']}", device["name"], device["ports"]))

    shown = {node["id"] for node in snapshot["nodes"]}
    html = []
    for node_id, name, ports in boxes:
        if node_id not in shown:
            continue
        cells = []
        for port, info in sorted(ports.items(), key=lambda item: (item[1].get("index") or 0, item[0])):
            other, link = attached.get((node_id, port), (None, None))
            tip = " · ".join(filter(None, [port, _speed_text(info["speed"]) if info["up"] else "down", other,
                                           f"{link['patch']} {link['label']}".strip() if link else ""]))
            short = port.replace("Port ", "") if port.startswith("Port ") else port
            cells.append(f'<span class="{"up " if info["up"] else ""}{_speed_class(info["speed"])}" title="{_esc(tip)}">'
                         f'<b>{_esc(short)}</b><small>{_esc(other or "")}</small></span>')
        up = sum(1 for info in ports.values() if info["up"])
        html.append(f'<details id="fp-{_esc(node_id)}"><summary>{_esc(name)} '
                    f'<span class="when">· {up}/{len(ports)} ports up</span></summary>'
                    f'<div class="fp">{"".join(cells)}</div></details>')

    return "".join(html) or '<p class="muted">No switch port data yet.</p>'


def render_cabling_page(latest, changes, enabled, now=None):

    if not enabled:
        body = ('<p class="muted">The cabling map is off. Add a <code>wiring:</code> section to atlas.yaml '
                '(see atlas.yaml.example) and copy cabling.example.yaml to cabling.yaml for patch panels.</p>')
        return render_page("Cabling", CABLING_STYLE + body, active="cabling")

    refresh = '<button class="cab-btn" id="wiring-refresh" type="button">Refresh map</button>'

    if not latest:
        body = (f'<div class="cab-head">{refresh}</div><p id="msg"></p>'
                '<p class="muted">No wiring scan yet - press Refresh map (or run <code>atlas wiring scan</code>).</p>')
        return render_page("Cabling", CABLING_STYLE + body + DIAGRAM_SCRIPT, active="cabling")

    now = now or datetime.utcnow()
    snapshot, sources = latest["snapshot"], latest["sources"]

    chips = []
    for name, source in sources.items():
        state = "ok" if source["ok"] else "stale" if source["stale"] else "error"
        detail = source["error"] or source["note"] or "ok"
        chips.append(f'<span class="chip {state}" title="{_esc(detail)}">{_esc(name)}'
                     f'{" · stale" if state == "stale" else ""}{" · " + _esc(source["note"]) if source["note"] else ""}</span>')

    warnings = "".join(f"<li>{_esc(warning)}</li>" for warning in snapshot["warnings"])
    data = json.dumps({"nodes": snapshot["nodes"], "links": snapshot["links"]}).replace("</", "<\\/")

    rows = "".join(
        f'<tr><td>{_esc(row["switch"])}</td><td>{_esc(row["port"])}</td><td>{_esc(row["device"])}</td>'
        f'<td>{_esc(row["device_port"])}</td><td class="{"" if row["up"] else "down"}">'
        f'{_esc(_speed_text(row["speed"]) if row["up"] else "down")}</td><td>{_esc(row["patch"])}</td>'
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
        + (f'<ul class="warn">{warnings}</ul>' if warnings else "")
        + '<section id="diagram"><h2>Wired topology</h2>'
        '<div class="legend"><span><i style="background:#8b98a5"></i>100M</span>'
        '<span><i style="background:#5aa7f0"></i>1G</span><span><i style="background:#3ccfb4"></i>2.5G</span>'
        '<span><i style="background:#b48cf2"></i>10G</span><span>dashed = down</span>'
        '<span>click a box for its ports</span>'
        '<button class="cab-btn ghost" id="wiring-export" type="button">Export SVG</button></div>'
        f'<div class="frame"><svg id="wiring-svg" xmlns="http://www.w3.org/2000/svg"></svg></div>'
        f'<script type="application/json" id="wiring-data">{data}</script></section>'
        f'<section id="faceplates"><h2>Switch ports</h2>{_faceplates(snapshot, latest.get("raw") or {})}</section>'
        '<section id="portmap"><h2>Port map</h2><div class="cab-tools">'
        '<input id="portmap-filter" type="search" placeholder="Filter: device, port, label…" aria-label="Filter port map">'
        '<a class="cab-btn ghost" href="/cabling.csv" download>CSV</a></div>'
        '<table class="portmap"><thead><tr><th>Switch</th><th>Port</th><th>Device</th><th>Device port</th>'
        f'<th>Link</th><th>Patch</th><th>Label</th><th>Source</th></tr></thead><tbody>{rows}</tbody></table></section>'
        f'<section id="patch"><h2>Patch panels</h2>{panel_html}</section>'
        f'<section id="changes"><h2>Changes since the previous scan</h2>{change_html}</section>'
    )

    return render_page("Cabling", CABLING_STYLE + body + DIAGRAM_SCRIPT, active="cabling")
