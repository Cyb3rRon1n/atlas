# Configuration

Atlas uses YAML configuration, loaded from `atlas.yaml` in the current working directory. If the file doesn't exist, Atlas runs on defaults (safe — no Proxmox connection is attempted, discovery is fully enabled, the Anthropic provider is assumed but nothing is contacted until you run `atlas analyze`).

Run `atlas init` to generate this file interactively instead of writing it by hand — it only prompts for the fields below that actually vary per deployment (Proxmox, AI provider, Prometheus), leaves `discovery`/`inventory` at their defaults, and logs the session to `logs/` for troubleshooting. The reference below is for editing the result by hand, or understanding what each field does.

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
  token_name: atlas-token
  token_value: ""
  # password: ""
  verify_ssl: false

intelligence:
  provider: anthropic
  model: claude-opus-5
  ollama_host: http://localhost:11434

monitoring:
  enabled: false
  prometheus_url: http://localhost:9090

fleet:
  nodes:
    - name: media-server
      host: 192.168.1.20
      user: atlas
      port: 22
      identity_file: ""
```

## `name`

A label for this Atlas instance. Defaults to `atlas-node`.

## `discovery`

Toggles which discovery categories `atlas discover` collects. All default to `true`.

| Field | Default | Description |
|---|---|---|
| `hardware` | `true` | CPU and memory information |
| `storage` | `true` | Disk partitions and usage |
| `network` | `true` | Hostname and network addresses |

## `inventory`

| Field | Default | Description |
|---|---|---|
| `directory` | `inventory/generated` | Where `atlas discover` writes `system-inventory.yaml` |

## `proxmox`

See [Deployment](deployment/index.md) for why a scoped API token is preferred over the account password.

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | Must be `true` for `atlas proxmox scan` to attempt a connection |
| `host` | `""` | Proxmox host/IP |
| `user` | `""` | Proxmox user, e.g. `atlas@pve` |
| `token_name` | `""` | API token name — **preferred** over `password` |
| `token_value` | `""` | API token value |
| `password` | `""` | Fallback if not using a token |
| `verify_ssl` | `false` | Verify the Proxmox host's TLS certificate |

If both a token and a password are configured, the token is used.

Read access (the built-in `PVEAuditor` role) is enough for `atlas proxmox scan`. `atlas proxmox restart <vmid>` needs additional power-management permission on top of that — confirmed against a real Proxmox instance, granting the built-in `PVEVMUser` role (which includes `VM.PowerMgmt`) at path `/` is enough. If the token has **Privilege Separation** enabled (Proxmox's default), that permission has to be granted to the token identity itself (`user@realm!tokenid`), not just the user — see [Deployment](deployment/index.md) for the exact gotcha and fix.

## `intelligence`

Controls the AI backend behind `atlas analyze`.

| Field | Default | Description |
|---|---|---|
| `provider` | `anthropic` | `anthropic` or `ollama` |
| `model` | `claude-opus-5` | The Claude model ID, or an Ollama model name (e.g. `llama3.1`) when `provider: ollama` |
| `ollama_host` | `http://localhost:11434` | Only used when `provider: ollama` |

The Anthropic provider reads its API key from the `ANTHROPIC_API_KEY` environment variable — it is never stored in `atlas.yaml`.

## `monitoring`

Controls `atlas monitor`.

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | Must be `true` for `atlas monitor` to attempt a connection |
| `prometheus_url` | `http://localhost:9090` | Base URL of an existing Prometheus server |
| `cpu_threshold` | `90.0` | CPU usage percentage at or above which `atlas monitor` flags the metric |
| `memory_threshold` | `90.0` | Memory usage percentage at or above which `atlas monitor` flags the metric |
| `disk_threshold` | `90.0` | Disk usage percentage at or above which `atlas monitor` flags the metric |

The default metric queries assume [`node_exporter`](https://github.com/prometheus/node_exporter) is running on the monitored host and being scraped by Prometheus — install and configure it there for `atlas monitor` to return real CPU/memory/disk figures. If Prometheus is reachable but `node_exporter` isn't set up yet, `atlas monitor` still runs; each affected metric just reports as unavailable rather than failing the whole command.

A metric at or above its threshold prints with a yellow `!` instead of a green `✓` (e.g. `! cpu_percent: 92.1% (threshold: 90.0%)`), and if anything crossed its threshold, `atlas monitor` publishes `atlas.monitoring.threshold_exceeded` (visible via `atlas history`) alongside the `atlas.monitoring.scan.completed` event every scan already publishes — so a no-op scan doesn't add event-log noise, only an actual threshold crossing does. A metric with no data (`node_exporter` not scraped, etc.) is never flagged either way — "unavailable" isn't "under the limit."

## `fleet`

Controls `atlas fleet doctor`. No daemon, no central server — each node just needs to be reachable over SSH with Atlas already installed there; `atlas fleet doctor` SSHes in and runs `atlas doctor --json` remotely.

`nodes` is a list, each entry:

| Field | Default | Description |
|---|---|---|
| `name` | *(required)* | A label for this node, shown in `atlas fleet doctor`'s output |
| `host` | *(required)* | Hostname or IP to SSH to |
| `user` | `atlas` | SSH user |
| `port` | `22` | SSH port |
| `identity_file` | `""` | Path to an SSH private key; empty uses your normal SSH agent/default key |

An empty `nodes` list (the default) means "no fleet nodes configured" — `atlas fleet doctor` exits 0, the same way a disabled Proxmox/monitoring integration does, not an error state.

## `knowledge`

Your own notes, for `atlas chat`.

| Field | Default | Description |
|---|---|---|
| `notes_paths` | `[]` | Folders (or files) of Markdown, text and scripts (`.sh`, `.py`, `.yml`, unit files...) to search. Empty = no `search_notes` tool. Hidden folders (`.git`) are skipped. |
| `pinned_paths` | `[]` | Short files (a host/IP map, conventions) attached to **every** chat question. Keep them small. |
| `auto_context` | `3` | How many best-matching note sections are attached to every question automatically (0 = only when the model calls `search_notes`). |

Markdown is searched section by section; scripts whole (they document themselves in comments). Files under a folder named `incidents/` or `cases/` rank above general docs - keep one short file per solved problem there (symptom, cause, how it was found, fix) and Atlas starts from it next time. Automatic attachment exists because small local models often skip optional lookups.

## `jellyfin`

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | Offer `get_jellyfin_sessions` / `get_jellyfin_activity` / `get_jellyfin_plugins` to chat. |
| `url` | `http://jellyfin:8096` | Jellyfin base URL as reachable from Atlas. |
| `api_key` | `""` | A Jellyfin API key (Dashboard > API Keys) created for Atlas. |

## `health`

| Field | Default | Description |
|---|---|---|
| `status_urls` | `{}` | `name: url` of JSON status feeds that `get_host_health` includes (e.g. a RAID-card watchdog). |

## `map`

`hosts` lists other machines to draw on the network map (`atlas map`, web `/map`). Atlas only checks their TCP reachability - it never acts on them.

| Field | Default | Description |
|---|---|---|
| `name` | *(required)* | Label on the map |
| `address` | *(required)* | IP or hostname |
| `role` | `""` | Short description |
| `ports` | `[22]` | TCP ports to test (a machine is "up" if any accepts) |

A host whose address equals `proxmox.host` gets the Proxmox guests drawn under it; the one serving `intelligence.ollama_host` is labelled as the AI endpoint.

## `scan`

Controls `atlas scan`, whole-LAN device discovery. Sightings link into the device inventory shown by `atlas devices` (see [CLI Reference](cli-reference.md)).

| Field | Default | Description |
|---|---|---|
| `enabled` | `true` | Must be `true` for `atlas scan` to run |
| `subnets` | `[]` | CIDR subnets to scan; empty = the default-route interface's own networks |
| `timeout` | `0.5` | Per-address TCP connect timeout, in seconds |

How often the `atlas-scan` container loops `atlas scan; atlas discover; atlas proxmox scan; atlas map` is controlled by the `ATLAS_SCAN_MINUTES` environment variable (`docker-compose.yml`), default `15` - not an `atlas.yaml` field, since it's a property of the compose service's loop, not of scanning itself.

`atlas scan` never pings and never opens a raw socket: it TCP-connects to port 9 on every address in scope, which makes the kernel ARP-resolve each live host, then reads `/proc/net/arp` for the resulting IP-to-MAC table (only complete entries count — an address nobody answered for isn't in it) and does a best-effort reverse DNS lookup for a hostname. This needs host networking (`network_mode: host`) but no extra capabilities. A scan refuses to run over more than 1024 addresses at once — narrow `subnets` if your LAN is bigger than that.

## `notify`

Controls Signal alerts for new and offline devices, sent through [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api).

```yaml
notify:
  signal:
    url: http://signal-cli:8080
    number: "+15551234567"
    recipients: ["+15559876543"]
```

| Field | Default | Description |
|---|---|---|
| `url` | `""` | Base URL of a running signal-cli-rest-api instance. Empty = alerts off |
| `number` | `""` | The registered Signal number to send from |
| `recipients` | `[]` | Numbers (or group IDs) to send to |

The first successful run of each source (`lan`, `proxmox`, ...) is a baseline — it never generates new-device alerts by itself. After that, new-device alerts roll up: if one was already sent in the last 24 hours, further new devices are held and folded into the next message instead of each firing its own alert. An important device going quiet (missed the last 2 successful runs of every source) alerts once per episode, not on every scan it stays quiet. A failed Signal send leaves the notification queued and retries on the next run.

