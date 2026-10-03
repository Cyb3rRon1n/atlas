import json

import pytest

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


class CopyingFakeAgent:
    """
    Mimics AtlasAgent._with_notes(): when notes are configured, converse()
    is handed a *copy* of messages and appends the assistant reply to that
    copy only - the original list passed in is never mutated. chat_turn
    must not rely on that mutation to preserve history.
    """

    def __init__(self, reply):
        self.reply, self.seen = reply, []

    def converse(self, messages):
        self.seen.append([dict(message) for message in messages])
        copied = list(messages)
        copied.append({"role": "assistant", "content": "never stored - this is the agent's own copy"})
        return self.reply


RESTART = SuggestedAction(type="restart_container", target="sonarr")

ENVIRONMENT = {"containers": {"Docker": {"containers": [{"name": "sonarr"}]}}}


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
    assert {"role": "assistant", "content": "All good."} in agent.seen[1]

    event = KnowledgeQueries().recent_events(5)[0]
    assert event.event_type == "atlas.chat.turn"


def test_turn_history_survives_agent_copying_messages_before_appending(temp_db):
    """
    IMPORTANT regression test: AtlasAgent.converse() can hand the provider a
    *copy* of messages (_with_notes() does this whenever notes are
    configured) and only append the assistant reply to that copy - chat_turn
    must still store the assistant's own reply itself, not rely on the
    agent having mutated what it was given.
    """

    sessions = ChatSessions()
    agent = CopyingFakeAgent(ChatReply(text="ok"))

    sid = chat_turn(sessions, None, "first", lambda: agent, now=0)[1]["session"]
    chat_turn(sessions, sid, "second", lambda: agent, now=1)

    assert agent.seen[1] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "second"},
    ]


def test_turn_provider_error_is_502_and_question_not_kept(temp_db):

    sessions = ChatSessions()
    agent = FakeAgent(reply=ChatReply(text="All good."))

    sid = chat_turn(sessions, None, "hello", lambda: agent, now=0)[1]["session"]
    messages_before = list(sessions.sessions[sid]["messages"])
    turns_before = sessions.sessions[sid]["turns"]

    failing_agent = FakeAgent(error=AIProviderError("Ollama unreachable"))
    status, payload = chat_turn(sessions, sid, "boom", lambda: failing_agent, now=1)

    assert status == 502 and payload == {"error": "Ollama unreachable"}
    assert sessions.sessions[sid]["messages"] == messages_before
    assert sessions.sessions[sid]["turns"] == turns_before


def test_blank_message_is_400(temp_db):

    assert chat_turn(ChatSessions(), None, "   ", lambda: FakeAgent(reply=ChatReply(text="x")))[0] == 400


def test_non_str_session_id_is_treated_as_new_session(temp_db):

    sessions = ChatSessions()
    agent = FakeAgent(reply=ChatReply(text="ok"))

    status, payload = chat_turn(sessions, 12345, "hello", lambda: agent, now=0)

    assert status == 200 and isinstance(payload["session"], str) and payload["session"] != 12345


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

    calls = []

    def executor(action):
        calls.append(action)
        return {"success": True, "previous_status": "running"}

    status, payload = execute_step({"type": "restart_container", "target": "sonarr"}, lambda: ENVIRONMENT, executor)
    assert status == 200 and payload == {"ok": True, "result": {"success": True, "previous_status": "running"}}
    assert calls[0].target == "sonarr"
    event = KnowledgeQueries().recent_events(5)[0]
    assert event.event_type == "atlas.action.container_restarted" and event.source == "AtlasWeb"


def test_execute_step_refuses_ungrounded_and_malformed(temp_db):

    def executor(action):
        raise AssertionError("must not run")

    assert execute_step({"type": "restart_container", "target": "ghost"}, lambda: ENVIRONMENT, executor) == \
        (409, {"error": "target no longer exists / state changed"})
    assert execute_step({"type": "format_disk", "target": "sonarr"}, lambda: ENVIRONMENT, executor)[0] == 400
    assert execute_step({"target": "sonarr"}, lambda: ENVIRONMENT, executor)[0] == 400
    assert execute_step("restart sonarr", lambda: ENVIRONMENT, executor)[0] == 400


def test_execute_step_rejects_unhashable_type(temp_db):

    def executor(action):
        raise AssertionError("must not run")

    status, payload = execute_step({"type": ["restart_container"], "target": "sonarr"}, lambda: ENVIRONMENT, executor)
    assert status == 400


def test_execute_step_rejects_non_str_target(temp_db):

    def executor(action):
        raise AssertionError("must not run")

    status, payload = execute_step({"type": "restart_container", "target": 123}, lambda: ENVIRONMENT, executor)
    assert status == 400


def test_execute_step_resize_requires_cpus_or_memory(temp_db):

    def executor(action):
        raise AssertionError("must not run")

    status, payload = execute_step({"type": "resize_container", "target": "sonarr"}, lambda: ENVIRONMENT, executor)
    assert status == 400


@pytest.mark.parametrize("cpus", ["abc", "nan", "inf", True])
def test_execute_step_rejects_bad_cpus(temp_db, cpus):

    def executor(action):
        raise AssertionError("must not run")

    status, payload = execute_step(
        {"type": "resize_container", "target": "sonarr", "cpus": cpus}, lambda: ENVIRONMENT, executor
    )
    assert status == 400


@pytest.mark.parametrize("memory", ["abc", ["512m"]])
def test_execute_step_rejects_bad_memory(temp_db, memory):

    def executor(action):
        raise AssertionError("must not run")

    status, payload = execute_step(
        {"type": "resize_container", "target": "sonarr", "memory": memory}, lambda: ENVIRONMENT, executor
    )
    assert status == 400


def test_execute_step_rejects_cpus_on_non_resize_type(temp_db):

    def executor(action):
        raise AssertionError("must not run")

    status, payload = execute_step(
        {"type": "restart_container", "target": "sonarr", "cpus": "0.5"}, lambda: ENVIRONMENT, executor
    )
    assert status == 400


def test_execute_step_executor_exception_becomes_ok_false(temp_db):

    def executor(action):
        raise RuntimeError("docker exploded")

    status, payload = execute_step({"type": "restart_container", "target": "sonarr"}, lambda: ENVIRONMENT, executor)

    assert status == 200
    assert payload == {"ok": False, "result": {"success": False, "error": "docker exploded"}}

    event = KnowledgeQueries().recent_events(5)[0]
    assert event.event_type == "atlas.action.container_restarted"
    assert json.loads(event.payload)["result"] == {"success": False, "error": "docker exploded"}


def test_execute_step_docker_unavailable_gives_503_and_does_not_run(temp_db):

    def executor(action):
        raise AssertionError("must not run")

    environment = {"containers": {"Docker": {"available": False, "containers": []}}}

    status, payload = execute_step({"type": "restart_container", "target": "sonarr"}, lambda: environment, executor)

    assert status == 503 and payload == {"error": "could not check live state: Docker unavailable"}


def test_execute_step_proxmox_error_gives_503_and_does_not_run(temp_db):

    def executor(action):
        raise AssertionError("must not run")

    environment = {"virtualization": {"guests": [], "error": "Could not reach Proxmox at https://pve:8006."}}

    status, payload = execute_step({"type": "restart_guest", "target": "100"}, lambda: environment, executor)

    assert status == 503 and payload == {"error": "could not check live state: Proxmox unavailable"}


def test_execute_step_missing_target_with_docker_available_stays_409(temp_db):

    def executor(action):
        raise AssertionError("must not run")

    environment = {"containers": {"Docker": {"available": True, "containers": [{"name": "sonarr"}]}}}

    status, payload = execute_step({"type": "restart_container", "target": "ghost"}, lambda: environment, executor)

    assert status == 409 and payload == {"error": "target no longer exists / state changed"}


def test_execute_step_valid_resize_reaches_executor_intact(temp_db):

    calls = []

    def executor(action):
        calls.append(action)
        return {"success": True}

    status, payload = execute_step(
        {"type": "resize_container", "target": "sonarr", "cpus": "0.5"}, lambda: ENVIRONMENT, executor
    )

    assert status == 200 and payload["ok"] is True
    assert calls[0].type == "resize_container"
    assert calls[0].target == "sonarr"
    assert calls[0].cpus == "0.5"
    assert calls[0].memory is None
