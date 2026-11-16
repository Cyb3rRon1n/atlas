<p align="center">
  <img src="images/social-preview.svg" alt="Atlas - see and secure everything on your home network" style="max-width: 100%;">
</p>

# Atlas

**Know every device on your home network, what changed, and what needs you — without sending anything to the cloud.**

Atlas is a self-hosted watchdog for homelabs. It finds every machine on your LAN without installing anything on
them, maps how they are cabled together down to the switch port, watches your Docker containers and Proxmox
guests, checks your network's security, and alerts you when something new shows up or something important goes
quiet. An AI model is optional: run one locally with Ollama and ask questions in plain language.

!!! quote "Watch everything. Change nothing without asking."
    Atlas observes and explains. Restarting a container or a VM is only ever suggested, and every action asks you
    first. There is no autonomous mode and no bypass flag.

## What Atlas does

- **Device inventory**: every device on the LAN, found from ARP, SNMP and LLDP. New ones wait for you to name them;
  important ones alert you when they drop off.
- **Cabling map**: a wired view from the internet down to every switch port — link speeds, PoE, spanning tree,
  link bundles, VLANs and your patch panels — read over SNMP and (optionally) your UniFi console.
- **Security watch**: new open ports on LAN devices, a rogue DHCP server, ARP spoofing of your gateway, expiring
  TLS certificates, what reaches the internet and what the internet can reach, and whether your torrent client is
  still behind its VPN.
- **Health**: cable errors, temperatures near their limit, full disks, crashed or restart-looping containers.
- **Alerts where you already look**: ntfy, Discord, Slack, email, any webhook, Signal, or 100+ services through
  Apprise. One alert when a problem starts, one when it clears.
- **Containers and VMs**: Docker, Proxmox and libvirt — what's running, what's unhealthy, and restart, stop or
  resize when you approve it.
- **Chat with your homelab** (optional): answers come from live state, logs and your own notes, using Ollama on
  your own hardware or Claude.

Start with [Getting Started](getting-started/index.md), or see [Architecture](architecture/index.md) for how the
pieces fit together.

## See it in action

<p align="center">
  <img src="images/screenshots/cabling-map.png" alt="Cabling map: internet, gateway, a 28-port switch and the hosts on each port" style="max-width: 100%; width: 900px;"><br>
  <img src="images/screenshots/cabling-ports.png" alt="Switch front panels with a standby backup cable and a PoE-powered access point" style="max-width: 100%; width: 900px;"><br>
  <sub>The Cabling page, shown with example data.</sub>
</p>

<p align="center">
  <img src="images/screenshots/devices.png" alt="Devices page" style="max-width: 100%; width: 900px;"><br>
  <sub>The Devices page, shown with example data.</sub>
</p>

### From the terminal

Representative output, not a literal capture — field names and formatting match real commands; hostnames, containers, and figures are illustrative.

<p align="center">
  <img src="images/screenshots/doctor.svg" alt="atlas doctor example output" style="max-width: 100%; width: 820px;"><br>
  <sub><code>atlas doctor</code> — environment health plus integration readiness</sub>
</p>

<p align="center">
  <img src="images/screenshots/proxmox-scan.svg" alt="atlas proxmox scan example output" style="max-width: 100%; width: 820px;"><br>
  <sub><code>atlas proxmox scan</code> — cluster inventory and change detection since the last scan</sub>
</p>

<p align="center">
  <img src="images/screenshots/analyze.svg" alt="atlas analyze example output" style="max-width: 100%; width: 820px;"><br>
  <sub><code>atlas analyze</code> — AI summary with a grounded, approval-gated action suggestion</sub>
</p>

<p align="center">
  <img src="images/screenshots/chat.svg" alt="atlas chat example output" style="max-width: 100%; width: 820px;"><br>
  <sub><code>atlas chat</code> — a live conversation, grounded the same way as <code>atlas analyze</code></sub>
</p>

<p align="center">
  <img src="images/screenshots/plan.svg" alt="atlas analyze multi-step plan example output" style="max-width: 100%; width: 820px;"><br>
  <sub>A suggested multi-step plan — printed for you to run yourself, one step at a time</sub>
</p>

<p align="center">
  <img src="images/screenshots/trends.svg" alt="atlas trends example output" style="max-width: 100%; width: 820px;"><br>
  <sub><code>atlas trends</code> — resource-usage history built from saved <code>atlas monitor</code> snapshots</sub>
</p>

## Where this is headed

Atlas isn't meant to run on your laptop and poke at infrastructure from the outside — see [Deployment](deployment/index.md) for the intended model of Atlas running as a guest on the Proxmox host it's helping you manage. The [Roadmap](roadmap.md) covers what's shipped and what's next.
