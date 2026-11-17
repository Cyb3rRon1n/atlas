# Supported hardware

Atlas works on **any** home network with no logins at all: it finds every device from its own LAN scan, watches
for rogue DHCP servers and spoofed gateways, lists open ports, checks your public certificates, and runs uptime
checks. Connecting your gear adds detail - switch ports, Wi-Fi access points, VMs. Everything atlas reads is
read-only, and it never changes a device's settings.

On the **Setup** tab, *What's on your network?* asks what you have and shows only the matching cards. Gear atlas
has already found is ticked for you.

## What works today

| You have | How atlas reads it | What it adds | Set up on |
|---|---|---|---|
| **Any router** (ISP box, ASUS, Netgear, eero, Fritz!Box, Deco...) | Nothing to connect | Devices, DHCP/ARP watch, open ports, router port forwards via UPnP where it's on | - |
| **Managed switch** (Cisco SG/CBS, Netgear Smart, TP-Link JetStream, Zyxel GS1900, Aruba Instant On, MikroTik...) | SNMPv3, or v2c | Every port on the Cabling map: what's plugged in, speed, PoE, VLANs, spanning tree, cable health, traffic | Setup → Switches and routers |
| **Router or firewall with SNMP** (OPNsense, pfSense, OpenWrt, MikroTik RouterOS) | SNMPv3, or v2c | Its ports, links and traffic on the map | Setup → Switches and routers |
| **NAS** (Synology, QNAP, TrueNAS) | SNMPv3, or v2c | Its network ports and traffic on the map | Setup → Switches and routers |
| **UniFi** (gateway, switches, access points) | The console's local API, View Only account | UniFi ports and uplinks SNMP can't see, wired clients, port forwards | Setup → UniFi |
| **Proxmox VE** | API token with the PVEAuditor role | VMs and containers, drawn under their host | Setup → Proxmox |
| **Docker** | A read-only socket proxy | Containers and the services they publish | `docker-compose.yml` |
| **UPS** (APC, CyberPower, Eaton... plugged into a computer or NAS) | NUT (Network UPS Tools), port 3493, read-only | Alerts on a power cut, low battery and power back; charge, time left and load | Setup → UPS |
| **Any device** (phones, TVs, speakers, printers, smart plugs...) | MAC maker list, mDNS/Bonjour, SSDP/UPnP - nothing to set up | What new devices are: maker, the name and model they announce, where they're plugged in, a suggested name | Network → Devices |
| **Any web service or port** | HTTP or TCP | Up/down alerts, response time, uptime % | Servers → Uptime |

**SNMPv3 or v2c?** Use v3 whenever the device offers it (a read-only user, SHA + AES). Many cheaper switches,
routers and NAS boxes only speak v2c: atlas reads them with a read-only *community*, which travels unencrypted,
so give it no write access. Unmanaged switches and "Easy Smart" / "Plus" switches with no SNMP can't show their
ports - atlas still sees every device behind them, and lists them on the port of the managed switch they hang off.

**Not supported:** mesh systems and routers that are only managed from a phone app or vendor cloud (eero,
Google/Nest Wifi, Deco, Orbi, Firewalla) have no local interface atlas can read. Your devices still show up from
the LAN scan.

## Coming next

From our research into what homes and home labs actually run, roughly in this order:

1. **Internet health** - latency, packet loss and outage history for your connection, so you can show your ISP
   when it dropped.
2. **Pi-hole and AdGuard Home** - DNS clients and filtering status.
3. **Router details** - DHCP leases and Wi-Fi clients from OPNsense, OpenWrt, MikroTik and Fritz!Box.
4. **NAS health** - disk SMART status, pool health and temperatures from TrueNAS and Synology.
5. **Home Assistant** - one connection that covers many smart devices.
6. **TP-Link Omada and Unraid**, and APC network management cards read over SNMP (for a UPS with no NUT server).

Something you own missing? Open an issue with the make and model.
