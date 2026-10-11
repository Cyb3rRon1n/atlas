"""
/map - the Network page: what is reachable from the internet, what only from
home, what runs in the background, and the machines/devices behind it all.
Plain server-rendered lanes (no canvas, nothing to zoom). Pure renderers:
server.py passes the latest topology, Traefik routes and the device graph.
"""

import re

from atlas.web.render import _esc, ask_chips, render_page

UNNAMED = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


NETWORK_CHIPS = ("What is reachable from the internet without Authelia?",
                 "Is anything exposed that should only be on the home network?",
                 "Which containers are down or unhealthy right now?",
                 "Explain how a visitor reaches Jellyfin from outside.")

NETWORK_STYLE = """
<style>
.nlane { border:1px dashed #2c4560; border-radius:12px; padding:12px 14px; margin-bottom:14px; background:rgba(90,167,240,.04); }
.nlane > h2, .nlane > summary { margin:0 0 4px; font-size:13px; font-weight:600; text-transform:uppercase; letter-spacing:.06em;
                                color:var(--muted); border:0; padding:0; cursor:default; }
.nlane > summary { cursor:pointer; }
.nlane .why { margin:0 0 10px; font-size:13px; color:var(--muted); }
.nlane h3.sub { margin:14px 0 2px; font-size:14px; }
.svc { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:8px; }
.svc details { background:#1b2430; border:1px solid #2f3b4c; border-radius:8px; padding:8px 10px; font-size:14px; }
.svc details[open] { border-color:var(--blue); }
.svc summary { display:flex; align-items:center; gap:8px; cursor:pointer; list-style:none; }
.svc summary::-webkit-details-marker { display:none; }
.svc .name { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.svc dl { display:grid; grid-template-columns:auto 1fr; gap:3px 10px; margin:8px 0 0; font-size:12px; }
.svc dt { color:var(--muted); } .svc dd { margin:0; word-break:break-all; }
.badge { font-size:11px; padding:1px 7px; border-radius:999px; border:1px solid var(--line); color:var(--muted); white-space:nowrap; }
.badge.auth { color:#7fdcb5; border-color:#2f6b55; } .badge.own { color:#ffd08a; border-color:#6b5530; }
.badge.vpn { color:#9fd0ff; border-color:#2c4560; }
.dot { width:9px; height:9px; border-radius:50%; background:var(--muted); display:inline-block; flex:none; }
.dot.ok { background:var(--green); } .dot.warn { background:var(--orange); } .dot.down { background:var(--red); }
.machines { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:10px; }
.machine { background:#111821; border:1px solid #222c38; border-radius:10px; padding:10px 12px; font-size:14px; }
.machine h3 { margin:0 0 6px; font-size:14px; display:flex; gap:8px; align-items:center; }
.machine ul, .tree ul { list-style:none; margin:0; padding:0; }
.machine li { display:flex; gap:8px; align-items:center; padding:2px 0; }
.tree ul ul { margin-left:18px; padding-left:10px; border-left:1px solid var(--line); }
.tree li { padding:3px 0; }
.tree .row { display:inline-flex; gap:8px; align-items:center; font-size:14px; }
.tree .kind { font-size:12px; color:var(--muted); }
</style>
"""


def _state(container):

    if container["status"] != "running":
        return "down"

    return "warn" if container.get("health") == "unhealthy" else "ok"


def classify(topology, routes):
    """
    Split this host's containers into internet / home / background:
    internet = a Traefik route on the `tunnel` entrypoint (Cloudflare tunnel),
    home = any other route or a published host port, background = neither.
    """

    by_host = {host: route for route in routes or [] for host in route.get("hosts", [])}
    lanes = {"internet": [], "home": [], "background": []}

    for network, members in ((topology or {}).get("docker") or {}).get("networks", {}).items():
        for c in members:
            mine = [by_host[h] for h in c.get("public", []) if h in by_host]
            item = {"name": c["name"], "state": _state(c), "health": c.get("health") or "", "status": c["status"],
                    "network": network, "vpn": network == "via gluetun", "hosts": c.get("public", []),
                    "ports": c.get("ports", []),
                    "protection": "authelia" if any(r.get("protection") == "authelia" for r in mine) else "own"}
            if any("tunnel" in r.get("entrypoints", []) for r in mine):
                lanes["internet"].append(item)
            elif c.get("public") or c.get("ports"):
                lanes["home"].append(item)
            else:
                lanes["background"].append(item)

    for items in lanes.values():
        items.sort(key=lambda item: (item["state"] == "ok", item["name"]))

    return lanes


def _service(item, lane):

    badges = ""
    if lane == "internet":
        badges += ('<span class="badge auth">Authelia</span>' if item["protection"] == "authelia"
                   else '<span class="badge own">own login</span>')
    if item["vpn"]:
        badges += '<span class="badge vpn">via VPN</span>'

    rows = [("Status", item["status"] + (f" ({item['health']})" if item["health"] else "")), ("Network", item["network"])]
    if item["hosts"]:
        rows.append(("Address", ", ".join(item["hosts"])))
    if item["ports"]:
        rows.append(("Ports", ", ".join(map(str, item["ports"]))))
    detail = "".join(f"<dt>{_esc(k)}</dt><dd>{_esc(v)}</dd>" for k, v in rows)
    link = (f'<dt></dt><dd><a href="https://{_esc(item["hosts"][0])}" target="_blank" rel="noopener">open</a></dd>'
            if item["hosts"] and lane == "internet" else "")

    return (f'<details><summary><span class="dot {item["state"]}"></span><span class="name">{_esc(item["name"])}</span>'
            f'{badges}</summary><dl>{detail}{link}</dl></details>')


def _tree(graph):
    """
    The device graph (atlas.web.graph.build_graph) as a nested list: edges give
    the uplink tree from Internet, `parent` nests guests inside their host.
    """

    nodes = {n["data"]["id"]: n["data"] for n in (graph or {}).get("nodes", [])}
    kids = {}
    for e in (graph or {}).get("edges", []):
        kids.setdefault(e["data"]["source"], []).append(e["data"]["target"])
    for node_id, data in nodes.items():
        if data.get("parent"):
            kids.setdefault(data["parent"], []).append(node_id)

    seen = set()

    def item(node_id):
        if node_id in seen or node_id not in nodes:
            return ""
        seen.add(node_id)
        d = nodes[node_id]
        dot = {"seen": "ok", "quiet": "warn", "invisible": ""}.get(d.get("status", ""), "")
        label = _esc(d.get("label") or node_id)
        if d.get("device_id") is not None:
            label = f'<a href="/devices/{int(d["device_id"])}">{label}</a>'
        kind = f'<span class="kind">{_esc(d["kind"])}</span>' if d.get("kind") and d["kind"] != "other" else ""
        order = sorted(kids.get(node_id, []), key=lambda k: str(nodes.get(k, {}).get("label")))
        # devices nobody named yet (label is still a bare IP) fold into one line so the tree stays short
        unnamed = [k for k in order if UNNAMED.match(str(nodes.get(k, {}).get("label", ""))) and not kids.get(k)]
        children = "".join(item(k) for k in order if k not in unnamed)
        if unnamed:
            children += (f'<li><details><summary class="kind">{len(unnamed)} unnamed devices - name them on '
                         f'Devices</summary><ul>{"".join(item(k) for k in unnamed)}</ul></details></li>')
        return (f'<li><span class="row"><span class="dot {dot}"></span>{label}{kind}</span>'
                + (f"<ul>{children}</ul>" if children else "") + "</li>")

    roots = [n for n in nodes if n == "internet"] or [n for n in nodes if not nodes[n].get("parent")][:1]
    body = "".join(item(r) for r in roots)
    hidden = (graph or {}).get("hidden_wireless") or 0
    note = f'<p class="why">{hidden} wireless devices hidden - see <a href="/devices">Devices</a>.</p>' if hidden else ""

    return f'<div class="tree"><ul>{body}</ul></div>{note}' if body else '<p class="muted">No devices yet.</p>'


def render_network_page(topology, routes, graph):

    if not topology:
        body = '<p class="muted">No network snapshot yet - atlas-scan refreshes it every 15 minutes (<code>atlas map</code>).</p>'
        return render_page("Network", body, active="lan")

    lanes = classify(topology, routes)
    grid = lambda lane, items=None: '<div class="svc">' + "".join(_service(i, lane) for i in (lanes[lane] if items is None else items)) + "</div>"
    guarded = [i for i in lanes["internet"] if i["protection"] == "authelia"]
    own = [i for i in lanes["internet"] if i["protection"] != "authelia"]
    down = sum(i["state"] != "ok" for items in lanes.values() for i in items)

    guests = [g for g in (topology.get("proxmox") or {}).get("guests", []) if not g.get("template")]
    guest_names = {g["name"] for g in guests}
    lan = [h for h in topology.get("lan", []) if h["name"] not in guest_names]   # a guest is listed once, under Proxmox
    total = sum(len(v) for v in lanes.values())
    machines = (
        f'<div class="machine"><h3><span class="dot ok"></span>{_esc(topology.get("host", "this host"))}</h3>'
        f'<p class="why">{total} containers, {total - down} healthy - grouped above</p></div>'
        + ('<div class="machine"><h3>Proxmox guests</h3><ul>' + "".join(
            f'<li><span class="dot {"ok" if g["status"] == "running" else "down"}"></span>{_esc(g["name"])}'
            f' <span class="kind">{_esc(g.get("type", ""))}</span></li>' for g in guests) + "</ul></div>" if guests else "")
        + ('<div class="machine"><h3>Other machines</h3><ul>' + "".join(
            f'<li><span class="dot {"ok" if h["reachable"] else "down"}"></span>{_esc(h["name"])}'
            f' <span class="kind">{_esc(h.get("role") or h["address"])}</span></li>' for h in lan) + "</ul></div>" if lan else "")
    )

    body = (
        NETWORK_STYLE + ask_chips(NETWORK_CHIPS)
        + f'<p class="muted">Snapshot {_esc(topology.get("generated_at", ""))}. Click a service for details.'
        + (f' <strong>{down} not healthy</strong> (listed first in each lane).' if down else "") + "</p>"
        + '<section class="nlane"><h2>\U0001F310 From the internet</h2><p class="why">Reachable by anyone through the '
          'Cloudflare tunnel. Every request passes CrowdSec (bans bad IPs) and is logged; Atlas watches it.</p>'
        + f'<h3 class="sub">\U0001F512 Behind Authelia ({len(guarded)})</h3><p class="why">Authelia\'s login comes first - '
          'nobody reaches the app without your account.</p>' + grid("internet", guarded)
        + f'<h3 class="sub">\U0001F6E1\ufe0f Own login only ({len(own)})</h3><p class="why">Not behind Authelia (their '
          'phone/TV apps can\'t pass it) - the app\'s own login is the gate, CrowdSec and Atlas still watch.</p>'
        + grid("internet", own) + "</section>"
        + '<section class="nlane"><h2>\U0001F3E0 Home network only</h2><p class="why">A web page or port, but no '
          'route from the internet.</p>' + grid("home") + "</section>"
        + '<details class="nlane"><summary>⚙️ Background (' + str(len(lanes["background"]))
        + ')</summary><p class="why">No web page - helpers like the VPN tunnel, CrowdSec and Recyclarr.</p>'
        + grid("background") + "</details>"
        + '<section class="nlane"><h2>\U0001F5A5️ Machines</h2><div class="machines">' + machines + "</div></section>"
        + '<section class="nlane"><h2>\U0001F50C Devices by connection</h2>' + _tree(graph) + "</section>"
    )

    return render_page("Network", body, active="lan")
