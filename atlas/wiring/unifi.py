"""
Optional UniFi adapter: a local read-only account on a UniFi OS console. Fills in
what SNMP can't see on UniFi gear (gateway/AP/Flex ports and their uplinks, and
which gateway port each wired client is learned on). Field names come from
community clients, not an official schema, and vary by firmware - every read
here uses .get() with a default so a renamed field degrades, never crashes.
"""

import http.cookiejar
import ipaddress
import json
import ssl
import urllib.error
import urllib.request

from atlas.wiring import WiringError, normalize_mac


def _lan_ip(value):
    """A gateway reports its WAN (public) address as `ip`; the map only shows LAN addresses."""

    try:
        return value if ipaddress.ip_address(value).is_private else ""
    except ValueError:
        return ""


def _role(device, macs):

    if device.get("type") == "usw":
        return "switch"
    uplink = device.get("last_uplink") or {}
    if device.get("type") == "uap" or (device.get("radio_table") and normalize_mac(uplink.get("uplink_mac")) in macs):
        return "ap"
    return "gateway"


def parse_unifi(devices, clients):

    macs = {normalize_mac(d.get("mac")) for d in devices}
    parsed = []

    for device in devices:
        ports, port_macs = {}, {}
        for port in device.get("port_table") or []:
            index = port.get("port_idx")
            name = port.get("name") or f"Port {index}"
            ports[name] = {"index": index, "up": bool(port.get("up")), "speed": int(port.get("speed") or 0),
                           "counters": {"in_errors": port.get("rx_errors"), "out_errors": port.get("tx_errors"),
                                        "fcs": None, "align": None, "late": None, "packets": port.get("rx_packets"),
                                        "duplex": {True: "full", False: "half"}.get(port.get("full_duplex"), "unknown"),
                                        "last_change": None}}
            if normalize_mac(port.get("mac")):
                port_macs[normalize_mac(port.get("mac"))] = name
        uplink = device.get("last_uplink") or device.get("uplink") or {}
        parsed.append({
            "mac": normalize_mac(device.get("mac")), "name": device.get("name") or device.get("mac"),
            "model": device.get("model", ""), "ip": _lan_ip(device.get("ip", "")), "type": device.get("type", ""),
            "role": _role(device, macs), "ports": ports, "port_macs": port_macs,
            "uplink": {"type": uplink.get("type"), "mac": normalize_mac(uplink.get("uplink_mac")),
                       "remote_port": uplink.get("uplink_remote_port"), "local_port": uplink.get("port_idx")}})

    wired = [{"mac": normalize_mac(c.get("mac")), "name": c.get("name") or c.get("hostname") or c.get("oui") or "",
              "ip": c.get("ip", ""), "switch_mac": normalize_mac(c.get("sw_mac")), "switch_port": c.get("sw_port")}
             for c in clients if c.get("is_wired") and normalize_mac(c.get("mac"))]

    return {"devices": parsed, "clients": wired}


def _default_opener(verify_ssl):

    context = ssl.create_default_context()
    if not verify_ssl:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=context),
                                       urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def fetch_unifi(config, env, timeout, opener_factory=None):

    user, password = env.get("ATLAS_UNIFI_USER"), env.get("ATLAS_UNIFI_PASS")
    if not user or not password:
        raise WiringError("set ATLAS_UNIFI_USER and ATLAS_UNIFI_PASS in the atlas env file")

    opener = (opener_factory or (lambda: _default_opener(config.verify_ssl)))()
    base = config.url.rstrip("/")

    try:
        opener.open(urllib.request.Request(f"{base}/api/auth/login",
                                           json.dumps({"username": user, "password": password}).encode(),
                                           {"Content-Type": "application/json"}), timeout=timeout)

        def get(path):
            with opener.open(f"{base}/proxy/network/api/s/{config.site}/{path}", timeout=timeout) as response:
                return json.load(response).get("data") or []

        return parse_unifi(get("stat/device"), get("stat/sta"))

    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise WiringError("UniFi login refused - check ATLAS_UNIFI_USER/PASS (a local, read-only account)")
        raise WiringError(f"UniFi API error {error.code}")
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise WiringError(f"UniFi unreachable: {getattr(error, 'reason', error)}")