from atlas.intelligence.analyzer import (
    AtlasAnalyzer,
    known_container_names,
    known_guest_ids,
)
from atlas.intelligence.providers.base import (
    AIProvider,
    AnalysisResult,
    Recommendation,
    SuggestedAction,
)


class FakeProvider(AIProvider):

    def __init__(self, result: AnalysisResult):

        self.result = result
        self.received_context = None

    def analyze(self, context: dict) -> AnalysisResult:

        self.received_context = context

        return self.result


def test_analyzer_delegates_to_provider_and_returns_its_result():

    expected = AnalysisResult(
        summary="All good.",
        recommendations=[
            Recommendation(
                title="Add monitoring",
                detail="No monitoring stack was detected.",
                severity="info"
            )
        ]
    )

    provider = FakeProvider(expected)
    analyzer = AtlasAnalyzer(provider)

    environment = {"system": {"hostname": "sentinel"}}

    result = analyzer.analyze(environment)

    assert provider.received_context is environment
    assert result is expected


def test_known_container_names_flattens_across_plugins():

    environment = {
        "containers": {
            "Docker": {
                "available": True,
                "containers": [
                    {"name": "plex", "status": "running"},
                    {"name": "sonarr", "status": "exited"},
                ]
            }
        }
    }

    assert known_container_names(environment) == {"plex", "sonarr"}


def test_known_container_names_empty_when_no_containers_key():

    assert known_container_names({"system": {}}) == set()


def test_analyzer_keeps_action_when_target_is_a_known_container():

    result = AnalysisResult(
        summary="...",
        recommendations=[
            Recommendation(
                title="Container 'plex' looks unhealthy",
                detail="...",
                severity="warning",
                action=SuggestedAction(type="restart_container", target="plex")
            )
        ]
    )

    analyzer = AtlasAnalyzer(FakeProvider(result))

    environment = {
        "containers": {
            "Docker": {
                "available": True,
                "containers": [{"name": "plex", "status": "running"}]
            }
        }
    }

    analyzed = analyzer.analyze(environment)

    assert analyzed.recommendations[0].action.target == "plex"


def test_analyzer_drops_action_when_target_is_not_a_known_container():
    """
    Guards against surfacing a hallucinated container name as if it
    were grounded in what Atlas actually observed.
    """

    result = AnalysisResult(
        summary="...",
        recommendations=[
            Recommendation(
                title="Container 'ghost' looks unhealthy",
                detail="...",
                severity="warning",
                action=SuggestedAction(type="restart_container", target="ghost")
            )
        ]
    )

    analyzer = AtlasAnalyzer(FakeProvider(result))

    environment = {
        "containers": {
            "Docker": {
                "available": True,
                "containers": [{"name": "plex", "status": "running"}]
            }
        }
    }

    analyzed = analyzer.analyze(environment)

    assert analyzed.recommendations[0].action is None


def test_known_guest_ids_flattens_vmids_as_strings():

    environment = {
        "virtualization": {
            "nodes": [{"name": "pve1", "status": "online"}],
            "guests": [
                {"vmid": 100, "name": "plex", "type": "qemu", "status": "running"},
                {"vmid": 101, "name": "pihole", "type": "lxc", "status": "stopped"},
            ]
        }
    }

    assert known_guest_ids(environment) == {"100", "101"}


def test_known_guest_ids_empty_when_no_virtualization_key():

    assert known_guest_ids({"system": {}}) == set()


def test_analyzer_keeps_action_when_target_is_a_known_guest():

    result = AnalysisResult(
        summary="...",
        recommendations=[
            Recommendation(
                title="Guest 100 is stopped",
                detail="...",
                severity="warning",
                action=SuggestedAction(type="restart_guest", target="100")
            )
        ]
    )

    analyzer = AtlasAnalyzer(FakeProvider(result))

    environment = {
        "virtualization": {
            "nodes": [],
            "guests": [{"vmid": 100, "name": "plex", "type": "qemu", "status": "stopped"}]
        }
    }

    analyzed = analyzer.analyze(environment)

    assert analyzed.recommendations[0].action.target == "100"


def test_analyzer_drops_action_when_target_is_not_a_known_guest():

    result = AnalysisResult(
        summary="...",
        recommendations=[
            Recommendation(
                title="Guest 999 is stopped",
                detail="...",
                severity="warning",
                action=SuggestedAction(type="restart_guest", target="999")
            )
        ]
    )

    analyzer = AtlasAnalyzer(FakeProvider(result))

    environment = {
        "virtualization": {
            "nodes": [],
            "guests": [{"vmid": 100, "name": "plex", "type": "qemu", "status": "running"}]
        }
    }

    analyzed = analyzer.analyze(environment)

    assert analyzed.recommendations[0].action is None


def test_analyzer_drops_action_with_unrecognized_type():
    """
    Defensive: an action type outside the registry is never trusted,
    even if its target happens to match something real - guards
    against a schema/prompt drifting apart from what analyze() knows
    how to validate.
    """

    result = AnalysisResult(
        summary="...",
        recommendations=[
            Recommendation(
                title="Container 'plex' looks unhealthy",
                detail="...",
                severity="warning",
                action=SuggestedAction(type="delete_everything", target="plex")
            )
        ]
    )

    analyzer = AtlasAnalyzer(FakeProvider(result))

    environment = {
        "containers": {
            "Docker": {
                "available": True,
                "containers": [{"name": "plex", "status": "running"}]
            }
        }
    }

    analyzed = analyzer.analyze(environment)

    assert analyzed.recommendations[0].action is None
