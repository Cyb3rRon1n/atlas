# Changelog

All notable changes to atlas. Versions follow [semantic versioning](https://semver.org); the
Docker image is published as `ghcr.io/cyb3rron1n/atlas:<version>` for every release.

## Unreleased

### Changed
- **No chat panel or "ask" chips while AI is off** (`intelligence.provider: none`, the default): they only led to
  "No AI assistant set up". They come back as soon as an AI is set up in Setup or atlas.yaml.

### Fixed
- **Smaller database**: routine discovery and plugin events (a copy of the system snapshot every scan, read by
  nothing after the latest) are kept 7 days instead of 90 - on a live install they were over half the database.
- **Ready for newer Python**: `datetime.utcnow()` (deprecated, to be removed) replaced everywhere by one helper
  that returns the same naive-UTC time; the test run went from ~600 warnings to none.
- **Browser tab icon**: pages now carry atlas's globe as their icon (inline), so tabs and bookmarks show it and
  browsers stop asking for a missing `/favicon.ico`.

## 0.11.1 - 2026-11-17

### Added
- **What changed** at the top of Alerts → Activity: the last 24 hours or 7 days in plain words - problems that
  started or cleared, one-off findings, new devices, Proxmox guests added or removed, container limits crossed.

### Fixed
- **Proxmox "changes detected" on every scan**: each scan reported the whole cluster (node and every guest) as
  newly added, because it compared against a saved state other atlas-scan commands overwrite. It now compares
  against the previous Proxmox scan, so Activity shows real changes only.
- **Servers → Overview and the AI check-up often saw an empty picture**: each atlas-scan command saves only its
  own part (the map, the Proxmox scan...), and the newest save was read alone. The newest state now fills each
  missing part from the most recent save that has it (container change detection gets the same fix).
- **Devices: Keep / Ignore no longer reload the page**, so the expanded "Show more" list stays open; the row turns
  into a short note. Buttons that still reload keep open lists and the scroll position.

## 0.11.0 - 2026-11-17

### Added
- **TrueNAS and Synology** (Setup → *TrueNAS or Synology*, or *What's on your network?* → NAS): Home's Storage &
  RAID card shows each pool or volume and every disk's health and temperature. Alerts when a pool isn't healthy,
  and the same disk alerts as Proxmox (failing, hot, worn out). TrueNAS 24.10+ over its websocket API with an API
  key; Synology DSM 7 with an admin account. Read-only. Built from the vendors' API docs and not yet checked
  against real hardware.
- **UniFi names and Wi-Fi details on Devices**: every client UniFi knows is linked to its device by MAC. A name
  you gave it in UniFi becomes atlas's suggested name, and the clue line shows the Wi-Fi network, access point,
  band and signal (and a guest network). Uses the existing UniFi connection.
- **Heartbeats** (Servers → Uptime): a backup or cron job pings its own secret address when it finishes
  (`/fail` when it failed). One alert when it doesn't check in on time or reports a failure, one when it's fine
  again.
- **Quiet hours** (Alerts page, or `notify.quiet_hours`): weekly windows, in your time zone, when no messages go
  out - problems still show on the Alerts page, like a scheduled Pause.
- **DNS check** in internet health: a name is looked up each minute (this machine's resolver, or each of
  `internet.dns_servers` - your router, Pi-hole) and shown under Internet on Servers → Uptime; one alert when
  lookups fail while the internet answers, one when they work again.
- **Prometheus `/metrics`**: uptime, internet, DNS, devices, alerts, disks, UPS, heartbeats and Pi-hole numbers
  for Grafana; read with the existing read-only API token.
- **Weekly summary**: Sunday evening, one message on how the week went (internet, services, new devices, alerts,
  heartbeats, disks, UPS) - which also shows atlas is alive. `notify.weekly_summary: false` turns it off.

## 0.10.0 - 2026-11-17

### Added
- **Internet health** on Servers → Uptime and a Home tile: once a minute atlas times a connection to public DNS
  servers (Cloudflare, Google, Quad9; `internet.targets`) and to your router. One alert when the internet drops
  and one when it's back with how long it lasted; the outage list says whether your router answered (so it was
  the provider) or not. Same graphs, uptime % and 30-day history as the uptime checks; no ping, no extra
  privileges. Turn off with `internet.enabled: false`.
- **Pi-hole and AdGuard Home** (Setup → *Pi-hole or AdGuard Home*, or *What's on your network?*): Home shows
  whether ad blocking is on, how many DNS questions were asked and blocked, and the devices that ask the most,
  named from your device list. One alert when blocking stays off (two checks in a row) and one when it's back.
  Pi-hole 6 (password or app password; atlas signs out after every read) and AdGuard Home (username +
  password). Read-only. Checked against real Pi-hole 6 and AdGuard Home v0.107.
- **Disk health from Proxmox**: every Proxmox scan reads each disk's SMART result, life left, temperature and
  bad-sector count. Home's Storage & RAID card sums them per host and lists any disk with a problem. Alerts when
  a disk fails SMART, runs hot (two scans in a row), is nearly worn out, or gains bad sectors; limits under
  `health.disk_*`. Works with the existing PVEAuditor token.

## 0.9.1 - 2026-11-17

### Fixed
- Atlas's own downloads (the IP-owner table, the IP-location file and the MAC maker list) no longer show up on
  the Security page as a new place this host talks to: after a download, its server is marked known.
- The event log and environment snapshots no longer grow forever: snapshots are kept 7 days and events 90 days
  (the newest of each kind is always kept). The tables get indexes, so Home and Overview stay fast.
- *Sign out* now ends every session, so a copied cookie stops working too.
- Two devices with the same name no longer confuse outage grouping or the device clues' *behind ...* place.
- The tests no longer touch the network (mDNS, UPnP, downloads) and run about 15 seconds faster.

## 0.9.0 - 2026-11-16

A new look (side menu, light and dark, Home and Cabling redesigned), clues that say what each new device is,
uptime checks, UPS power alerts, per-port traffic, one alert per outage, and a Setup tab that asks what you own.

### Added
- **Clues for new devices** on Devices and Triage, so you can tell what an IP address is: the maker from its
  MAC address (the IEEE's public list, downloaded monthly into `inventory/oui.csv`; without internet it is
  just left out), a private (randomised) Wi-Fi address, the name it gives itself, where the cabling map saw
  it (switch port, or behind which access point), what it announces about itself over mDNS/Bonjour and
  UPnP ("Living Room TV - Chromecast", "HP LaserJet M404", AirPlay, printing, HomeKit; `scan.discover`, on by
  default), its open ports and when it first appeared. Atlas fills
  in a suggested name and kind - *Espressif smart device*, *Nintendo game console*, *Phone, tablet or
  laptop* - and Keep saves both; change either before keeping.
- **Alerts page**: every problem atlas's checks find, in one place - *Needs action* (problems, which also send
  alerts), *Watching* (page only, e.g. a switch atlas can't read or devices waiting for a name) and *Resolved in
  the last 7 days*, each with a link to investigate. Covers the LAN watch, host health, certificates, cabling
  (cable health, loops, unreadable switches), open ports, important devices offline and the torrent VPN check.
  Problems resolve by themselves when the check stops seeing them; one-off findings (a new open port) after 7
  days. Home's *Needs attention* includes them.
- **Acknowledge, mute and pause** on the Alerts page. *Acknowledge* marks a problem as seen (it sinks down the
  list and leaves Home; a one-off finding is cleared). *Mute* stops messages about one alert, or about its whole
  device, for a day, a week or always - it stays listed. *Pause alerts* (1 hour to a day) holds every message
  during maintenance and shows a banner; *Resume now* ends it. Muted items are listed with *Unmute*. Every check
  asks before sending; if the alert list can't be read, alerts are sent as before.
- **UPS watch** (Setup → UPS): reads a NUT server - nut-server, or a Synology/QNAP/Unraid/TrueNAS network UPS
  server - once a minute. One alert on a power cut (charge and time left), one when the battery runs low, one when
  power is back (with how long it lasted). Status shows on Servers → Uptime.
- **Setup asks what's on your network.** Tick what you have (managed switch, SNMP router/firewall, NAS, UniFi,
  Proxmox, or just an ISP router) and Setup shows only the matching cards; gear atlas already found is ticked for
  you. Nothing is required - atlas works on any network from its own scan.
- **SNMPv2c** for switches, routers and NAS boxes that don't offer v3: a read-only community, kept with the other
  secrets. The card is now *Switches and routers (SNMP)*.
- **Supported hardware** page in the docs: what works today with which gear, and what's coming next.
- **Uptime checks** (Servers → Uptime). Add a web address or `host:port`; atlas tries it every minute. After two
  failures in a row it alerts once ("Media server is down") and again when it's back, with how long it was down.
  The page shows response time over 24 hours and uptime over 24 hours, 7 days and 30 days, and offers your public
  hostnames as one-click checks. `atlas uptime check` runs one pass; the compose file runs it every minute.
- **Fewer, clearer tabs.** Ten top tabs are now six - *Home, Alerts, Network, Servers, Security, Setup* - each
  with its pages as sub-tabs: Alerts · Activity (was History); Devices · Triage · Coverage · Cabling; Overview ·
  Trends (was Hosts); Exposure (was Posture) · Services (was Network) · Visitors (was Access). Every old address
  still works.
- **Traffic per port.** The cabling scan now reads each port's byte counters and works out its average traffic
  since the last scan. Busy cables show on the map (thick orange over half full, red over 80%, with the rate on the
  label), and the Port map gains a 24-hour graph per port. Kept a week; no extra polling.
- **One alert per outage.** When a switch or AP on the cabling map goes offline, the offline devices behind it fold
  under it - one alert and one message ("core-switch is offline - 12 devices behind it unreachable") instead of one
  per device.
- **Atlas finds switches it could read.** Each port check sends devices the standard SNMPv3 discovery message
  (no user, no password) and reads the LLDP capability flags the mapped switches already collect. Devices that
  look like managed switches or routers are suggested on the Cabling page, on their device page and under
  *Found on your network* on the Setup tab's Switches card (**Use** fills in the form, **Don't ask** hides it).
  `security.snmp_discovery` turns the probe off; `wiring.not_managed` lists dismissed addresses.

### Changed
- The chat panel starts closed on every page (open it from *Chat* in the side menu; atlas remembers).
  Devices, Triage and Coverage show times as *5 min ago*, with the exact time on hover. Makers known by
  another name show that name (Shenzhen Intellirocks shows as Govee).
- Line icons instead of emoji on Devices, Activity, Services, Visitors and Cabling, drawn in the theme's colours.
- **Cabling** opens on the switches' front panels (all expanded), with a *Front panels / Map* switch at the top
  and a one-line summary (switches, cables, what to check). Clicking a port shows a panel beside it: what's
  plugged in, speed, traffic now, PoE, VLANs, bundle or standby, and any cable problem in words. Clicking a
  box on the map jumps to its front panel.
- **Home** opens with one plain sentence (*Everything is healthy*, or how many things need a look), a row of
  numbers - devices online, servers healthy, uptime over 7 days, public routes, power or storage - each
  linking to its page, and a *Needs attention* table with how serious each item is and where to fix it.
- **New look**: a side menu with each section's pages listed under it (no second row of tabs), and a light
  theme by default that follows your system's dark mode. A sun / moon button in the side menu switches it and
  remembers your choice. Every page draws its colours from one set of theme tokens; the exported cabling SVG
  keeps the colours you see.
- Clearer errors from the Setup tab's tests and the cabling scan: a switch that doesn't answer, an unknown
  SNMPv3 user, a wrong passphrase or privacy type, and a Proxmox host that's down or refuses the token are each
  explained in plain words instead of net-snmp's or the HTTP library's raw message.

## 0.8.0 - 2026-11-16

### Added
- **Setup tab** on the web page: connect alerts (ntfy, Discord/Slack/webhooks, email), an AI model, managed
  switches (SNMPv3), a UniFi console and Proxmox without editing files. Every card has a Test button (alerts send
  one test message; the AI check only lists models; switches get one SNMP request; UniFi and Proxmox are signed
  in to and read) and Save / Turn off. Saving a switch, UniFi or Proxmox turns that feature on. Values set in
  `atlas.yaml` or `.env` win and show read-only; passwords and keys are stored privately in the data volume and
  never shown again. No restart needed.
- **Getting started checklist** on the Home page: name your devices, turn on alerts, then (optional) map your
  cabling and connect Proxmox. Each step links to where it's done and ticks off by itself; the list disappears
  once the required steps are done.

### Changed
- No AI model is assumed by default (`intelligence.provider` defaults to `none`, as the installer always
  wrote); `atlas doctor` reports it as off instead of an unknown provider. The installer no longer writes the AI
  section unless you choose one, so it can be set on the Setup tab.
- New description everywhere: atlas is a self-hosted watchdog for your home network (devices, cabling, security,
  alerts), not an "AI operations platform". New banner, docs home page and package description to match.

### Fixed
- The one-line installer (`curl ... | bash`) stopped silently after starting the containers, without printing
  the address and setup code: `docker compose` read the rest of the piped script as its input. Atlas itself was
  running fine. The installer now reads the whole script before running anything.

## 0.7.0 - 2026-11-15

### Added
- **PoE at a glance**: each device's front-panel header on the Cabling page lists the ports that can supply PoE
  and how many are powering something, e.g. `PoE: Port 4 (1 powering, 9.6 W of 30 W)`.
- **Device pages link to the wired map**: a switch, gateway or access point shows its model and a link that opens
  its front panel on the Cabling page; other wired devices link to where they plug in.
- **Spanning tree, link bundles and VLANs** on the cabling map: a spare cable that spanning tree blocks shows as
  standby (a note, not a warning); cables that all carry traffic are flagged as a loop risk and alerted once; LACP
  bundles draw as one labelled bundle; port tooltips show VLANs, with a VLAN picker when there's more than one. The
  switch model shows next to its name. Standard MIBs, plus UniFi's own port data.
- **Certificate watch** (`atlas certs check`, run daily by atlas-scan): alerts 14 and 3 days before a public
  hostname's TLS certificate expires, when a browser would refuse it, and when it's renewed. Days left show next
  to each route on the Posture page's Public exposure tab. Hostnames come from the Traefik routes plus
  `security.cert_hosts`.
- **Cable health** on the cabling map: CRC/alignment errors growing between scans, duplex mismatches, ports
  linking slower than before and flapping links, from SNMP and UniFi port counters. Problems turn the port red
  and send an alert (plus one when it clears).
- **LAN watch** (`atlas lan check`, run by atlas-scan): alerts on a DHCP server other than your router or
  `security.dhcp_servers`, on DHCP going silent, and on the gateway's IP answering from a new MAC (ARP spoofing).
  Shown as the LAN tile on the Posture page. The Docker image adds `atlas-dhcp-python`, an interpreter copy
  with only the permission to listen on UDP port 68.
- **Open-port watch** (`atlas ports check`, run by atlas-scan): alerts once when a LAN device, this host or the
  router opens a new port - common service ports by TCP connect, listening sockets, UniFi port forwards / UPnP
  switch, and UPnP IGD mappings on other routers. The first run only learns. Device pages list open ports; the
  Posture page shows the router's exposure.
- **PoE on the cabling map:** ⚡ on ports powering a device, capable ports outlined, per-device use and budget,
  PoE faults alert, a nearly used budget is shown, and ports starting/stopping PoE appear as changes. Read from
  SNMP (POWER-ETHERNET-MIB) and the UniFi console.
- **Host health alerts** (`atlas sample`): a sensor near its own temperature limit, memory or disks above 90%,
  crashed or restart-looping containers, and status feeds (e.g. a RAID watchdog) reporting a problem - one alert
  when it starts, one when it clears. Limits under `health:`.

### Changed
- **Asleep containers:** a container that stopped cleanly (exit code 0, e.g. a game room put to sleep by an idle
  timer) or has the label `atlas.on-demand=true` is listed as *Asleep* on the home page, not as a problem;
  `/api/summary` adds `containers_asleep`.
- Posture forgets a container's destinations and "expected" marks after `posture.retention_days` without traffic.
- The README shows the cabling map and switch front panels; the long design history moved from `CLAUDE.md`
  to [Design notes](docs/development/design-notes.md).

## 0.6.0 - 2026-11-15

### Added
- Alerts beyond Signal: `notify.ntfy`, `notify.webhooks` (Discord, Slack or plain JSON), `notify.email`
  (SMTP) and `notify.apprise` (100+ services; the Docker image includes Apprise). Every set channel gets
  each alert; one failing never blocks the others. `ATLAS_NTFY_TOKEN` / `ATLAS_SMTP_PASSWORD` can stay in `.env`.
- `atlas notify test` sends a test alert and shows which channels got it.
- New README: install, first steps, privacy (no telemetry), FAQ and troubleshooting on one short page.

## 0.5.1 - 2026-11-14

### Fixed
- Docker page and scans failed with "403 Forbidden" behind the socket proxy: the container list
  reads each container's image tags, so the proxy now also allows read-only image lookups
  (`IMAGES: 1`). Upgrade by running the installer again.

## 0.5.0 - 2026-11-14

### Upgrading from 0.4.x - read first
- **atlas now asks for its own admin password** (`web.auth: builtin`, the default). After the
  upgrade the web page shows a setup screen; the one-time code is in `docker compose logs atlas`.
  Already behind Authelia, Authentik or another auth proxy? Add `web: {auth: proxy}` to
  `atlas.yaml` before upgrading and nothing changes.
- **`docker.sock` is no longer mounted into atlas.** The new compose file adds a read-only Docker
  socket proxy. Copy the new `docker-compose.yml` (or re-run the installer). The chat's
  stop/restart/resize actions need `ATLAS_DOCKER_WRITE=1` in `.env`.
- Homepage widgets on `/api/summary` need the API token header (`atlas auth token`) unless you use
  `web.auth: proxy`.

### Added
- **One-line installer** (`install.sh`): checks Docker, asks four questions, writes `~/atlas`,
  starts atlas and sets the admin password. Re-run to upgrade; `--uninstall` to remove.
- **Built-in sign-in**: scrypt-hashed admin password, signed session cookie, per-client rate limit,
  first-run setup code, read-only API token for dashboards, `atlas auth` commands, `/healthz`.
- **Cabling map** (`/cabling`): port-level wired topology from your switches over SNMPv3 (read-only)
  and, optionally, a UniFi console - front-panel port layouts, patch-panel labels, change history,
  CSV/SVG export, Refresh button.
- **Access page**: a world map of who reaches your public services, sign-ins from Authelia,
  Jellyfin, Audiobookshelf and Kavita, learned normal places and new-place review.
- **Network page**: internet / home-only / background lanes plus the device tree.
- **Trends** as charts from atlas's own host history.
- **Torrent VPN watch**: alerts when a qBittorrent behind gluetun is unreachable, disconnected or
  firewalled.
- Home page redesign: what needs attention, storage, security trends, a daily AI check-up, and a
  docked chat panel.

### Changed
- Docker access goes through a read-only socket proxy by default.
- `ATLAS_BIND` in `.env` opens the web page to the LAN (sign-in makes that safe).
- Example configs, tests and docs use neutral example names and addresses.

### Security
- The web page no longer relies on a proxy for authentication by default; JSON writes need a
  signed-in session, not just a same-origin request.
