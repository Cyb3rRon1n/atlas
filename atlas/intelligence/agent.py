from atlas.actions import ACTIONS
from atlas.config.models import AtlasConfig
from atlas.intelligence.providers import AIProvider, ChatReply
from atlas.intelligence.tools import build_tools, execute_tool


class AtlasAgent:
    """
    Runs a multi-turn conversation through an AI provider's tool-use
    loop, backing atlas chat. Plays the same orchestration role
    AtlasAnalyzer plays for atlas analyze's single-shot flow, but for
    an ongoing session that has no guaranteed prior atlas discover.
    """

    def __init__(self, provider: AIProvider, config: AtlasConfig):

        self.provider = provider
        self.config = config
        self.tools = build_tools(config)

    def converse(self, messages: list) -> ChatReply:

        reply = self.provider.converse(messages, self.tools)

        action = reply.action

        if not action:
            return reply

        definition = ACTIONS.get(action.type)

        if not definition or action.target not in definition.known_targets(self._live_environment()):
            reply.action = None

        return reply

    def _live_environment(self) -> dict:
        """
        A minimal, freshly-queried stand-in for the saved environment
        snapshot atlas analyze grounds suggested actions against.
        Chat has no guaranteed prior atlas discover to read a
        snapshot from, so it grounds against current live state
        instead - the same read paths the get_containers/
        get_proxmox_status tools already use, not a second copy of
        the connection logic.
        """

        from atlas.docker import collect_containers

        environment = {
            "containers": {
                "Docker": collect_containers()
            }
        }

        if "get_proxmox_status" in self.tools:

            proxmox_data = execute_tool(self.tools, "get_proxmox_status", {})

            environment["virtualization"] = {
                "guests": proxmox_data.get("guests", [])
            }

        return environment
