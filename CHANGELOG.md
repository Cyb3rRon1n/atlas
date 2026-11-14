# Changelog

All notable changes to atlas. Versions follow [semantic versioning](https://semver.org); the
Docker image is published as `ghcr.io/cyb3rron1n/atlas:<version>` for every release.

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
