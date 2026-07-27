from atlas.intelligence.providers import AIProvider, AnalysisResult


def known_container_names(environment: dict) -> set[str]:
    """
    Flatten every container name Atlas actually observed, across all
    discovery plugins, e.g. environment["containers"] ==
    {"Docker": {"available": True, "containers": [{"name": "plex", ...}]}}.
    """

    names = set()

    for plugin_data in environment.get("containers", {}).values():

        for container in plugin_data.get("containers", []):

            if "name" in container:
                names.add(container["name"])

    return names


class AtlasAnalyzer:
    """
    Runs an environment snapshot through an AI provider
    to produce a summary and recommendations.
    """

    def __init__(self, provider: AIProvider):

        self.provider = provider

    def analyze(self, environment: dict) -> AnalysisResult:

        result = self.provider.analyze(environment)

        known_containers = known_container_names(environment)

        for recommendation in result.recommendations:

            if (
                recommendation.action
                and recommendation.action.target not in known_containers
            ):
                recommendation.action = None

        return result
