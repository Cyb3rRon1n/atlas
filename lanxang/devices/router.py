"""
Router details: the names your router's DHCP server knows (and on OpenWrt, who is on which Wi-Fi), recorded as
device sightings so they link to devices by MAC and show as clues on Devices. Read with every `atlas scan`.

  OpenWrt  its web API (ubus over HTTP, what LuCI uses): session login with the router's user and password,
           luci-rpc getDHCPLeases, and for Wi-Fi luci-rpc getWirelessDevices + iwinfo assoclist per interface;
           the session is ended after each read. Checked against OpenWrt 24.10 (DHCP leases; Wi-Fi only with
           no radios, so empty).
"""

import json
import os

PASSWORD_ENV = "LANXANG_ROUTER_PASSWORD"
NO_SESSION = "0" * 32


class RouterError(Exception):
    pass


def _openwrt(http, base, user, password, timeout, verify):

    def call(sid, obj, method, args=None):
        try:
            response = http.post(f"{base}/ubus", json={"jsonrpc": "2.0", "id": 1, "method": "call",
                                                       "params": [sid, obj, method, args or {}]},
                                 timeout=timeout, verify=verify)
        except Exception as error:
            raise RouterError(f"No answer from {base}: {type(error).__name__}") from error
        if response.status_code >= 400:
            raise RouterError(f"OpenWrt {obj}.{method}: HTTP {response.status_code} - is the web interface "
                              "(uhttpd with ubus) on?")
        try:
            reply = response.json()
        except ValueError:
            raise RouterError(f"OpenWrt {obj}.{method}: not a JSON answer - is this the router's address?")
        if "error" in reply:
            raise RouterError(f"OpenWrt {obj}.{method}: {reply['error'].get('message', 'error')}")
        result = reply.get("result") or [None]
        if result[0] == 6:                                  # UBUS_STATUS_PERMISSION_DENIED
            if (obj, method) == ("session", "login"):
                raise RouterError("OpenWrt sign-in: wrong user or password")
            raise RouterError(f"OpenWrt {obj}.{method}: permission denied for this user")
        return result[1] if len(result) > 1 else {}

    login = call(NO_SESSION, "session", "login", {"username": user or "root", "password": password})
    sid = (login or {}).get("ubus_rpc_session")
    if not sid:
        raise RouterError("OpenWrt sign-in: wrong user or password")
    try:
        leases = (call(sid, "luci-rpc", "getDHCPLeases") or {}).get("dhcp_leases") or []
        wifi = {}
        try:
            radios = call(sid, "luci-rpc", "getWirelessDevices") or {}
            for radio in radios.values():
                for iface in radio.get("interfaces") or []:
                    name = iface.get("ifname")
                    ssid = ((iface.get("iwinfo") or {}).get("ssid") or (iface.get("config") or {}).get("ssid") or "")
                    if not name:
                        continue
                    for client in (call(sid, "iwinfo", "assoclist", {"device": name}) or {}).get("results") or []:
                        wifi[str(client.get("mac", "")).lower()] = {"ssid": ssid, "ap": "", "band": "",
                                                                     "signal": client.get("signal")}
        except RouterError:
            pass                                            # Wi-Fi is extra: DHCP names still count
    finally:
        try:
            call(sid, "session", "destroy")
        except RouterError:
            pass
    return [{"mac": str(lease.get("macaddr", "")).lower(), "ip": lease.get("ipaddr") or None,
             "hostname": lease.get("hostname") or "", "wifi": wifi.get(str(lease.get("macaddr", "")).lower())}
            for lease in leases if lease.get("macaddr")]


def fetch(config, environ=None, http=None):
    """[{"mac", "ip", "hostname", "wifi"}] from the router. Raises RouterError in words a person can act on."""

    import requests

    environ = os.environ if environ is None else environ
    base = (config.url or "").rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise RouterError("Enter the router's address, like http://192.168.1.1")
    return _openwrt(http or requests, base, config.user, environ.get(PASSWORD_ENV, ""), config.timeout,
                    config.verify_ssl)


def sightings(clients):
    """Device-inventory sightings: the DHCP name (and Wi-Fi) per MAC, as the UniFi source does."""

    from lanxang.devices import Sighting
    from lanxang.wiring import normalize_mac

    found = []
    for client in clients:
        mac = normalize_mac(client["mac"])
        if not mac:
            continue
        detail = {key: client[key] for key in ("hostname", "wifi") if client.get(key)}
        found.append(Sighting("router", mac, ip=client["ip"], mac=mac, hostname=client["hostname"] or None,
                              detail={"router": detail}))
    return found
