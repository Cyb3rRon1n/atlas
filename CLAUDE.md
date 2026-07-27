# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup — use the [dev] extra, not requirements.txt (see Testing note below)
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run the CLI
atlas <command>            # e.g. atlas discover, atlas analyze, atlas doctor
python -m atlas.cli.main <command>   # equivalent, for running from source without reinstalling

# Tests (pytest, no config beyond auto-detected rootdir)
python -m pytest tests/
python -m pytest tests/test_discovery.py -v
python -m pytest tests/test_intelligence_providers.py::TestAnthropicProvider::test_refusal_raises_provider_error
python -m pytest tests/ --cov=atlas --cov-report=term-missing   # coverage, matches CI

# requirements.txt is a pip-freeze lockfile regenerated from the venv, not hand-edited,
# and is NOT used for install (see Testing note below):
pip install <new-package>
pip freeze > requirements.txt
```

There is no configured linter or formatter — nothing enforces style automatically. CI (`.github/workflows/ci.yml`) runs the test suite on Python 3.11/3.12 for every push/PR to `main`; it does not gate on a coverage threshold.

**Testing note:** `requirements.txt` is a `pip freeze` dump that includes a self-referential editable install line (`-e git+ssh://...`) — this only works on a machine with SSH access to the repo, so CI (and any fresh clone) must install via `pip install -e ".[dev]"` against the checked-out tree, never `pip install -r requirements.txt`. Most tests rely on two `tests/conftest.py` fixtures rather than hitting real state: `isolated_cwd` (chdirs into a temp dir, since a real local `atlas.yaml` exists and `load_config()`/file-writing code reads/writes relative to cwd) and `temp_db` (points `KnowledgeStore`/`KnowledgeQueries` at a throwaway SQLite file instead of the committed `inventory/atlas.db` — done by monkeypatching the `engine` name in both `atlas.knowledge.store` and `atlas.knowledge.queries`, since each did `from atlas.database.engine import engine`, a local name binding). Docker- and hostname-resolution-dependent code (`atlas/docker/manager.py`, `atlas/discovery/network.py`) is mocked in tests rather than relying on ambient environment state, since GitHub-hosted runners have a live Docker daemon and CI network namespaces can't always resolve their own hostname.

## Architecture

**Runtime wiring.** `atlas.core.application.application` is a module-level singleton (`AtlasApplication`) constructed at import time; it owns an `AtlasRuntime` (`atlas/core/runtime.py`), which in turn owns:
- `AtlasContext` (`atlas/core/context.py`) — a plain dataclass bag (`config`, `inventory`, `docker`, `proxmox`, `services`, `health`) that subsystems write into.
- `AtlasEnvironmentContext` (`atlas/intelligence/context.py`) — the accumulated discovery snapshot (system/hardware/storage/network/services/containers/virtualization), updated via `.ingest_discovery(data)` after `atlas discover` and read back via `.summary()`.
- `EventBus` (`atlas/events/bus.py`) — a synchronous pub/sub bus; `subscribe("*", cb)` receives every event type.

CLI commands (`atlas/cli/main.py`) reach the singleton via `from atlas.core.application import application; runtime = application.runtime` rather than constructing their own runtime.

**Event flow.** Almost everything that produces data publishes an `AtlasEvent(event_type, source, payload)` on the bus (see `atlas.discovery.completed`, `atlas.plugin.loaded`, `atlas.analysis.completed`, `atlas.action.container_restarted`). `atlas/listeners/database.py`'s `DatabaseListener` subscribes to `"*"` and persists every event via `KnowledgeStore.save_event`; it's registered onto every `AtlasRuntime`'s event bus in `atlas/core/runtime.py`'s `__init__` (`DatabaseListener().register(self.events)`). **This registration was missing until it was added** — the listener class existed but nothing ever instantiated/registered it, so `atlas history` was silently non-functional (no published event was ever persisted; only the direct `save_environment()`/`save_analysis()` calls worked) for the entire life of the project up to that point. If event persistence ever looks broken again, check this wiring first. `atlas/listeners/logger.py`'s `EventLogger` (prints plugin-load events) is defined but still **not** registered anywhere — leave it that way unless you have a specific reason, since wiring it up changes visible CLI output for every existing command that publishes events. New features that produce meaningful state changes should publish an event rather than writing to the knowledge store directly from the CLI command, to keep that persistence path centralized.

**Approval-gated actions.** `atlas restart <name>` (`atlas/cli/main.py`, backed by `get_container_info`/`restart_container` in `atlas/docker/manager.py`) is the first command that mutates infrastructure instead of observing it. The shape to replicate for any future action: the capability itself is a pure function returning a plain result dict (`{"success"/"found": bool, "error": str, ...}`, never raising the underlying library's exceptions to the caller — same style as `collect_containers()`); the CLI layer shows the current state and gates on `typer.confirm()` (default deny, no bypass flag) before calling it; the result is published as an event so it's logged via the same `DatabaseListener` path as everything else — no bespoke persistence code. There is deliberately no generic action/registry framework yet (`atlas/actions/` doesn't exist) — that's future work once there's a second action to generalize from, not before.

**Persistence.** SQLite via SQLAlchemy, engine at `atlas/database/engine.py` pointing at `inventory/atlas.db`. `atlas/database/models.py` holds the ORM models (`EventRecord`, `EnvironmentRecord`, `AnalysisRecord`); `atlas.database.initialize_database()` runs `Base.metadata.create_all` — new tables just need a model added there. Reads and writes are split: `atlas/knowledge/store.py` (`KnowledgeStore`) writes, `atlas/knowledge/queries.py` (`KnowledgeQueries`) reads (`latest_environment()`, `latest_analysis()`, `recent_events()`). Note `inventory/atlas.db` itself is currently committed to git (not gitignored) — be aware of this rather than assuming it's disposable local state.

**Discovery: built-in + plugins, unified in `atlas discover`.** `atlas.discovery.run_discovery()` (`atlas/discovery/__init__.py`) is the built-in, synchronous path — it directly calls `collect_system/hardware/storage/network` and returns a merged dict. Separately, `atlas/plugins/` implements a plugin architecture (`AtlasPlugin` ABC with `initialize(runtime)` / `discover()`, `PluginManager.load_plugins()` auto-discovers via `atlas/plugins/loader.py`, `discover_all()` runs every registered plugin, currently just a Docker plugin). The `atlas discover` CLI command (`atlas/cli/main.py`) runs both in one pass: built-in results go through `AtlasEnvironmentContext.ingest_discovery()`, plugin results go through `.update("containers", plugin_data)`, and both are saved to the knowledge store in a single `save_environment()` call before two separate events publish (`atlas.discovery.completed`, `atlas.plugins.discovery.completed`). There used to be a separate `atlas discover-plugins` command; it was removed once its job was folded into `atlas discover` — don't reintroduce it as a distinct command without a reason, the whole point was one discovery entry point. `atlas plugins` (list registered plugins, no discovery) is unrelated and still exists.

**Config.** `atlas/config/loader.py`'s `load_config()` reads `atlas.yaml` from the current working directory (returns `AtlasConfig()` defaults if the file doesn't exist) and validates it against the pydantic models in `atlas/config/models.py`. `atlas/config/config.yaml` is an unrelated template fragment, not read by the loader. Config sections are added by adding a new pydantic `BaseModel` subclass and a field on `AtlasConfig`, following the existing `ProxmoxConfig`/`IntelligenceConfig` pattern.

**AI providers.** `atlas/intelligence/providers/` defines an `AIProvider` ABC (`base.py`) returning a schema-shaped `AnalysisResult`/`Recommendation`; `AnthropicProvider` and `OllamaProvider` both use structured/schema-constrained output so responses never need free-text parsing. `get_provider(config.intelligence)` is the factory (provider implementations are imported lazily inside it so the `anthropic` import isn't required just to build the config or use the Ollama path). `AtlasAnalyzer` (`atlas/intelligence/analyzer.py`) is a thin wrapper that just delegates to whichever provider it's given — put orchestration logic there, not in the CLI command.

**Rich-based CLI conventions.** Every `atlas/cli/main.py` command uses a shared `Console()` and follows the same shape: print a bold header, do the work, print results with `rich` color tags (`[green]✓ ...`, `[yellow]! ...`, `[red]...`), and for commands with a data dependency (`report`, `intelligence`, `analyze`), print a "Run: atlas discover" hint and return early rather than raising when no data exists yet.

## Code style notes

The existing codebase (outside `atlas/intelligence/providers/` and `tests/`, which are newer) is written with heavy vertical spacing — each function argument on its own line, a blank line after `def ...():` before the body, blank lines between most statements — and very few docstrings (mostly on classes, not functions). New code should generally match whatever file it's editing rather than importing a different style mid-file.

## Project philosophy (from CONTRIBUTING.md)

- **Local-first**: prefer self-hosted/local solutions where practical (e.g. the Ollama provider option alongside Anthropic).
- **Explainability**: Atlas should be able to explain what it's doing, why, the expected outcome, and any risk — reflected in both code and docs.
- **Safety**: changes affecting real infrastructure should be observable, logged, reversible where possible, and gated behind user approval — Atlas is meant to observe/recommend, not silently act.
