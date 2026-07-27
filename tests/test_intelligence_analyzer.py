from atlas.intelligence.analyzer import AtlasAnalyzer
from atlas.intelligence.providers.base import (
    AIProvider,
    AnalysisResult,
    Recommendation,
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
