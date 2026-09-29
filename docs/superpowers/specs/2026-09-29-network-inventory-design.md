# Network inventory, triage, map v2 and web chat - design

Date: 2026-09-29. Status: approved in conversation, ready for an implementation plan.

## Goal

Make atlas an accurate monitor of *what is on the network and how well atlas covers it*:

- Discover every device on the LAN, not just hand-listed hosts.
- Store devices persistently so the admin can rename, tag, annotate, merge and ignore them.
- Show each device once. Today mediabox and media-tools are each drawn twice, once as
  a Proxmox guest and once as a LAN host, because the map is a stateless snapshot.
- Put new, unknown, duplicate and quiet devices in a triage inbox, with a Signal alert for new ones.
- Show coverage honestly: what each source saw, when it last ran, and what has gone quiet.
- Give the web UI (the Homepage tile, behind Authelia) an interactive map and a chat panel
  whose proposed actions run from an Approve button.

Out of scope for v1:
- A raw shell or PTY terminal in the browser. The chat panel is the "terminal".
- MAC vendor lookup (it needs a bundled OUI database).
- Automatic fuzzy merging.
- Any scan outside the configured subnets.

## Architecture

Two containers from the same image share `./data`, which holds `inventory/atlas.db`:

| Container | Network | Runs |
|---|---|---|
| `atlas` | stack network (Traefik + Authelia in front) | `atlas web`: pages, JSON API, chat |
| `atlas-scan` (new) | `network_mode: host` | loops `atlas scan; atlas discover; atlas proxmox scan; atlas map` every `ATLAS_SCAN_MINUTES` (default 15) |

`atlas-scan` replaces the cyberpac cron entries and the `atlas-refresh` compose profile.
SQLite is opened with WAL and `busy_timeout` so both containers can write.

### LAN discovery (`atlas scan`)

1. For each subnet (config `scan.subnets`, or auto-detected from the host's default-route
   interface when empty), TCP connect to port 9 on every address concurrently - the kernel
   ARP-resolves each one whether or not the port is open. No ping, no NET_RAW.
2. Read `/proc/net/arp` (host network, so this is the real LAN neighbour table) for IP to MAC.
3. Reverse DNS for a hostname, best effort.
4. Upsert one `sighting` per MAC, with source `lan`. An IP that answered but has no MAC
   (such as the scanning host itself) is keyed by IP.

No new Python dependency and no new image dependency - the TCP connect uses the stdlib
`socket` module only.

### Data model (new SQLAlchemy models in `atlas/database/models.py`)

`DeviceRecord`:
- `id`
- `name`, `kind` (server / vm / lxc / container-host / workstation / phone / tv / iot / network / other)
- `tags` (JSON list), `notes`
- `important` (bool)
- `state`: `new` / `known` / `ignored`
- `locked_fields` (JSON list: fields the admin set, which automation never overwrites)
- `created_at`, `updated_at`

`SightingRecord`:
- `id`
- `source`: `lan` / `proxmox` / `docker` / `manual`
- `external_id`: the source's own key (MAC, `pve:<vmid>`, container name). Unique together with `source`.
- `ip`, `hostname`, `mac`, `detail` (JSON)
- `first_seen`, `last_seen`
- `device_id`: FK, nullable. Null means an unlinked sighting.

`SourceRunRecord`:
- `source`, `started_at`, `finished_at`, `ok`, `error`, `seen_count`
- Powers the Coverage tab and prevents a failed source from making devices look quiet.

`NotificationRecord`:
- `device_id`, `kind` (`new` / `offline`), `created_at`, `sent_at`
- The alert queue and roll-up.

### Linking rules (`atlas/inventory/linking.py`, pure functions)

These run after every source run. Each rule links only when it is certain:

1. An existing sighting keeps its device, since it is keyed by (source, external_id).
2. A new sighting whose MAC matches another source's sighting joins that device.
3. A Proxmox guest sighting whose IP equals a LAN sighting's IP joins that device, so the
   guest and its LAN presence become one device.
   - Guest IPs come from the Proxmox agent or LXC config when available.
   - Otherwise the guest stays separate and the name match becomes a *suggestion*.
4. Docker containers are not devices. They attach to the device of the host atlas runs on.
5. First run: `map.hosts` entries are imported as `known` devices, each with a `manual`
   sighting (address, role, and name as a locked field).
6. Anything still unlinked creates a `new` device.
   - When a same-name or same-hostname device exists, a merge *suggestion* is recorded
     instead of an automatic merge.

Merge moves the sightings to the target device and deletes the empty source. Split moves
one sighting to a new device. Both publish events, so they appear in History.

### Status

- **seen**: `last_seen` falls within the last successful run of that source.
- **quiet**: not seen in the last 2 *successful* runs of every source that has ever seen it.
  A failed run never counts toward quiet.
- **offline alert**: an `important` device that is quiet.
- **known but invisible**: a `known` device whose only sighting is `manual`.

### Notifications

- Config `notify.signal`: `url` (e.g. `http://signal-cli:8080`), `number`, `recipients`.
  An empty `url` disables alerts.
- A new device or important-offline event queues a `NotificationRecord`.
- At the end of `atlas scan`, queued items are sent:
  - Items for the same kind within 24 hours are rolled into one message.
  - A failed send is logged and retried on the next run.
- The message format follows the operator's Signal style: bold headline, emoji, short lines.

## Web UI

The pages share one tab bar: Overview, **Map**, **Triage**, **Devices**, **Coverage**, **Chat**,
History, Trends. The existing pages stay as they are.

- **Map**
  - Cytoscape.js with a dagre layered layout. Both are **vendored** under
    `atlas/web/static/`, so there is no CDN and the page works offline.
  - Structure: Internet, then the LAN, then devices, with guests and Docker networks as
    compound children inside their host. Templates and ignored devices are hidden
    behind a toggle.
  - Colours: green = seen, amber = quiet, red = important and offline, grey = unknown.
  - Drag, zoom, and collapse a host.
- **Side panel** (opens from any device click):
  - Edit the name, kind, tags, notes and the important flag. An edited field becomes locked.
  - A sightings table with the source and last-seen time.
  - Merge into…, split a sighting out, and ignore.
  - "Ask atlas about this device" opens Chat with the device as context.
- **Triage**
  - New devices, merge suggestions, and quiet devices.
  - One-click buttons: Keep (with a name), Merge into…, Ignore.
- **Devices**: a searchable list filterable by tag and state.
- **Coverage**
  - Per source: the last run, whether it succeeded, the error, and how many devices it saw.
  - Lists of quiet devices and known-but-invisible devices.
- **Chat**
  - `POST /api/chat` runs `AtlasAgent.converse` against a server-side, in-memory session
    (keyed by a random session id cookie, capped history, discarded after 2 hours idle).
  - The page shows "thinking…" while it waits.
  - A reply's plan or action renders as steps, each with an **Approve** button.
- **Approve**
  - `POST /api/actions/execute` takes one `SuggestedAction`.
  - It re-grounds the action against a freshly collected live environment
    (`is_action_grounded`), then calls `execute_action`.
  - It publishes the same events as the CLI, so the action appears in History.
  - It returns the plain result dict.
- **Homepage**: `/api/summary` gains `to_triage` and `devices_quiet` counts.

### JSON API

The web server stays on stdlib `http.server`, which now gains `do_POST`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/devices`, `/api/devices/<id>` | list, detail with sightings |
| PATCH (as POST) | `/api/devices/<id>` | edit fields (locks them) |
| POST | `/api/devices/<id>/merge` `{into}` | merge |
| POST | `/api/sightings/<id>/split` | split |
| GET | `/api/triage`, `/api/coverage`, `/api/graph` | tab data, Cytoscape elements |
| POST | `/api/chat` `{message}` | chat turn |
| POST | `/api/actions/execute` `{action}` | approved action |

### Security

- The whole host sits behind Authelia's admin-only rule. This is unchanged and is the auth boundary.
- Every POST requires a same-origin check:
  - `Origin` (or `Referer`) must match `Host`, or `Sec-Fetch-Site: same-origin`.
  - A request with no such header gets 403.
  - This blocks cross-site requests that ride on the Authelia cookie.
- Request bodies are capped at 64 KB and must be JSON.
- There is no shell. Executable actions are exactly the `ACTIONS` registry, which is re-grounded
  before running.
- The module docstring changes from "no write path by construction" to "writes only
  through these routes".

## Error handling

- A source failure writes a `SourceRunRecord(ok=False, error)` and marks no device quiet.
  Coverage shows the failure.
- An unreachable AI makes chat return an error message. The other tabs are unaffected.
- A signal-cli failure leaves the notification queued, is logged, and retries next run.
- A grounding failure on Approve returns 409 "target no longer exists / state changed".
  Nothing runs.

## Testing

- Unit tests:
  - Linking: MAC join, Proxmox IP join, name to suggestion never auto-merged, locked fields
    survive re-scans, `map.hosts` import.
  - Merge, split and status: quiet over 2 successful runs, failed runs ignored, important
    goes offline.
  - Notification roll-up and retry.
  - `/proc/net/arp` parsing.
  - Subnet auto-detection.
- Web tests:
  - Every GET and POST route.
  - Same-origin 403.
  - The body cap.
  - Execute re-grounding, with 409 when a target is gone.
- CI keeps to shape assertions, not machine state (per the uptime-test lesson).
- **Real-infra verification on cyberpac before calling it done:**
  - The scan finds the real LAN.
  - mediabox appears once.
  - A test Signal alert arrives.
  - An approved restart of a harmless container runs and appears in History.

## Delivery (one atlas PR each, CI green before merge)

1. Inventory core and scanner: models, `atlas scan`, linking, status, notifications,
   `atlas devices` CLI list, and the `atlas-scan` compose service.
2. The web write API, plus the Triage, Devices and Coverage tabs.
3. Map v2 (vendored Cytoscape and dagre) and the side panel.
4. The Chat tab and Approve.
5. vulcan PR (the `atlas-scan` service and `notify` settings), then the cyberpac switchover:
   drop the cron jobs, configure Signal, verify.
