# Getting Started

## Requirements

Lanxang itself needs Linux, Python 3.11+, and pip — that's enough for `lanxang discover`, `lanxang report`, `lanxang docker`, `lanxang services`, `lanxang compose`, and `lanxang doctor`, no config file or external services required.

Everything else is an optional integration, gated independently by `lanxang.yaml` (or the web page's **Setup** tab) and checked by `lanxang doctor`:

| Integration | Enables | What it actually needs |
|---|---|---|
| Docker | Container discovery, `lanxang restart`/`stop`/`resize`, cAdvisor container metrics | A Docker daemon reachable from wherever Lanxang runs (local socket, or `DOCKER_HOST` for a remote one) |
| Proxmox VE | `lanxang proxmox scan`/`restart` | A reachable Proxmox host and an API token — a network call over HTTPS, nothing installed on Proxmox itself. See [Deployment](../deployment/index.md) for the recommended (not required) topology |
| Anthropic **or** Ollama | `lanxang analyze`, `lanxang chat` | An `ANTHROPIC_API_KEY`, or a locally-reachable Ollama instance — only one is needed |
| Prometheus | `lanxang monitor` | An existing Prometheus, `node_exporter` for host metrics, and [cAdvisor](https://github.com/google/cadvisor) for per-container metrics |

Verified against real infrastructure on two distros: Ubuntu (CI runs the full test suite on real `ubuntu-latest` GitHub Actions runners) and Fedora (this project's actual development environment — every real-infrastructure check documented here has genuinely run on Fedora). Other Linux distros are expected to work — discovery has no distro-specific code — but aren't independently verified. macOS/Windows are out of scope.

## Install

### With Docker (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/Cyb3rRon1n/lanxang/main/install.sh | bash
```

Needs Docker with the Compose plugin. The installer asks for a folder, port, who can open the page
(this machine or your whole LAN) and which AI assistant to use, then starts lanxang and has you set
the admin password. Re-run it to upgrade; `bash install.sh --uninstall` removes it (and asks before
deleting data). Prefer to read it first: download it with `curl -fsSLO`, read it, then `bash install.sh`.

Installing by hand with `docker compose` instead? Copy `lanxang.yaml.example` to `lanxang.yaml` next to
`docker-compose.yml`, edit it, then `docker compose up -d`.

### From source

```bash
git clone https://github.com/Cyb3rRon1n/lanxang.git
cd lanxang

python -m venv .venv
source .venv/bin/activate

pip install -e .
lanxang version
```

## First run

Generate `lanxang.yaml` interactively — prompts for the Proxmox/AI provider/Prometheus settings you actually need, skips anything you don't, and never writes `ANTHROPIC_API_KEY` to disk. Every run is logged to `logs/lanxang-init-<timestamp>.log` (secrets redacted) for troubleshooting:

```bash
lanxang init
```

You can skip this and run on defaults instead — `lanxang.yaml` is optional; see [Configuration](../configuration.md) for the full field reference if you'd rather write it by hand.

Then discover the host you're running on, generate a report, and get an AI-assisted read on what you found:

```bash
lanxang discover   # inventories the host, saves it to inventory/generated/
lanxang report     # generates a Markdown report from the latest inventory
lanxang analyze    # sends the latest snapshot to an AI provider for a summary + recommendations
```

`lanxang analyze` needs an AI provider configured — see [Configuration](../configuration.md#intelligence). By default it expects an `ANTHROPIC_API_KEY` environment variable; if you'd rather run fully local, point it at [Ollama](../configuration.md#intelligence) instead.

## Upgrading from atlas

Lanxang was called Atlas before 1.0. Since 1.3 only the new names are read. The easiest way to move over is to
run the installer again: it renames `atlas.yaml` to `lanxang.yaml` and the `ATLAS_*` entries in `.env` to
`LANXANG_*` (keeping the old file as `.env.before-1.3`), then pulls and restarts.

By hand: rename `atlas.yaml` to `lanxang.yaml`; rename every `ATLAS_*` entry in `.env` to `LANXANG_*`; use
`lanxang` instead of `atlas` in scripts; pull `ghcr.io/cyb3rron1n/lanxang` (the old image name is no longer
published); then `docker compose pull && docker compose up -d`. Until you do, Lanxang logs a warning naming
what it no longer reads.

Unchanged: the compose services keep the names `atlas` and `atlas-scan`, and your data, sign-in and history carry
over as they are.

## Next steps

- Run `lanxang doctor` to sanity-check your environment (Python, memory, storage, Docker, inventory presence, other virtualization/orchestration backends detected on the host) and live-check whatever optional integrations `lanxang.yaml` has configured (Proxmox, `ANTHROPIC_API_KEY`/Ollama, Prometheus) — each reachability check is bounded by a short timeout, so it can't hang
- If you run Docker workloads, `lanxang docker` and `lanxang services` will inventory containers and recognize known homelab services (Jellyfin, Sonarr, Radarr, and friends — see the [Service Catalog](../service-catalog.md))
- If you run Proxmox, see [Deployment](../deployment/index.md) for how Lanxang is meant to connect to it, then `lanxang proxmox scan`
- The full command list is in [CLI Reference](../cli-reference.md)
