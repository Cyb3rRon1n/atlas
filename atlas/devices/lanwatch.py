"""
LAN watch: rogue DHCP servers and ARP spoofing of the gateway.

  DHCP  one DHCPDISCOVER per run (broadcast flag set, a fixed locally
        administered client MAC, never followed by a REQUEST - no address is
        ever taken). Every server that offers is listed; one that is neither
        the default gateway nor in security.dhcp_servers is a problem.
        Answering needs UDP port 68: root, or the image's capability-only
        helper interpreter (atlas-dhcp-python, cap_net_bind_service).
  ARP   passive, from the host's ARP table (and UniFi's wired clients when the
        cabling map has them): the gateway's MAC is learned on first sight; a
        different MAC later is the classic man-in-the-middle sign.

Pure checks (assess / alerts) + one run() that the CLI calls. State lives in
the posture status table under source "lan".
"""

import json
import random
import shutil
import socket
import struct
import subprocess
import sys
import time

PROBE_MAC = bytes.fromhex("02a7145c0001")    # locally administered: never a real NIC
HELPER = "atlas-dhcp-python"
SILENT_RUNS = 2       # runs in a row with no DHCP answer before "DHCP is down" alerts
MAGIC = b"\x63\x82\x53\x63"

REASONS = {
    "rogue_dhcp": "Unknown DHCP server",
    "dhcp_down": "No DHCP server answered",
    "dhcp_unheard": "No DHCP answer heard yet",
    "gateway_mac": "Gateway MAC address changed",
    "gateway_claim": "A device claims the gateway's address",
    "shared_mac": "Gateway MAC also answers for another address",
    "duplicate_ip": "Same IP on two devices",
}


# --- DHCP ------------------------------------------------------------------

def build_discover(xid, mac=PROBE_MAC):

    header = struct.pack("!BBBBIHH4s4s4s4s16s64s128s", 1, 1, 6, 0, xid, 0, 0x8000,
                         b"\0" * 4, b"\0" * 4, b"\0" * 4, b"\0" * 4, mac.ljust(16, b"\0"), b"", b"")
    options = MAGIC + bytes([53, 1, 1, 55, 3, 1, 3, 6, 255])     # DISCOVER; ask for mask, router, DNS

    return header + options


def _options(data):

    found, i = {}, 240
    while i < len(data) and data[i] != 255:
        if data[i] == 0:
            i += 1
            continue
        if i + 1 >= len(data):
            break
        code, length = data[i], data[i + 1]
        found[code] = data[i + 2:i + 2 + length]
        i += 2 + length

    return found


def parse_offer(data, xid, source_ip=None):
    """{server, offered, router} for a DHCPOFFER answering our xid, else None."""

    if len(data) < 240 or data[0] != 2 or data[236:240] != MAGIC or struct.unpack("!I", data[4:8])[0] != xid:
        return None
    options = _options(data)
    if options.get(53) != b"\x02":
        return None
    server = socket.inet_ntoa(options[54]) if len(options.get(54, b"")) == 4 else source_ip
    router = socket.inet_ntoa(options[3][:4]) if len(options.get(3, b"")) >= 4 else None

    return {"server": server, "offered": socket.inet_ntoa(data[16:20]), "router": router}


def probe_dhcp(timeout=3.0, sock=None):
    """Offers from every DHCP server that answers within timeout. Raises OSError when port 68 can't be bound."""

    xid = random.getrandbits(32)
    if sock is None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", 68))
    offers, deadline = {}, time.monotonic() + timeout

    with sock:
        sock.sendto(build_discover(xid), ("255.255.255.255", 67))
        while (left := deadline - time.monotonic()) > 0:
            sock.settimeout(left)
            try:
                data, (source_ip, _) = sock.recvfrom(4096)
            except socket.timeout:
                break
            offer = parse_offer(data, xid, source_ip)
            if offer:
                offers.setdefault(offer["server"], offer)

    return sorted(offers.values(), key=lambda o: o["server"])


def probe_with_helper(timeout=3.0, run=subprocess.run):
    """probe_dhcp in-process, or via the capability-only helper when this user can't bind port 68."""

    try:
        return probe_dhcp(timeout)
    except PermissionError:
        helper = shutil.which(HELPER)
        if not helper:
            raise PermissionError("binding UDP port 68 needs root or the atlas-dhcp-python helper (Docker image)")
    result = run([helper, "-I", "-m", "atlas.devices.lanwatch", str(timeout)],
                 capture_output=True, text=True, timeout=timeout + 10)
    if result.returncode:
        raise OSError(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "DHCP probe failed")

    return json.loads(result.stdout)


# --- checks ----------------------------------------------------------------

def assess(*, offers, probe_error, gateway_ip, arp, clients, allowed, state):
    """
    Issues for one run plus the state to keep. offers: probe_dhcp() result (None
    when the probe is off); arp: {ip: mac}; clients: UniFi wired clients
    [{mac, ip, name}]; allowed: extra DHCP server IPs; state: what the last run
    kept ({gateway_mac, silent}). Returns (issues, state).
    """

    issues, state = [], dict(state or {})

    def add(kind, level, subject, detail):
        issues.append({"kind": kind, "level": level, "subject": subject, "reason": REASONS[kind], "detail": detail})

    if offers is not None and not probe_error:
        expected = set(allowed) | ({gateway_ip} if gateway_ip else set())
        for offer in offers:
            if offer["server"] not in expected:
                mac = arp.get(offer["server"])
                add("rogue_dhcp", "bad", offer["server"],
                    f"{offer['server']}{f' ({mac})' if mac else ''} offered {offer['offered']} "
                    f"with gateway {offer['router'] or 'none'}. If it is yours, add it to security.dhcp_servers.")
        state["silent"] = 0 if offers else state.get("silent", 0) + 1
        state["heard"] = state.get("heard", False) or bool(offers)
        if state["silent"] >= SILENT_RUNS and state["heard"]:
            add("dhcp_down", "bad", "dhcp", f"no answer to {state['silent']} DHCP probes in a row - "
                                            "new devices can't get an address")
        elif state["silent"] >= SILENT_RUNS:     # never heard one: far likelier a host firewall than no DHCP at all
            add("dhcp_unheard", "watch", "dhcp", "no DHCP server has ever answered this host's probe - "
                                                 "if it runs a firewall, allow incoming UDP port 68")

    gateway_mac = arp.get(gateway_ip) if gateway_ip else None
    learned = state.get("gateway_mac")
    if gateway_mac:
        others = sorted(ip for ip, mac in arp.items() if mac == gateway_mac and ip != gateway_ip)
        if learned and gateway_mac != learned:
            also = f"; that MAC is also {', '.join(others)}" if others else ""
            add("gateway_mac", "bad", gateway_ip,
                f"{gateway_ip} now answers from {gateway_mac}, was {learned}{also}. A new router? "
                "Run `atlas lan check --trust-gateway`. Otherwise something on the LAN is impersonating it.")
        elif others:
            add("shared_mac", "watch", gateway_ip, f"{gateway_mac} answers for {gateway_ip} and {', '.join(others)}")
        state.setdefault("gateway_mac", gateway_mac)

    by_ip = {}
    for client in clients or []:
        if client.get("ip") and client.get("mac"):
            by_ip.setdefault(client["ip"], {})[client["mac"]] = client.get("name") or client["mac"]
    for ip, macs in sorted(by_ip.items()):
        names = ", ".join(f"{name} ({mac})" if name != mac else mac for mac, name in sorted(macs.items()))
        if ip == gateway_ip and any(mac != (learned or gateway_mac) for mac in macs):
            add("gateway_claim", "bad", ip, f"UniFi sees {names} using the gateway's address {ip}")
        elif len(macs) > 1:
            add("duplicate_ip", "watch", ip, f"{ip} is used by {names}")

    return issues, state


def alerts(previous_issues, issues):
    """Alert texts for bad issues new since the last run, and for bad ones that cleared."""

    key = lambda i: (i["kind"], i["subject"])
    old = {key(i): i for i in previous_issues or [] if i["level"] == "bad"}
    new = {key(i): i for i in issues if i["level"] == "bad"}
    from atlas.alerts import Text
    tag = lambda k: f"lan:{k[0]}:{k[1]}"
    texts = [Text(f"**🛡️ {i['reason']}**\n• {i['detail']}\n\nSee Atlas → Posture.", tag(k))
             for k, i in new.items() if k not in old]
    texts += [Text(f"**✅ Resolved: {i['reason'].lower()}**\n• {i['subject']}", tag(k)) for k, i in old.items() if k not in new]

    return texts


# --- one run ---------------------------------------------------------------

def run(settings, store, now, *, probe=probe_with_helper, read=None, unifi_clients=(), send=None, trust_gateway=False):

    from atlas import notify
    from atlas.devices.lan import default_gateway, parse_arp, _read

    read = read or _read
    config = settings.security
    previous = store.statuses().get("lan") or {}
    previous = previous.get("detail") or {}
    state = {k: previous[k] for k in ("gateway_mac", "silent", "heard") if k in previous}
    if trust_gateway:
        state.pop("gateway_mac", None)

    offers, probe_error = None, ""
    if config.dhcp_probe:
        try:
            offers = probe(config.dhcp_timeout)
        except (OSError, ValueError) as error:
            probe_error = str(error)[:300]

    gateway_ip = default_gateway(read("/proc/net/route"))
    arp = parse_arp(read("/proc/net/arp"))
    issues, state = assess(offers=offers, probe_error=probe_error, gateway_ip=gateway_ip, arp=arp,
                           clients=unifi_clients, allowed=config.dhcp_servers, state=state)

    from atlas.alerts import issue, report
    report("lan", [issue(i["kind"], i["subject"], i["reason"], i["detail"],
                         "problem" if i["level"] == "bad" else "watch", "/posture") for i in issues], now, store)

    from atlas.alerts import allowed
    for text in alerts(previous.get("issues"), issues):
        if not allowed(store, text, now):
            continue
        if send:
            send(text)
        elif notify.configured(settings.notify):
            notify.send(settings.notify, text)

    detail = {**state, "gateway_ip": gateway_ip, "gateway_seen": arp.get(gateway_ip) if gateway_ip else None,
              "offers": offers, "probe_error": probe_error, "issues": issues}
    store.set_status("lan", not any(i["level"] == "bad" for i in issues), detail, now)

    return detail


if __name__ == "__main__":      # the helper: atlas-dhcp-python -I -m atlas.devices.lanwatch [timeout]
    print(json.dumps(probe_dhcp(float(sys.argv[1]) if len(sys.argv) > 1 else 3.0)))
