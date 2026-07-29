from atlas.intelligence.analyzer import AtlasAnalyzer
from atlas.intelligence.providers.base import (
    AIProvider,
    AnalysisResult,
    PlanStep,
    Recommendation,
    SuggestedAction,
    SuggestedPlan,
)


class FakeProvider(AIProvider):

    def __init__(self, result: AnalysisResult):

        self.result = result
        self.received_context = None
        self.received_tools = None

    def analyze(self, context: dict, tools: dict | None = None) -> AnalysisResult:

        self.received_context = context
        self.received_tools = tools

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


def test_analyzer_keeps_plan_when_every_step_is_grounded():

    result = AnalysisResult(
        summary="...",
        plan=SuggestedPlan(
            summary="Recover the media stack",
            steps=[
                PlanStep(
                    action=SuggestedAction(type="stop_container", target="sonarr"),
                    rationale="sonarr is holding a lock radarr needs"
                ),
                PlanStep(
                    action=SuggestedAction(type="restart_container", target="radarr"),
                    rationale="will pick up cleanly once sonarr is stopped"
                ),
            ]
        )
    )

    analyzer = AtlasAnalyzer(FakeProvider(result))

    environment = {
        "containers": {
            "Docker": {
                "available": True,
                "containers": [
                    {"name": "sonarr", "status": "running"},
                    {"name": "radarr", "status": "running"},
                ]
            }
        }
    }

    analyzed = analyzer.analyze(environment)

    assert analyzed.plan is not None
    assert len(analyzed.plan.steps) == 2


def test_analyzer_drops_entire_plan_when_one_step_is_ungrounded():
    """
    A plan is a coherent whole, unlike independent recommendations -
    one hallucinated step target invalidates the whole sequence
    rather than leaving a partially-runnable plan behind.
    """

    result = AnalysisResult(
        summary="...",
        plan=SuggestedPlan(
            summary="Recover the media stack",
            steps=[
                PlanStep(
                    action=SuggestedAction(type="stop_container", target="sonarr"),
                    rationale="sonarr is holding a lock radarr needs"
                ),
                PlanStep(
                    action=SuggestedAction(type="restart_container", target="ghost"),
                    rationale="will pick up cleanly once sonarr is stopped"
                ),
            ]
        )
    )

    analyzer = AtlasAnalyzer(FakeProvider(result))

    environment = {
        "containers": {
            "Docker": {
                "available": True,
                "containers": [{"name": "sonarr", "status": "running"}]
            }
        }
    }

    analyzed = analyzer.analyze(environment)

    assert analyzed.plan is None


def test_analyzer_leaves_plan_as_none_when_no_plan_was_suggested():

    result = AnalysisResult(summary="Nothing to report.")

    analyzer = AtlasAnalyzer(FakeProvider(result))

    analyzed = analyzer.analyze({"system": {}})

    assert analyzed.plan is None


def test_analyzer_keeps_action_when_stop_target_is_a_known_container():

    result = AnalysisResult(
        summary="...",
        recommendations=[
            Recommendation(
                title="Container 'plex' is consuming excessive resources",
                detail="...",
                severity="warning",
                action=SuggestedAction(type="stop_container", target="plex")
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


def test_analyzer_drops_action_when_stop_target_is_not_a_known_container():

    result = AnalysisResult(
        summary="...",
        recommendations=[
            Recommendation(
                title="Container 'ghost' is consuming excessive resources",
                detail="...",
                severity="warning",
                action=SuggestedAction(type="stop_container", target="ghost")
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
