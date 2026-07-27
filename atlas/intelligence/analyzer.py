from atlas.intelligence.providers import AIProvider, AnalysisResult


class AtlasAnalyzer:
    """
    Runs an environment snapshot through an AI provider
    to produce a summary and recommendations.
    """

    def __init__(self, provider: AIProvider):

        self.provider = provider

    def analyze(self, environment: dict) -> AnalysisResult:

        return self.provider.analyze(environment)
