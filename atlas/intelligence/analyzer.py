from atlas.actions import is_action_grounded
from atlas.intelligence.providers import AIProvider, AnalysisResult


class AtlasAnalyzer:
    """
    Runs an environment snapshot through an AI provider
    to produce a summary and recommendations.
    """

    def __init__(self, provider: AIProvider):

        self.provider = provider

    def analyze(self, environment: dict, tools: dict | None = None) -> AnalysisResult:

        result = self.provider.analyze(environment, tools)

        for recommendation in result.recommendations:

            action = recommendation.action

            if action and not is_action_grounded(action, environment):
                recommendation.action = None

        if result.plan and not all(
            is_action_grounded(step.action, environment)
            for step in result.plan.steps
        ):

            # A plan is a coherent whole in a way independent
            # recommendations aren't - one hallucinated step target
            # means dropping the entire plan rather than leaving a
            # broken partial sequence behind.
            result.plan = None

        return result
