"""
Clues for naming a new device, from what atlas already has - no extra scanning:

  maker       the IEEE's public list of MAC prefixes (oui.csv, refreshed monthly into inventory/)
  private     a randomised MAC (the locally administered bit): phones, tablets and laptops do this on Wi-Fi
  hostname    what DHCP / reverse DNS called it, without the .lan / .localdomain suffix
  place       where the cabling map saw it: "core-switch port 9" or "behind house Wi-Fi"
  ports       the port watch's open ports, in words ("printing (631)")

guess() turns those into a suggested name and kind for the Keep button. A clue that's missing is left out.
"""

import csv
import io
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

OUI_URL = "https://standards-oui.ieee.org/oui/oui.csv"
OUI_PATH = "inventory/oui.csv"

SUFFIXES = (".localdomain", ".lan", ".local", ".home", ".home.arpa", ".fritz.box")
VIRTUAL = ("52:54:00", "02:42", "bc:24:11")      # QEMU/libvirt, Docker, Proxmox: virtual, not private

# (words in the maker's name, kind, what to call it). First match wins.
MAKERS = (
    (("proxmox server solutions",), "vm", "Proxmox VM"),
    (("roku", "tcl", "vizio", "hisense", "lg electronics", "sony", "gaoshengda"), "tv", "TV"),
    (("espressif", "tuya", "shelly", "itead", "sonoff", "wyze", "signify", "philips lighting", "lifx", "ecobee",
      "tp-link smart", "ring", "arlo", "wemo", "belkin", "chamberlain", "irobot", "nest", "intellirocks", "govee",
      "sengled", "meross", "lumi", "aqara", "sonos"), "iot", "smart device"),
    (("hewlett", "hp inc", "brother", "canon", "epson", "lexmark", "xerox", "kyocera"), "other", "printer"),
    (("synology", "qnap", "asustor", "western digital"), "server", "NAS"),
    (("super micro", "supermicro"), "server", "server"),
    (("ubiquiti", "netgear", "tp-link", "cisco", "aruba", "mikrotik", "zyxel", "eero", "juniper"), "network",
     "network device"),
    (("raspberry",), "server", "Raspberry Pi"),
    (("nintendo", "valve"), "other", "game console"),
    (("amazon", "google"), "iot", "smart device"),
    (("apple", "samsung", "xiaomi", "oneplus", "motorola", "huawei", "oppo"), "phone", "phone or tablet"),
    (("intel", "realtek", "dell", "lenovo", "micro-star", "asustek", "gigabyte", "liteon", "azurewave"),
     "workstation", "computer"),
)
# words in its own hostname -> kind
HOSTNAMES = ((("iphone", "ipad", "android", "galaxy", "pixel"), "phone"), (("roku", "tv", "chromecast", "firetv"), "tv"),
             (("desktop", "laptop", "macbook", "imac", "pc"), "workstation"), (("printer", "laserjet", "officejet"), "other"),
             (("esp", "shelly", "tasmota", "wled"), "iot"), (("nas", "pve", "proxmox", "server", "pi"), "server"))
GENERIC = {"wlan0", "eth0", "localhost", "unknown", "android", "espressif"}
# mDNS service -> (kind, what it tells); first match in this order wins
SERVICE_KINDS = (("_googlecast._tcp", "tv", "Chromecast or Google TV"), ("_amzn-wplay._tcp", "tv", "Fire TV"),
                 ("_androidtvremote2._tcp", "tv", "Android TV"), ("_airplay._tcp", "tv", "AirPlay device"),
                 ("_ipp._tcp", "other", "printer"), ("_ipps._tcp", "other", "printer"), ("_printer._tcp", "other", "printer"),
                 ("_pdl-datastream._tcp", "other", "printer"), ("_sonos._tcp", "iot", "Sonos speaker"),
                 ("_spotify-connect._tcp", "iot", "speaker"), ("_raop._tcp", "iot", "AirPlay speaker"),
                 ("_hap._tcp", "iot", "HomeKit device"), ("_matter._tcp", "iot", "Matter device"),
                 ("_esphomelib._tcp", "iot", "ESPHome device"), ("_hue._tcp", "iot", "Hue bridge"),
                 ("_shelly._tcp", "iot", "Shelly device"), ("_miio._udp", "iot", "Xiaomi device"),
                 ("_companion-link._tcp", "phone", "Apple device"), ("_workstation._tcp", "workstation", "computer"),
                 ("_smb._tcp", "workstation", "computer with file sharing"))
SERVICE_WORDS = {"_googlecast._tcp": "Chromecast", "_airplay._tcp": "AirPlay", "_raop._tcp": "AirPlay audio",
                 "_ipp._tcp": "printing", "_ipps._tcp": "printing", "_printer._tcp": "printing",
                 "_hap._tcp": "HomeKit", "_matter._tcp": "Matter", "_esphomelib._tcp": "ESPHome",
                 "_spotify-connect._tcp": "Spotify", "_sonos._tcp": "Sonos", "_smb._tcp": "file sharing",
                 "_amzn-wplay._tcp": "Fire TV", "_hue._tcp": "Hue", "_companion-link._tcp": "Apple"}
# open port -> (kind, what it tells)
PORTS = {631: ("other", "printer"), 9100: ("other", "printer"), 8009: ("tv", "Chromecast or Google TV"),
         7000: ("tv", "AirPlay receiver"), 554: ("iot", "camera"), 3389: ("workstation", "Windows PC"),
         62078: ("phone", "iPhone or iPad"), 8060: ("tv", "Roku"), 1400: ("iot", "Sonos speaker"),
         5000: ("server", "NAS"), 8006: ("server", "Proxmox server"), 8123: ("server", "Home Assistant")}


def parse_oui(text):
    """{"AA:BB:CC": "Maker"} from the IEEE's oui.csv (Registry, Assignment, Organization Name, Address)."""

    makers = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) >= 3 and len(row[1]) == 6:
            prefix = ":".join(row[1][i:i + 2] for i in (0, 2, 4)).upper()
            makers[prefix] = row[2].strip()
    return makers


@lru_cache(maxsize=2)
def _load(path, mtime):

    return parse_oui(Path(path).read_text(encoding="utf-8", errors="replace"))


def makers(path=OUI_PATH):
    """The prefix table, {} until the file has been downloaded."""

    path = Path(path)
    return _load(str(path), path.stat().st_mtime) if path.exists() else {}


GET = None          # requests.get unless a test swaps it


def refresh(now, path=OUI_PATH, url=OUI_URL, get=None):
    """Download oui.csv when missing or a month old. True when it was fetched; never raises (no internet just
    means no maker names)."""

    path = Path(path)
    if path.exists() and now - datetime.fromtimestamp(path.stat().st_mtime) < timedelta(days=30):
        return False
    try:
        import requests
        response = (get or GET or requests.get)(url, timeout=60, headers={"User-Agent": "atlas"})
        response.raise_for_status()
        if len(parse_oui(response.text)) < 1000:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(response.text, encoding="utf-8")
        tmp.replace(path)
        from lanxang.posture.collectors.asn import remember_download
        remember_download(url, "Lanxang: MAC maker list download")
        return True
    except Exception:
        return False


def private(mac):

    mac = (mac or "").lower()
    if not mac or mac.startswith(VIRTUAL):
        return False
    try:
        return bool(int(mac[:2], 16) & 0x02)
    except ValueError:
        return False


def maker(mac, table):

    found = table.get((mac or "")[:8].upper()) if mac and not private(mac) else None
    return None if (found or "").strip().lower() in ("", "private") else found


# Registered company -> the name people know it by (or what its chip usually sits in).
ALIASES = (("intellirocks", "Govee"), ("gaoshengda", "Gaoshengda (TV Wi-Fi module)"), ("xiaomi", "Xiaomi"),
           ("hon hai", "Foxconn (builds for many brands)"), ("fugui", "Foxconn (builds for many brands)"),
           ("azurewave", "AzureWave (laptop Wi-Fi)"), ("liteon", "Lite-On (laptop Wi-Fi)"),
           ("universal global scientific", "USI (Wi-Fi module)"), ("murata", "Murata (Wi-Fi module)"),
           ("amazon technologies", "Amazon"), ("arcadyan", "Arcadyan (internet-provider router)"),
           ("sagemcom", "Sagemcom (internet-provider router)"), ("technicolor", "Technicolor (internet-provider router)"),
           ("ring llc", "Ring"), ("wyze", "Wyze"), ("sonos", "Sonos"), ("roku", "Roku"), ("nintendo", "Nintendo"))


def short_maker(name):
    """'Espressif Inc.' -> 'Espressif'; 'TP-LINK TECHNOLOGIES CO.,LTD.' -> 'TP-Link'; known aliases first."""

    lowered = (name or "").lower()
    for word, alias in ALIASES:
        if word in lowered:
            return alias

    words = (name or "").replace(",", " ").split()
    keep = []
    for word in words:
        if word.lower().strip(".") in ("inc", "ltd", "co", "corp", "corporation", "llc", "gmbh", "limited",
                                       "technologies", "technology", "electronics", "communications", "systems",
                                       "international", "company", "ag", "sa", "bv", "pte", "corporate", "tech", "network",
                                       "solutions"):
            break
        keep.append(word)
    text = " ".join(keep[:3]) or name or ""
    if not (text.isupper() and len(text) > 4):
        return text
    return " ".join("-".join(part if len(part) <= 3 else part.title() for part in word.split("-"))
                    for word in text.split())


def clean_hostname(hostname):

    name = (hostname or "").strip().rstrip(".")
    for suffix in SUFFIXES:
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
    return "" if name.lower() in GENERIC else name


def places(snapshot, devices):
    """{device id: "core-switch port 9" | "behind house Wi-Fi"} from the newest cabling map."""

    if not snapshot:
        return {}
    by_mac = {s["mac"].lower(): d["id"] for d in devices for s in d.get("sightings", []) if s.get("mac")}
    by_ip = {d["ip"]: d["id"] for d in devices if d.get("ip")}
    names = [device["name"] for device in devices if device.get("name")]
    # "behind" lists names: one shared by two devices (two "iPhone"s) can't say which, so it is skipped
    by_name = {device["name"]: device["id"] for device in devices
               if device.get("name") and names.count(device["name"]) == 1}
    nodes = {node["id"]: node for node in snapshot.get("nodes", [])}
    found = {}
    for link in snapshot.get("links", []):
        up, node = nodes.get(link["a"]) or {}, nodes.get(link["b"]) or {}
        device = node.get("device_id") or by_mac.get((node.get("mac") or "").lower()) or by_ip.get(node.get("ip"))
        if device and up.get("name"):
            port = str(link.get("a_port") or "")
            found.setdefault(device, f'{up["name"]} {port if port.lower().startswith("port") else "port " + port}'
                             if port else up["name"])
    for node in nodes.values():
        for name in node.get("behind") or []:
            if name in by_name:
                found.setdefault(by_name[name], f'behind {node["name"]}')
    return found


def clues(device, table, open_ports=(), place=None):
    """What atlas knows that helps name one device: {"maker", "private", "hostname", "place", "ports"}."""

    from lanxang.devices.ports import COMMON_PORTS

    macs = [s["mac"] for s in device.get("sightings", []) if s.get("mac")]
    hostnames = [clean_hostname(s.get("hostname")) for s in device.get("sightings", []) if s.get("hostname")]
    mac = macs[0] if macs else None
    said = next((s["detail"]["announce"] for s in device.get("sightings", [])
                 if isinstance(s.get("detail"), dict) and s["detail"].get("announce")), {})
    unifi = next((s["detail"]["unifi"] for s in device.get("sightings", [])
                  if isinstance(s.get("detail"), dict) and s["detail"].get("unifi")), {})
    router = next((s["detail"]["router"] for s in device.get("sightings", [])
                   if isinstance(s.get("detail"), dict) and s["detail"].get("router")), {})
    unifi = {**unifi, "wifi": unifi.get("wifi") or router.get("wifi")}
    return {"unifi_name": unifi.get("name"), "wifi": unifi.get("wifi"), "network": unifi.get("network"),
            "guest": unifi.get("guest", False), "announced": said.get("name"), "model": said.get("model"), "said_maker": said.get("maker"),
            "services": list(dict.fromkeys(SERVICE_WORDS[s] for s in said.get("services") or () if s in SERVICE_WORDS)),
            "service_ids": list(said.get("services") or ()),"maker": short_maker(maker(mac, table)) if maker(mac, table) else None,
            "private": private(mac), "hostname": next((h for h in hostnames if h), None),
            "place": place, "ports": [f"{COMMON_PORTS[port]} ({port})" if port in COMMON_PORTS else str(port) for port in sorted(open_ports)],
            "open": sorted(open_ports)}


def guess(found):
    """(suggested name, kind or None) from clues()."""

    kind, what = None, None
    services = set(found.get("service_ids") or ())
    model = found.get("model") or ""
    for service, service_kind, service_what in SERVICE_KINDS:
        if service in services:
            kind, what = service_kind, service_what
            if service == "_companion-link._tcp":
                kind = "workstation" if model.lower().startswith(("mac", "imac")) else "phone"
            break
    for port in found["open"] if not kind else ():
        if port in PORTS:
            kind, what = PORTS[port]
            break
    brand = found["maker"] or ""
    if not kind and brand:
        lowered = brand.lower()
        for words, maker_kind, maker_what in MAKERS:
            if any(f" {word} " in f" {lowered} " for word in words):
                kind, what = maker_kind, maker_what
                break
    hostname = found["hostname"]
    if not kind and hostname:
        lowered = "".join(ch if ch.isalnum() else " " for ch in hostname.lower())
        for words, host_kind in HOSTNAMES:
            if any(word in lowered.split() or (len(word) > 3 and word in lowered) for word in words):
                kind = host_kind
                break
    if not kind and found["private"]:
        kind, what = "phone", "phone, tablet or laptop"
    if found.get("unifi_name"):                    # the name someone already gave it in UniFi
        name = found["unifi_name"]
    elif found.get("announced"):
        name = found["announced"]
    elif model and not hostname:
        who = found.get("said_maker") or brand
        name = model if not who or model.lower().startswith(who.lower()) else f"{who} {model}"
    elif hostname:
        name = hostname
    elif what:
        name = f"{brand} {what}".strip() if brand and brand.lower() not in what.lower() else what.capitalize()
    else:
        name = f"{brand} device" if brand else None

    return name, kind


def for_devices(devices, table, open_ports=None, snapshot=None):
    """{device id: {"clues": clues(), "name": suggested name, "kind": suggested kind}} for the new devices.
    open_ports: the port watch's {device id (str): {"open": [ports]}}; snapshot: the newest cabling map."""

    where = places(snapshot, devices)
    found = {}
    for device in devices:
        if device["state"] != "new":
            continue
        info = clues(device, table, ((open_ports or {}).get(str(device["id"])) or {}).get("open") or (),
                     where.get(device["id"]))
        name, kind = guess(info)
        found[device["id"]] = {"clues": info, "name": name, "kind": kind}
    return found


def gather(devices):
    """for_devices() with the data atlas has saved; any source that fails is just left out."""

    open_ports = snapshot = None
    try:
        from lanxang.posture.store import PostureStore
        open_ports = ((PostureStore().statuses().get("ports") or {}).get("detail") or {}).get("devices")
    except Exception:
        pass
    try:
        from lanxang.wiring.store import WiringStore
        latest = WiringStore().latest(1)
        snapshot = latest[0]["snapshot"] if latest else None
    except Exception:
        pass
    try:
        table = makers()
    except Exception:
        table = {}
    return for_devices(devices, table, open_ports, snapshot)
