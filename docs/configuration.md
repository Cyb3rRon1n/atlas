# Configuration

Atlas uses YAML configuration, loaded from `atlas.yaml` in the current working directory. If the file doesn't exist, Atlas runs on defaults (safe — no Proxmox connection is attempted, discovery is fully enabled, the Anthropic provider is assumed but nothing is contacted until you run `atlas analyze`).

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

## `intelligence`

Controls the AI backend behind `atlas analyze`.

| Field | Default | Description |
|---|---|---|
| `provider` | `anthropic` | `anthropic` or `ollama` |
| `model` | `claude-opus-5` | The Claude model ID, or an Ollama model name (e.g. `llama3.1`) when `provider: ollama` |
| `ollama_host` | `http://localhost:11434` | Only used when `provider: ollama` |

The Anthropic provider reads its API key from the `ANTHROPIC_API_KEY` environment variable — it is never stored in `atlas.yaml`.
