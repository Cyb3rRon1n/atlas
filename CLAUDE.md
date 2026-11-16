# CLAUDE.md

Guidance for AI coding assistants (and humans) working in this repository. The long-form history of design
decisions lives in [docs/development/design-notes.md](docs/development/design-notes.md); read the section for the
area you are changing before you change it.

## Commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # never `pip install -r requirements.txt` (a pip-freeze lockfile)
python -m pytest tests/            # what CI runs, on Python 3.11 and 3.12
python -m atlas.cli.main <command> # the CLI from source; `atlas web` serves the pages
```

No linter or formatter is configured. Match the style of the file you are editing.

## Layout

| Path | What lives there |
|---|---|
| `atlas/cli/main.py` | Every CLI command (Typer + Rich) |
| `atlas/web/` | `atlas web`: stdlib `http.server`, one `*_page.py` per page, `api.py` for the write routes |
| `atlas/devices/` | Device inventory: LAN scan, sightings merged into devices, open-port watch, LAN (DHCP/ARP) watch |
| `atlas/wiring/` | Cabling map: SNMP + UniFi collectors, `build.py` turns them into nodes and links, cable health |
| `atlas/posture/` | Egress/exposure collectors, certificate watch, the Posture page's data |
| `atlas/access/` | Who reaches the public services (Traefik access log + GeoIP) |
| `atlas/docker`, `proxmox`, `libvirt`, `fleet` | Integrations; mutating calls are pure functions returning result dicts |
| `atlas/intelligence/` | AI providers (Ollama, Anthropic), read-only chat tools, the agent |
| `atlas/actions/` | Registry of actions the AI may suggest; each one still asks before it runs |
| `atlas/notify.py` | Alert fan-out (ntfy, webhooks, email, Signal, Apprise) |
| `atlas/config/models.py` | Every `atlas.yaml` setting (pydantic); add a section by adding a model |

## Rules

- **Never act without asking.** Anything that changes infrastructure is shown first and gated by a confirmation;
  there is no bypass flag and no autonomous mode.
- **Read-only by default.** New collectors observe; alerts fire once when a problem appears and once when it clears.
- **Optional data never fails a scan.** A table a device doesn't support, or an integration that isn't configured,
  means that part is left out, not an error.
- **No personal data in the repo.** Examples use `192.0.2.x`/`example.org` and made-up names; screenshots use
  example data.
- **Tests use fixtures, not ambient state**: `isolated_cwd` and `temp_db` in `tests/conftest.py`. Docker, SNMP and
  network calls are injected or mocked. A feature that talks to real hardware is also checked against it before
  release.
- **Docs move with the code**: `docs/configuration.md` for settings, `CHANGELOG.md` under *Unreleased*.
