"""
Made-up home network for screenshots: python tools/demo_data.py <dir> [--degraded]

Writes <dir>/lanxang.yaml and <dir>/inventory/atlas.db (plus a small maker table) through the same store APIs
the scans use. Everything is invented: addresses on 192.0.2.0/24 (TEST-NET-1), example.org names.
Run the web UI from <dir> to see it. --degraded puts the NAS pool "tank" in DEGRADED for the hardware docs.
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "demo").resolve()
DEGRADED = "--degraded" in sys.argv
(DIR / "inventory").mkdir(parents=True, exist_ok=True)
os.chdir(DIR)                                   # the stores open inventory/atlas.db relative to here

(DIR / "lanxang.yaml").write_text("""\
name: homeserver
web: {auth: proxy}
notify: {ntfy: {url: "https://ntfy.example.org", topic: home-alerts}}
proxmox: {enabled: true, host: 192.0.2.11}
nas: {enabled: true, kind: truenas, url: "https://192.0.2.12", user: lanxang, name: storage}
ups: {enabled: true, host: 192.0.2.10}
wiring: {enabled: true, unifi: {enabled: true, url: "https://192.0.2.1"}}
uptime:
  checks:
    - {name: Photos, target: "https://photos.example.org"}
    - {name: Media, target: "https://media.example.org"}
    - {name: Files, target: "192.0.2.12:445"}
""")

# Maker names by MAC prefix (the IEEE oui.csv format); the prefixes are invented for this demo.
MAKERS = {"0C1001": "Apple, Inc.", "0C1002": "Samsung Electronics Co.,Ltd", "0C1003": "Intel Corporate",
          "0C1004": "Ubiquiti Inc", "0C1005": "Super Micro Computer, Inc.", "0C1006": "Brother Industries, LTD.",
          "0C1007": "Roku, Inc", "0C1008": "Sonos, Inc.", "0C1009": "Espressif Inc.", "0C100A": "Google, Inc.",
          "0C100B": "Netgear", "0C100C": "iXsystems, Inc.", "0C100D": "Raspberry Pi Trading Ltd",
          "0C100E": "Nintendo Co.,Ltd", "0C100F": "Signify Netherlands B.V.", "0C1010": "Dell Inc."}
(DIR / "inventory" / "oui.csv").write_text("Registry,Assignment,Organization Name,Organization Address\n" + "".join(
    f'MA-L,{prefix},"{maker}",-\n' for prefix, maker in MAKERS.items()))

from lanxang.alerts import AlertStore                                   # noqa: E402 (after the chdir)
from lanxang.clock import utcnow                                        # noqa: E402
from lanxang.config.models import AtlasConfig                           # noqa: E402
from lanxang.devices import Sighting                                    # noqa: E402
from lanxang.devices.store import InventoryStore                        # noqa: E402
from lanxang.events import AtlasEvent                                   # noqa: E402
from lanxang.intelligence.context import AtlasEnvironmentContext        # noqa: E402
from lanxang.knowledge.store import KnowledgeStore                      # noqa: E402
from lanxang.monitoring import nas, ups                                 # noqa: E402
from lanxang.monitoring.uptime import UptimeStore                       # noqa: E402
from lanxang.posture.store import PostureStore                          # noqa: E402
from lanxang.wiring.scan import run_scan                                # noqa: E402
from lanxang.wiring.store import WiringStore                            # noqa: E402
from lanxang.wiring.unifi import parse_unifi                            # noqa: E402

settings = AtlasConfig.model_validate(__import__("yaml").safe_load((DIR / "lanxang.yaml").read_text()))
now = utcnow()


def mac(maker, n):
    prefix = next(p for p, m in MAKERS.items() if m.startswith(maker))
    return f"{prefix[0:2]}:{prefix[2:4]}:{prefix[4:6]}:00:00:{n:02x}".lower()


# (last octet, name, kind, maker, wired?, state). "new" ones are left for the owner to name.
DEVICES = [
    (1, "gateway", "network", "Ubiquiti", True, "known"), (2, "core-switch", "network", "Ubiquiti", True, "known"),
    (3, "living-room-ap", "network", "Ubiquiti", True, "known"), (4, "desk-switch", "network", "Netgear", True, "known"),
    (10, "homeserver", "container-host", "Super Micro", True, "known"), (11, "pve1", "server", "Dell", True, "known"),
    (12, "storage", "server", "iXsystems", True, "known"), (13, "pi-dns", "server", "Raspberry", True, "known"),
    (20, "office-desktop", "workstation", "Intel", True, "known"), (21, "work-laptop", "workstation", "Dell", False, "known"),
    (22, "kitchen-laptop", "workstation", "Apple", False, "known"), (23, "study-laptop", "workstation", "Intel", False, "known"),
    (30, "printer", "other", "Brother", True, "known"), (31, "living-room-tv", "tv", "Samsung", True, "known"),
    (32, "bedroom-tv", "tv", "Roku", False, "known"), (33, "kitchen-speaker", "iot", "Sonos", False, "known"),
    (34, "lounge-speaker", "iot", "Sonos", False, "known"), (35, "game-console", "other", "Nintendo", False, "known"),
    (36, "media-stick", "tv", "Google", False, "known"), (37, "tablet", "phone", "Apple", False, "known"),
    (40, "phone-a", "phone", "Apple", False, "known"), (41, "phone-b", "phone", "Samsung", False, "known"),
    (42, "phone-c", "phone", "Google", False, "known"), (43, "phone-d", "phone", "Apple", False, "known"),
    (44, "watch", "phone", "Apple", False, "known"),
    (50, "hall-light", "iot", "Signify", False, "known"), (51, "porch-light", "iot", "Signify", False, "known"),
    (52, "lounge-light", "iot", "Signify", False, "known"), (53, "thermostat", "iot", "Espressif", False, "known"),
    (54, "doorbell", "iot", "Espressif", False, "known"), (55, "smart-plug-1", "iot", "Espressif", False, "known"),
    (56, "smart-plug-2", "iot", "Espressif", False, "known"), (57, "air-sensor", "iot", "Espressif", False, "known"),
    (58, "garden-camera", "iot", "Espressif", False, "known"), (59, "hub", "iot", "Signify", True, "known"),
    (70, "Galaxy-Tab", "other", "Samsung", False, "new"), (71, "192.0.2.71", "other", "Espressif", False, "new"),
]
GUESTS = [(100, "photos", "running"), (101, "media", "running"), (102, "backup", "running"),
          (103, "home-automation", "running"), (104, "test-vm", "stopped")]

lan = [Sighting("lan", mac(maker, octet), ip=f"192.0.2.{octet}", mac=mac(maker, octet),
                hostname=None if name.startswith("192.") else name,
                detail={"gateway": True} if octet == 1 else {})
       for octet, name, _, maker, _, _ in DEVICES]
inventory = InventoryStore()
# Three LAN scans ten minutes apart; the printer answered only the first, so it now shows as offline.
for i, minutes in enumerate((30, 20, 10)):
    inventory.record_run("lan", [s for s in lan if i == 0 or s.ip != "192.0.2.30"], now=now - timedelta(minutes=minutes))
inventory.record_run("proxmox", [Sighting("proxmox", f"pve:{vmid}", ip=f"192.0.2.{vmid - 20}" if up == "running" else None,
                                          hostname=name, detail={"type": "qemu" if vmid != 103 else "lxc"})
                                 for vmid, name, up in GUESTS], now=now - timedelta(minutes=10))

# UniFi: gateway Port 1 -> core-switch Port 1 (uplink), switch ports to the servers, the AP on PoE Port 8.
GW, SW, AP = mac("Ubiquiti", 1), mac("Ubiquiti", 2), mac("Ubiquiti", 3)
switch_port = {10: 3, 11: 4, 12: 5}
desk = {4, 13, 20, 31, 59}               # behind desk-switch (unmanaged) on the gateway's Port 3
UNIFI_DEVICES = [
    {"mac": GW, "name": "gateway", "model": "UCG-Ultra", "type": "udm", "ip": "192.0.2.1",
     "port_table": [{"port_idx": i, "name": f"Port {i}", "up": i in (1, 3, 5), "speed": 2500 if i == 5 else 1000 if i in (1, 3) else 0,
                     "rx_bytes": 10**9, "tx_bytes": 10**9} for i in range(1, 6)],
     "last_uplink": {"type": "wire", "uplink_mac": "02:00:5e:00:53:99", "port_idx": 5}},
    {"mac": SW, "name": "core-switch", "model": "USW-Lite-16-PoE", "type": "usw", "ip": "192.0.2.2", "total_max_power": 45,
     "port_table": [{"port_idx": i, "name": f"Port {i}", "up": i in (1, 8) or i in switch_port.values(),
                     "speed": 1000 if i in (1, 8) or i in switch_port.values() else 0, "full_duplex": True,
                     **({"port_poe": True, "poe_enable": True, "poe_mode": "auto", "poe_power": "6.4", "poe_class": "Class 4"}
                        if i == 8 else {})} for i in range(1, 17)],
     "last_uplink": {"type": "wire", "uplink_mac": GW, "uplink_remote_port": 1, "port_idx": 1}},
    {"mac": AP, "name": "living-room-ap", "model": "U6-Lite", "type": "uap", "ip": "192.0.2.3", "radio_table": [{}],
     "port_table": [{"port_idx": 1, "up": True, "speed": 1000}],
     "last_uplink": {"type": "wire", "uplink_mac": SW, "uplink_remote_port": 8, "port_idx": 1}},
]
UNIFI_CLIENTS = [{"mac": mac(maker, octet), "ip": f"192.0.2.{octet}", "hostname": "" if name.startswith("192.") else name, "network": "Default",
                  **({"is_wired": True, "sw_mac": SW, "sw_port": switch_port[octet]} if octet in switch_port else
                     {"is_wired": True, "sw_mac": GW, "sw_port": 3} if octet in desk else
                     {"is_wired": False, "essid": "home", "ap_mac": AP, "signal": -48 - octet % 17,
                      "radio": "na" if octet % 3 else "ng"})}
                 for octet, name, _, maker, _, _ in DEVICES if octet > 3 and octet != 30]
run_scan(settings, WiringStore(), inventory.devices(), env={}, now=now - timedelta(minutes=5),
         fetch=lambda *a, **k: parse_unifi(UNIFI_DEVICES, UNIFI_CLIENTS))

for device in inventory.devices():                    # the owner named and typed what they recognise
    row = next((d for d in DEVICES if f"192.0.2.{d[0]}" == device["ip"]), None)
    if row and row[5] == "known":
        inventory.set_fields(device["id"], {"name": row[1], "kind": row[2], "state": "known"})
    elif device["sightings"][0]["source"] == "proxmox":
        inventory.set_fields(device["id"], {"state": "known"})

# What the map and a Proxmox scan would have saved.
environment = AtlasEnvironmentContext()
environment.update("topology", {
    "host": "homeserver",
    "docker": {"available": True, "networks": {"apps": [{"name": n, "status": "running", "health": "healthy"} for n in (
        "reverse-proxy", "photos", "media", "files", "dns", "home-automation", "backups", "monitoring")]}},
    "proxmox": {"host": "192.0.2.11", "guests": [{"name": n, "status": s, "template": False} for _, n, s in GUESTS
                                                  if s == "running"]},
    "lan": [{"name": name, "address": f"192.0.2.{octet}", "reachable": octet != 30}
            for octet, name, _, _, _, _ in DEVICES[:13]]})
KnowledgeStore().save_environment(environment)
KnowledgeStore().save_event(AtlasEvent("atlas.proxmox.scan.completed", "proxmox", {"nodes": [
    {"name": "pve1", "status": "online", "cpu": 0.07, "mem": 17 * 2**30, "maxmem": 64 * 2**30,
     "disk": 310 * 2**30, "maxdisk": 960 * 2**30}]}))

posture = PostureStore()
nas.run(settings, posture, now - timedelta(minutes=2), send=lambda text: None, get=lambda config: {
    "kind": "TrueNAS", "pools": [{"name": "tank", "health": "DEGRADED" if DEGRADED else "ONLINE",
                                  "size": 16 * 10**12, "alloc": 7 * 10**12}],
    "disks": [{"dev": f"sd{c}", "type": "hdd", "serial": f"DEMO{i}", "health": "PASSED", "temp": 34 + i}
              for i, c in enumerate("abcd")]})
ups.run(settings, posture, now - timedelta(minutes=1), send=lambda text: None, get=lambda *a: {"rack": {
    "ups.status": "OL", "battery.charge": "100", "battery.runtime": "2700", "ups.load": "21",
    "device.mfr": "APC", "device.model": "Back-UPS 1500"}})
posture.save_routes([{"name": n, "hosts": [f"{n}.example.org"], "entrypoints": ["websecure"],
                      "protection": "authelia" if n != "photos" else "public"} for n in ("photos", "media", "files")],
                    now)

# The security posture collectors' last readings: tunnel up, VPN exit differs from home, a few bans, LAN fine.
for source, detail in (("tunnel", {"connections": 4}), ("gluetun", {"exit_ip": "198.51.100.7"}),
                       ("public_ip", {"ip": "203.0.113.20"}), ("crowdsec", {"active": 7}),
                       ("lan", {"issues": [], "offers": [{"server": "192.0.2.1"}]})):
    posture.set_status(source, True, detail, now)
for hour in range(24, 0, -1):                          # a day of outbound traffic, busier in the evening
    load = 1 + (hour % 24 in range(2, 8)) * 3
    posture.record_flows([{"source": src, "band": band, "dest_ip": f"198.51.100.{n}", "dest_port": 443,
                           "proto": "tcp", "asn": 64500 + n, "org": "Example Net", "cc": "US",
                           "bytes_out": load * size // 4, "bytes_in": load * size, "new_conn": True}
                          for n, (src, band, size) in enumerate((("homeserver", "direct", 40 * 10**6),
                                                                 ("media", "vpn", 90 * 10**6)))],
                         now - timedelta(hours=hour), track_seen=False)
for minutes, event_type, payload in ((300, "atlas.proxmox.changes_detected", {"changes": [
                                         {"type": "guest_status_changed", "vmid": 120, "name": "test-vm",
                                          "from": "running", "to": "stopped"}]}),
                                     (90, "atlas.monitoring.changes_detected", {"changes": [
                                         {"type": "container_metric_crossed", "container": "photos",
                                          "metric": "memory"}]}),
                                     (40, "atlas.devices.updated", {"name": "kitchen-speaker"})):
    KnowledgeStore().save_event(AtlasEvent(event_type, "demo", payload))

printer = next(d for d in inventory.devices() if d["ip"] == "192.0.2.30")
AlertStore().sync("devices", [{"key": "offline:printer", "title": "Printer is offline", "level": "problem",
                               "detail": "not seen on the network for 20 minutes", "href": f"/devices/{printer['id']}",
                               "device_id": printer["id"]}], now - timedelta(minutes=20))

uptime = UptimeStore()
for minute in range(60, 0, -1):
    uptime.save({"Internet": (True, 14.0 + minute % 5, ""), **{c.name: (True, 40.0 + minute % 7, "")
                                                               for c in settings.uptime.checks}},
                now - timedelta(minutes=minute))

print(f"{len(inventory.devices())} devices in {DIR / 'inventory' / 'atlas.db'}")
