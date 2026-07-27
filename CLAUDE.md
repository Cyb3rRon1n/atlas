# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup (editable install pulls in all deps from pyproject.toml)
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Run the CLI
atlas <command>            # e.g. atlas discover, atlas analyze, atlas doctor
python -m atlas.cli.main <command>   # equivalent, for running from source without reinstalling

# Tests (pytest, no config beyond auto-detected rootdir; tests/ currently only covers atlas/intelligence)
python -m pytest tests/
python -m pytest tests/test_intelligence_providers.py -v
python -m pytest tests/test_intelligence_providers.py::TestAnthropicProvider::test_refusal_raises_provider_error

# requirements.txt is a pip-freeze lockfile regenerated from the venv, not hand-edited:
pip install <new-package>
pip freeze > requirements.txt
```

There is no configured linter, formatter, or CI workflow (no `.github/workflows`) — nothing enforces style automatically.

## Architecture

**Runtime wiring.** `atlas.core.application.application` is a module-level singleton (`AtlasApplication`) constructed at import time; it owns an `AtlasRuntime` (`atlas/core/runtime.py`), which in turn owns:
- `AtlasContext` (`atlas/core/context.py`) — a plain dataclass bag (`config`, `inventory`, `docker`, `proxmox`, `services`, `health`) that subsystems write into.
- `AtlasEnvironmentContext` (`atlas/intelligence/context.py`) — the accumulated discovery snapshot (system/hardware/storage/network/services/containers/virtualization), updated via `.ingest_discovery(data)` after `atlas discover` and read back via `.summary()`.
- `EventBus` (`atlas/events/bus.py`) — a synchronous pub/sub bus; `subscribe("*", cb)` receives every event type.

CLI commands (`atlas/cli/main.py`) reach the singleton via `from atlas.core.application import application; runtime = application.runtime` rather than constructing their own runtime.

**Event flow.** Almost everything that produces data publishes an `AtlasEvent(event_type, source, payload)` on the bus (see `atlas.discovery.completed`, `atlas.plugin.loaded`, `atlas.analysis.completed`). `atlas/listeners/database.py`'s `DatabaseListener` subscribes to `"*"` and persists every event via `KnowledgeStore.save_event`; `atlas/listeners/logger.py`'s `EventLogger` prints plugin-load events. New features that produce meaningful state changes should publish an event rather than writing to the knowledge store directly from the CLI command, to keep that persistence path centralized.

**Persistence.** SQLite via SQLAlchemy, engine at `atlas/database/engine.py` pointing at `inventory/atlas.db`. `atlas/database/models.py` holds the ORM models (`EventRecord`, `EnvironmentRecord`, `AnalysisRecord`); `atlas.database.initialize_database()` runs `Base.metadata.create_all` — new tables just need a model added there. Reads and writes are split: `atlas/knowledge/store.py` (`KnowledgeStore`) writes, `atlas/knowledge/queries.py` (`KnowledgeQueries`) reads (`latest_environment()`, `latest_analysis()`, `recent_events()`). Note `inventory/atlas.db` itself is currently committed to git (not gitignored) — be aware of this rather than assuming it's disposable local state.

**Discovery vs. plugins — two parallel systems.** `atlas.discovery.run_discovery()` (`atlas/discovery/__init__.py`) is the built-in, synchronous path used by `atlas discover` — it directly calls `collect_system/hardware/storage/network` and returns a merged dict. Separately, `atlas/plugins/` implements a plugin architecture (`AtlasPlugin` ABC with `initialize(runtime)` / `discover()`, `PluginManager.load_plugins()` auto-discovers via `atlas/plugins/loader.py`, `discover_all()` runs every registered plugin) — this is what `atlas plugins` / `atlas discover-plugins` exercise. They are not yet unified: built-in discovery does not go through the plugin system, and plugin-based discovery results aren't currently merged into `AtlasEnvironmentContext`.

**Config.** `atlas/config/loader.py`'s `load_config()` reads `atlas.yaml` from the current working directory (returns `AtlasConfig()` defaults if the file doesn't exist) and validates it against the pydantic models in `atlas/config/models.py`. `atlas/config/config.yaml` is an unrelated template fragment, not read by the loader. Config sections are added by adding a new pydantic `BaseModel` subclass and a field on `AtlasConfig`, following the existing `ProxmoxConfig`/`IntelligenceConfig` pattern.

**AI providers.** `atlas/intelligence/providers/` defines an `AIProvider` ABC (`base.py`) returning a schema-shaped `AnalysisResult`/`Recommendation`; `AnthropicProvider` and `OllamaProvider` both use structured/schema-constrained output so responses never need free-text parsing. `get_provider(config.intelligence)` is the factory (provider implementations are imported lazily inside it so the `anthropic` import isn't required just to build the config or use the Ollama path). `AtlasAnalyzer` (`atlas/intelligence/analyzer.py`) is a thin wrapper that just delegates to whichever provider it's given — put orchestration logic there, not in the CLI command.

**Rich-based CLI conventions.** Every `atlas/cli/main.py` command uses a shared `Console()` and follows the same shape: print a bold header, do the work, print results with `rich` color tags (`[green]✓ ...`, `[yellow]! ...`, `[red]...`), and for commands with a data dependency (`report`, `intelligence`, `analyze`), print a "Run: atlas discover" hint and return early rather than raising when no data exists yet.

## Code style notes

The existing codebase (outside `atlas/intelligence/providers/` and `tests/`, which are newer) is written with heavy vertical spacing — each function argument on its own line, a blank line after `def ...():` before the body, blank lines between most statements — and very few docstrings (mostly on classes, not functions). New code should generally match whatever file it's editing rather than importing a different style mid-file.

## Project philosophy (from CONTRIBUTING.md)

- **Local-first**: prefer self-hosted/local solutions where practical (e.g. the Ollama provider option alongside Anthropic).
- **Explainability**: Atlas should be able to explain what it's doing, why, the expected outcome, and any risk — reflected in both code and docs.
- **Safety**: changes affecting real infrastructure should be observable, logged, reversible where possible, and gated behind user approval — Atlas is meant to observe/recommend, not silently act.
