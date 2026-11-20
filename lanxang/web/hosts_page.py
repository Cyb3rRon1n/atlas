"""
Summary half of /overview (Hosts): one card per machine with usage bars, the
storage card, this host's containers as status chips by network, and the
Proxmox guests. Pure renderer over data server.py already gathers for Home
(build_hosts / build_storage) plus the latest topology.
"""

from lanxang.web.blocks import sparkline
from lanxang.web.render import _esc, ask_chips, plural


HOSTS_CHIPS = ("What is using the most CPU and memory right now?", "Is any disk or pool getting full?",
               "Which containers restarted or are unhealthy?", "How is my Proxmox host doing?")

HOSTS_STYLE = """
<style>
.hgrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:16px; margin-bottom:16px; }
.hbox { background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:16px; }
.hbox.warn { border-color:var(--red); }
.hbox h2 { margin:0 0 10px; font-size:1rem; border:0; padding:0; display:flex; gap:8px; align-items:center; }
.meter { display:grid; grid-template-columns:48px 1fr 44px auto; gap:8px; align-items:center; font-size:.8125rem; margin:6px 0; }
.meter .track { height:8px; border-radius:4px; background:var(--surface2); overflow:hidden; }
.meter .fill { height:100%; background:var(--green); }
.meter .fill.mid { background:var(--orange); } .meter .fill.high { background:var(--red); }
.hbox .bad { color:var(--bad-text); font-size:.8125rem; }
.chipset h3 { margin:12px 0 6px; font-size:.75rem; color:var(--muted); font-weight:500; text-transform:uppercase; letter-spacing:.06em; }
.cchip { display:inline-flex; align-items:center; gap:6px; margin:0 6px 6px 0; padding:4px 10px; border-radius:999px;
         background:var(--surface2); font-size:.8125rem; }
.dot { width:9px; height:9px; border-radius:50%; background:var(--muted); display:inline-block; flex:none; }
.dot.ok { background:var(--green); } .dot.warn { background:var(--orange); } .dot.down { background:var(--red); }
.srow { display:flex; justify-content:space-between; gap:8px; padding:5px 0; border-top:1px solid var(--line); font-size:.875rem; }
.srow:first-of-type { border-top:0; } .srow.warn span:last-child { color:var(--bad-text); }
.counts { margin:0 0 14px; }
details.raw > summary { cursor:pointer; color:var(--muted); margin:8px 0 12px; }
</style>
"""


def _meter(label, value, points=None, name=""):
    """A usage bar with the last 24 h as a small line beside it (left out when there is no history)."""

    if value is None:
        return ""
    level = "high" if value >= 90 else "mid" if value >= 75 else ""
    line = sparkline(points or [], f"{name} {label} over 24 h", width=64)

    return (f'<div class="meter"><span>{label}</span><div class="track"><div class="fill {level}" '
            f'style="width:{max(0, min(100, value))}%"></div></div><span>{value}%</span>{line}</div>')


def build_history(samples, scans, host_name, node_names=None):
    """
    {name: {"cpu": [...], "mem": [...], "disk": [...]}} oldest first, for render_hosts_summary(): this host from
    atlas.host.sample payloads, each Proxmox node from atlas.proxmox.scan.completed (percentages, names mapped
    through node_names the way /trends does). samples/scans: [(time, payload)].
    """

    history = {}
    if samples:
        history[host_name] = {key: [payload.get(key) for _, payload in samples] for key in ("cpu", "mem", "disk")}

    for _, payload in scans:
        for node in payload.get("nodes", []):
            if "maxmem" not in node:
                continue
            row = history.setdefault((node_names or {}).get(node["name"], node["name"]),
                                     {"cpu": [], "mem": [], "disk": []})
            row["cpu"].append((node.get("cpu") or 0) * 100)
            row["mem"].append(_pct(node.get("mem"), node.get("maxmem")))
            row["disk"].append(_pct(node.get("disk"), node.get("maxdisk")))

    return history


def _pct(used, total):

    return used / total * 100 if used is not None and total else None


def _host_box(row, history=None):

    state = "warn" if row["problems"] else ""
    lines = (history or {}).get(row["name"]) or {}
    body = "".join(_meter(label, row[key], lines.get(key), row["name"])
                   for label, key in (("CPU", "cpu"), ("RAM", "mem"), ("Disk", "disk")))
    body += f'<p class="muted">{_esc(row["detail"])}</p>' if row["detail"] else ""
    body += f'<p class="bad">{_esc(", ".join(row["problems"][:6]))}</p>' if row["problems"] else ""

    return (f'<section class="hbox {state}"><h2><span class="dot {"warn" if state else "ok"}"></span>'
            f'{_esc(row["name"])}</h2>{body}</section>')


def _counts(topology, guests):
    """The short list: how many of each kind, each linking to where they are listed."""

    topology = topology or {}
    containers = sum(len(members) for members in ((topology.get("docker") or {}).get("networks") or {}).values())
    lan = len(topology.get("lan") or [])
    items = [f'<a href="#containers">{plural(containers, "container")}</a>' if containers else "",
             f'<a href="#guests">{plural(len(guests), "Proxmox guest")}</a>' if guests else "",
             f'<a href="/devices">{plural(lan, "LAN host")}</a>' if lan else ""]
    items = [item for item in items if item]

    return f'<p class="counts">{" · ".join(items)}</p>' if items else ""


def _container_chips(topology):

    out = ""
    for network, members in ((topology or {}).get("docker") or {}).get("networks", {}).items():
        chips = "".join(
            f'<span class="cchip"><span class="dot {"down" if c["status"] != "running" else "warn" if c.get("health") == "unhealthy" else "ok"}">'
            f'</span>{_esc(c["name"])}</span>' for c in members)
        out += f"<h3>{_esc(network)} ({len(members)})</h3>{chips}"

    return out


def render_hosts_summary(hosts, storage, topology, history=None):
    """
    hosts: home_page.build_hosts() output; storage: build_storage() output;
    topology: KnowledgeQueries().latest_topology() or None;
    history: build_history()'s output, or None for meters without lines.
    """

    boxes = "".join(_host_box(row, history) for row in hosts["rows"]) or '<p class="muted">No host data yet.</p>'
    store = "".join(f'<div class="srow{" warn" if r["warn"] else ""}"><span>{_esc(r["name"])}</span>'
                    f'<span class="muted">{_esc(r["detail"])}</span></div>' for r in storage["rows"])
    guests = [g for g in ((topology or {}).get("proxmox") or {}).get("guests", []) if not g.get("template")]
    guest_chips = "".join(f'<span class="cchip"><span class="dot {"ok" if g["status"] == "running" else "down"}"></span>'
                          f'{_esc(g["name"])}</span>' for g in guests)

    return (HOSTS_STYLE + ask_chips(HOSTS_CHIPS) + _counts(topology, guests)
            + f'<div class="hgrid">{boxes}'
            + (f'<section class="hbox"><h2>Storage &amp; RAID</h2>{store}</section>' if store else "")
            + "</div>"
            + '<section class="hbox chipset" id="containers"><h2>Containers on this host</h2>' + (_container_chips(topology)
               or '<p class="muted">No container snapshot yet.</p>')
            + (f'<h3 id="guests">Proxmox guests ({len(guests)})</h3>{guest_chips}' if guests else "") + "</section>")
