<p align="center">
  <img src="docs/images/brand/social-preview.png" alt="Lanxang - see and secure everything on your home network" width="100%">
</p>

<p align="center">
  <a href="https://github.com/Cyb3rRon1n/lanxang/actions/workflows/ci.yml"><img src="https://github.com/Cyb3rRon1n/lanxang/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/Cyb3rRon1n/lanxang/releases/latest"><img src="https://img.shields.io/github/v/release/Cyb3rRon1n/lanxang" alt="Latest release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
</p>

<p align="center">
  📖 <a href="https://cyb3rron1n.github.io/lanxang/">Documentation</a> · <a href="https://cyb3rron1n.github.io/lanxang/getting-started/">Getting started</a> · <a href="https://cyb3rron1n.github.io/lanxang/configuration/">Configuration</a> · <a href="https://cyb3rron1n.github.io/lanxang/roadmap/">Roadmap</a>
</p>

# Lanxang

**Know every device on your home network, what changed, and what needs you — without sending anything to the cloud.**

Lanxang (formerly Atlas) is a self-hosted monitor for homelabs. It finds every machine on your LAN, maps how they're cabled together, watches your Docker containers and Proxmox guests, and tells you when something new shows up or something important goes quiet. Ask it questions in plain language and it answers from what it actually sees, using a local AI model if you like.

It never changes anything on its own. Restarting a container or a VM is only ever *suggested*, and every action asks you first.

<p align="center">
  <img src="docs/images/screenshots/home.png" alt="Lanxang home page: one sentence saying two things need a look, number tiles for devices, servers, uptime, public routes and power, and a Needs attention table" width="90%">
  <br><img src="docs/images/screenshots/devices.png" alt="Lanxang devices page: new devices with their maker, what they announce, where they are plugged in and a suggested name and type" width="90%">
  <br><sub>Home and the devices page, shown with example data.</sub>
</p>

## What it does

- **Device inventory**: every device on the LAN, found without installing anything on them. New ones come with clues - the maker, the name and model they announce, where they're plugged in - and a suggested name; important ones alert you when they drop off.
- **Network and cabling map**: a wired view from the internet down to every switch port, read over SNMP and (optionally) your UniFi console, with your patch panels added by hand.
- **Containers and VMs**: Docker containers, Proxmox and libvirt guests: what's running, what's unhealthy, and restart/stop/resize when you approve it.
- **Alerts where you already look**: ntfy, Discord, Slack, email, any webhook, Signal, or 100+ more services through Apprise.
- **Security posture**: what reaches the internet and what the internet can reach, new sign-in locations, and whether your torrent client is still behind its VPN.
- **Chat with your homelab**: "why did Jellyfin stop transcoding?" gets answered from live logs, status and your own notes, using Ollama on your hardware or Claude.

<p align="center">
  <img src="docs/images/screenshots/cabling-map.png" alt="Lanxang cabling map: internet, gateway, a switch, an access point and a Wi-Fi bridge, with port-to-port labels and link speeds" width="90%">
  <br><img src="docs/images/screenshots/cabling-ports.png" alt="Switch front panels: which device is on each port, with a panel explaining the selected port" width="90%">
  <br><sub>The cabling map and switch front panels, shown with example data.</sub>
</p>

## Install

You need Linux with Docker. One line sets it up in `~/lanxang` and starts it:

```bash
curl -fsSL https://raw.githubusercontent.com/Cyb3rRon1n/lanxang/main/install.sh | bash
```

Prefer to read it first? `curl -fsSLO https://raw.githubusercontent.com/Cyb3rRon1n/lanxang/main/install.sh`, then `less install.sh` and `bash install.sh`.

The installer asks three things (port, whether the whole LAN may open the page, and which AI to use, if any), then prints the address. The first visit asks for a **setup code** to choose the admin password; the installer shows it, and `docker compose logs atlas` does too.

No Docker? `pip install` works as well; see [Getting started](https://cyb3rron1n.github.io/lanxang/getting-started/).

## First steps

1. **Open the page** and set your password. The Home page shows a *Getting started* list until the next two steps are done.
2. **Name your devices**: Devices → *Needs attention*. Give each new device a name and press Keep, or Ignore it.
3. **Turn on alerts** on the **Setup** tab: ntfy (the quickest), Discord, Slack, any webhook or email. *Send test* checks it before you save.
4. **Add what you have**, also on the Setup tab: tick what's on your network and it shows the matching cards - switches, routers and NAS boxes over SNMP (v3 or v2c), a UniFi console, Proxmox, and an AI model (Ollama or Claude). Each card has a read-only *Test* button. Nothing is required: [Supported hardware](https://cyb3rron1n.github.io/lanxang/hardware/) lists what each adds.

Prefer files? Everything on the Setup tab can also go in `~/lanxang/lanxang.yaml`, and anything set there wins; [Configuration](https://cyb3rron1n.github.io/lanxang/configuration/) has copy-paste examples. Signal and Apprise alerts are set there.

<p align="center">
  <img src="docs/images/screenshots/setup.png" alt="The Setup tab: What is on your network? with a managed switch and a UPS ticked, then cards for ntfy and webhooks" width="80%">
  <br><sub>The Setup tab, shown with example data.</sub>
</p>

## Privacy

**No telemetry.** Lanxang never reports usage, crashes or anything else to anyone. It talks only to the things you configure (your Proxmox, switches, AI model and alert channels), plus a few optional downloads that run only when you turn the matching feature on:

- the free DB-IP city database and the iptoasn.com table, for the access and posture pages (lookups then happen on your machine);
- api.ipify.org, to compare your VPN exit address with your home address.

Everything it learns stays in one SQLite file in a Docker volume on your machine.

## Safety

- **Read-only Docker access by default.** Lanxang reaches Docker through a socket proxy that only allows reads. Set `LANXANG_DOCKER_WRITE=1` in `.env` to let it restart and stop containers. That gives it full Docker control, so only do it if you want those buttons.
- **Approval for every change.** Suggested fixes are printed or shown; each step asks before it runs. There is no autonomous mode and no bypass flag.
- **Signed in by default.** The web page has its own password (or hands sign-in to Authelia/Authentik with `web.auth: proxy`). Dashboards such as Homepage use a separate read-only API token.

## FAQ

**Does it need an AI?** No. Inventory, maps, alerts and posture all work without one. The AI only powers chat and the daily check-up.

**Which AI?** A local [Ollama](https://ollama.com) model keeps everything at home (an 8B model on any 8 GB GPU is plenty). Claude is supported for heavier analysis if you have an API key.

**Do I have to install anything on my devices?** No. Discovery uses your router's and switches' own information (ARP, SNMP, LLDP) and the Docker and Proxmox APIs.

**Can it run on a Raspberry Pi?** It's plain Python, so it should, but it's only tested on x86-64 (Ubuntu in CI, Fedora in daily use).

**Can I put it on a dashboard?** Yes: [Homepage tile setup](https://cyb3rron1n.github.io/lanxang/deployment/#as-a-dashboard-tile-homepage).

## Troubleshooting

| Problem | Fix |
|---|---|
| The page doesn't load | From `~/lanxang`: `docker compose ps`, then `docker compose logs atlas`. By default it only listens on this machine; re-run the installer and choose "anyone on your LAN" to open it up |
| Lost the setup code or password | `docker compose exec atlas lanxang auth setup-code`, or set a new password with `docker compose exec -it atlas lanxang auth password` |
| No devices found | Devices are found by `atlas-scan`, which needs host networking: check `docker compose logs atlas-scan`, and set `scan.subnets` if your LAN isn't the machine's own subnet |
| Alerts don't arrive | `docker compose exec atlas lanxang notify test` shows each channel's error |
| Restarting a container fails with "403" | Docker access is read-only; set `LANXANG_DOCKER_WRITE=1` in `.env` and `docker compose up -d` |

## Upgrade and uninstall

Run the installer again to upgrade: it keeps your `.env`, your config file (`lanxang.yaml`, or `atlas.yaml` from an earlier install) and data. Coming from Atlas? The old command, config file, `ATLAS_*` settings and image keep working until 1.2; see [Upgrading from atlas](https://cyb3rron1n.github.io/lanxang/getting-started/#upgrading-from-atlas). To remove Lanxang, run `bash install.sh --uninstall`; it asks before deleting your data.

## Learn more

- [Getting started](https://cyb3rron1n.github.io/lanxang/getting-started/), [Configuration](https://cyb3rron1n.github.io/lanxang/configuration/), [CLI reference](https://cyb3rron1n.github.io/lanxang/cli-reference/) and [Deployment](https://cyb3rron1n.github.io/lanxang/deployment/) (reverse proxy, Homepage tile, posture page)
- [Architecture](https://cyb3rron1n.github.io/lanxang/architecture/) and the [Roadmap](https://cyb3rron1n.github.io/lanxang/roadmap/), including what has been tested against real hardware
- [Changelog](CHANGELOG.md)

## Contributing, security, license

Issues and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md). Please report security problems privately as described in [SECURITY.md](SECURITY.md). Lanxang is MIT licensed.
