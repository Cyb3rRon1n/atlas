# Atlas cabling map (port-level wired topology) - design

Date: 2026-11-14. Status: approved in brainstorming, pending spec review.

## Why

The existing /map is device-level: it knows *what* is on the LAN and roughly what hangs
off what (operator-set `uplink_id`), but not *which port*. An operator re-cabling a rack
wants "what is in gi14", "which patch-panel port goes to the office jack" and "what moved
since last week" without walking to the rack. No common self-hosted tool auto-draws a
port-level view that includes patch panels: NetBox traces cables but is hand-entered;
LibreNMS/UniFi discover but draw device bubbles; Netdisco has port tables but no drawing.

This is also a step toward atlas's goal: once deployed, it discovers and maps the
network by itself and becomes the network's monitor and security watch.

## Scope

In: a one-shot collector (CLI + web Refresh button), SNMP and optional UniFi sources,
an operator-kept patch-panel file, stored snapshots with a diff, a new Cabling page
(diagram, faceplate, patch table, exports).

Out (later): continuous polling or alerts on link changes, write access to any network
gear, VLAN/STP views, wireless topology, public docs/screenshots (after it runs on the
first real network).

## Privacy rule (repo)

Nothing site-specific is committed: no real IPs, hostnames, MACs, port maps, SNMP or
UniFi credentials, or `cabling.yaml` contents. Tests and docs use RFC 5737 addresses
(192.0.2.0/24), example names (`gateway`, `core-switch`, `nas`) and locally made-up MACs.
Recorded SNMP/UniFi fixtures are rewritten to example data before they enter `tests/`.

## Data sources

| Source | How | Gives |
|---|---|---|
| SNMP (any managed switch) | shell to net-snmp `snmpbulkwalk` (no new Python dep; image gains the `snmp` apt package) | IF-MIB `ifName`/`ifAlias`/`ifOperStatus`/`ifHighSpeed`; LLDP-MIB `lldpLocPortTable` + `lldpRemTable`; BRIDGE-MIB `dot1dBasePortIfIndex`; Q-BRIDGE-MIB `dot1qTpFdbPort` (fallback BRIDGE-MIB `dot1dTpFdbPort`) |
| SNMP LLDP fallback | if `lldpRemTable` is empty, walk CISCOSB-LLDP-MIB (Cisco Sx300/Sx350) | neighbours on switches that don't fill the standard table |
| UniFi (optional adapter) | local read-only account; `POST /api/auth/login`, `GET /proxy/network/api/s/<site>/stat/device` | per UniFi device: `port_table` (speed, up, `is_uplink`, nested `lldp_table`), `last_uplink` |
| atlas inventory | existing `InventoryStore.devices()` sightings | MAC -> device name/kind/IP |

SNMP is v3 authPriv only. v2c is refused - read communities travel in clear text.
Auth SHA; privacy AES by default, `priv: des` allowed per switch because older gear (Cisco
Sx300) only offers DES - atlas shows a "weak privacy" note for those, it doesn't refuse them. UniFi field names vary by firmware: the adapter reads them defensively and logs
missing fields once, never crashes.

First implementation step (spike): `snmpbulkwalk` the real switch to confirm which LLDP
table answers and how it encodes port IDs (number, ifName or MAC subtype).

## Config

`atlas.yaml`:

```yaml
wiring:
  enabled: false
  timeout: 10            # seconds per source
  keep_snapshots: 30
  switches:
    - name: core-switch
      host: 192.0.2.2
      snmp_user: atlas
      priv: aes             # aes | des (older switches)
      # auth/priv passwords come from env: ATLAS_SNMP_<NAME>_AUTH / _PRIV
  unifi:
    enabled: false
    url: https://192.0.2.1
    site: default
    # username/password from env: ATLAS_UNIFI_USER / ATLAS_UNIFI_PASS
  cabling_file: cabling.yaml   # relative to the config dir
```

Secrets only come from env (the atlas env file), never from YAML, never logged, never
stored in a snapshot.

`cabling.yaml` (operator-kept; the repo ships only `cabling.example.yaml`):

```yaml
panels:
  - name: PP1
    ports:
      1: {switch: core-switch, port: gi1, label: "Office A", color: blue}
      2: {switch: core-switch, port: gi2, label: "Rack - nas"}
```

## Building the link list

1. Switch-switch: LLDP from both ends, matched on chassis MAC. One edge per physical
   link, ends `(device, port)`; UniFi `last_uplink`/`lldp_table` fill links SNMP can't see.
2. Uplink ports: a port with an LLDP neighbour that is a known switch/gateway/AP, or
   more than 3 learned MACs. Host placement ignores uplink ports.
3. Host-port: each MAC learned on a non-uplink port. Matched to an inventory device by
   sighting MAC; no match -> an `unknown` node labelled with the MAC vendor prefix if known.
   A MAC learned on several access ports at once (rare: moved mid-walk) takes the most
   recent walk's port.
4. Speed/state from `ifHighSpeed`/`ifOperStatus` of the switch-side port.
5. Patch: each panel port is inserted as a hop between the switch port and the device.
   A mismatch (panel says gi7, discovery puts the device on gi9) is kept as a warning,
   discovery wins for drawing.
6. Wireless: clients seen only through an AP are dropped (the existing `effective_connection`
   rules still apply). APs with a cable uplink are drawn.

Pure function: `build_wiring(walks, unifi, inventory, cabling) -> Snapshot` - no I/O,
unit-tested on example fixtures.

## Snapshots

New table `wiring_snapshots(id, taken_at, data JSON, errors JSON)`, created idempotently at
startup like the other atlas tables; pruned to `keep_snapshots`. `diff(prev, cur)` lists:
link moved (device on a different port), link added/removed, speed change, port down.
A source that fails keeps its part of the previous snapshot, marked stale with the error.

## Triggers

- CLI: `atlas wiring scan [--json]` (cron-friendly exit codes, like `atlas doctor`).
- Web: `POST /api/wiring/refresh`, behind the existing origin gate for /api POSTs. One scan
  at a time (a lock; a second click returns "already running"). Runs in the atlas-scan
  container, which already does LAN scans.

## The Cabling page (/cabling)

- Header: "Refreshed 12 min ago" + Refresh button + source status chips (green/stale/error).
- Diagram: ELK.js layered layout (vendored, hash-pinned like Cytoscape), drawn as SVG.
  Gateway -> core -> access -> hosts. Switch nodes carry real ports (FIXED_ORDER, port
  side south for downlinks). Edge label: `gi14 ⇄ eth0 · 1G`; colour by speed (100M/1G/2.5G/10G);
  down = dashed; patch hop shown as a small `PP1-07` tag on the edge.
- Click a switch: faceplate grid (port number, lit if up, colour by speed, tooltip with the
  device and patch label).
- Tabs: Diagram / Patch table (panel port, label, switch port, device, speed, status,
  warning; filterable) / Changes (diff list).
- Export: SVG of the diagram, CSV of the patch table.
- Rendering rules from the existing pages: no data in `innerHTML`; build DOM/SVG nodes.

## Errors

- Each source is independent: timeout, auth failure or parse failure -> a chip with the
  error, last good data kept as stale.
- `snmpbulkwalk` missing -> a clear "install net-snmp" message (bare-metal installs).
- Bad `cabling.yaml` -> the page still renders discovery; the YAML error is shown with the
  line number.

## Testing

- Unit: SNMP walk parser, UniFi parser, `build_wiring`, `diff`, cabling validation - on
  example fixtures.
- Web: route tests for /cabling and the refresh POST (origin gate, lock).
- Real: run against the operator's switch and gateway (project rule: mocked green is not
  enough). Recorded output stays outside the repo.
