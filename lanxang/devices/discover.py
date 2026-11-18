"""
Ask the LAN what each device calls itself (lanxang scan, needs host networking - atlas-scan has it). Two standard,
read-only questions, a few seconds each:

  mDNS / Bonjour   one query for the common service types (Chromecast, AirPlay, printers, HomeKit, ESPHome...),
                   sent from an ordinary port so devices answer us directly. Gives names like "Living Room TV"
                   and models from the TXT records (md=, model=, ty=).
  SSDP / UPnP      the M-SEARCH every UPnP device answers; its description XML (on the device itself) gives
                   friendlyName, manufacturer and modelName.

discover() -> {ip: {"name", "model", "maker", "services"}}; anything that fails is left out, never raised.
"""

import re
import socket
import struct
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree

MDNS = ("224.0.0.251", 5353)
SSDP = ("239.255.255.250", 1900)
SERVICES = ("_googlecast._tcp", "_airplay._tcp", "_raop._tcp", "_ipp._tcp", "_ipps._tcp", "_printer._tcp",
            "_pdl-datastream._tcp", "_hap._tcp", "_matter._tcp", "_esphomelib._tcp", "_hue._tcp",
            "_spotify-connect._tcp", "_sonos._tcp", "_companion-link._tcp", "_device-info._tcp", "_workstation._tcp",
            "_smb._tcp", "_amzn-wplay._tcp", "_androidtvremote2._tcp", "_shelly._tcp", "_miio._udp")
ANONYMOUS = {"_spotify-connect._tcp", "_matter._tcp", "_miio._udp"}     # instance names are ids, not names
GENERIC_NAME = re.compile(r"^(spotifyconnect|chromecast|google-cast|android|[0-9a-f]{12,})(-[0-9a-f]+)?$", re.I)
MODEL_KEYS = ("md", "model", "ty", "usb_MDL", "product", "am")
NAME_KEYS = ("fn", "n", "name")
MAX_XML = 256 * 1024


def _question(name):

    return b"".join(bytes([len(part)]) + part.encode() for part in name.split(".")) + b"\x00" + struct.pack(">HH", 12, 1)


def mdns_query(services=SERVICES):

    return struct.pack(">6H", 0, 0, len(services), 0, 0, 0) + b"".join(_question(f"{s}.local") for s in services)


def _name(data, offset, depth=0):
    """(dotted name, offset after it) with DNS compression; raises ValueError on a loop or bad pointer."""

    labels, end = [], None
    while True:
        if offset >= len(data) or depth > 20:
            raise ValueError("bad name")
        length = data[offset]
        if length & 0xC0 == 0xC0:
            pointer = struct.unpack(">H", data[offset:offset + 2])[0] & 0x3FFF
            end = end or offset + 2
            offset, depth = pointer, depth + 1
            continue
        if length == 0:
            return ".".join(labels), end or offset + 1
        labels.append(data[offset + 1:offset + 1 + length].decode("utf-8", "replace"))
        offset += 1 + length


def parse_mdns(data):
    """[(type, owner name, value)] for the PTR (value = target name) and TXT (value = {key: text}) records."""

    _, _, qd, an, ns, ar = struct.unpack(">6H", data[:12])
    offset, records = 12, []
    for _ in range(qd):
        offset = _name(data, offset)[1] + 4
    for _ in range(an + ns + ar):
        owner, offset = _name(data, offset)
        kind, _, _, size = struct.unpack(">HHIH", data[offset:offset + 10])
        offset += 10
        rdata = data[offset:offset + size]
        if kind == 12:
            records.append(("PTR", owner, _name(data, offset)[0]))
        elif kind == 16:
            texts, i = {}, 0
            while i < len(rdata):
                item = rdata[i + 1:i + 1 + rdata[i]].decode("utf-8", "replace")
                key, _, value = item.partition("=")
                texts[key] = value
                i += 1 + rdata[i]
            records.append(("TXT", owner, texts))
        offset += size

    return records


def _collect_mdns(records, found):

    for kind, owner, value in records:
        if kind == "PTR" and owner.startswith("_"):
            service = owner.removesuffix(".local")
            found["services"].add(service)
            instance = re.sub(r" \(\d+\)$", "", value.removesuffix("." + owner))
            if (instance and instance != value and not found.get("name") and service not in ANONYMOUS
                    and not GENERIC_NAME.match(instance)):
                found["name"] = instance
        elif kind == "TXT":
            model = next((value[key] for key in MODEL_KEYS if value.get(key)), None)
            name = next((value[key] for key in NAME_KEYS if value.get(key)), None)
            found["model"] = found.get("model") or model
            if name:
                found["name"] = name                      # a TXT friendly name beats the instance label
            if value.get("manufacturer") or value.get("usb_MFG"):
                found["maker"] = found.get("maker") or value.get("manufacturer") or value.get("usb_MFG")


def _listen(sock, timeout, handle):

    end = time.monotonic() + timeout
    while (left := end - time.monotonic()) > 0:
        sock.settimeout(left)
        try:
            data, (ip, _) = sock.recvfrom(9000)
        except (socket.timeout, OSError):
            return
        try:
            handle(ip, data)
        except (ValueError, struct.error, IndexError):
            continue                                       # one odd packet never spoils the rest


def mdns(timeout=2.5):
    """{ip: {"name", "model", "maker", "services": set}} from Bonjour answers."""

    found = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        sock.bind(("", 0))
        sock.sendto(mdns_query(), MDNS)
        _listen(sock, timeout, lambda ip, data: _collect_mdns(
            parse_mdns(data), found.setdefault(ip, {"services": set()})))
    return found


def _headers(data):

    lines = data.decode("utf-8", "replace").split("\r\n")
    return {key.strip().lower(): value.strip() for key, _, value in (line.partition(":") for line in lines[1:]) if key}


def parse_description(xml):
    """{"name", "maker", "model"} from a UPnP device description."""

    root = ElementTree.fromstring(xml)
    device = next((el for el in root.iter() if el.tag.endswith("device")), None)
    if device is None:
        return {}
    pick = lambda tag: next((el.text.strip() for el in device if el.tag.endswith(tag) and el.text), None)
    model = " ".join(filter(None, (pick("modelName"), pick("modelNumber")))) or pick("modelDescription")
    return {"name": pick("friendlyName"), "maker": pick("manufacturer"), "model": model}


def _fetch(url, timeout):

    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "atlas"}), timeout=timeout) as reply:
        return reply.read(MAX_XML)


def ssdp(timeout=2.5, fetch=_fetch):
    """{ip: {"name", "maker", "model"}} from UPnP devices; the description is only read from the device itself."""

    locations = {}
    search = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 2\r\n"
              "ST: ssdp:all\r\n\r\n").encode()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.bind(("", 0))
        sock.sendto(search, SSDP)

        def keep(ip, data):
            location = _headers(data).get("location", "")
            if urllib.parse.urlsplit(location).hostname == ip and location.startswith("http://"):
                locations.setdefault(ip, location)

        _listen(sock, timeout, keep)

    def read(item):
        ip, url = item
        try:
            return ip, parse_description(fetch(url, 2.0))
        except Exception:
            return ip, {}

    with ThreadPoolExecutor(max_workers=8) as pool:
        return {ip: info for ip, info in pool.map(read, list(locations.items())[:64]) if info}


def _clean(text):

    return re.sub(r"\s+", " ", str(text or "")).strip()[:80] or None


def discover(timeout=2.5, ask_mdns=None, ask_ssdp=None):
    """{ip: {"name", "model", "maker", "services": [..]}} merged from both; {} when the network says nothing."""

    merged = {}
    for ask in (ask_mdns or mdns, ask_ssdp or ssdp):
        try:
            answers = ask(timeout)
        except Exception:
            continue
        for ip, info in answers.items():
            entry = merged.setdefault(ip, {"name": None, "model": None, "maker": None, "services": []})
            for key in ("name", "model", "maker"):
                entry[key] = entry[key] or _clean(info.get(key))
            entry["services"] = sorted(set(entry["services"]) | set(info.get("services") or ()))

    return {ip: info for ip, info in merged.items() if info["name"] or info["model"] or info["services"]}
