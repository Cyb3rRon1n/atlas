"""
The posture page's data: status strip, zone-map nodes/edges with preset
positions (three bands: inbound, outbound direct, outbound via VPN), public
exposure and unreviewed new destinations. Pure over PostureStore reads.
"""

import socket
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import timedelta

from atlas.posture.store import asn_key


WINDOWS = {"live": timedelta(0), "1h": timedelta(hours=1), "24h": timedelta(hours=24)}
NEW_FOR = timedelta(days=7)
STALE_AFTER = timedelta(minutes=5)
MAX_SOURCES, MAX_DESTS = 8, 10
COL, ROW = 200, 64
BANDS = {"inbound": 40, "direct": 220, "vpn": 0}   # vpn y is computed after direct's height


def _fmt_bytes(value):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000


def _fresh(statuses, name, now):
    status = statuses.get(name)
    return bool(status and status["ok"] and now - status["updated_at"] <= STALE_AFTER)


def _strip(statuses, routes, review, now):

    tunnel = statuses.get("tunnel")
    gluetun, home = statuses.get("gluetun"), statuses.get("public_ip")
    crowdsec = statuses.get("crowdsec")
    public = [r for r in routes if r["protection"] != "authelia"]

    if not tunnel or now - tunnel["updated_at"] > STALE_AFTER:
        ingress = ("unknown", "No data", "")
    elif tunnel["ok"]:
        ingress = ("ok", "Tunnel up", f"{tunnel['detail'].get('connections', 0)} connections")
    else:
        ingress = ("warn", "Tunnel down", "no connections to Cloudflare")

    exit_ip = (gluetun or {}).get("detail", {}).get("exit_ip") if gluetun and gluetun["ok"] else None
    home_ip = (home or {}).get("detail", {}).get("ip") if home and home["ok"] else None
    if not exit_ip or not home_ip:
        vpn = ("unknown", "Unknown", "gluetun or public IP unavailable")
    elif exit_ip == home_ip:
        vpn = ("warn", "Leaking", "VPN exit IP equals the home IP")
    else:
        vpn = ("ok", "Verified", "exit IP differs from home")

    blocked = (("ok", str(crowdsec["detail"].get("active", 0)), "active CrowdSec bans")
               if crowdsec and crowdsec["ok"] else ("unknown", "-", "CrowdSec unavailable"))

    item = lambda key, label, state_value_detail: {"key": key, "label": label, "state": state_value_detail[0],
                                                    "value": state_value_detail[1], "detail": state_value_detail[2]}

    return [
        item("ingress", "Ingress", ingress),
        item("vpn", "VPN egress", vpn),
        item("exposure", "Exposure", ("ok" if routes else "unknown", f"{len(routes)} routes",
                                      f"{len(public)} without Authelia")),
        item("blocked", "Blocked", blocked),
        item("new", "New destinations", ("review" if review else "ok", str(len(review)),
                                         "need review" if review else "nothing new")),
    ]


def _node(node_id, label, sub, band, x, y, state="ok", w=170):
    return {"id": node_id, "label": label, "sub": sub, "band": band, "state": state, "x": x, "y": y, "w": w}


def _edge(source, target, bytes_=0, state="ok"):
    return {"id": f"{source}->{target}", "source": source, "target": target, "bytes": bytes_, "state": state}


def build_posture(store, now, window="24h"):

    statuses, routes = store.statuses(), store.latest_routes()
    seen = store.seen()
    review = sorted(({k: s[k] for k in ("source", "asn_key", "org", "cc", "first_seen")}
                     for s in seen if not s["known"] and now - s["first_seen"] <= NEW_FOR),
                    key=lambda s: s["first_seen"], reverse=True)
    review_keys = {(r["source"], r["asn_key"]) for r in review}
    flows = store.flows(now - WINDOWS[window])
    strip_items = _strip(statuses, routes, review, now)
    nodes, edges = [], []

    # Inbound band - fixed chain.
    y = BANDS["inbound"]
    authed = sum(r["protection"] == "authelia" for r in routes)
    tunnel_ok = _fresh(statuses, "tunnel", now)
    chain = [("in:internet", "Internet", "visitors"), ("in:cloudflare", "Cloudflare", "DNS + proxy"),
             ("in:tunnel", "cloudflared", f"{statuses.get('tunnel', {}).get('detail', {}).get('connections', 0)} connections"),
             ("in:traefik", "Traefik", f"{len(routes)} routes"), ("in:auth", "Authelia", f"{authed} routes")]
    for i, (node_id, label, sub) in enumerate(chain):
        nodes.append(_node(node_id, label, sub, "inbound", i * COL, y,
                           state="ok" if node_id != "in:tunnel" or tunnel_ok else "warn"))
        if i:
            edges.append(_edge(chain[i - 1][0], node_id))
    nodes.append(_node("in:svc-auth", "Behind Authelia", f"{authed} services", "inbound", 5 * COL, y))
    nodes.append(_node("in:svc-public", "Public", f"{len(routes) - authed} services", "inbound", 5 * COL, y + ROW,
                       state="review" if len(routes) - authed else "ok"))
    edges += [_edge("in:auth", "in:svc-auth"), _edge("in:traefik", "in:svc-public")]

    # Outbound direct band.
    direct = [f for f in flows if f["band"] == "direct"]
    by_source, by_dest, dest_meta, pair_state = {}, {}, {}, {}
    for f in direct:
        total = f["bytes_out"] + f["bytes_in"]
        key = asn_key(f["asn"], f["dest_ip"])
        by_source[f["source"]] = by_source.get(f["source"], 0) + total
        by_dest[key] = by_dest.get(key, 0) + total
        dest_meta[key] = (f["org"] or f["dest_ip"], f["cc"])
        if (f["source"], key) in review_keys:
            pair_state[key] = "review"

    top_sources = sorted(by_source, key=by_source.get, reverse=True)[:MAX_SOURCES]
    shown = sorted(by_dest, key=by_dest.get, reverse=True)[:MAX_DESTS]
    shown += [k for k in pair_state if k not in shown]
    others = sum(v for k, v in by_dest.items() if k not in shown)

    y0 = BANDS["direct"]
    for i, name in enumerate(top_sources):
        nodes.append(_node(f"src:{name}", name, _fmt_bytes(by_source[name]), "direct", 0, y0 + i * ROW))
        edges.append(_edge(f"src:{name}", "out:router", by_source[name]))
    rows = max(len(top_sources), len(shown) + (1 if others else 0), 1)
    nodes.append(_node("out:router", "Home router", "WAN", "direct", COL + 40, y0 + (rows - 1) * ROW // 2))
    for i, key in enumerate(shown):
        org, cc = dest_meta[key]
        nodes.append(_node(f"dst:{key}", org, f"{key} · {cc}" if cc else key, "direct", 2 * COL + 120,
                           y0 + i * ROW, state=pair_state.get(key, "ok"), w=260))
        edges.append(_edge("out:router", f"dst:{key}", by_dest[key], pair_state.get(key, "ok")))
    if others:
        nodes.append(_node("dst:others", "Other destinations", _fmt_bytes(others), "direct", 2 * COL + 120,
                           y0 + len(shown) * ROW, w=260))
        edges.append(_edge("out:router", "dst:others", others))

    # VPN band.
    vpn_y = y0 + rows * ROW + 60
    vpn_bytes = sum(f["bytes_out"] + f["bytes_in"] for f in flows if f["band"] == "vpn")
    gluetun = statuses.get("gluetun") or {}
    vpn_state = next(s["state"] for s in strip_items if s["key"] == "vpn")
    nodes += [_node("vpn:members", "VPN clients", "qBittorrent etc.", "vpn", 0, vpn_y),
              _node("vpn:gluetun", "gluetun", _fmt_bytes(vpn_bytes), "vpn", COL + 40, vpn_y),
              _node("vpn:exit", "VPN exit", gluetun.get("detail", {}).get("exit_ip", "unknown"), "vpn",
                    2 * COL + 120, vpn_y, state=vpn_state, w=260)]
    edges += [_edge("vpn:members", "vpn:gluetun"), _edge("vpn:gluetun", "vpn:exit", vpn_bytes, vpn_state)]

    bands = [
        {"id": "inbound", "label": "Inbound · public", "y": BANDS["inbound"] - 30, "h": 2 * ROW + 40,
         "stale": not _fresh(statuses, "tunnel", now) and not _fresh(statuses, "routes", now)},
        {"id": "direct", "label": "Outbound · direct", "y": y0 - 30, "h": rows * ROW + 40,
         "stale": not _fresh(statuses, "conntrack", now)},
        {"id": "vpn", "label": "Outbound · via VPN", "y": vpn_y - 30, "h": ROW + 40,
         "stale": not _fresh(statuses, "gluetun", now)},
    ]

    return {"generated_at": now.isoformat(), "window": window, "strip": strip_items,
            "nodes": nodes, "edges": edges, "bands": bands, "exposure": routes,
            "review": [{**r, "first_seen": r["first_seen"].isoformat()} for r in review]}


def _reverse_dns(ip):
    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            return pool.submit(lambda: socket.gethostbyaddr(ip)[0]).result(timeout=1)
        except (FutureTimeout, OSError):
            return ""


def node_details(store, node_id, now, resolve=_reverse_dns):

    if not node_id.startswith("dst:") or node_id == "dst:others":
        return None

    key = node_id[4:]
    flows = [f for f in store.flows(now - WINDOWS["24h"]) if asn_key(f["asn"], f["dest_ip"]) == key]
    if not flows:
        return None

    seen = [s for s in store.seen() if s["asn_key"] == key]
    sources, ips = {}, {}
    for f in flows:
        total = f["bytes_out"] + f["bytes_in"]
        sources[f["source"]] = sources.get(f["source"], 0) + total
        ips[f["dest_ip"]] = ips.get(f["dest_ip"], 0) + total
    top_ips = sorted(ips, key=ips.get, reverse=True)[:5]

    return {"id": node_id, "asn_key": key, "asn": flows[0]["asn"], "org": flows[0]["org"], "cc": flows[0]["cc"],
            "first_seen": min(s["first_seen"] for s in seen).isoformat() if seen else None,
            "known": all(s["known"] for s in seen) if seen else False,
            "sources": [{"source": s, "bytes": b} for s, b in sorted(sources.items(), key=lambda kv: -kv[1])],
            "ips": [{"ip": ip, "rdns": resolve(ip) if i == 0 else ""} for i, ip in enumerate(top_ips)],
            "ports": sorted({f["dest_port"] for f in flows})}
