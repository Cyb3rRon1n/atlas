# Roadmap

## Shipped

- Python CLI application, configuration management
- Hardware, OS, storage, and network discovery
- Inventory generation and reporting
- Docker discovery and known-service detection ([Service Catalog](service-catalog.md))
- Docker Compose analysis
- Event-driven system with persistent operational history
- Plugin architecture (currently: a Docker plugin)
- **Proxmox integration** — node discovery, cluster-wide VM/container inventory, API token authentication
- **AI analysis engine** — `atlas analyze`, pluggable Anthropic/Ollama providers, structured recommendations
- Test suite (59+ tests) and CI (GitHub Actions, Python 3.11/3.12)

## In progress / next

- **Automation framework** — turning `atlas analyze` recommendations into approval-gated actions, consistent with the project's Safety principle (observable, logged, reversible, approval-gated — see [Deployment](deployment/index.md))
- **Unifying discovery** — built-in discovery (`atlas discover`) and the plugin system (`atlas plugins`) are still two separate code paths; plugin-based discovery results don't yet merge into the environment context the way built-in discovery and Proxmox scans do
- **Proxmox resource trending / change detection** — the current inventory is a point-in-time snapshot; historical tracking needs time-series storage, not just the existing snapshot table
- Advanced monitoring integrations (Prometheus/Grafana-style metrics feeding into the knowledge store)
- Agent-based capabilities

## Guiding principle

Every step up this list is expected to remain consistent with Atlas's core loop:

```mermaid
graph LR
    A[Observe] --> B[Understand]
    B --> C[Recommend]
    C --> D[Automate with approval]
```

Automation is the last step, not the first — Atlas earns the right to act by first being reliably right about what it observes and recommends.
