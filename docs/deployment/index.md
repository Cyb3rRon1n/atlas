# Deployment

## The intended model

Atlas is designed to run **as a guest on the Proxmox host it's helping you manage**, not as an external tool polling your infrastructure from somewhere else:

```mermaid
graph TD
    A[Proxmox VE host] -->|hosts| B[Ubuntu VM guest]
    B -->|runs| C[Atlas]
    C -->|connects back to| A
```

The typical setup:

1. Install Proxmox VE on your hardware, on a static (or DHCP-reserved) IP — Atlas's config keys off a fixed host address, and Proxmox itself expects a stable management IP regardless.
2. Create an Ubuntu VM inside that Proxmox host.
3. Clone Atlas into that VM, install it (`pip install -e .`), and run `atlas init` there to generate `atlas.yaml` — see [Getting Started](../getting-started/index.md).

Because Atlas runs on the same cluster it inspects, connecting back to the Proxmox API is a same-network call rather than something exposed externally.

## Authentication: use a scoped API token, not the root password

Atlas's [`proxmox` configuration](../configuration.md#proxmox) accepts either a password or an API token. **Prefer the token.** Generate one in the Proxmox UI under **Datacenter → Permissions → API Tokens** (create a dedicated user first, e.g. `atlas@pve` under the *Proxmox VE authentication server* realm, rather than tokenizing `root@pam`), and grant it a role scoped to only what Atlas actually needs — the built-in `PVEAuditor` role is read-only and sufficient for `atlas proxmox scan`. `atlas proxmox restart` needs additional write/power-management permission on top of that — see [Configuration](../configuration.md#proxmox). `atlas init` prompts for the token directly and writes it into `atlas.yaml` for you; it does not create the token in Proxmox itself, so generate it in the UI first.

This isn't just caution for its own sake — it's the project's own stated principle. From `CONTRIBUTING.md`:

!!! note "Safety"
    Changes affecting infrastructure should be observable, logged, reversible whenever possible, and configurable through user approval.

Atlas's role is to assist — observe, understand, recommend — not to require unrestricted access to operate. A least-privilege token that can be widened later is a better default than broad access you have to walk back.

## What this means for the rest of Atlas

Every discovery path (`atlas discover`, `atlas proxmox scan`) feeds into the same local knowledge store and environment context, which `atlas analyze` reads from. Nothing about the deployment model changes the trust boundary of the intelligence layer: recommendations come from Anthropic or a local Ollama model reasoning over what Atlas observed, not from Atlas taking action on its own.
