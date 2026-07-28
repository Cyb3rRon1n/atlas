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


def known_guest_ids(environment: dict) -> set[str]:
    """
    Flatten every Proxmox guest vmid Atlas actually observed, as
    strings (action targets are always strings) - matches by vmid,
    not name, same stable-identifier principle as
    atlas.proxmox.changes.diff_virtualization.
    """

    guests = environment.get("virtualization", {}).get("guests", [])

    return {
        str(guest["vmid"])
        for guest in guests
        if "vmid" in guest
    }


TARGET_VALIDATORS = {
    "restart_container": known_container_names,
    "restart_guest": known_guest_ids,
}


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

            validator = TARGET_VALIDATORS.get(action.type)

            if not validator or action.target not in validator(environment):
                recommendation.action = None

        return result
