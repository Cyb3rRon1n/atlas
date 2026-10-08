# Atlas posture map + new shell (Phase 1) - design

Date: 2026-10-08. Status: approved in brainstorming, pending spec review.
Mockups: private claude.ai canvas "Atlas Home Layouts" (layout A + C's chat panel).

## Why

Homepage, Netdata, Uptime Kuma and Scrutiny already answer "is it up, how busy is it".
None answer "what talks to the internet, through which door, and should it". Atlas owns
that lane. Phase 1 replaces the web UI front door with a posture page built around a
zone map of inbound, outbound and VPN traffic, and reworks the Homepage tile.

## Roadmap context

| Phase | Scope |
|---|---|
| **1 (this spec)** | New shell + posture map + chat side panel (existing chat backend) + new tile |
| 2 | Chat on Claude API with local Ollama fallback; posture/temps/SMART/log tools |
| 3 | Daily "what changed" digest, deterministic checks, external exposure check |

Out of Phase 1: Claude chat, digest, external scan, DNS-log hostnames, world map.

## Data sources (verified on cyberpac 2026-10-08)

| Source | State | Phase 1 requirement |
|---|---|---|
| Kernel conntrack (netlink; ~330 flows) | byte accounting OFF, `conntrack` CLI absent, no `/proc/net/nf_conntrack` | host: `net.netfilter.nf_conntrack_acct=1` persisted in `/etc/sysctl.d/` (user runs, sudo); image: install `conntrack` package; collector container: `cap_add: NET_ADMIN` |
| Traefik | `--api=true` | read routers + middlewares (API or Docker labels via the existing socket access) |
| gluetun control server `:8000` | role-based auth file | add an Atlas API key/role allowing `GET /v1/publicip/ip` (and VPN status) |
| CrowdSec LAPI | running | `cscli bouncers add atlas` - read-only decisions key |
| cloudflared | no `--metrics` | optional `--metrics 0.0.0.0:<port>`; fallback = container health + recent log errors |
| DNS logs | none (router does DNS) | not in Phase 1 |
| IP -> ASN/country | - | iptoasn.com combined TSV, downloaded weekly, offline lookup |

Home WAN IP for the VPN-leak comparison: fetched by the collector from an IP-echo endpoint
(config `posture.ip_echo_url`, default `https://api.ipify.org`) over the host network, at most
every 10 min; VPN "verified" = gluetun exit IP present and different from it.

## Architecture

New package `atlas/posture/`, three units:

1. **Collectors** (`collectors/`): one module per source, each a pure parse function over
   raw output plus a thin fetch wrapper. Output: plain dataclasses.
   - `conntrack.py`: runs `conntrack -L -o extended` (or `-o xml`), parses proto, src/dst
     ip:port (original + reply tuples), state, bytes/packets.
   - `traefik.py`: routers (rule host, service, entrypoints, middlewares), flags
     `authelia` middleware presence -> route protection (`2fa` / `app-login` / `crowdsec-only`).
   - `gluetun.py`: VPN status + public exit IP.
   - `crowdsec.py`: active decisions (count, last 24 h, values).
   - `asn.py`: loads the iptoasn TSV into a sorted range table; `lookup(ip) -> (asn, org, cc)`.
   - `tunnel.py`: cloudflared health (metrics if enabled, else container state).
2. **Aggregator** (`aggregate.py`), every 30 s:
   - maps container bridge IPs -> container names via the Docker API;
   - classifies each flow: inbound (via tunnel/Traefik), outbound direct, outbound via VPN
     (source = a container in gluetun's network namespace), LAN-internal (ignored on this map);
   - accumulates per (container, dest ASN, dest ip, dest port, proto) per hour bucket bytes;
     conntrack counters are cumulative per connection, so store deltas keyed by the conntrack id;
   - flags **new destination** = (container, ASN) pair never seen before and not in the
     known list.
3. **Posture model** (`model.py`): builds the zone graph (nodes, edges with volume, bands,
   statuses) and the status-strip values from the store; this is what the API serves.

Runs inside the existing `atlas-scan` service (host network) - it gains `cap_add: NET_ADMIN`,
the CrowdSec and gluetun keys via `atlas.yaml`, and the `conntrack` binary in the image.

### Storage (existing SQLite, new tables)

- `posture_flows(hour, container, dest_ip, dest_port, proto, asn, cc, bytes_out, bytes_in, conns)` - 30-day retention.
- `posture_known(container, asn, note, marked_at)` - "Mark as expected" allow-list.
- `posture_seen(container, asn, first_seen, last_seen)` - drives "new".
- `posture_routes(snapshot_at, host, service, protection)` - route snapshots (feeds Phase 3 change detection).
- `posture_status(source, ok, detail, updated_at)` - last result per collector.

### Failure handling

Every collector result carries `ok` + `updated_at`. A failing source never fails the page:
its band/chip shows grey "no data since HH:MM". Collector exceptions are logged once per
state change, not every 30 s.

## Web UI

Stays on the stdlib `http.server` + server-rendered shell + vanilla JS + vendored Cytoscape
(no build step, no new runtime deps). All CSS inline in the app; fonts bundled or system
stack - no runtime fetch from Google Fonts.

- **Navigation:** Posture (home `/`) · Devices (tabs: Devices, Triage, Coverage) · LAN map
  (today's `/map`) · History (History + Trends merged). An "Atlas" button opens the chat
  panel; `/chat` remains as the full-page chat.
- **Status strip:** Ingress, VPN egress, Exposure, Blocked 24 h, New destinations.
  Colour = state (green/grey/orange, differing in lightness too); click highlights the band.
- **Map:** Cytoscape with preset positions computed by the posture model into three bands
  (Inbound, Outbound direct, Outbound via VPN). Destinations grouped by ASN/org (expand on
  click). Edge width = bytes; dashed orange = new/unreviewed. Live / 1 h / 24 h toggle; live
  polls `GET /api/posture` every 30 s. Phone width: map scrolls horizontally, panels stack.
- **Details panel (right):** selected node facts (owner, country, first seen, container,
  traffic, rDNS); buttons "Ask Atlas about this" (opens chat panel prefilled with the node
  context) and "Mark as expected" (`POST /api/posture/known`, same-origin guarded like the
  existing write routes). Below: public exposure list with each route's protection.
- **Chat panel:** slide-out right drawer, docked beside the map on wide screens, overlay on
  narrow ones; conversation persists across pages (session id in `sessionStorage`). Uses the
  existing `/api/chat` + Approve flow unchanged in Phase 1.

### API

- `GET /api/posture?window=live|1h|24h` -> `{status_strip, bands, nodes, edges, exposure, sources}`.
- `GET /api/posture/node/<id>` -> details for the panel.
- `POST /api/posture/known` -> `{container, asn}`; 64 KB cap, same-origin check.
- `GET /api/summary` gains `posture: {state: ok|review, tunnel, vpn, routes, blocked_24h, review_count, message, link}` (existing fields kept for compatibility).

## Homepage tile

Same customapi widget against `/api/summary`. Two states: "All good" with tunnel / VPN /
public routes / blocked-24h; "N to review" with the one-line reason and a link to
`/?node=<id>`. services.yaml change applied on cyberpac with a backup, mirrored to homelab-ops.

## Security

- Auth boundary unchanged: Authelia admin rule in front of atlas.
- New secrets (CrowdSec bouncer key, gluetun key) only in host `atlas.yaml` (600); never rendered or logged.
- `NET_ADMIN` is used only to list conntrack entries; Atlas never writes netfilter state.
- ASN/country lookups are offline; no destination IPs leave the host.

## Testing

- Collector parsers: unit tests over recorded real samples from cyberpac (conntrack
  extended output, Traefik routers JSON, gluetun publicip, CrowdSec decisions, iptoasn rows).
- Aggregator: container-IP mapping, conntrack delta accounting, hour bucketing, VPN
  classification, new-destination flag incl. after Mark-as-expected, retention.
- Model/API: band/node/edge JSON shape, failure greying, summary fields.
- Render: shell, nav, strip, panel markup.
- Real-infra verification on cyberpac (required before calling it done): live conntrack
  flows appear, a real Traefik route shows correct protection, gluetun exit IP differs from
  home IP, a real CrowdSec decision is counted, the tile renders both states.

## Rollout (small PRs, CI green before each merge)

1. Collectors + storage tables.
2. Aggregator + posture model + `/api/posture`.
3. New shell + nav + status strip; old pages folded in.
4. Map + details panel + Mark as expected.
5. Chat side panel.
6. `/api/summary` posture fields + Homepage tile.

Host changes land right before PR 1 is deployed: sysctl (user, sudo), CrowdSec bouncer key,
gluetun key, `NET_ADMIN` + keys in the cyberpac atlas override (backed up, mirrored to homelab-ops).
