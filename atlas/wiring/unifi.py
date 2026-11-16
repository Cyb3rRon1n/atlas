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


def _float(value):

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
        ports, port_macs, bundles = {}, {}, {}
        for port in device.get("port_table") or []:
            index = port.get("port_idx")
            name = port.get("name") or f"Port {index}"
            ports[name] = {"index": index, "up": bool(port.get("up")), "speed": int(port.get("speed") or 0),
                           "counters": {"in_errors": port.get("rx_errors"), "out_errors": port.get("tx_errors"),
                                        "fcs": None, "align": None, "late": None, "packets": port.get("rx_packets"),
                                        "duplex": {True: "full", False: "half"}.get(port.get("full_duplex"), "unknown"),
                                        "last_change": None, "in_bytes": port.get("rx_bytes"),
                                        "out_bytes": port.get("tx_bytes")}}
            if port.get("port_poe"):
                watts = _float(port.get("poe_power"))
                ports[name]["poe"] = {"delivering": bool(port.get("poe_enable")) and (watts or 0) > 0,
                                      "fault": False, "enabled": port.get("poe_mode", "auto") != "off",
                                      "watts": watts, "mode": port.get("poe_mode", ""),
                                      "class": port.get("poe_class", "") if (watts or 0) > 0 else ""}
            if port.get("stp_state"):
                ports[name]["stp"] = str(port["stp_state"]).lower()
            if port.get("aggregated_by"):       # the bundle's first port_idx; that port is in it too
                bundles[port["aggregated_by"]] = f"LAG {port['aggregated_by']}"
                ports[name]["lag"] = bundles[port["aggregated_by"]]
            if normalize_mac(port.get("mac")):
                port_macs[normalize_mac(port.get("mac"))] = name
        for info in ports.values():
            if info["index"] in bundles:
                info["lag"] = bundles[info["index"]]
        uplink = device.get("last_uplink") or device.get("uplink") or {}
        poe_watts = [p["poe"]["watts"] or 0 for p in ports.values() if "poe" in p]
        parsed.append({
            "mac": normalize_mac(device.get("mac")), "name": device.get("name") or device.get("mac"),
            "model": device.get("model", ""), "ip": _lan_ip(device.get("ip", "")), "type": device.get("type", ""),
            "role": _role(device, macs), "ports": ports, "port_macs": port_macs,
            "poe_budget_w": _float(device.get("total_max_power")) if poe_watts else None,
            "poe_used_w": round(sum(poe_watts), 2) if poe_watts else None,
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


def _session(config, env, timeout, opener_factory, read):
    """Sign in with the read-only account, then read(get) - get(path) returns that API path's data list."""

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

        return read(get)

    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise WiringError("UniFi login refused - check ATLAS_UNIFI_USER/PASS (a local, read-only account)")
        raise WiringError(f"UniFi API error {error.code}")
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise WiringError(f"UniFi unreachable: {getattr(error, 'reason', error)}")


def fetch_unifi(config, env, timeout, opener_factory=None):

    return _session(config, env, timeout, opener_factory,
                    lambda get: parse_unifi(get("stat/device"), get("stat/sta")))


def parse_exposure(forwards, settings):
    """Enabled port forwards and whether UPnP is on, from rest/portforward and rest/setting."""

    upnp = next((bool(s.get("upnp_enabled")) for s in settings if "upnp_enabled" in s), None)
    rules = []
    for rule in forwards:
        if rule.get("enabled", True) is False:
            continue
        for protocol in ("tcp", "udp") if rule.get("proto", "tcp_udp") == "tcp_udp" else (rule.get("proto"),):
            rules.append({"protocol": protocol, "external": rule.get("dst_port"), "client": rule.get("fwd"),
                          "port": rule.get("fwd_port"), "description": rule.get("name", "")})

    return {"forwards": rules, "upnp": upnp}


def fetch_exposure(config, env, timeout, opener_factory=None):
    """What the router opens to the internet: port forwards + the UPnP switch (read-only)."""

    return _session(config, env, timeout, opener_factory,
                    lambda get: parse_exposure(get("rest/portforward"), get("rest/setting")))