# Changelog

All notable changes to atlas. Versions follow [semantic versioning](https://semver.org); the
Docker image is published as `ghcr.io/cyb3rron1n/atlas:<version>` for every release.

## Unreleased

### Added
- **Cable health** on the cabling map: CRC/alignment errors growing between scans, duplex mismatches, ports
  linking slower than before and flapping links, from SNMP and UniFi port counters. Problems turn the port red
  and send an alert (plus one when it clears).
- **LAN watch** (`atlas lan check`, run by atlas-scan): alerts on a DHCP server other than your router or
  `security.dhcp_servers`, on DHCP going silent, and on the gateway's IP answering from a new MAC (ARP spoofing).
  Shown as the LAN tile on the Posture page. The Docker image adds `atlas-dhcp-python`, an interpreter copy
  with only the permission to listen on UDP port 68.

### Changed
- **Asleep containers:** a container that stopped cleanly (exit code 0, e.g. a game room put to sleep by an idle
  timer) or has the label `atlas.on-demand=true` is listed as *Asleep* on the home page, not as a problem;
  `/api/summary` adds `containers_asleep`.
- Posture forgets a container's destinations and "expected" marks after `posture.retention_days` without traffic.

### Added
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
