from unittest.mock import patch

from atlas.config.models import AtlasConfig
from atlas.intelligence.agent import AtlasAgent
from atlas.intelligence.providers.base import (
    AIProvider,
    ChatReply,
    PlanStep,
    SuggestedAction,
    SuggestedPlan,
)


class FakeProvider(AIProvider):

    def __init__(self, reply: ChatReply):

        self.reply = reply
        self.received_messages = None
        self.received_tools = None

    def analyze(self, context, tools=None):
        raise NotImplementedError

    def converse(self, messages, tools=None):

        self.received_messages = messages
        self.received_tools = tools

        return self.reply


def test_converse_keeps_action_when_target_is_a_known_container():

    reply = ChatReply(
        text="I'll flag plex for a restart.",
        action=SuggestedAction(type="restart_container", target="plex")
    )

    agent = AtlasAgent(FakeProvider(reply), AtlasConfig())

    with patch(
        "atlas.docker.collect_containers",
        return_value={"available": True, "containers": [{"name": "plex"}]}
    ):

        result = agent.converse([{"role": "user", "content": "how's plex?"}])

    assert result.action is not None
    assert result.action.target == "plex"


def test_converse_drops_action_for_hallucinated_container():

    reply = ChatReply(
        text="I'll flag ghost for a restart.",
        action=SuggestedAction(type="restart_container", target="ghost")
    )

    agent = AtlasAgent(FakeProvider(reply), AtlasConfig())

    with patch(
        "atlas.docker.collect_containers",
        return_value={"available": True, "containers": [{"name": "plex"}]}
    ):

        result = agent.converse([{"role": "user", "content": "how's ghost?"}])

    assert result.action is None


def test_converse_passes_no_action_through_unchanged():

    reply = ChatReply(text="Nothing stands out right now.", action=None)

    agent = AtlasAgent(FakeProvider(reply), AtlasConfig())

    with patch(
        "atlas.docker.collect_containers",
        return_value={"available": True, "containers": []}
    ):

        result = agent.converse([{"role": "user", "content": "how's it going?"}])

    assert result.action is None
    assert result.text == "Nothing stands out right now."


def test_converse_keeps_plan_when_every_step_is_grounded():

    reply = ChatReply(
        text="Here's how to recover the media stack.",
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

    agent = AtlasAgent(FakeProvider(reply), AtlasConfig())

    with patch(
        "atlas.docker.collect_containers",
        return_value={
            "available": True,
            "containers": [{"name": "sonarr"}, {"name": "radarr"}]
        }
    ):

        result = agent.converse([{"role": "user", "content": "help me recover"}])

    assert result.plan is not None
    assert len(result.plan.steps) == 2


def test_converse_clears_standalone_action_when_a_plan_is_also_present():
    """
    Seen against a real Ollama model: it filled in both a plan and a
    standalone action (a copy of the plan's first step), which would
    print as a redundant suggestion alongside the plan.
    """

    reply = ChatReply(
        text="Here's how to recover the media stack.",
        action=SuggestedAction(type="stop_container", target="sonarr"),
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

    agent = AtlasAgent(FakeProvider(reply), AtlasConfig())

    with patch(
        "atlas.docker.collect_containers",
        return_value={
            "available": True,
            "containers": [{"name": "sonarr"}, {"name": "radarr"}]
        }
    ):

        result = agent.converse([{"role": "user", "content": "help me recover"}])

    assert result.plan is not None
    assert result.action is None


def test_converse_drops_entire_plan_when_one_step_is_ungrounded():

    reply = ChatReply(
        text="Here's how to recover the media stack.",
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

    agent = AtlasAgent(FakeProvider(reply), AtlasConfig())

    with patch(
        "atlas.docker.collect_containers",
        return_value={"available": True, "containers": [{"name": "sonarr"}]}
    ):

        result = agent.converse([{"role": "user", "content": "help me recover"}])

    assert result.plan is None


def test_agent_builds_tools_from_config_once():

    config = AtlasConfig()
    config.monitoring.enabled = True

    agent = AtlasAgent(FakeProvider(ChatReply(text="ok")), config)

    assert "get_monitoring" in agent.tools
    assert "get_proxmox_status" not in agent.tools
