# Changelog

All notable changes to atlas. Versions follow [semantic versioning](https://semver.org); the
Docker image is published as `ghcr.io/cyb3rron1n/atlas:<version>` for every release.

## Unreleased

### Added
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
- **Atlas finds switches it could read.** Each port check sends devices the standard SNMPv3 discovery message
  (no user, no password) and reads the LLDP capability flags the mapped switches already collect. Devices that
  look like managed switches or routers are suggested on the Cabling page, on their device page and under
  *Found on your network* on the Setup tab's Switches card (**Use** fills in the form, **Don't ask** hides it).
  `security.snmp_discovery` turns the probe off; `wiring.not_managed` lists dismissed addresses.

### Changed
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
