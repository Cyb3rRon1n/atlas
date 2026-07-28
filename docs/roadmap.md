# Roadmap

## Shipped

- Python CLI application, configuration management
- Hardware, OS, storage, and network discovery
- Inventory generation and reporting
- Docker discovery and known-service detection ([Service Catalog](service-catalog.md))
- Docker Compose analysis
- Event-driven system with persistent operational history
- Plugin architecture (currently: a Docker plugin)
- **Proxmox integration** — node discovery, cluster-wide VM/container inventory, API token authentication
- **AI analysis engine** — `atlas analyze`, pluggable Anthropic/Ollama providers, structured recommendations
- Test suite (125 tests) and CI (GitHub Actions, Python 3.11/3.12)
- **Unified discovery** — `atlas discover` now runs built-in discovery and every registered plugin in one pass, saving one complete environment snapshot; the separate `atlas discover-plugins` command was removed once its job was folded in
- **First automation action** — `atlas restart <name>` restarts a Docker container after showing its state and requiring confirmation, logged via the event bus. The first Atlas command that acts rather than observes — see [Architecture](architecture/index.md#approval-gated-actions). Along the way, found and fixed a real bug: the event bus's knowledge-store listener was defined but never actually registered, so no published event had ever been persisted (`atlas history` was effectively non-functional before this).
- **`atlas analyze` suggests actions** — recommendations carry a schema-validated, optional `action` field (currently just `restart_container`); `AtlasAnalyzer` cross-checks the suggested target against containers Atlas actually observed and drops anything ungrounded before it's shown. `atlas analyze` only prints the suggestion (`→ Suggested: atlas restart plex`) — running it is a separate step through `atlas restart`'s own approval gate, not something `analyze` executes itself.
- **Proxmox change detection** — `atlas proxmox scan` now reports what changed since the last scan (nodes/guests added, removed, or status-changed) and logs it via `atlas.proxmox.changes_detected`. This turned out not to need new storage: `save_environment()` was already insert-only, so a full history of past snapshots already existed in the database — this item was mis-scoped before it was actually looked into, the same way the event-listener registration gap was.
- **Monitoring integration** — `atlas monitor` queries an existing Prometheus server for host CPU/memory/disk usage via standard `node_exporter` metrics, following the same "Atlas reaches out on command" shape as every other integration rather than exposing a `/metrics` endpoint. Disabled by default; built and tested against mocked Prometheus responses, not yet verified against a live Prometheus since none exists in this environment yet — see [Architecture](architecture/index.md#monitoring).
- **Fixed: database tables were never created automatically.** `atlas.database.initialize_database()` existed but nothing called it, and the (then still committed) `inventory/atlas.db` predated the `AnalysisRecord` model — so `atlas analyze` would crash on its very first real use (`no such table: analysis`), and a genuinely fresh install with no pre-existing db would crash on *any* command that touches the database. Fixed by calling `initialize_database()` lazily at the top of every `KnowledgeStore`/`KnowledgeQueries` method rather than at construction time — construction happens as part of the `AtlasRuntime` singleton built at module import, so doing it there would create/mutate the database using whatever the process's cwd happens to be at first import (e.g. the real repo root during a `pytest` run), not the user's actual working directory. Verified against a copy of the (then still committed) db (existing rows untouched, missing table added) and against a fresh directory with no `inventory/` at all.
- **`inventory/atlas.db` un-tracked from git.** It grows a new row on every command run and now self-heals its own schema (above), so there was nothing left it needed to seed — keeping it committed just meant every real usage session against real hardware would show up as a binary diff to commit. It's gitignored now; the file still exists locally and nothing about its behavior changed.
- **`atlas doctor` readiness checks** — now also checks the three integrations that were previously invisible to it: Proxmox (enabled + host + credentials present), the AI provider (`ANTHROPIC_API_KEY` set for Anthropic; no key needed for Ollama), and Prometheus (enabled + URL present). These are config/presence checks, not live connection attempts — `doctor` stays fast and never hangs waiting on a network call. A disabled integration reports healthy (`✓ Proxmox: disabled`) since that's a valid, intentional state, not a problem; only "enabled but misconfigured" reports unhealthy. This is what actually answers "is this ready for my real setup" from the command line instead of by hand.
- **Second automation action: `atlas proxmox restart <vmid>`** — restarts a Proxmox VM or LXC guest, the same approval-gated shape as `atlas restart` for Docker (pure result-dict manager function, unconditional `typer.confirm()`, logged via the event bus). This forced the action framework's first real generalization, previously only ever exercised with one action type: `ANALYSIS_SCHEMA`'s `action.type` enum, `AtlasAnalyzer`'s target-grounding check, and `analyze()`'s suggested-command print all moved from a single hardcoded case to small lookup dicts (`TARGET_VALIDATORS`, `action_commands`) keyed by action type — see [Architecture](architecture/index.md#approval-gated-actions). Needs write/power-management permission on the Proxmox token beyond the read-only scope `scan` uses. Along the way, found and fixed two more real bugs in the database-initialization fix from the previous entry: (1) the directory-creation check compared `engine is None`, which no real call site ever satisfies (`KnowledgeStore`/`KnowledgeQueries` always pass their bound `engine` explicitly) — it never actually ran outside a direct no-argument call, masked until now because every prior manual test happened to run `atlas discover` first, whose unrelated `save_inventory()` creates the same parent directory as a side effect; (2) while writing the regression test, discovered that reusing the real `atlas.database.engine.engine` singleton across an in-process `chdir()` (what pytest's `isolated_cwd` fixture does) silently read/wrote the developer's real local database, since SQLAlchemy resolves a relative sqlite path to absolute once at engine-creation time, not per-connection — a test-safety hazard, not a product bug, but real enough that it needed a dedicated fully-isolated-engine regression test rather than reusing the shared singleton.

## In progress / next

- **Verification against real infrastructure.** Proxmox, both AI providers (Anthropic/Ollama), and Prometheus are real, tested code — but every test so far has been against mocks, never the actual live systems, since none existed in the development environment. This is tracked as its own milestone rather than left implicit: it gets checked off integration-by-integration as each is actually run against real hardware, distinct from "built and unit-tested." `atlas doctor`'s readiness checks confirm config is *present*, not that the target is actually reachable — that's still what this milestone covers.
- **Broader automation framework** — the action *registry* is real now (two dicts, above), but there's still no generic `atlas/actions/` framework where an action is its own pluggable unit; each action is still its own CLI command plus its own manager module, by convention rather than structure. A third action (container removal, VM start/stop, etc.) is what would force that next layer.
- **Deeper monitoring** — container-level metrics (cAdvisor), threshold/alerting on the metrics `atlas monitor` already collects, and wiring monitoring data into the change-detection pattern built for Proxmox. All deferred until there's a real Prometheus to validate against.
- Agent-based capabilities

## Guiding principle

Every step up this list is expected to remain consistent with Atlas's core loop:

```mermaid
graph LR
    A[Observe] --> B[Understand]
    B --> C[Recommend]
    C --> D[Automate with approval]
```

Automation is the last step, not the first — Atlas earns the right to act by first being reliably right about what it observes and recommends.
