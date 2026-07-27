# CLI Reference

All 16 current Atlas commands. Run `atlas <command> --help` for any command-specific options.

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
| `atlas discover` | Discover infrastructure information and generate inventory. |
| `atlas report` | Generate an infrastructure report from the latest inventory. |
| `atlas docker` | Display Docker container status. |
| `atlas services` | Detect known homelab services running in Docker (see [Service Catalog](service-catalog.md)). |
| `atlas compose` | Analyze a Docker Compose file. |
| `atlas proxmox scan` | Scan Proxmox infrastructure — nodes, VMs, and containers (requires `proxmox.enabled: true`, see [Configuration](configuration.md#proxmox)). |

## Plugins

| Command | Description |
|---|---|
| `atlas plugins` | Display registered Atlas plugins. |
| `atlas discover-plugins` | Run discovery through all registered plugins. |

## Knowledge & AI

| Command | Description |
|---|---|
| `atlas history` | Display recorded operational events. |
| `atlas intelligence` | Display the latest stored environment context. |
| `atlas analyze` | Analyze the latest environment snapshot with AI and print a summary plus recommendations (see [Configuration](configuration.md#intelligence)). |
