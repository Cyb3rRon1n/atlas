from atlas.intelligence.providers.base import AIProviderError, ChatReply, PlanStep, SuggestedAction, SuggestedPlan
from atlas.knowledge.queries import KnowledgeQueries
from atlas.web.chat import ChatSessions, chat_turn, execute_step, reply_to_dict


class FakeAgent:

    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.seen = reply, error, []

    def converse(self, messages):
        self.seen.append([dict(message) for message in messages])
        if self.error:
            raise self.error
        return self.reply


RESTART = SuggestedAction(type="restart_container", target="sonarr")


def test_reply_to_dict_adds_commands_and_is_json_plain():

    reply = ChatReply(text="Sonarr is stuck.", action=RESTART,
                      plan=SuggestedPlan(summary="Bounce it", steps=[PlanStep(action=RESTART, rationale="unstick")]))

    data = reply_to_dict(reply)

    assert data["text"] == "Sonarr is stuck."
    assert data["action"] == {"type": "restart_container", "target": "sonarr", "cpus": None, "memory": None,
                              "command": "atlas restart sonarr"}
    assert data["plan"]["steps"][0]["action"]["command"] == "atlas restart sonarr"
    assert data["plan"]["steps"][0]["rationale"] == "unstick"
    assert reply_to_dict(ChatReply(text="hi")) == {"text": "hi", "action": None, "plan": None}


def test_turn_keeps_history_per_session_and_logs_event(temp_db):

    sessions = ChatSessions()
    agent = FakeAgent(reply=ChatReply(text="All good."))

    status, first = chat_turn(sessions, None, "is jellyfin up?", lambda: agent, now=0)
    assert status == 200 and first["text"] == "All good." and first["session"]

    chat_turn(sessions, first["session"], "and sonarr?", lambda: agent, now=10)
    assert [m["content"] for m in agent.seen[1] if m["role"] == "user"] == ["is jellyfin up?", "and sonarr?"]

    event = KnowledgeQueries().recent_events(5)[0]
    assert event.event_type == "atlas.chat.turn"


def test_turn_provider_error_is_502_and_question_not_kept(temp_db):

    sessions = ChatSessions()
    status, payload = chat_turn(sessions, None, "hello", lambda: FakeAgent(error=AIProviderError("Ollama unreachable")), now=0)

    assert status == 502 and payload == {"error": "Ollama unreachable"}


def test_blank_message_is_400(temp_db):

    assert chat_turn(ChatSessions(), None, "   ", lambda: FakeAgent(reply=ChatReply(text="x")))[0] == 400


def test_sessions_expire_and_cap_turns(temp_db):

    sessions = ChatSessions(idle_seconds=100, max_turns=2)
    agent = FakeAgent(reply=ChatReply(text="ok"))

    sid = chat_turn(sessions, None, "1", lambda: agent, now=0)[1]["session"]
    chat_turn(sessions, sid, "2", lambda: agent, now=1)
    status, full = chat_turn(sessions, sid, "3", lambda: agent, now=2)
    assert status == 200 and full.get("reset") is True and full["session"] != sid

    later = chat_turn(sessions, full["session"], "x", lambda: agent, now=500)[1]
    assert later["session"] != full["session"]


def test_execute_step_grounds_runs_and_logs(temp_db):

    environment = {"containers": {"Docker": {"containers": [{"name": "sonarr"}]}}}
    calls = []

    def executor(action):
        calls.append(action)
        return {"success": True, "previous_status": "running"}

    status, payload = execute_step({"type": "restart_container", "target": "sonarr"}, lambda: environment, executor)
    assert status == 200 and payload == {"ok": True, "result": {"success": True, "previous_status": "running"}}
    assert calls[0].target == "sonarr"
    event = KnowledgeQueries().recent_events(5)[0]
    assert event.event_type == "atlas.action.container_restarted" and event.source == "AtlasWeb"


def test_execute_step_refuses_ungrounded_and_malformed(temp_db):

    environment = {"containers": {"Docker": {"containers": [{"name": "sonarr"}]}}}

    def executor(action):
        raise AssertionError("must not run")

    assert execute_step({"type": "restart_container", "target": "ghost"}, lambda: environment, executor) == \
        (409, {"error": "target no longer exists / state changed"})
    assert execute_step({"type": "format_disk", "target": "sonarr"}, lambda: environment, executor)[0] == 400
    assert execute_step({"target": "sonarr"}, lambda: environment, executor)[0] == 400
    assert execute_step("restart sonarr", lambda: environment, executor)[0] == 400
