from sqlalchemy import create_engine

import lanxang.knowledge.queries as queries_module
import lanxang.knowledge.store as store_module
from lanxang.events import AtlasEvent
from lanxang.intelligence.context import AtlasEnvironmentContext
from lanxang.intelligence.providers.base import (
    AnalysisResult,
    Recommendation,
    SuggestedAction,
)
from lanxang.knowledge.queries import KnowledgeQueries
from lanxang.knowledge.store import KnowledgeStore


def test_recent_events_empty_when_nothing_stored(temp_db):

    assert KnowledgeQueries().recent_events() == []


def test_save_and_query_events(temp_db):

    store = KnowledgeStore()

    store.save_event(
        AtlasEvent(
            event_type="atlas.discovery.completed",
            source="test",
            payload={"ok": True}
        )
    )

    events = KnowledgeQueries().recent_events()

    assert len(events) == 1
    assert events[0].event_type == "atlas.discovery.completed"
    assert events[0].source == "test"


def test_latest_event_payload_picks_newest_of_type(temp_db):

    store = KnowledgeStore()
    assert KnowledgeQueries().latest_event_payload("atlas.proxmox.scan.completed") is None

    for event_type, payload in (("atlas.proxmox.scan.completed", {"n": 1}), ("other", {"n": 2}),
                                ("atlas.proxmox.scan.completed", {"n": 3})):
        store.save_event(AtlasEvent(event_type=event_type, source="test", payload=payload))

    assert KnowledgeQueries().latest_event_payload("atlas.proxmox.scan.completed") == {"n": 3}


def test_latest_environment_none_when_nothing_stored(temp_db):

    assert KnowledgeQueries().latest_environment() is None


def test_save_and_query_environment(temp_db):

    environment = AtlasEnvironmentContext()

    environment.ingest_discovery(
        {"system": {"hostname": "homelab"}}
    )

    KnowledgeStore().save_environment(environment)

    latest = KnowledgeQueries().latest_environment()

    assert latest["system"] == {"hostname": "homelab"}


def test_environment_history_empty_when_nothing_stored(temp_db):

    assert KnowledgeQueries().environment_history() == []


def test_environment_history_returns_rows_most_recent_first(temp_db):

    store = KnowledgeStore()

    first = AtlasEnvironmentContext()
    first.ingest_discovery({"system": {"hostname": "first"}})
    store.save_environment(first)

    second = AtlasEnvironmentContext()
    second.ingest_discovery({"system": {"hostname": "second"}})
    store.save_environment(second)

    history = KnowledgeQueries().environment_history()

    assert len(history) == 2
    assert history[0]["data"]["system"] == {"hostname": "second"}
    assert history[1]["data"]["system"] == {"hostname": "first"}


def test_environment_history_respects_limit(temp_db):

    store = KnowledgeStore()

    for index in range(5):

        environment = AtlasEnvironmentContext()
        environment.ingest_discovery({"system": {"hostname": str(index)}})
        store.save_environment(environment)

    history = KnowledgeQueries().environment_history(limit=2)

    assert len(history) == 2
    assert history[0]["data"]["system"] == {"hostname": "4"}
    assert history[1]["data"]["system"] == {"hostname": "3"}


def test_latest_analysis_none_when_nothing_stored(temp_db):

    assert KnowledgeQueries().latest_analysis() is None


def test_save_and_query_analysis(temp_db):

    result = AnalysisResult(
        summary="All good.",
        recommendations=[
            Recommendation(
                title="Add monitoring",
                detail="No monitoring stack detected.",
                severity="info"
            ),
            Recommendation(
                title="Container 'plex' looks unhealthy",
                detail="Restarted 4 times in the last hour.",
                severity="warning",
                action=SuggestedAction(type="restart_container", target="plex")
            )
        ]
    )

    KnowledgeStore().save_analysis(
        result,
        provider="anthropic",
        model="claude-opus-5"
    )

    latest = KnowledgeQueries().latest_analysis()

    assert latest["summary"] == "All good."
    assert latest["provider"] == "anthropic"
    assert latest["model"] == "claude-opus-5"
    assert latest["recommendations"] == [
        {
            "title": "Add monitoring",
            "detail": "No monitoring stack detected.",
            "severity": "info",
            "action": None
        },
        {
            "title": "Container 'plex' looks unhealthy",
            "detail": "Restarted 4 times in the last hour.",
            "severity": "warning",
            "action": {"type": "restart_container", "target": "plex"}
        }
    ]


def test_store_and_queries_self_heal_a_database_with_no_tables(tmp_path, monkeypatch):
    """
    Regression test: the committed inventory/atlas.db once predated
    AnalysisRecord and was missing the 'analysis' table entirely, and
    nothing called initialize_database() automatically - so the first
    real save_analysis()/latest_analysis() call crashed with
    'no such table: analysis'. Every KnowledgeStore/KnowledgeQueries
    method now self-heals by creating any missing tables on first use.
    """

    engine = create_engine(
        f"sqlite:///{tmp_path / 'no-tables-yet.db'}"
    )

    monkeypatch.setattr(store_module, "engine", engine)
    monkeypatch.setattr(queries_module, "engine", engine)

    assert KnowledgeQueries().latest_analysis() is None

    KnowledgeStore().save_analysis(
        AnalysisResult(summary="ok", recommendations=[]),
        provider="anthropic",
        model="claude-opus-5"
    )

    assert KnowledgeQueries().latest_analysis()["summary"] == "ok"

    engine.dispose()


def test_initialize_database_creates_parent_directory_for_default_engine(
    tmp_path, monkeypatch
):
    """
    Regression test: initialize_database()'s directory-creation branch
    used to check `if engine is None`, but every real call site
    (KnowledgeStore/KnowledgeQueries) passes its own bound `engine`
    explicitly rather than relying on the default argument, so that
    branch never actually fired outside of a direct, no-argument call -
    meaning a genuinely fresh directory with no inventory/ folder yet
    (e.g. running any command other than `atlas discover`, whose
    save_inventory() incidentally creates inventory/ as a side effect
    and was masking this) crashed with "unable to open database file".
    The fix compares identity against `default_engine` instead.

    Uses a fully isolated, absolute-path engine (not the process-wide
    lanxang.database.engine.engine singleton) - that singleton bakes in
    an absolute path the first time anything imports it, so reusing it
    across a cwd change within the same process (as pytest's
    isolated_cwd fixture does) doesn't behave like a real, separate
    `atlas` invocation and risks touching the real local database.
    """

    import lanxang.database as database_module

    fresh_path = tmp_path / "inventory" / "atlas.db"
    fresh_engine = create_engine(f"sqlite:///{fresh_path}")

    monkeypatch.setattr(database_module, "DATABASE_PATH", fresh_path)
    monkeypatch.setattr(database_module, "default_engine", fresh_engine)

    assert not fresh_path.parent.exists()

    database_module.initialize_database(fresh_engine)

    assert fresh_path.parent.exists()

    fresh_engine.dispose()


def test_latest_environment_fills_parts_the_newest_save_left_empty(temp_db):
    """Each atlas-scan command saves only its own part; the newest row alone used to look nearly empty."""

    store = KnowledgeStore()
    for part in ({"system": {"hostname": "homelab"}, "containers": {"web": 1}}, {"system": {"hostname": "newer"}},
                 {"topology": {"lan": []}}):
        environment = AtlasEnvironmentContext()
        for key, value in part.items():
            environment.update(key, value)                             # what the commands do
        store.save_environment(environment)

    latest = KnowledgeQueries().latest_environment()
    assert latest["topology"] == {"lan": []}
    assert latest["system"] == {"hostname": "newer"}                  # the most recent one that has it
    assert latest["containers"] == {"web": 1}
    assert KnowledgeQueries().environment_history(1)[0]["data"]["system"] in (None, {}, [])   # rows stay as saved
