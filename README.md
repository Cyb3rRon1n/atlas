<p align="center">
  <img src="docs/images/social-preview.svg" alt="Atlas - AI-powered operations platform for self-hosted infrastructure" width="100%">
</p>

<p align="center">
  <a href="https://github.com/Cyb3rRon1n/atlas/actions/workflows/ci.yml"><img src="https://github.com/Cyb3rRon1n/atlas/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+">
</p>

<p align="center">
  📖 <a href="https://cyb3rron1n.github.io/atlas/">Documentation</a> · <a href="https://cyb3rron1n.github.io/atlas/getting-started/">Getting Started</a> · <a href="https://cyb3rron1n.github.io/atlas/roadmap/">Roadmap</a> · <a href="https://cyb3rron1n.github.io/atlas/architecture/">Architecture</a> · <a href="https://cyb3rron1n.github.io/">Sibling Projects</a> · <a href="docs/images/favicon.svg">Favicon</a>
</p>

# Atlas

**Know what's running on your infrastructure, why, and what changed — before you have to go find out the hard way.**

Atlas is a CLI built for people running real infrastructure at home — Proxmox clusters, Docker containers, and the self-hosted services on top of them — who are tired of learning something broke by noticing it's down. Run it locally, alongside whatever you're managing, whenever you want a read on things: it discovers what's actually there, remembers what changed since last time, and can explain either in plain language, via Claude or a fully local Ollama model. Nothing it tells you is guessed — every AI-suggested action is checked against what Atlas actually observed first.

When it comes to acting — restarting a container, resizing its limits, restarting a Proxmox guest — Atlas always asks first. No daemon, no autonomous mode, no bypass flag.

Everything above is real and working today. See [Project Status](#project-status) for what's shipped and verified against real infrastructure, not mocks.

---

## Why run Atlas alongside your stack

A homelab media/server stack (Jellyfin, the *arr apps, a VPN'd torrent client, a reverse proxy, a Proxmox box or two) has dozens of moving parts and no single place that knows how they fit together. Atlas is that place:

- **One page that shows everything** — the [network map](#network-map) draws every machine on your LAN, the containers on this host grouped by Docker network (with their public hostnames), your Proxmox guests, and what's up or down — and states plainly what Atlas is allowed to act on.
- **Answers from evidence, not guesses** — `atlas chat` pulls live state mid-conversation: container status and logs (including searching a log for *when* a problem started), Proxmox guests, host health and reboots, reachability of any host/port, and Jellyfin playback (direct play vs remux vs transcode, plugins, play history).
- **It learns your setup** — point it at your own notes (runbooks, scripts, a folder of solved incidents) and every question automatically comes with the most relevant ones, so "we've seen this before" answers come with the fix that worked last time. Tested on a real case: it diagnosed a Jellyfin plugin silently killing 4K remuxes from the logs plus the incident note.
- **Private and offline-capable** — run the brain on a local Ollama model (a spare GPU laptop is plenty); nothing leaves your network. Claude is optional for heavier analysis.
- **Safe by construction** — it observes freely but never changes anything on its own: restarts/stops/resizes are only ever *proposed*, and each step asks you first. The web view has no write path at all.
- **Cheap to keep** — one small container, no daemon, no database server; refreshes are a host cron line.

---

## Project Status

Atlas has a working CLI covering discovery, Docker and Proxmox integration, AI-assisted analysis, and approval-gated automation — and it's been verified against real infrastructure, not just tests. See the [Roadmap](https://cyb3rron1n.github.io/atlas/roadmap/) for the full, detailed history, including real bugs found and fixed along the way.

### Shipped and verified against real infrastructure

- ✅ Hardware, OS, storage, and network discovery
- ✅ Docker discovery, service detection, and Compose analysis
- ✅ Docker container restart, stop, and resize (CPU/memory limits) — approval-gated actions backed by a real `atlas/actions/` registry
- ✅ Container resource-allocation visibility — per-container CPU/memory usage relative to its own configured limit, not just relative to the host
- ✅ Proxmox cluster discovery, change detection, and guest restart/stop/resize (CPU/memory limits) — the same three actions Docker containers have
- ✅ AI analysis via a local Ollama model end to end; Anthropic Claude also supported (connection and error handling verified, a full response is pending your own billing setup)
- ✅ Agent-based capabilities — both providers can call read-only tools mid-request for live state; `atlas analyze` uses this by default, and it powers the new `atlas chat` command
- ✅ Multi-step action plans — an ordered sequence of approval-gated actions for genuinely dependent steps (e.g. stop one container, then restart another), which Atlas can run for you step by step, each with its own confirmation
- ✅ Persisted `atlas chat` transcripts — a session's conversation saves as one event on exit, visible via `atlas history`
- ✅ `get_container_logs` tool — lets both AI providers pull recent log lines for a specific container instead of reasoning from status alone
- ✅ Prometheus monitoring — host and per-container (cAdvisor) metrics, configurable threshold alerting, and change detection between scans
- ✅ Resource-usage trending (`atlas trends`) — latest/min/max/avg over time for host, per-container, and per-Proxmox-guest metrics, built from the history `atlas monitor`/`atlas proxmox scan` already save
- ✅ Guided setup (`atlas init`) and environment/integration health checks (`atlas doctor`)
- ✅ `--json` output and cron-friendly exit codes on `atlas doctor`/`atlas monitor`/`atlas trends` — wire either health check into your own cron job or systemd timer without Atlas becoming a daemon
- ✅ Event-driven architecture with persistent operational history
- ✅ Plugin architecture — a Docker plugin and a libvirt/KVM plugin (guest discovery, plus approval-gated `atlas libvirt restart`/`stop`/`resize`), proving the plugin system generalizes beyond one implementation
- ✅ Read-only web view (`atlas web`) — overview, history, and trends over the same data the CLI already reads, no new write path
- ✅ Multi-node fleet view (`atlas fleet doctor`/`trends`/`report`) — SSHes into each configured node and runs the matching `--json` command there, no daemon or central server
- ✅ Network map (`atlas map` + web `/map`) — machines on the LAN, containers by network with public hostnames, Proxmox guests (templates greyed), the AI endpoint, and what Atlas may act on
- ✅ Investigation tools for chat — full-log search over a time window, host health (boot time, temps, status feeds such as a RAID watchdog), TCP reachability checks, Jellyfin sessions/activity/plugins
- ✅ Operator knowledge — searches your own notes; pinned facts plus the best-matching notes (solved incidents ranked first) are attached to every chat question, so a small local model uses them reliably

### Next

Nothing currently in progress, but a real, non-empty backlog exists — see the [Roadmap](https://cyb3rron1n.github.io/atlas/roadmap/#next)'s own checklist for exactly what's queued (remote fleet actions, and a fully successful Anthropic response pending your own billing setup) versus deliberately out of scope (no daemon, no push notifications, no unattended automation).

---

## Requirements & Platform Support

Atlas itself needs very little. Everything past the base install is an optional integration, independently gated by config, and `atlas doctor` will tell you exactly what's configured versus missing.

**To run Atlas at all:** Linux, Python 3.11+, and pip. That's enough for `atlas discover`, `atlas report`, `atlas docker`, `atlas services`, `atlas compose`, and `atlas doctor` — no config file, no external services.

**Optional — only needed for the specific integration it backs:**

| Integration | Enables | What it actually needs |
|---|---|---|
| Docker | Container discovery, `atlas restart`/`stop`/`resize`, cAdvisor container metrics | A Docker daemon reachable from wherever Atlas runs — the local socket by default, or `DOCKER_HOST` for a remote one |
| Proxmox VE | `atlas proxmox scan`/`restart` | A reachable Proxmox host and an API token — a network call over HTTPS, nothing installed on the Proxmox host itself. See [Deployment](https://cyb3rron1n.github.io/atlas/deployment/) for the recommended (not required) topology |
| libvirt/KVM | Guest discovery via `atlas discover`, `atlas libvirt restart`/`stop`/`resize` | The `virsh` CLI on the host Atlas runs on — no separate daemon config, unlike Docker/Proxmox |
| Anthropic **or** Ollama | `atlas analyze`, `atlas chat` | An `ANTHROPIC_API_KEY`, or a locally-reachable Ollama instance — only one is needed |
| Prometheus | `atlas monitor` | An existing Prometheus, [`node_exporter`](https://github.com/prometheus/node_exporter) for host metrics, and [cAdvisor](https://github.com/google/cadvisor) if you also want per-container metrics |

None of the above is required to get started — see [Quick Start](#quick-start).

**Platform support** — "verified" means run against real infrastructure, not just unit-tested against mocks (see the [Roadmap](https://cyb3rron1n.github.io/atlas/roadmap/) for what each verification covered):

| Platform | Status |
|---|---|
| Ubuntu | ✅ verified — CI runs the full test suite on real `ubuntu-latest` GitHub Actions runners (Python 3.11/3.12) |
| Fedora | ✅ verified — this project's actual development environment throughout, including every real-infrastructure check in this doc (Docker actions, Proxmox, Prometheus/cAdvisor, Ollama), plus a `btrfs`-rooted filesystem discovery correctly handles that Ubuntu's ext4-default setup never exercised |
| Other Linux distros (Debian, Arch, RHEL, ...) | best-effort — no distro-specific code, but not independently run |
| macOS / Windows | out of scope — `pyproject.toml` classifies POSIX/Linux only |

| Integration | Status |
|---|---|
| Docker | ✅ verified against real containers |
| Proxmox VE | ✅ verified against a real Proxmox VE host |
| Ollama | ✅ verified against a real local `llama3.1` |
| Anthropic | ◐ partially verified — auth and error handling confirmed; a full response is pending the maintainer's own billing setup |
| Prometheus + node_exporter + cAdvisor | ✅ verified against real infrastructure |

---

## Quick Start

Clone the repository and set up a virtual environment:

```bash
git clone https://github.com/Cyb3rRon1n/atlas.git
cd atlas

python -m venv .venv
source .venv/bin/activate

pip install -e .
atlas version
```

Generate `atlas.yaml` interactively (optional — Atlas runs on safe defaults without one):

```bash
atlas init
```

Run a first discovery pass and inspect the results:

```bash
atlas discover   # inventories the host and saves it to inventory/generated/
atlas report     # generates a report from the latest inventory
atlas analyze    # sends the latest snapshot to an AI provider for a summary + recommendations
atlas chat       # ask Atlas about your infrastructure directly - no atlas discover needed first
```

### Run `atlas web` as a Docker stack

Atlas is deliberately not a daemon — no scheduled mode, no automation the
tool decided to run for you. This container doesn't change that: it runs
`atlas web` (the existing read-only dashboard) as a long-running process;
refreshing data is still a command you run yourself.

```bash
cp atlas.yaml.example atlas.yaml   # edit: Proxmox/Prometheus/AI config
docker compose up -d               # pulls ghcr.io/cyb3rron1n/atlas (or builds it); dashboard on :8420
docker compose exec atlas atlas discover
```

The image is published to **`ghcr.io/cyb3rron1n/atlas`** (linux/amd64 + arm64): `latest` tracks
`main`, `sha-<commit>` pins a build, and release tags publish `X.Y.Z` / `X.Y`. Set
`ATLAS_TAG` to pin one.

Want it kept fresh without typing that by hand every time? Either add a **host** cron entry —
e.g. `*/30 * * * * docker exec atlas atlas map` — or start the optional **`atlas-refresh`**
container: `docker compose --profile refresh up -d`. It's the same image running nothing but a
visible loop of `atlas discover`, `atlas proxmox scan` and `atlas map` every
`ATLAS_REFRESH_MINUTES` (default 30) - your scheduler, your call, not a daemon inside Atlas.

Values in `atlas.yaml` can reference the environment - `${NAME}` or `${NAME:-default}` - so
secrets (a Jellyfin API key, a Proxmox token) can live in your stack's `.env` instead.

`docker-compose.yml` mounts `/var/run/docker.sock` for the Docker
plugin/actions by default — comment that out if you don't need
container-level insight; mounting it at all is root-equivalent host access
regardless of any read-only mount flag.

### Add Atlas as a Homepage tile

If you run [Homepage](https://gethomepage.dev) (or any dashboard), give Atlas a tile so the map and dashboard are one click away. Put Atlas behind your reverse proxy instead of publishing port 8420 — e.g. with Traefik + Authelia, a `docker-compose.override.yml` next to Atlas's own:

```yaml
services:
  atlas:
    ports: !reset []                 # no host port; Traefik reaches it on the shared network
    networks: [proxy]                # your Traefik network
    labels:
      - traefik.enable=true
      - traefik.http.routers.atlas.rule=Host(`atlas.example.com`)
      - traefik.http.routers.atlas.entrypoints=websecure
      - traefik.http.routers.atlas.tls=true
      - traefik.http.routers.atlas.middlewares=authelia@docker   # admins only
      - traefik.http.services.atlas.loadbalancer.server.port=8420
networks:
  proxy:
    external: true
```

Then the tile, in Homepage's `services.yaml` - with live counts from Atlas's `/api/summary`
(a small read-only JSON view of the latest network map):

```yaml
- Infrastructure:
  - Atlas:
      href: https://atlas.example.com/map
      icon: mdi-radar
      description: Network map, inventory, history - chat via `atlas chat`
      siteMonitor: http://atlas:8420
      widget:
        type: customapi
        url: http://atlas:8420/api/summary
        refreshInterval: 60000
        mappings:
          - field: status
            label: Status
          - field: containers_running
            label: Containers up
          - field: hosts_up
            label: Hosts up
          - field: guests_running
            label: Guests up
```

`/api/summary` returns `status` (`ok` / `degraded` when a map host is down or a container is
unhealthy), `containers_running`/`_total`/`_unhealthy`, `guests_running`/`_total`,
`hosts_up`/`_total`/`_down`, `ai_reachable` and `generated_at`.

Keep what the tile shows current with the `atlas-refresh` container (`--profile refresh`) or one
host cron line:

```cron
*/30 * * * * docker exec atlas atlas discover >/dev/null 2>&1; docker exec atlas atlas proxmox scan >/dev/null 2>&1; docker exec atlas atlas map >/dev/null 2>&1
```

Chat lives in the terminal: `docker exec -it atlas atlas chat` (a one-line `atlas-chat` wrapper script on the host makes it easy to reach from an SSH/Guacamole session). If you use Authelia, make sure admin-only rules end with a `deny` rule for the same domains — a rule whose `subject` doesn't match falls through to the default policy.

---

## Screenshots

Representative output, not a literal capture — field names and formatting match real commands; hostnames, containers, and figures are illustrative.

<p align="center">
  <img src="docs/images/network-map.png" alt="atlas web network map" width="820"><br>
  <sub><code>atlas web</code> <code>/map</code> — every machine on the LAN, this host's containers by network, Proxmox guests (templates grey), the AI endpoint</sub>
</p>

<p align="center">
  <img src="docs/images/screenshots/doctor.svg" alt="atlas doctor example output" width="820"><br>
  <sub><code>atlas doctor</code> — environment health plus integration readiness</sub>
</p>

<p align="center">
  <img src="docs/images/screenshots/proxmox-scan.svg" alt="atlas proxmox scan example output" width="820"><br>
  <sub><code>atlas proxmox scan</code> — cluster inventory and change detection since the last scan</sub>
</p>

<p align="center">
  <img src="docs/images/screenshots/analyze.svg" alt="atlas analyze example output" width="820"><br>
  <sub><code>atlas analyze</code> — AI summary with a grounded, approval-gated action suggestion</sub>
</p>

<p align="center">
  <img src="docs/images/screenshots/chat.svg" alt="atlas chat example output" width="820"><br>
  <sub><code>atlas chat</code> — a live conversation, grounded the same way as <code>atlas analyze</code></sub>
</p>

More examples (monitoring, resource-usage trends, multi-step plans) are on the [docs site](https://cyb3rron1n.github.io/atlas/).

---

## CLI Reference

| Command | Description |
|---|---|
| `atlas version` | Display the Atlas version. |
| `atlas status` | Display current Atlas status. |
| `atlas doctor` | Run Atlas health checks, including live reachability of configured Proxmox/AI/Prometheus integrations and detection of other virtualization/orchestration backends (libvirt/KVM, Kubernetes). `--json` for machine-readable output; exits 1 if anything's unhealthy. |
| `atlas init` | Interactively generate `atlas.yaml`, logging the session to `logs/`. |
| `atlas config` | Display the active Atlas configuration. |
| `atlas discover` | Discover infrastructure information (including registered plugins) and generate inventory. |
| `atlas report` | Generate an infrastructure report from the latest inventory. `--json` prints the inventory dict instead of writing a Markdown file. |
| `atlas docker` | Display Docker container status. |
| `atlas restart <name>` | Restart a Docker container. `--node <fleet-node>` to act on a fleet node instead of locally. Prompts for confirmation before acting. |
| `atlas stop <name>` | Stop a Docker container without removing it. `--node <fleet-node>` supported. Prompts for confirmation before acting. |
| `atlas resize <name>` | Resize a Docker container's CPU (`--cpus`) and/or memory (`--memory`) limit, live, without a restart. `--node <fleet-node>` supported. Prompts for confirmation before acting. |
| `atlas services` | Detect known self-hosted services running in Docker. |
| `atlas compose` | Analyze a Docker Compose file. |
| `atlas proxmox scan` | Scan Proxmox infrastructure and report changes since the last scan (requires `proxmox.enabled: true`). |
| `atlas proxmox restart <vmid>` | Restart a Proxmox VM or LXC guest. Prompts for confirmation before acting. |
| `atlas proxmox stop <vmid>` | Shut down a Proxmox VM or LXC guest (ACPI request). Prompts for confirmation before acting. |
| `atlas proxmox resize <vmid>` | Resize a Proxmox guest's CPU (`--cpus`) and/or memory (`--memory`) limit. Prompts for confirmation before acting. |
| `atlas libvirt restart <name>` | Restart a libvirt/KVM guest (ACPI request via `virsh reboot`). `--node <fleet-node>` to act on a fleet node instead of locally. Prompts for confirmation before acting. |
| `atlas libvirt stop <name>` | Stop a libvirt/KVM guest (ACPI request via `virsh shutdown`). `--node <fleet-node>` supported. Prompts for confirmation before acting. |
| `atlas libvirt resize <name>` | Resize a libvirt/KVM guest's vCPU count (`--vcpus`) and/or memory (`--memory`, e.g. `512MiB`). Applies at next boot only. `--node <fleet-node>` supported. Prompts for confirmation before acting. |
| `atlas monitor` | Query Prometheus for host metrics and flag any at or above their configured threshold (requires `monitoring.enabled: true`). `--json` for machine-readable output; exits 1 if anything's exceeded or Prometheus is unreachable. |
| `atlas trends` | Show host, per-container, and per-Proxmox-guest resource-usage trends from saved `atlas monitor`/`atlas proxmox scan` snapshots. `--json` for machine-readable output. |
| `atlas plugins` | Display registered Atlas plugins. |
| `atlas history` | Display recorded operational events. |
| `atlas intelligence` | Display the latest stored environment context. |
| `atlas analyze` | Analyze the latest environment snapshot with AI (using live tool calls for current state) and print a summary plus recommendations. `--json` prints the result as JSON instead (never auto-runs a suggested plan); exits 1 on a provider error. |
| `atlas chat` | Interactive multi-turn chat with Atlas about your infrastructure — no prior `atlas discover` required. Type `exit` to quit. |
| `atlas web` | Serve a local, read-only web view (overview/history/trends/network map, plus `/api/summary` JSON for dashboard widgets) over the same data `atlas report`/`atlas history`/`atlas trends` already read. `--host`/`--port` (defaults `127.0.0.1:8420`). No write path. |
| `atlas fleet doctor` | SSH into every node under `fleet.nodes` in `atlas.yaml` and run `atlas doctor --json` there, aggregating results. `--json` for machine-readable output; exits 1 if any node is unreachable or unhealthy. |
| `atlas fleet trends` | SSH into every fleet node and run `atlas trends --json` there, aggregating results. `--json` for machine-readable output; exits 1 if any node is unreachable (no fleet-wide health concept, same as `atlas trends`). |
| `atlas fleet report` | SSH into every fleet node and run `atlas report --json` there, aggregating results. `--json` for machine-readable output; exits 1 if any node is unreachable (no fleet-wide health concept, same as `atlas report`). |
| `atlas map` | Build the network map: this host's containers by Docker network (with Traefik public hostnames), Proxmox guests, configured LAN hosts' reachability, the AI endpoint, and what Atlas may act on. Saved for `atlas web`'s `/map`; `--json` prints it. |
| `atlas runtime` | Display Atlas runtime information. |

Run `atlas <command> --help` for command-specific options.

---

## Features

**Guided Setup** — `atlas init` walks you through only what actually varies per deployment (name, Proxmox, AI provider, Prometheus), shows a full review screen before writing anything, and logs the session (secrets redacted) to `logs/`. `ANTHROPIC_API_KEY` is never prompted for or written to disk.

**Health Checks** — `atlas doctor` checks your environment (Python, memory, storage, Docker, other virtualization/orchestration backends detected on the host) and each optional integration you've configured — Proxmox, your AI provider, Prometheus are checked for real reachability, not just presence, each bounded by a short timeout so a dead endpoint can't hang the run.

**Infrastructure Discovery** — `atlas discover` inventories the host — OS, hardware, storage, network — and saves it for reporting, analysis, and change detection.

**Docker Integration** — `atlas docker` inspects containers; `atlas services` recognizes known self-hosted services running in them (Plex, Sonarr, and more — see the [Service Catalog](https://cyb3rron1n.github.io/atlas/service-catalog/)). Atlas can also act: `atlas restart`/`stop`/`resize <name>`, always after showing current state and asking for confirmation.

**Docker Compose Analysis** — `atlas compose` parses a Compose file to surface its services, images, ports, and volumes.

**Proxmox Integration** — `atlas proxmox scan` inventories a cluster (nodes, VMs, containers) and reports what changed since the last scan. Atlas can also act: `atlas proxmox restart`/`stop`/`resize <vmid>` — the same three actions Docker containers have, always after showing current state and asking for confirmation. Token-based auth is recommended — see [Configuration](#configuration).

**libvirt/KVM Integration** — for hosts running plain libvirt/KVM instead of (or alongside) Proxmox: guest discovery rides `atlas discover` via a plugin (`atlas plugins` lists it). Atlas can also act: `atlas libvirt restart`/`stop`/`resize <name>`, always after showing current state and asking for confirmation — resize is CLI-only (not AI-suggestable) since libvirt's vCPU count is a different concept from Docker/Proxmox's fractional CPU limit. Just needs `virsh` on the host Atlas runs on — no separate config section.

**Monitoring** — `atlas monitor` queries an existing Prometheus for host and per-container metrics (via `node_exporter`/cAdvisor), flags anything over a configurable threshold, and reports what changed since the last scan. `atlas trends` shows how those metrics moved over time — host, per-container, and per-Proxmox-guest — built entirely from history `atlas monitor`/`atlas proxmox scan` already save, no new collection or storage. Disabled by default.

**Plugin Architecture** — new discovery/integration capabilities register through a plugin system (`atlas plugins`) without touching the core.

**Operational Memory** — every meaningful action publishes an event onto an internal bus and is persisted automatically — `atlas history` shows the full record: discoveries, scans, restarts, chat sessions, and more.

**Read-Only Web View** — `atlas web` serves a local overview/history/trends dashboard over the exact same reads `atlas report`/`atlas history`/`atlas trends` already do — no new write path, no automation. Runs in the foreground until `Ctrl+C`, same on-demand shape as every other Atlas command.

**Fleet View** — `atlas fleet doctor`/`trends`/`report` run `atlas doctor`/`trends`/`report` over SSH on every node listed under `fleet.nodes` in `atlas.yaml` and aggregate the results into one view — no daemon, no central server, no new dependency (shells out to `ssh`). Just needs each node reachable over SSH with Atlas already installed there.

**Remote Fleet Actions** — add `--node <name>` to `atlas restart`/`stop`/`resize` or `atlas libvirt restart`/`stop`/`resize` to act on a fleet node's Docker/libvirt instead of the local one. Same confirmation prompt as always, just retargeted — no bypass flag, no unattended remote execution. Docker's remote path uses docker-py's `ssh://` transport (requires the `paramiko` dependency); libvirt uses its own native `qemu+ssh://` transport (no new dependency). Proxmox needs nothing extra — its API already reaches any guest in the configured cluster.

**AI Analysis Engine** — `atlas analyze` sends your latest environment snapshot to Claude or a local Ollama model and gets back a plain-language summary plus concrete recommendations. See [Configuration](#configuration) for provider setup.

<a id="network-map"></a>**Network Map** — `atlas map` collects what Atlas can see into one snapshot and `atlas web` draws it at `/map`: Internet → LAN → one box per machine, with this host's container networks and each Proxmox host's guests underneath, green/red/grey for up/down/not-applicable, plus detail tables and a plain "what Atlas is responsible for" list.

**Operator Knowledge** — `knowledge.notes_paths` points Atlas at your own Markdown/scripts (a docs repo, runbooks, an `incidents/` folder of solved problems). `search_notes` is a chat tool, and pinned files plus the top matches are attached to every question automatically — small local models often skip optional lookups, so retrieval doesn't depend on them.

**Agent-Based Capabilities** — both providers can call a small, read-only tool set mid-request (containers, services, Proxmox status, metrics, logs, recent history) instead of only ever seeing one fixed snapshot. This powers `atlas chat`, an interactive command that needs no prior `atlas discover`. Either command can suggest an approval-gated action, or a multi-step **plan** for genuinely dependent steps (stop this, then restart that) — always grounded against what Atlas actually observed, and after printing, both offer to run it for you: each step still gets its own confirmation, and a declined or failed step stops the rest of the plan.

---

## Architecture

Atlas is built around a modular, event-driven core (CLI → Runtime → Plugins / Event Bus / Knowledge Store), designed so new capabilities plug in without rewriting existing ones. See the [Architecture docs](https://cyb3rron1n.github.io/atlas/architecture/) for the full picture, including how every integration and approval-gated action fits together.

---

## Configuration

Atlas uses YAML configuration, loaded from `atlas.yaml` in the working directory:

```yaml
name: sentinel

discovery:
  hardware: true
  storage: true
  network: true

inventory:
  directory: inventory/generated

proxmox:
  enabled: true
  host: 192.168.1.10
  user: atlas@pve
  token_name: atlas-token   # preferred: a scoped API token generated in the Proxmox UI
  token_value: ""
  # password: ""            # fallback if not using a token
  verify_ssl: false

intelligence:
  provider: anthropic   # or "ollama"
  model: claude-opus-5  # or an Ollama model name, e.g. llama3.1
  ollama_host: http://localhost:11434

knowledge:                      # optional: your own notes
  notes_paths: [/notes]         # folders of Markdown/scripts to search
  pinned_paths: [/notes/HOSTS.md]   # short facts attached to every chat question
  auto_context: 3               # best-matching note sections attached per question (0 = off)

jellyfin:                       # optional: playback diagnosis tools
  enabled: true
  url: http://jellyfin:8096
  api_key: ""                   # a Jellyfin API key made for Atlas

health:
  status_urls:                  # optional JSON feeds shown by get_host_health
    raid_watchdog: http://172.17.0.1:9101/status.json

map:
  hosts:                        # other LAN machines for the network map
    - {name: proxmox, address: 192.168.1.10, role: Proxmox host, ports: [22, 8006]}
    - {name: gpu-laptop, address: 192.168.1.19, role: Ollama, ports: [22, 11434]}
```

The Anthropic provider reads its API key from the `ANTHROPIC_API_KEY` environment variable — it is never stored in `atlas.yaml`. For Proxmox, prefer a scoped API token over the account password: create one in the Proxmox UI under **Datacenter → Permissions → API Tokens**, and grant it only the privileges Atlas needs (read access is enough for `atlas proxmox scan`).

---

## Documentation

The full documentation site — architecture, CLI reference, configuration reference, deployment model, service catalog, and roadmap — is live at **[cyb3rron1n.github.io/atlas](https://cyb3rron1n.github.io/atlas/)**, built from [`docs/`](docs/) with [MkDocs Material](https://squidfunk.github.io/mkdocs-material/).

To browse it locally, or after editing a page:

```bash
pip install -e ".[docs]"
mkdocs serve
```

Redeploying the live site is manual (`.github/workflows/docs.yml`, triggered via `gh workflow run docs.yml` or the Actions tab) rather than automatic on every push, so a docs edit doesn't go live until you choose to publish it.

---

## Contributing

Contributions, ideas, and discussions are welcome. Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) before submitting changes.

## Security

Security issues should be reported according to [`SECURITY.md`](SECURITY.md).

## License

Atlas is released under the [MIT License](LICENSE).

---

## Vision

Atlas's long-term goal: observe → understand → recommend → automate → optimize, with every step staying observable, explainable, and under your control.
