"""
Small HTTP/Docker lookups for the posture collector. The collector runs with
host networking, where Docker DNS names don't resolve, so service URLs are
built from each container's current bridge IP (looked up per run - IPs change
when containers are recreated). Every function returns a result dict and never
raises; failures become {"ok": False, "error": ...}.
"""

import ipaddress

import requests


def _networks(container):
    return (container.attrs.get("NetworkSettings") or {}).get("Networks") or {}


def container_ips(client):
    return {net["IPAddress"]: c.name for c in client.containers.list()
            for net in _networks(c).values() if net.get("IPAddress")}


def container_ip(client, name):
    try:
        container = client.containers.get(name)
    except Exception:
        return None
    return next((net["IPAddress"] for net in _networks(container).values() if net.get("IPAddress")), None)


def vpn_members(client, gluetun_name):
    try:
        gluetun = client.containers.get(gluetun_name)
    except Exception:
        return []
    targets = {f"container:{gluetun.id}", f"container:{gluetun_name}"}
    return [c.name for c in client.containers.list()
            if (c.attrs.get("HostConfig") or {}).get("NetworkMode") in targets]


def _fail(error):
    return {"ok": False, "error": str(error)[:300]}


def gluetun_status(base_url, api_key, get=requests.get):
    try:
        response = get(f"{base_url}/v1/publicip/ip", headers={"X-API-Key": api_key}, timeout=5)
        response.raise_for_status()
        data = response.json() or {}
        if not data.get("public_ip"):
            return _fail("gluetun returned no public_ip")
        return {"ok": True, "exit_ip": data["public_ip"], "country": data.get("country", "")}
    except (requests.RequestException, ValueError) as error:
        return _fail(error)


def crowdsec_bans(base_url, api_key, get=requests.get):
    try:
        response = get(f"{base_url}/v1/decisions", headers={"X-Api-Key": api_key}, timeout=5)
        response.raise_for_status()
        return {"ok": True, "active": len(response.json() or [])}
    except (requests.RequestException, ValueError) as error:
        return _fail(error)


def public_ip(url, get=requests.get):
    try:
        response = get(url, timeout=5)
        response.raise_for_status()
        ip = response.text.strip()
        ipaddress.ip_address(ip)
        return {"ok": True, "ip": ip}
    except (requests.RequestException, ValueError) as error:
        return _fail(error)
