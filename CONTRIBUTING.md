# Contributing to Atlas

First off, thank you for your interest in contributing to Atlas!

Whether you're fixing a typo, improving documentation, adding a new feature, or helping shape the project's direction, your contributions are appreciated.

Atlas is built on the idea that self-hosted infrastructure should be easier to understand, document, and manage. Every contribution helps move that vision forward.

---

# Our Mission

Atlas exists to help people understand and operate their homelabs through safe, explainable, and AI-assisted tooling.

Before proposing a feature, ask yourself:

> **Does this help Atlas better understand the infrastructure?**

If the answer is "yes," it likely aligns with the project's goals.

---

# Ways to Contribute

There are many ways to contribute, including:

## Documentation

* Improve guides
* Fix typos
* Clarify explanations
* Add examples
* Expand tutorials

---

## Development

* Implement new features
* Improve existing code
* Fix bugs
* Improve performance
* Refactor for readability

---

## Testing

Help test Atlas across different environments:

* Fedora
* Ubuntu
* Debian
* Proxmox VE
* Docker
* Docker Compose

Future support may include additional Linux distributions and virtualization platforms.

---

## Ideas

Suggestions are always welcome.

Examples include:

* New discovery modules
* AI workflows
* Monitoring integrations
* Documentation improvements
* Plugin ideas
* CLI enhancements

---

# Before You Start

Please check:

* Existing Issues
* Existing Pull Requests
* The project roadmap

This helps avoid duplicate work.

---

# Development Philosophy

Atlas follows several guiding principles.

## Documentation First

Every significant feature should include documentation.

If a feature cannot be explained clearly, it likely needs refinement.

---

## Explainability

Atlas should be able to explain:

* What it is doing
* Why it is doing it
* What the expected outcome is
* Any associated risks

This philosophy should be reflected in both code and documentation.

---

## Local-First

Whenever practical, Atlas prioritizes self-hosted and local solutions.

Examples include:

* Local AI models
* Self-hosted monitoring
* Local infrastructure management

---

## Safety

Atlas should never encourage unsafe automation.

Changes affecting infrastructure should be:

* Observable
* Logged
* Reversible whenever possible
* Configurable through user approval

---

# Development Setup

Clone the repository:

```bash
git clone https://github.com/<your-username>/atlas.git
cd atlas
```

Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install atlas with its development extras, then run the tests (CI runs them on Python 3.11 and 3.12):

```bash
pip install -e ".[dev]"            # not `pip install -r requirements.txt` - that is a pip-freeze lockfile
python -m pytest tests/
python -m atlas.cli.main <command> # the CLI from source; `atlas web` serves the pages
```

No linter or formatter is configured. Match the style of the file you are editing. The history of design
decisions lives in [docs/development/design-notes.md](docs/development/design-notes.md); read the section for the
area you are changing before you change it.

## Project Layout

| Path | What lives there |
|---|---|
| `atlas/cli/` | The CLI (Typer + Rich): `app.py` the shared app, `main.py` setup/status/web commands, `watch.py` what atlas-scan runs, `virt.py` Proxmox/libvirt/fleet, `containers.py` Docker, `ai.py` the AI model |
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
| `atlas/config/local.py` | Settings and secrets saved from the web Setup tab (`inventory/`); `atlas.yaml` and `.env` always win |
| `atlas/web/settings_page.py` | The Setup tab: one card per integration, read-only Test, Save / Turn off |

## Ground Rules

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

---

# Branch Naming

Please create a feature branch instead of working directly on `main`.

Examples:

```text
feature/docker-discovery

feature/proxmox-support

feature/status-command

feature/media-module

fix/docker-parser

docs/getting-started

refactor/cli
```

---

# Commit Messages

Atlas follows the Conventional Commits specification.

Examples:

```text
feat: add Docker discovery

feat: implement hardware inventory

fix: resolve container parser

docs: improve installation guide

docs: update roadmap

refactor: simplify CLI structure

test: add inventory unit tests

ci: add GitHub Actions workflow

chore: update dependencies
```

---

# Pull Requests

Good pull requests typically:

* Focus on one logical change
* Include clear descriptions
* Update documentation when needed
* Pass automated checks
* Keep changes as small and reviewable as practical

If your change affects user behavior, include an explanation of the expected outcome.

---

# Coding Standards

General principles:

* Favor readability over cleverness.
* Keep functions focused and small.
* Avoid unnecessary complexity.
* Write descriptive names.
* Add comments where intent is not immediately obvious.
* Remove unused code before submitting.

Future coding standards will be documented as the project grows.

---

# Documentation Standards

Documentation is a core feature of Atlas.

Whenever appropriate, include:

* Purpose
* Requirements
* Examples
* Limitations
* Future improvements

Well-written documentation is just as valuable as code.

---

# Reporting Bugs

When reporting an issue, please include:

* Operating system
* Atlas version
* Python version
* Relevant logs
* Steps to reproduce
* Expected behavior
* Actual behavior

Screenshots are welcome when helpful.

---

# Suggesting Features

Feature requests should explain:

* The problem being solved
* Why it matters
* A proposed approach (if you have one)
* Alternative solutions you've considered

Discussion is encouraged before implementation for larger features.

---

# Code of Conduct

Please follow the project's Code of Conduct.

Be respectful, constructive, and welcoming to others.

Atlas is intended to be a friendly and inclusive open-source community.

---

# Recognition

Every contribution matters.

Whether you improve a single sentence, fix a bug, or implement a major feature, you are helping Atlas become a better project.

Thank you for contributing.

---

# Our Philosophy

Atlas is guided by three simple ideas:

**Understand first.**

Build an accurate understanding of infrastructure before making decisions.

**Document continuously.**

Documentation should evolve alongside the system.

**Automate carefully.**

Automation should be transparent, explainable, and under the user's control.

If your contribution supports those principles, you're helping move Atlas in the right direction.

Welcome aboard!
