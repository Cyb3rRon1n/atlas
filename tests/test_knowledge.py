from atlas.events import AtlasEvent
from atlas.intelligence.context import AtlasEnvironmentContext
from atlas.intelligence.providers.base import (
    AnalysisResult,
    Recommendation,
    SuggestedAction,
)
from atlas.knowledge.queries import KnowledgeQueries
from atlas.knowledge.store import KnowledgeStore


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


def test_latest_environment_none_when_nothing_stored(temp_db):

    assert KnowledgeQueries().latest_environment() is None


def test_save_and_query_environment(temp_db):

    environment = AtlasEnvironmentContext()

    environment.ingest_discovery(
        {"system": {"hostname": "sentinel"}}
    )

    KnowledgeStore().save_environment(environment)

    latest = KnowledgeQueries().latest_environment()

    assert latest["system"] == {"hostname": "sentinel"}


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
