"""
Open-port watch (atlas ports check, every atlas-scan pass). Three read-only views:

  internet  port forwards and UPnP on the router: the UniFi console when it is
            set up, and the standard UPnP IGD port-mapping list that most home
            routers answer (asked only of the default gateway)
  LAN       a TCP connect to ~25 common service ports on every device that is
            online right now (in the ARP table). Connect and close - nothing is
            sent, nothing logged in to, only the scan subnets.
  host      sockets listening on this machine for other machines (not loopback)

The first run learns what is normal and stays quiet. After that each newly
open port alerts once; a port that closes and reopens later does not, since
devices that sleep would otherwise alert every morning.
"""

import ipaddress
import os
import re
import socket
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from concurrent.futures import ThreadPoolExecutor

COMMON_PORTS = {
    21: "FTP", 22: "SSH", 23: "telnet", 25: "SMTP", 53: "DNS", 80: "web", 139: "NetBIOS", 443: "web (TLS)",
    445: "SMB file sharing", 554: "RTSP camera stream", 1883: "MQTT", 2375: "Docker API", 3306: "MySQL",
    3389: "remote desktop", 5000: "web", 5432: "PostgreSQL", 5900: "VNC", 6379: "Redis", 8000: "web",
    8080: "web", 8443: "web (TLS)", 8888: "web", 9000: "web", 9100: "printer", 11434: "Ollama", 27017: "MongoDB",
}
# Open on a LAN device these usually mean "anyone on the network can log in or read data".
RISKY = {23, 139, 445, 2375, 3306, 3389, 5432, 5900, 6379, 27017}
RECENT_MAX = 30
MAX_MAPPINGS = 64


def port_label(port):

    name = COMMON_PORTS.get(port)
    text = f"{port} ({name})" if name else str(port)

    return text + (" - risky: lets others on the network log in or read data" if port in RISKY else "")


# --- LAN devices -----------------------------------------------------------

def _open(ip, port, timeout):

    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe(ips, ports, timeout=0.5, check=_open):
    """{ip: sorted open ports} for every ip, by plain TCP connect."""

    pairs = [(ip, port) for ip in ips for port in ports]
    with ThreadPoolExecutor(max_workers=64) as pool:
        results = pool.map(lambda pair: check(pair[0], pair[1], timeout), pairs)
    found = {ip: [] for ip in ips}
    for (ip, port), is_open in zip(pairs, results):
        if is_open:
            found[ip].append(port)

    return {ip: sorted(ports) for ip, ports in found.items()}


# --- this host -------------------------------------------------------------

def host_listeners(connections=None):
    """Sorted TCP ports this machine listens on for other machines (loopback-only binds left out)."""

    import psutil

    ports = set()
    for conn in connections if connections is not None else psutil.net_connections(kind="tcp"):
        if conn.status != "LISTEN" or not conn.laddr:
            continue
        address = conn.laddr.ip.split("%")[0]
        try:
            if ipaddress.ip_address(address).is_loopback:
                continue
        except ValueError:
            continue
        ports.add(conn.laddr.port)

    return sorted(ports)


# --- router: UPnP IGD ------------------------------------------------------

SEARCH = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 2\r\n"
          "ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n\r\n")
WAN_SERVICES = ("WANIPConnection", "WANPPPConnection")


def _ssdp_location(gateway, timeout):

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(SEARCH.encode(), ("239.255.255.250", 1900))
        try:
            while True:
                data, (source, _) = sock.recvfrom(4096)
                match = re.search(rb"(?im)^location:\s*(\S+)", data)
                if source == gateway and match:
                    return match.group(1).decode(errors="replace")
        except socket.timeout:
            return None


def _soap(control, service, action, arguments, timeout):

    body = (f'<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            f's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:{action} xmlns:u="{service}">'
            + "".join(f"<{k}>{v}</{k}>" for k, v in arguments.items()) + f"</u:{action}></s:Body></s:Envelope>")
    request = urllib.request.Request(control, body.encode(), {"Content-Type": 'text/xml; charset="utf-8"',
                                                               "SOAPAction": f'"{service}#{action}"'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return ElementTree.fromstring(response.read(65536))


def upnp_mappings(gateway, timeout=2.0, locate=_ssdp_location, fetch=None, soap=_soap):
    """
    The gateway's UPnP port mappings [{external, protocol, client, port, description}], or None when it
    doesn't answer UPnP (off, or not supported). Only the default gateway is asked, and only over HTTP on it.
    """

    location = locate(gateway, timeout) if gateway else None
    if not location or urllib.parse.urlparse(location).hostname != gateway:
        return None
    fetch = fetch or (lambda url: urllib.request.urlopen(url, timeout=timeout).read(65536))
    try:
        root = ElementTree.fromstring(fetch(location))
    except (OSError, ElementTree.ParseError):
        return None
    strip = lambda tag: tag.rsplit("}", 1)[-1]
    service = control = None
    for node in root.iter():
        if strip(node.tag) == "service":
            fields = {strip(child.tag): (child.text or "").strip() for child in node}
            if any(name in fields.get("serviceType", "") for name in WAN_SERVICES):
                service, control = fields["serviceType"], urllib.parse.urljoin(location, fields.get("controlURL", ""))
                break
    if not control or urllib.parse.urlparse(control).hostname != gateway:
        return None

    mappings = []
    for index in range(MAX_MAPPINGS):
        try:
            reply = soap(control, service, "GetGenericPortMappingEntry", {"NewPortMappingIndex": index}, timeout)
        except (OSError, ElementTree.ParseError):
            break                      # SpecifiedArrayIndexInvalid (HTTP 500) ends the list
        values = {strip(node.tag): (node.text or "").strip() for node in reply.iter()}
        mappings.append({"external": int(values.get("NewExternalPort") or 0), "protocol": values.get("NewProtocol", ""),
                         "client": values.get("NewInternalClient", ""), "port": int(values.get("NewInternalPort") or 0),
                         "description": values.get("NewPortMappingDescription", "")})

    return mappings


# --- what changed ----------------------------------------------------------

def _forward_key(forward):

    return f"{forward.get('protocol', '')}/{forward.get('external')}->{forward.get('client', '')}:{forward.get('port')}"


def assess(previous, current):
    """
    previous: last run's state ({} on the first run). current: {"devices": {id: {name, ip, open}},
    "listeners": [...] or None, "forwards": [...] or None, "upnp": bool or None, "host": name}.
    Returns (alert texts, new state).
    """

    learning = not previous.get("learned")
    known_devices = previous.get("devices") or {}
    texts, devices = [], {}

    for device_id, device in current["devices"].items():
        before = known_devices.get(device_id)
        known = set((before or {}).get("known") or [])
        new = [port for port in device["open"] if port not in known]
        if before and new and not learning:
            ports = "\n".join(f"• {port_label(port)}" for port in new)
            texts.append(f"**🔓 New open port{'s' * (len(new) > 1)} on {device['name']}** ({device['ip']})\n{ports}\n\n"
                         "Expected (a new app or update)? Nothing to do. Otherwise see Atlas → Devices.")
        devices[device_id] = {"name": device["name"], "ip": device["ip"], "open": device["open"],
                              "known": sorted(known | set(device["open"]))}
    for device_id, device in known_devices.items():
        devices.setdefault(device_id, {**device, "open": device.get("open") or []})     # offline: keep what we know

    state = {"learned": True, "devices": devices}

    listeners = current.get("listeners")
    known = set((previous.get("listeners") or {}).get("known") or [])
    if listeners is not None:
        new = [port for port in listeners if port not in known]
        if new and previous.get("listeners") and not learning:
            texts.append(f"**🔓 New listening port on {current.get('host') or 'the atlas host'}**\n"
                         + "\n".join(f"• {port_label(port)}" for port in new))
        state["listeners"] = {"open": listeners, "known": sorted(known | set(listeners))}
    else:
        state["listeners"] = previous.get("listeners")

    forwards = current.get("forwards")
    known = set((previous.get("forwards") or {}).get("known") or [])
    if forwards is not None:
        keys = [_forward_key(f) for f in forwards]
        new = [f for f, key in zip(forwards, keys) if key not in known]
        if new and previous.get("forwards") is not None and not learning:
            texts.append("**🌐 New port opened to the internet**\n" + "\n".join(
                f"• {f.get('protocol', '').upper()} {f.get('external')} → {f.get('client')}:{f.get('port')}"
                f"{' (' + f['description'] + ')' if f.get('description') else ''}" for f in new)
                + "\n\nAnything on the internet can now reach that device. Not yours? Remove it on the router.")
        state["forwards"] = {"open": forwards, "known": sorted(known | set(keys))}
    else:
        state["forwards"] = previous.get("forwards")

    upnp = current.get("upnp")
    if upnp and previous.get("upnp") is False and not learning:
        texts.append("**🌐 UPnP was switched on**\n• devices on the LAN can now open router ports to the internet "
                     "by themselves")
    state["upnp"] = upnp if upnp is not None else previous.get("upnp")

    recent = [{"text": text.split("\n", 1)[0].strip("*"), "detail": text} for text in texts]
    state["recent"] = (recent + (previous.get("recent") or []))[:RECENT_MAX]

    return texts, state


# --- one run ---------------------------------------------------------------

def _local_ips():

    import psutil

    return {address.address for addresses in psutil.net_if_addrs().values() for address in addresses
            if address.family == socket.AF_INET}


def run(settings, store, devices, now, *, read=None, check=_open, listeners=host_listeners, exposure=None,
        upnp=upnp_mappings, local_ips=_local_ips, send=None, snmp=None):
    """
    One check: devices = InventoryStore().devices(). Probes the ones online now (complete ARP entries
    inside the scan subnets), reads this host's listeners and the router's openings, alerts, saves.
    """

    from atlas import notify
    from atlas.devices.lan import _read, default_gateway, parse_arp, parse_route
    from atlas.wiring import WiringError

    read = read or _read
    config = settings.security
    route = read("/proc/net/route")
    networks = [ipaddress.ip_network(net, strict=False) for net in (settings.scan.subnets or parse_route(route) or [])]
    arp, mine = parse_arp(read("/proc/net/arp")), local_ips()
    online = {d["id"]: d for d in devices if d.get("ip") and d["ip"] in arp and d["ip"] not in mine
              and any(ipaddress.ip_address(d["ip"]) in net for net in networks)}

    ports = sorted(set(COMMON_PORTS) | set(config.extra_ports))
    found = probe([d["ip"] for d in online.values()], ports, config.port_timeout, check)
    current = {"devices": {str(i): {"name": d["name"], "ip": d["ip"], "open": found[d["ip"]]} for i, d in online.items()},
               "host": socket.gethostname()}

    try:
        current["listeners"] = listeners()
    except Exception:                     # psutil may need privileges on some systems: skip, don't fail the run
        current["listeners"] = None

    forwards, upnp_on, source = None, None, ""
    if settings.wiring.unifi.enabled:
        try:
            from atlas.wiring.unifi import fetch_exposure
            result = (exposure or fetch_exposure)(settings.wiring.unifi, os.environ,
                                                  settings.wiring.timeout)
            forwards, upnp_on, source = result["forwards"], result["upnp"], "UniFi console"
        except WiringError:
            pass
    if upnp_on is not False:                      # UniFi says off: nothing to ask; otherwise ask the gateway
        mappings = upnp(default_gateway(route))
        if mappings is not None:
            forwards = (forwards or []) + [{**m, "description": f"UPnP: {m['description']}".strip(": ")}
                                           for m in mappings]
            upnp_on, source = True, source or "UPnP"
        elif not source:
            upnp_on = None
    current["forwards"], current["upnp"] = forwards, upnp_on

    previous = ((store.statuses().get("ports") or {}).get("detail")) or {}
    texts, state = assess(previous, current)
    from atlas.alerts import report_event
    for text in texts:
        title, _, rest = text.partition("\n")
        report_event("ports", title.strip("*").split(" ", 1)[1], now, store, detail=rest.strip(), href="/devices")
    for entry in state["recent"][:len(texts)]:
        entry["at"] = now.isoformat(timespec="minutes")
    for text in texts:
        if send:
            send(text)
        elif notify.configured(settings.notify):
            notify.send(settings.notify, text)
    state.update(checked_at=now.isoformat(timespec="minutes"), forwards_source=source, probed=len(online))
    if config.snmp_discovery:                     # which devices speak SNMPv3 (Setup suggests adding them)
        from atlas.devices.snmpprobe import discover
        try:
            state["snmp"] = (snmp or discover)([d["ip"] for d in online.values()])
        except OSError:
            pass
    store.set_status("ports", True, state, now)

    return texts, state
