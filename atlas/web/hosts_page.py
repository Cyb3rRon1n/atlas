"""
Summary half of /overview (Hosts): one card per machine with usage bars, the
storage card, this host's containers as status chips by network, and the
Proxmox guests. Pure renderer over data server.py already gathers for Home
(build_hosts / build_storage) plus the latest topology.
"""

from atlas.web.render import _esc, ask_chips


HOSTS_CHIPS = ("What is using the most CPU and memory right now?", "Is any disk or pool getting full?",
               "Which containers restarted or are unhealthy?", "How is cyberbox doing?")

HOSTS_STYLE = """
<style>
.hgrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:16px; margin-bottom:16px; }
.hbox { background:#111821; border:1px solid #222c38; border-radius:14px; padding:16px; }
.hbox.warn { border-color:var(--red); }
.hbox h2 { margin:0 0 10px; font-size:16px; border:0; padding:0; display:flex; gap:8px; align-items:center; }
.meter { display:grid; grid-template-columns:48px 1fr 44px; gap:8px; align-items:center; font-size:13px; margin:6px 0; }
.meter .track { height:8px; border-radius:4px; background:var(--surface2); overflow:hidden; }
.meter .fill { height:100%; background:var(--green); }
.meter .fill.mid { background:var(--orange); } .meter .fill.high { background:var(--red); }
.hbox .bad { color:#ffb4a2; font-size:13px; }
.chipset h3 { margin:12px 0 6px; font-size:12px; color:var(--muted); font-weight:500; text-transform:uppercase; letter-spacing:.06em; }
.cchip { display:inline-flex; align-items:center; gap:6px; margin:0 6px 6px 0; padding:4px 10px; border-radius:999px;
         background:var(--surface2); font-size:13px; }
.dot { width:9px; height:9px; border-radius:50%; background:var(--muted); display:inline-block; flex:none; }
.dot.ok { background:var(--green); } .dot.warn { background:var(--orange); } .dot.down { background:var(--red); }
.srow { display:flex; justify-content:space-between; gap:8px; padding:5px 0; border-top:1px solid var(--line); font-size:14px; }
.srow:first-of-type { border-top:0; } .srow.warn span:last-child { color:#ffb4a2; }
details.raw > summary { cursor:pointer; color:var(--muted); margin:8px 0 12px; }
</style>
"""


def _meter(label, value):

    if value is None:
        return ""
    level = "high" if value >= 90 else "mid" if value >= 75 else ""

    return (f'<div class="meter"><span>{label}</span><div class="track"><div class="fill {level}" '
            f'style="width:{max(0, min(100, value))}%"></div></div><span>{value}%</span></div>')


def _host_box(row):

    state = "warn" if row["problems"] else ""
    body = _meter("CPU", row["cpu"]) + _meter("RAM", row["mem"]) + _meter("Disk", row["disk"])
    body += f'<p class="muted">{_esc(row["detail"])}</p>' if row["detail"] else ""
    body += f'<p class="bad">{_esc(", ".join(row["problems"][:6]))}</p>' if row["problems"] else ""

    return (f'<section class="hbox {state}"><h2><span class="dot {"warn" if state else "ok"}"></span>'
            f'{_esc(row["name"])}</h2>{body}</section>')


def _container_chips(topology):

    out = ""
    for network, members in ((topology or {}).get("docker") or {}).get("networks", {}).items():
        chips = "".join(
            f'<span class="cchip"><span class="dot {"down" if c["status"] != "running" else "warn" if c.get("health") == "unhealthy" else "ok"}">'
            f'</span>{_esc(c["name"])}</span>' for c in members)
        out += f"<h3>{_esc(network)} ({len(members)})</h3>{chips}"

    return out


def render_hosts_summary(hosts, storage, topology):
    """
    hosts: home_page.build_hosts() output; storage: build_storage() output;
    topology: KnowledgeQueries().latest_topology() or None.
    """

    boxes = "".join(_host_box(row) for row in hosts["rows"]) or '<p class="muted">No host data yet.</p>'
    store = "".join(f'<div class="srow{" warn" if r["warn"] else ""}"><span>{_esc(r["name"])}</span>'
                    f'<span class="muted">{_esc(r["detail"])}</span></div>' for r in storage["rows"])
    guests = [g for g in ((topology or {}).get("proxmox") or {}).get("guests", []) if not g.get("template")]
    guest_chips = "".join(f'<span class="cchip"><span class="dot {"ok" if g["status"] == "running" else "down"}"></span>'
                          f'{_esc(g["name"])}</span>' for g in guests)

    return (HOSTS_STYLE + ask_chips(HOSTS_CHIPS)
            + f'<div class="hgrid">{boxes}'
            + (f'<section class="hbox"><h2>Storage &amp; RAID</h2>{store}</section>' if store else "")
            + "</div>"
            + '<section class="hbox chipset"><h2>Containers on this host</h2>' + (_container_chips(topology)
               or '<p class="muted">No container snapshot yet.</p>')
            + (f"<h3>Proxmox guests ({len(guests)})</h3>{guest_chips}" if guests else "") + "</section>")
