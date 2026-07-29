# CLI Reference

All 20 current Atlas commands. Run `atlas <command> --help` for any command-specific options.

## Status & health

| Command | Description |
|---|---|
| `atlas version` | Display the Atlas version. |
| `atlas status` | Display current Atlas status. |
| `atlas init` | Interactively generate `atlas.yaml` — prompts only for Proxmox/AI provider/Prometheus settings, skips whatever you decline, never writes `ANTHROPIC_API_KEY` to disk. Logs the session to `logs/atlas-init-<timestamp>.log` (secrets redacted) for troubleshooting and records. Optional — Atlas runs on safe defaults without an `atlas.yaml` at all. |
| `atlas doctor` | Run Atlas health checks (Python, memory, storage, Docker, inventory) plus readiness checks for the optional integrations (Proxmox, AI provider, Prometheus) against the current `atlas.yaml`. |
| `atlas config` | Display the active Atlas configuration. |
| `atlas runtime` | Display Atlas runtime information. |

## Discovery & reporting

| Command | Description |
|---|---|
| `atlas discover` | Discover infrastructure information — built-in (system, hardware, storage, network) and every registered plugin — in one pass, and generate inventory. |
| `atlas report` | Generate an infrastructure report from the latest inventory. |
| `atlas docker` | Display Docker container status. |
| `atlas services` | Detect known homelab services running in Docker (see [Service Catalog](service-catalog.md)). |
| `atlas compose` | Analyze a Docker Compose file. |
| `atlas proxmox scan` | Scan Proxmox infrastructure — nodes, VMs, and containers — and report what changed since the last scan (requires `proxmox.enabled: true`, see [Configuration](configuration.md#proxmox)). |
| `atlas monitor` | Query Prometheus for host metrics and flag any at or above their configured threshold (requires `monitoring.enabled: true`, see [Configuration](configuration.md#monitoring)). |

## Plugins

| Command | Description |
|---|---|
| `atlas plugins` | Display registered Atlas plugins. Running their discovery is folded into `atlas discover` (see above). |

## Actions

Commands that change infrastructure rather than just observe it. All are approval-gated — see [Architecture](architecture/index.md#approval-gated-actions).

| Command | Description |
|---|---|
| `atlas restart <name>` | Restart a Docker container. Shows the container's current state and asks for confirmation before acting. |
| `atlas stop <name>` | Stop a Docker container without removing it. Shows the container's current state and asks for confirmation before acting. |
| `atlas resize <name>` | Resize a Docker container's CPU (`--cpus <cores>`) and/or memory (`--memory <limit>`, e.g. `512m`/`1g`) limit, live, without a restart. Shows the container's current configured limit(s) and asks for confirmation before acting. |
| `atlas proxmox restart <vmid>` | Restart a Proxmox VM or LXC guest. Shows the guest's current state and asks for confirmation before acting (requires `proxmox.enabled: true` and write/power-management permission on the token, see [Configuration](configuration.md#proxmox)). |

## Knowledge & AI

| Command | Description |
|---|---|
| `atlas history` | Display recorded operational events. |
| `atlas intelligence` | Display the latest stored environment context. |
| `atlas analyze` | Analyze the latest environment snapshot with AI — using live tool calls for current state — and print a summary plus recommendations (see [Configuration](configuration.md#intelligence)). |
| `atlas chat` | Interactive multi-turn chat with Atlas about your infrastructure. No prior `atlas discover` required — grounds itself against live state on demand. Type `exit` to quit. |
