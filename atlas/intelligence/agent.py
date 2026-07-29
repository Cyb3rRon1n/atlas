from atlas.actions import is_action_grounded
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

        if not reply.action and not reply.plan:
            return reply

        environment = self._live_environment()

        if reply.action and not is_action_grounded(reply.action, environment):
            reply.action = None

        if reply.plan and not all(
            is_action_grounded(step.action, environment)
            for step in reply.plan.steps
        ):

            # Same "drop the whole plan on one bad step" rule
            # AtlasAnalyzer applies - see its analyze() for why.
            reply.plan = None

        if reply.plan and reply.action:

            # Seen in real testing: the model can propose a plan and
            # still fill in the standalone action (usually a copy of
            # the plan's own first step), which would print as a
            # redundant "suggested action" alongside the plan. The
            # prompt asks the model not to do this, but that's not
            # enforced - same reasoning as grounding above.
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
