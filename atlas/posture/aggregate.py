"""
Turns conntrack snapshots into per-poll deltas. conntrack byte counters are
cumulative per connection, so the Accountant remembers the last counters per
connection key and emits only the growth; a connection seen for the first time
counts in full (including after an atlas restart - a bounded over-count that is
documented rather than worked around). Only outbound flows to public addresses
are kept: source = the container that owns the original source IP (or "host"),
band = "vpn" for containers routed through gluetun, else "direct".
"""

import ipaddress


CGNAT = ipaddress.ip_network("100.64.0.0/10")


def is_public(ip):
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return address.is_global and address not in CGNAT and not address.is_multicast


def _key(flow):
    return flow.id if flow.id is not None else (flow.proto, flow.src, flow.sport, flow.dst, flow.dport)


class Accountant:

    def __init__(self):
        self.last = {}

    def deltas(self, flows, sources, host_ip, vpn_sources, asn):

        current, out = {}, []

        for flow in flows:

            source = sources.get(flow.src) or ("host" if flow.src == host_ip else None)
            if source is None or not is_public(flow.dst):
                continue

            key = _key(flow)
            current[key] = (flow.bytes_out, flow.bytes_in)
            previous = self.last.get(key)

            if previous and flow.bytes_out >= previous[0] and flow.bytes_in >= previous[1]:
                bytes_out, bytes_in, new_conn = flow.bytes_out - previous[0], flow.bytes_in - previous[1], False
            else:
                bytes_out, bytes_in, new_conn = flow.bytes_out, flow.bytes_in, previous is None

            if not (bytes_out or bytes_in or new_conn):
                continue

            info = asn.lookup(flow.dst) if asn is not None else None
            out.append({"source": source, "band": "vpn" if source in vpn_sources else "direct",
                        "dest_ip": flow.dst, "dest_port": flow.dport or 0, "proto": flow.proto,
                        "asn": info.asn if info else 0, "org": info.org if info else "",
                        "cc": info.cc if info else "", "bytes_out": bytes_out, "bytes_in": bytes_in,
                        "new_conn": new_conn})

        self.last = current
        return out


def inbound_counts(flows, host_ip, traefik_ip):

    counts = {"public": 0, "private": 0}

    for flow in flows:
        if flow.dport in (80, 443) and flow.dst in (host_ip, traefik_ip):
            counts["public" if is_public(flow.src) else "private"] += 1

    return counts


def tunnel_connections(flows, cloudflared_ip):
    return sum(1 for f in flows if cloudflared_ip and f.src == cloudflared_ip and f.dport == 7844)
