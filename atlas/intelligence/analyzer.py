from atlas.actions import ACTIONS
from atlas.intelligence.providers import AIProvider, AnalysisResult


class AtlasAnalyzer:
    """
    Runs an environment snapshot through an AI provider
    to produce a summary and recommendations.
    """

    def __init__(self, provider: AIProvider):

        self.provider = provider

    def analyze(self, environment: dict) -> AnalysisResult:

        result = self.provider.analyze(environment)

        for recommendation in result.recommendations:

            action = recommendation.action

            if not action:
                continue

            definition = ACTIONS.get(action.type)

            if not definition or action.target not in definition.known_targets(environment):
                recommendation.action = None

        return result
