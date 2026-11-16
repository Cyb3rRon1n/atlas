# Configuration

Atlas uses YAML configuration, loaded from `atlas.yaml` in the current working directory. If the file doesn't exist, Atlas runs on defaults (safe — no Proxmox connection is attempted, discovery is fully enabled, no AI model is used until you choose one).

**Prefer a web page?** The **Setup** tab sets up alerts (ntfy, webhooks, email), the AI model, managed switches (SNMPv3), a UniFi console and Proxmox, with a Test button for each. Tests are read-only: alerts send one test message, switches get one SNMP request, UniFi and Proxmox are signed in to and read. It saves to `inventory/settings.yaml` and keeps passwords in `inventory/secrets.json` (readable only by atlas), both in the data volume. Anything you set in `atlas.yaml` or `.env` wins and shows read-only there. Until alerts are on and every device has a name, the Home page shows a short **Getting started** list linking to each step.

Run `atlas init` to generate this file interactively instead of writing it by hand — it only prompts for the fields below that actually vary per deployment (Proxmox, AI provider, Prometheus), leaves `discovery`/`inventory` at their defaults, and logs the session to `logs/` for troubleshooting. The reference below is for editing the result by hand, or understanding what each field does.

```yaml
name: homelab

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
| `provider` | `none` | `none`, `ollama` or `anthropic` |
| `model` | `claude-opus-5` | The Claude model ID, or an Ollama model name (e.g. `llama3.1`) when `provider: ollama` |
| `ollama_host` | `http://localhost:11434` | Only used when `provider: ollama` |
| `think` | `false` | Only used when `provider: ollama`. Thinking models such as qwen3 reason silently before answering, which is much slower — `false` keeps replies fast. Set `null` if your Ollama or model rejects the field. |

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
| `storage_paths` | `{}` | `label: path` whose disk usage the web home page's Storage & RAID card shows - e.g. `media array: /media` with the array bind-mounted read-only into the container. Software-RAID (`/proc/mdstat`) and Proxmox ZFS pools are shown automatically. |
| `alerts` | `true` | Host health alerts (below) |
| `temp_margin_c` | `5.0` | Alert when a sensor is this close to its own "high" limit, two samples in a row |
| `memory_percent` | `90` | Alert when memory use reaches this |
| `disk_percent` | `90` | Alert when the root disk or any `storage_paths` entry reaches this |

### Host health alerts

Every atlas-scan pass (`atlas sample`) checks the machine atlas runs on and sends one alert when a problem starts and another when it clears:

- a temperature sensor within `temp_margin_c` of the limit the chip itself reports (CPUs and NVMe drives report one; sensors without a limit are skipped);
- memory, the root disk or a `storage_paths` disk above its limit;
- a container that crashed (stopped with an error code), keeps restarting, or fails its health check;
- a `status_urls` feed whose `state` is anything but `ok` (for example a RAID-card watchdog saying `warn`).

**Containers that sleep on purpose are not problems.** One that stopped cleanly (exit code 0), such as a game room an idle timer shuts down, shows as *Asleep* on the home page and never alerts. For an app that sleeps but exits with an error code, add the label `atlas.on-demand=true`. The `/api/summary` tile data counts them as `containers_asleep`.

A status feed only reachable from Docker's network can be read as a file instead: mount its directory read-only and use a `file://` URL (`raid card: file:///run/raid-watchdog/status.json`).

## `access`

Who reaches the public services and from where (web `/access`). `atlas access collect` (run by atlas-scan each cycle) reads new
Traefik access-log lines and app sign-ins, and geolocates IPs locally with DB-IP's free City Lite database (CC BY 4.0,
downloaded monthly) plus the posture ASN table - no visitor IP leaves the host.

| Field | Default | Description |
|---|---|---|
| `enabled` | `false` | Turn collection on |
| `traefik_log` | `/traefik-logs/access.log` | Traefik access log (mount it read-only into atlas-scan) |
| `geo_path` | `inventory/dbip-city-lite.mmdb` | Where the monthly geo database is kept |
| `jellyfin_url` / `jellyfin_api_key` | `""` | Read sign-ins and failed attempts from Jellyfin's activity log |
| `home_ips` | `[]` | Your WAN IPs - shown as "home", not drawn on the map |
| `ignore_ips` | `[]` | IPs to skip entirely (e.g. an uptime checker) |
| `retention_days` | `30` | Older hits, sign-ins and IPs are deleted |

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

## Alerts page

The web page's **Alerts** tab lists everything the checks below find: *Needs action* (problems: these also go to every `notify:` channel), *Watching* (shown on the page only) and *Resolved in the last 7 days*. Each item links to the page where you can investigate it, and resolves by itself once the check no longer sees it. One-off findings, such as a newly opened port, stay under *Needs action* for 7 days. Resolved items are kept for 30 days.

- **Acknowledge**: you've seen it. It moves down the list and off the Home page; a one-off finding is cleared.
- **Mute this alert / this device** (1 day, 7 days or always): no more messages about it - when the alert is about a device, about anything on that device - but it stays listed. *Muted* at the top of the page lists them, each with *Unmute*.
- **Pause alerts** (1 hour, 4 hours or a day) for maintenance: nothing is sent, problems are still recorded, and a banner shows until *Resume now* or the time runs out.

**One alert per outage.** When a switch or access point on the cabling map goes offline, the offline devices wired behind it fold under it: one alert ("core-switch is offline - 12 devices behind it unreachable") and one message, instead of one per device. Only the topmost offline box counts, so a dead core switch doesn't also report the edge switch behind it. Switches and APs are matched to inventory devices by MAC, then IP; muting the switch mutes its outage. Without a cabling map, every important device alerts on its own as before.

## `wiring`

The cabling map (web `/cabling`): every switch port, what's plugged into it, patch panels, and cable health. Read-only: atlas reads your switches over SNMPv3 and, optionally, a UniFi console, and never changes their settings. The atlas-scan container refreshes it every cycle; the page's **Refresh map** button does it on demand.

```yaml
wiring:
  enabled: true
  switches:
    - name: core-switch          # secrets in .env: ATLAS_SNMP_CORE_SWITCH_AUTH / _PRIV
      host: 192.168.1.2
      priv: aes                  # des only for old gear that offers nothing else
    - name: nas                  # SNMPv2c: read-only community in .env as ATLAS_SNMP_NAS_COMMUNITY
      host: 192.168.1.20
      version: 2c
  unifi:
    enabled: true                # a local View Only account: ATLAS_UNIFI_USER / ATLAS_UNIFI_PASS in .env
    url: https://192.168.1.1
```

| Field | Default | Description |
|---|---|---|
| `switches` | `[]` | Switches, routers and NAS boxes that speak the standard MIBs (IF-MIB, LLDP-MIB, BRIDGE-MIB). `version: "3"` (default, authPriv; `snmp_user` defaults to `atlas`) or `"2c"` with a read-only community - unencrypted, so only when the device offers nothing else. See [Supported hardware](hardware.md) |
| `unifi` | off | Adds UniFi gateway/AP/switch ports and their uplinks, which SNMP can't see |
| `cabling_file` | `cabling.yaml` | Patch panels and wall jacks, by hand (see `cabling.example.yaml`) |
| `not_managed` | `[]` | Addresses never suggested for a login (the Setup tab's *Don't ask* adds them) |
| `keep_snapshots` | `30` | Scans kept for "changes since the last scan" and cable health history |
| `timeout` | `10` | Seconds per SNMP or UniFi request |

### Traffic

Each scan compares every port's byte counters (64-bit `ifHCInOctets`/`ifHCOutOctets` over SNMP; UniFi's port table) with the scan before, giving the average traffic over that gap - 15 minutes with the default scan interval, so short bursts are smoothed out. Nothing extra is polled. On the map, a cable over half its link speed is drawn thick orange and over 80% red, and its label shows the rate. The **Port map** has a *Traffic (24 h)* column with a small graph per port; hover it for now, in/out and the peak. Rates are kept 7 days. A counter reset (switch reboot) skips one point instead of showing a spike.

### Cable health

Each scan compares every connected port's counters with the scan before it, so only new errors count. A switch reboot that resets the counters is recognised and ignored.

| Finding | Level | What it usually means |
|---|---|---|
| CRC / alignment errors growing (10 or more per scan, above 0.01% of packets; 0.1% = problem) | watch → problem | A damaged cable, a bad jack or a worn patch lead |
| Half duplex, or late collisions | problem | Duplex mismatch: one end is set to a fixed speed |
| Link slower than the port ran before (e.g. 100 Mbit/s instead of 1 Gbit/s) | watch | A damaged wire pair or bad jack, or simply a computer asleep |
| Link went down and up since the last scan | watch | Unplugged, rebooted, or a loose connector |
| Output errors growing | watch | Congestion or a failing port |
| PoE fault: a powered device detected but not powered | problem | A bad cable, or the device needs more power than the port gives |
| PoE budget 90% or more used | watch | Another powered device (camera, access point) may not start |

**Finding switches to add:** atlas notices network gear it can't read yet: devices that answer SNMPv3 discovery (the maker comes from the answer, e.g. Cisco, Netgear, MikroTik) and devices a mapped switch hears announcing themselves as a bridge, router or access point over LLDP. NAS and Linux SNMP agents are left out. The Cabling page then says how many devices could show their ports with a login, the device's own page links to the Setup tab with the address filled in, and the Switches card lists them under *Found on your network* with **Use** and **Don't ask**. Atlas never tries passwords: you give the SNMPv3 login, press Test, then Save.

**PoE:** ports powering a device show ⚡ on the faceplate, ports that can supply PoE but aren't have a dashed outline, and each device's line shows its PoE use and budget ("PoE 6.5 W of 30 W"). Hover a port for the PoE class, mode and watts. Switches report this over SNMP (the standard POWER-ETHERNET-MIB; per-port watts only come from UniFi), UniFi devices through the console. "Started/stopped delivering PoE" appears with the other changes since the last scan.

**Spanning tree, link bundles and VLANs:** when two or more cables join the same two switches or routers, the map checks spanning tree. If all but one cable is blocked, the spare shows as a grey dotted *standby* line, with a quiet note saying which port is idle. If more than one cable carries traffic, that's a **loop risk**: a warning at the top of the page and one alert (plus another when it's fixed). Cables bundled with LACP draw thicker and are labelled with the bundle name (for example `Po1`), with no warning. Hover a port to see its bundle, spanning-tree state and VLANs ("VLAN 1, tagged 20, 30"). When the switches carry more than one VLAN, a **VLAN** picker above the faceplates dims every port not on the chosen VLAN. The switch model (from `sysDescr`) shows next to its name. All of this uses standard MIBs (BRIDGE-MIB spanning tree, IEEE 802.3ad LAG-MIB, Q-BRIDGE-MIB VLANs). UniFi devices report their spanning-tree state and bundles through the console. A switch that lacks one of these tables just shows nothing for it.

Problems turn the port red on the faceplate, appear in **Cable health** and send one alert to every `notify:` channel, plus another alert when they clear. "Watch" findings are shown on the page only, because they have harmless causes too often to send alerts about. Switches without the EtherLike counters fall back to plain input errors, and UniFi ports use the console's own error counts.

## `uptime`

Is each service you care about answering? Add checks on the web page (**Servers → Uptime**: name, address, *Add*; your public hostnames are offered as one-click suggestions) or here. The atlas-scan container tries every check once a minute.

```yaml
uptime:
  fail_after: 2                 # failures in a row before a check counts as down
  checks:
    - name: Media server
      target: https://media.example.org     # up when it answers below HTTP 500 - a login page counts
    - name: NAS (SMB)
      target: 192.0.2.20:445                # up when the port accepts a connection
      timeout: 5                            # seconds, default 10
```

A check that fails `fail_after` times in a row is **down**: one alert ("Media server is down"), listed on the Alerts page, and one "back up" message saying how long it was down. Mute or pause it from the Alerts page like any other alert. The page shows each check's response time over 24 hours and its uptime over 24 hours, 7 days and 30 days; results are kept 30 days. Certificates aren't verified here - expiry and trust are the certificate watch's job (`security.cert_watch`). A list set in atlas.yaml wins over the page and makes the page read-only.

## `security`

LAN watch: `atlas lan check` looks for a second DHCP server and for something impersonating your router. atlas-scan runs it after every device scan, and the result shows as the **LAN** tile on the Security tab (Exposure).

```yaml
security:
  dhcp_servers: [192.168.1.5]   # only if something besides the router hands out addresses (Pi-hole, a second router)
```

| Field | Default | Description |
|---|---|---|
| `dhcp_probe` | `true` | Send one DHCP discover per run and list every server that answers. It never asks for or takes an address |
| `dhcp_timeout` | `3.0` | Seconds to wait for answers |
| `dhcp_servers` | `[]` | DHCP servers you expect besides the default gateway |
| `port_watch` | `true` | `atlas ports check`: alert on newly open ports (below) |
| `snmp_discovery` | `true` | During `atlas ports check`, send each device online the standard SNMPv3 discovery message (no user name, no password, so never a failed login) to find switches and routers that could show their ports |
| `port_timeout` | `0.5` | Seconds per port connect |
| `extra_ports` | `[]` | Ports to watch besides the ~25 common service ports |

| Finding | Level | What it usually means |
|---|---|---|
| A DHCP server that is neither the gateway nor listed | problem | A router plugged in backwards, a VM or container running DHCP by mistake, or an attacker handing out their own gateway |
| No DHCP server answered two runs in a row (after answering before) | problem | DHCP is down: new devices and renewing ones can't get an address |
| No DHCP server has ever answered | watch | Usually this host's firewall dropping the answers: allow incoming UDP port 68 (on firewalld: `firewall-cmd --add-port=68/udp --permanent`, then `--reload`) |
| The gateway's IP answers from a different MAC than the one learned on the first run | problem | ARP spoofing (a man in the middle), or you replaced the router: run `atlas lan check --trust-gateway` to accept the new MAC |
| A wired UniFi client using the gateway's IP | problem | Something claiming to be the router (needs `wiring.unifi`) |
| The gateway's MAC also answers for another address | watch | Usually harmless (proxy ARP, a router with two addresses) |
| One IP on two wired UniFi clients | watch | An address conflict, or a recent DHCP reassignment |

Problems send one alert to every `notify:` channel and another when they clear. The ARP checks see what the atlas host sees; UniFi's client list (when `wiring.unifi` is set) widens that to the rest of the wired network. Hearing DHCP answers needs UDP port 68: the Docker image ships `atlas-dhcp-python`, an interpreter copy holding only that one permission. Run outside Docker as a normal user, the probe reports that it can't listen and the ARP checks still run.

### Open-port watch

`atlas ports check` (run by atlas-scan after every device scan) looks at three things, all read-only:

- **LAN devices:** a plain TCP connect to about 25 common service ports (SSH, telnet, web, file sharing, remote desktop, VNC, databases, camera streams, MQTT, printers) on every device that is online, within your scan subnets. It never sends data or logs in.
- **This host:** sockets listening for other machines (loopback-only ones are left out).
- **The router:** port forwards and the UPnP switch from the UniFi console when `wiring.unifi` is set, and the standard UPnP port-mapping list that most home routers answer (only the default gateway is asked).

The first run learns what is normal and sends nothing. After that every newly open port sends one alert (risky ones such as telnet, SMB, remote desktop or databases say so), a new port forward or UPnP mapping alerts as "opened to the internet", and UPnP being switched on alerts. A port that closes and opens again later doesn't alert twice. Each device's page lists its open ports; the Security tab (Exposure)'s **Public exposure** tab shows the router's forwards, UPnP and the latest new ports.

### Certificate watch

`atlas certs check` (run by atlas-scan, but only once a day) opens a TLS connection to every hostname in your Traefik routes, plus any you list, the same way a browser would, and reads each certificate's expiry date. Nothing is changed and no login is needed. Behind Cloudflare (or any proxy) that is the certificate visitors actually get.

```yaml
security:
  cert_watch: true          # false turns it off
  cert_hosts: []            # more hostnames to check, e.g. a router or NAS with its own certificate
  cert_warn_days: 14        # first alert
  cert_urgent_days: 3       # second, red alert (also sent once it has expired)
  cert_timeout: 5.0
```

One alert per hostname each time things get worse (14 days left, then 3 days or expired), one when a browser would refuse the certificate (wrong name, untrusted issuer), and a "Resolved" once it is renewed. A hostname that can't be reached is only shown, not alerted: outages are the health checks' job. The Posture page's **Public exposure** tab shows days left next to each route, yellow inside the warning window and red when urgent or untrusted. `atlas certs check --force` checks right away.

## `notify`

Where alerts go: new devices, important devices gone offline, VPN/torrent clients disconnected, and sign-ins from new places. Set any number of channels — every one that is set gets each alert, and one failing never stops the others. Check your setup with `atlas notify test`.

```yaml
notify:
  ntfy:                              # free phone app (ntfy.sh, or your own server)
    url: https://ntfy.sh
    topic: my-homelab-a8f3k2         # pick something hard to guess on the public server
  webhooks:                          # Discord / Slack webhook URLs, or any URL that takes JSON
    - https://discord.com/api/webhooks/123/abc
    - http://homeassistant.local:8123/api/webhook/atlas
  email:
    host: smtp.example.com
    port: 587
    user: atlas@example.com
    to: [me@example.com]
  apprise:                           # 100+ more services, see the Apprise wiki
    - tgram://bottoken/ChatID
  signal:                            # signal-cli-rest-api
    url: http://signal-cli:8080
    number: "+15551234567"
    recipients: ["+15559876543"]
```

| Channel | Fields | Notes |
|---|---|---|
| `ntfy` | `url`, `topic`, `token` | Markdown messages with a title. `token` (or `ATLAS_NTFY_TOKEN` in `.env`) for a protected server |
| `webhooks` | list of URLs | `discord.com/api/webhooks/...` and `hooks.slack.com/...` get their own format; any other URL gets `{"title", "text", "source": "atlas"}` as JSON |
| `email` | `host`, `port` (587), `starttls` (true), `user`, `password`, `sender`, `to` | Port 465 uses implicit TLS. Put the password in `.env` as `ATLAS_SMTP_PASSWORD` rather than here |
| `apprise` | list of [Apprise URLs](https://github.com/caronc/apprise/wiki) | Telegram, Pushover, Gotify, Matrix, Teams and more. Needs the `apprise` package — the Docker image has it; with pip, `pip install "atlas[alerts]"` |
| `signal` | `url`, `number`, `recipients` | Through [signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api). `recipients` can be numbers or group IDs |

An alert counts as delivered when at least one channel took it; if every channel fails it stays queued and is retried on the next run.

The first successful run of each source (`lan`, `proxmox`, ...) is a baseline — it never generates new-device alerts by itself. After that, new-device alerts roll up: if one was already sent in the last 24 hours, further new devices are held and folded into the next message instead of each firing its own alert. An important device going quiet (missed the last 2 successful runs of every source) alerts once per episode, not on every scan it stays quiet. 

