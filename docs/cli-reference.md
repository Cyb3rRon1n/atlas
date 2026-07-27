# CLI Reference

All 17 current Atlas commands. Run `atlas <command> --help` for any command-specific options.

## Status & health

| Command | Description |
|---|---|
| `atlas version` | Display the Atlas version. |
| `atlas status` | Display current Atlas status. |
| `atlas doctor` | Run Atlas health checks (Python, memory, storage, Docker, inventory). |
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
| `atlas monitor` | Query Prometheus for host metrics (requires `monitoring.enabled: true`, see [Configuration](configuration.md#monitoring)). |

## Plugins

| Command | Description |
|---|---|
| `atlas plugins` | Display registered Atlas plugins. Running their discovery is folded into `atlas discover` (see above). |

## Actions

Commands that change infrastructure rather than just observe it. All are approval-gated — see [Architecture](architecture/index.md#approval-gated-actions).

| Command | Description |
|---|---|
| `atlas restart <name>` | Restart a Docker container. Shows the container's current state and asks for confirmation before acting. |

## Knowledge & AI

| Command | Description |
|---|---|
| `atlas history` | Display recorded operational events. |
| `atlas intelligence` | Display the latest stored environment context. |
| `atlas analyze` | Analyze the latest environment snapshot with AI and print a summary plus recommendations (see [Configuration](configuration.md#intelligence)). |
