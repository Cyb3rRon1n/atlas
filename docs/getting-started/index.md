# Getting Started

## Install

```bash
git clone https://github.com/Cyb3rRon1n/atlas.git
cd atlas

python -m venv .venv
source .venv/bin/activate

pip install -e .
atlas version
```

## First run

Generate `atlas.yaml` interactively — prompts for the Proxmox/AI provider/Prometheus settings you actually need, skips anything you don't, and never writes `ANTHROPIC_API_KEY` to disk. Every run is logged to `logs/atlas-init-<timestamp>.log` (secrets redacted) for troubleshooting:

```bash
atlas init
```

You can skip this and run on defaults instead — `atlas.yaml` is optional; see [Configuration](../configuration.md) for the full field reference if you'd rather write it by hand.

Then discover the host you're running on, generate a report, and get an AI-assisted read on what you found:

```bash
atlas discover   # inventories the host, saves it to inventory/generated/
atlas report     # generates a Markdown report from the latest inventory
atlas analyze    # sends the latest snapshot to an AI provider for a summary + recommendations
```

`atlas analyze` needs an AI provider configured — see [Configuration](../configuration.md#intelligence). By default it expects an `ANTHROPIC_API_KEY` environment variable; if you'd rather run fully local, point it at [Ollama](../configuration.md#intelligence) instead.

## Next steps

- Run `atlas doctor` to sanity-check your environment (Python, memory, storage, Docker, inventory presence) and check readiness of the optional integrations (Proxmox credentials, `ANTHROPIC_API_KEY`, Prometheus URL) against whatever `atlas.yaml` has configured
- If you run Docker workloads, `atlas docker` and `atlas services` will inventory containers and recognize known homelab services (Jellyfin, Sonarr, Radarr, and friends — see the [Service Catalog](../service-catalog.md))
- If you run Proxmox, see [Deployment](../deployment/index.md) for how Atlas is meant to connect to it, then `atlas proxmox scan`
- The full command list is in [CLI Reference](../cli-reference.md)
