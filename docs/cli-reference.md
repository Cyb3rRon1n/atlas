# CLI Reference

All 35 current Lanxang commands. Run `lanxang <command> --help` for any command-specific options.

## Status & health

| Command | Description |
|---|---|
| `lanxang version` | Display the Lanxang version. |
| `lanxang status` | Display current Lanxang status. |
| `lanxang init` | Interactively generate `lanxang.yaml` — prompts only for Proxmox/AI provider/Prometheus settings, skips whatever you decline, never writes `ANTHROPIC_API_KEY` to disk. Logs the session to `logs/lanxang-init-<timestamp>.log` (secrets redacted) for troubleshooting and records. Optional — Lanxang runs on safe defaults without an `lanxang.yaml` at all. |
| `lanxang doctor` | Run Lanxang health checks (Python, memory, storage, Docker, inventory, other virtualization/orchestration backends detected on the host) plus live reachability checks for the optional integrations you've configured (Proxmox, AI provider — Anthropic stays config-only to avoid a billed call, Ollama is checked live — Prometheus), each bounded by a short timeout so a dead endpoint can't hang the run. `--json` prints `{"checks": [...], "healthy": bool}` instead. Exits 1 if any check is unhealthy, in either output mode - safe to check `$?` from cron without `--json`. |
| `lanxang config` | Display the active Lanxang configuration. |
| `lanxang runtime` | Display Lanxang runtime information. |

## Discovery & reporting

| Command | Description |
|---|---|
| `lanxang discover` | Discover infrastructure information — built-in (system, hardware, storage, network) and every registered plugin — in one pass, and generate inventory. |
| `lanxang report` | Generate an infrastructure report from the latest inventory. `--json` prints the raw inventory dict instead of writing `reports/atlas-report.md` - `null` if `lanxang discover` hasn't run yet. No exit-code logic, same as `lanxang trends`. |
| `lanxang docker` | Display Docker container status. |
| `lanxang services` | Detect known homelab services running in Docker (see [Service Catalog](service-catalog.md)). |
| `lanxang compose` | Analyze a Docker Compose file. |
| `lanxang map` | Build the network map shown at `lanxang web`'s `/map` — an interactive graph (Cytoscape.js, vendored and served locally, so it works offline) drawn from the device inventory plus this snapshot. Hosts in a row with their guests and Docker networks inside, other devices in a grid, most important first. Internet → LAN → machines, with this host's containers grouped by Docker network and their public hostnames (Traefik), Proxmox guests, libvirt guests, each `map.hosts` entry's TCP reachability, the AI endpoint, and what Lanxang may act on. Colours: green=seen, amber=quiet, red=important+quiet, grey=never seen; dashed border=new (needs triage). Click a device to edit (name/kind/state/tags/notes/important flag) or link to the full device page (merge/split). Double-click a host to fold/unfold its guests. "Show ignored" checkbox filters the view. Without JavaScript, falls back to a static SVG map. Saved as a snapshot (`GET /api/graph[?ignored=1]` returns the data); `--json` prints it. Run it on a schedule to keep the map current. |
| `lanxang scan` | Find every device on the LAN (TCP-connect to port 9 on every address so the kernel ARP-resolves it, then read `/proc/net/arp`) and update the device inventory - links each sighting to a known device when certain, queues new devices for triage, and sends Signal alerts for new devices and important devices gone quiet (requires `scan.enabled: true`, see [Configuration](configuration.md#scan)). `--json` prints the scan result. Exits 1 on scan failure, recorded as a failed source run rather than making devices look quiet. Run by the `atlas-scan` container. |
| `lanxang devices` | List the device inventory: every device Lanxang knows, its status (`seen` / `quiet` / `invisible`), IP, state, and which sources have sighted it. `--json` prints the full inventory, including each device's individual sightings. |
| `lanxang proxmox scan` | Scan Proxmox infrastructure — nodes, VMs, and containers — and report what changed since the last scan (requires `proxmox.enabled: true`, see [Configuration](configuration.md#proxmox)). |
| `lanxang monitor` | Query Prometheus for host metrics and flag any at or above their configured threshold (requires `monitoring.enabled: true`, see [Configuration](configuration.md#monitoring)). `--json` prints the full scan as one payload instead. Exits 1 if disabled=false and Prometheus is unreachable, or if any metric exceeded its threshold; exits 0 when disabled (an intentional state, not a failure) - in either output mode. |
| `lanxang trends` | Show host, per-container, and per-Proxmox-guest resource-usage trends (latest/min/max/avg) from the environment snapshots `lanxang monitor`/`lanxang proxmox scan` have been saving. `--limit` controls how many recent snapshots to consider (default 20). `--json` prints `{"host": {...}, "containers": {...}, "guests": {...}}` instead - no exit-code logic, since a trend report has no health/threshold concept to signal. Guest `memory_percent` is percent of the guest's own allocated memory, not host-relative like container `memory_percent` is. |

## Plugins

| Command | Description |
|---|---|
| `lanxang plugins` | Display registered Lanxang plugins. Running their discovery is folded into `lanxang discover` (see above). |

## Actions

Commands that change infrastructure rather than just observe it. All are approval-gated — see [Architecture](architecture/index.md#approval-gated-actions).

| Command | Description |
|---|---|
| `lanxang restart <name>` | Restart a Docker container. `--node <fleet-node>` retargets the connection to that node's Docker daemon over SSH (docker-py's `ssh://` transport) instead of the local one - same confirmation, same event path, just a different client. Shows the container's current state and asks for confirmation before acting. |
| `lanxang stop <name>` | Stop a Docker container without removing it. `--node <fleet-node>` supported, same as `lanxang restart`. Shows the container's current state and asks for confirmation before acting. |
| `lanxang resize <name>` | Resize a Docker container's CPU (`--cpus <cores>`) and/or memory (`--memory <limit>`, e.g. `512m`/`1g`) limit, live, without a restart. `--node <fleet-node>` supported, same as `lanxang restart`. Shows the container's current configured limit(s) and asks for confirmation before acting. |
| `lanxang proxmox restart <vmid>` | Restart a Proxmox VM or LXC guest. Shows the guest's current state and asks for confirmation before acting (requires `proxmox.enabled: true` and write/power-management permission on the token, see [Configuration](configuration.md#proxmox)). |
| `lanxang proxmox stop <vmid>` | Shut down a Proxmox VM or LXC guest via an ACPI request (not a hard power-off) - may not complete if the guest OS isn't responding. Shows current state and asks for confirmation. |
| `lanxang proxmox resize <vmid>` | Resize a Proxmox guest's CPU (`--cpus <cores>`, maps to Proxmox's `cpulimit`) and/or memory (`--memory <limit>`) limit. For a `qemu` guest, may need hotplug enabled to apply without a restart; LXC applies live. Asks for confirmation. |
| `lanxang libvirt restart <name>` | Restart a libvirt/KVM guest via an ACPI `virsh reboot` request - like Proxmox's stop, may not complete if the guest OS isn't responding. `--node <fleet-node>` retargets `virsh` at that node via its native `-c qemu+ssh://` transport - no new dependency. Shows current state and asks for confirmation. |
| `lanxang libvirt stop <name>` | Stop a libvirt/KVM guest via an ACPI `virsh shutdown` request (not `virsh destroy`, libvirt's hard power-off) - same no-force-fallback caveat as restart. `--node <fleet-node>` supported, same as `lanxang libvirt restart`. Shows current state and asks for confirmation. |
| `lanxang libvirt resize <name>` | Resize a libvirt/KVM guest's vCPU count (`--vcpus <count>`, an integer - a different concept from Docker/Proxmox's fractional `--cpus` limit) and/or memory (`--memory <size>`, e.g. `512MiB`). Applies at next boot only - a running guest needs hotplug already configured to pick this up live, not attempted here. `--node <fleet-node>` supported, same as `lanxang libvirt restart`. CLI-only: not wired into `lanxang analyze`/`lanxang chat`'s suggestable actions. Asks for confirmation. |

## Knowledge & AI

| Command | Description |
|---|---|
| `lanxang history` | Display recorded operational events. |
| `lanxang intelligence` | Display the latest stored environment context. |
| `lanxang analyze` | Analyze the latest environment snapshot with AI — using live tool calls for current state — and print a summary plus recommendations (see [Configuration](configuration.md#intelligence)). `--json` prints `{"summary", "recommendations", "plan", "provider", "model"}` instead - never offers to run a suggested plan (no bypass flag), that's text-mode-only. No environment yet prints `null`, exit 0. Exits 1 on an `AIProviderError`, otherwise 0 - the one JSON-output command in this project with a real exit code for something other than reachability, since analysis has a genuine health concept `report`/`trends` don't. |
| `lanxang chat` | Interactive multi-turn chat with Lanxang about your infrastructure. No prior `lanxang discover` required — grounds itself against live state on demand. Type `exit` to quit. |
| `lanxang web` | Serve a local web view (overview/triage/devices/interactive map/coverage/history/trends) over the same data `lanxang report`/`lanxang history`/`lanxang trends` already read, plus a device inventory editor. `/map` is an interactive graph (Cytoscape.js, vendored locally, offline-capable) of machines, containers, and guests with colour-coded status, editable side panel, and fold controls; click a device's name for "Ask lanxang about this device" link. `/chat` is the same assistant as `lanxang chat` — read-only tools, suggested actions, and multi-step plans with per-step Approve buttons; steps are re-grounded before execution and recorded in history. `--host`/`--port` (defaults `127.0.0.1:8420`). The `/devices/<id>` edit page and `/api/devices/<id>` POST (plus merge/split), `/api/graph` (map data), `/api/chat`, and `/api/actions/execute` are same-origin-gated, and every page needs sign-in (lanxang's own admin password, or `web.auth: proxy` behind Authelia and similar). Runs in the foreground until `Ctrl+C`, same on-demand shape as every other command. |
| `lanxang auth password` / `setup-code` / `token [--new]` | Sign-in for `lanxang web`: set or reset the admin password (signs everyone out), print the first-run setup code, print (or replace) the read-only API token dashboards send as `Authorization: Bearer <token>`. |
| `lanxang notify test` | Send a test alert to every channel under `notify:` (ntfy, webhooks, email, Apprise, Signal) and show which got it. Exits 1 if any failed or none is set. |
| `lanxang ports check` | Open-port watch (see [Configuration](configuration.md#open-port-watch)): common service ports on online LAN devices, this host's listeners, router port forwards / UPnP. The first run learns; later runs alert once per newly open port. `--json` prints the saved state. |
| `lanxang certs check` | Certificate watch (see [Configuration](configuration.md#certificate-watch)): expiry date of every public hostname's TLS certificate (Traefik routes plus `security.cert_hosts`). Checks once a day unless `--force`; alerts at 14 and 3 days left, on an untrusted certificate, and when renewed. `--json` prints the saved state. |
| `lanxang internet check` | Internet view (see [Configuration](configuration.md#internet-view)), opt-in with `posture.internet_view`: asks Shodan's InternetDB what it last saw on the home's public IP. Checks once a day (or when the public IP changes) unless `--force`; alerts once per open port not in `posture.expected_ports` and per reported CVE, and when it clears. A failed lookup keeps the last answer and is retried an hour later. `--json` prints the saved state. |
| `lanxang lan check` | Rogue DHCP servers and gateway ARP spoofing (see [Configuration](configuration.md#security)): one DHCP discover that never takes an address, plus the gateway's MAC from the ARP table. Saves the result for the Security tab (Exposure) and alerts once per new problem. `--trust-gateway` accepts the gateway's current MAC after a router swap; `--json` prints the result. Exits 1 while a problem is open. Needs host networking (atlas-scan runs it). |
| `lanxang fleet doctor` | SSH into every node under `fleet.nodes` in `lanxang.yaml` (no config = "no fleet nodes configured", exit 0) and run `lanxang doctor --json` on each, reusing that same payload rather than a fleet-specific format. `-o BatchMode=yes` fails an auth prompt fast instead of hanging the whole scan; a per-node SSH/parse failure is reported as `"reachable": false` without aborting the rest. `--json` prints `{"nodes": [...], "healthy": bool}`. Exits 1 if any node is unreachable or unhealthy - safe to check `$?` from cron. No remote actions and no persistence - a live fan-out per invocation, not a saved snapshot. |
| `lanxang fleet trends` | SSH into every fleet node and run `lanxang trends --limit <n> --json` on each, reusing that payload. `--limit` (default 20) passed through per node. No fleet-wide health concept (same as `lanxang trends`) - `--json` prints `{"nodes": [...]}`, exit 1 iff any node is unreachable. |
| `lanxang fleet report` | SSH into every fleet node and run `lanxang report --json` on each, reusing that payload. A reachable node with no inventory yet reports `{"reachable": true, "inventory": null}`, distinct from an unreachable one - not a parse failure. No fleet-wide health concept (same as `lanxang report`) - `--json` prints `{"nodes": [...]}`, exit 1 iff any node is unreachable. |
