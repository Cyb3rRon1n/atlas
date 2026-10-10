# Atlas UI shell redesign - design

Approved in chat 2026-10-10. Follows the posture-map spec (2026-10-08); same stack: stdlib `http.server`,
server-rendered HTML, vanilla JS, no new dependencies.

## Problem
The home page (`/`) is the posture page itself (status strip + map + three stacked side lists), and chat is a
pop-out drawer. It reads as cluttered: no summary view, details everywhere.

## Layout
- Every page: top nav + main content + **docked chat column** on the right (~380px).
- Chat collapses to a thin rail (button in the panel head and the topbar "Atlas" button); choice is remembered
  in `localStorage` (`atlasChatCollapsed`). Under 900px wide the panel is hidden behind a floating button and
  opens full-screen.
- Collapsing/expanding fires a window `resize` so the Cytoscape maps refit.
- `/chat` stays as the full-page chat (no docked panel there).

## Navigation
`Home /` · `Posture /posture` · `Hosts /overview` (tabs: Overview, Trends) · `Devices /devices` ·
`LAN map /map` · `History /history` (events only; Trends moves to Hosts).

## Home (`/`, new)
Server-rendered, no JS needed:
- **Verdict line** at the top: "All good" or "N things need attention" (count of cards not ok).
- **Security posture card** -> /posture: state + message from `_posture_block`, VPN, public routes, CrowdSec
  bans, review count.
- **Hosts health card** -> /overview: one row per host.
  - cyberpac (the host Atlas runs on): CPU/RAM/disk % read live with psutil; containers running/total and
    unhealthy from the latest topology.
  - Proxmox nodes (cyberbox): status, CPU/RAM/disk % from the latest `atlas.proxmox.scan.completed` event;
    guests running/total (templates excluded). `discover_nodes` now keeps the node's cpu/mem/maxmem/disk/maxdisk
    /uptime fields from the Proxmox `/nodes` list.
  - Unreachable LAN hosts from the topology are listed as a warning.
- **Recent activity card** -> /history: last 8 events (time, type, source).
Each data source failing renders a muted "unavailable" line in its card, never a 500.

## Posture page (`/posture`)
Same map. The right-hand stack (Details / Public exposure / Needs review) becomes one card with three small tabs;
clicking a map node switches to Details. `_posture_block`'s link becomes `/posture`.

## Out of scope
ZFS pool health (Proxmox scan doesn't collect it), media-array disk usage (not mounted into the container).

## Testing
Unit tests for the home renderer (all cards, failure fallbacks, verdict count), nav/route changes, docked-chat
markup, `discover_nodes` fields; then a real run on cyberpac checked in the browser.
