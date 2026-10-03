"""
The web chat: the same AtlasAgent as `atlas chat`, behind /api/chat, with
in-memory per-browser sessions, plus Approve, which executes exactly one
suggested step after re-grounding it against live state. Pure of HTTP:
callers pass factories, so tests never touch an LLM or Docker.
"""

import math
import secrets
import threading
import time

import docker

from atlas.actions import ACTIONS, PLAN_STEP_EVENT_TYPES, execute_action, is_action_grounded
from atlas.core.application import application
from atlas.events import AtlasEvent
from atlas.intelligence.providers.base import AIProviderError, SuggestedAction


RESIZE_TYPES = {action_type for action_type in ACTIONS if action_type.startswith("resize_")}


ACTION_FIELDS = ("type", "target", "cpus", "memory")


def _publish(event_type, payload):

    try:
        application.runtime.events.publish(AtlasEvent(event_type=event_type, source="AtlasWeb", payload=payload))

    except Exception as error:  # the action/answer already happened; a logging failure must not hide it
        print(f"atlas web: could not record {event_type}: {error}")


class ChatSessions:

    def __init__(self, idle_seconds=7200, max_turns=20):

        self.idle_seconds = idle_seconds
        self.max_turns = max_turns
        self.lock = threading.Lock()
        self.sessions = {}

    def prune(self, now=None):

        now = time.time() if now is None else now

        for key in [key for key, session in self.sessions.items() if now - session["last"] > self.idle_seconds]:
            del self.sessions[key]

    def get_or_create(self, session_id, now=None):

        now = time.time() if now is None else now
        self.prune(now)

        if session_id not in self.sessions:
            session_id = secrets.token_urlsafe(16)
            self.sessions[session_id] = {"messages": [], "turns": 0, "last": now}

        self.sessions[session_id]["last"] = now

        return session_id, self.sessions[session_id]


def _action_dict(action):

    definition = ACTIONS.get(action.type)
    data = {key: getattr(action, key) for key in ACTION_FIELDS}
    data["command"] = definition.command_template(action) if definition else None

    return data


def reply_to_dict(reply):

    return {
        "text": reply.text,
        "action": _action_dict(reply.action) if reply.action else None,
        "plan": {
            "summary": reply.plan.summary,
            "steps": [{"action": _action_dict(step.action), "rationale": step.rationale} for step in reply.plan.steps],
        } if reply.plan else None,
    }


def chat_turn(sessions, session_id, message, agent_factory, now=None):

    if not isinstance(message, str) or not message.strip():
        return 400, {"error": "message must be non-empty text"}

    if session_id is not None and not isinstance(session_id, str):  # a non-str id from JSON means "no session"
        session_id = None

    with sessions.lock:
        session_id, session = sessions.get_or_create(session_id, now)

        if session["turns"] >= sessions.max_turns:
            del sessions.sessions[session_id]
            session_id, session = sessions.get_or_create(None, now)
            return 200, {"session": session_id, "text": "This conversation is full - starting a new one. Ask again.",
                         "action": None, "plan": None, "reset": True}

        messages = list(session["messages"]) + [{"role": "user", "content": message}]

    # The LLM call happens outside the lock: it can take 10-30 s and must not block other sessions.
    # A copy is passed in: AtlasAgent.converse() may hand the provider a *different* list
    # (e.g. _with_notes() copies when notes are configured) and only that copy ever gets the
    # assistant reply appended to it - messages here must never be relied on to have been
    # mutated. The assistant turn is added explicitly below instead, as a plain dict.
    try:
        reply = agent_factory().converse(list(messages))

    except AIProviderError as error:
        return 502, {"error": str(error)}

    data = reply_to_dict(reply)
    new_messages = messages + [{"role": "assistant", "content": data["text"]}]

    with sessions.lock:
        # ponytail: last-writer-wins if two turns on the same session race -
        # no per-turn ordering guarantee; a per-session queue would fix that
        # if concurrent chat on one browser tab ever becomes real.
        if sessions.sessions.get(session_id) is session:
            session["messages"] = new_messages
            session["turns"] += 1

    _publish("atlas.chat.turn", {"session": session_id, "question": message, "answer": data["text"],
                                 "action": data["action"], "plan": data["plan"]})

    return 200, {"session": session_id, **data}


def _validate_cpus(cpus):
    """cpus must be a str or number (never bool) that parses to a positive, finite float."""

    if isinstance(cpus, bool) or not isinstance(cpus, (str, int, float)):
        return None, "cpus must be a number or a numeric string"

    try:
        parsed = float(cpus)

    except (TypeError, ValueError):
        return None, "cpus must be a number or a numeric string"

    if not math.isfinite(parsed) or parsed <= 0:
        return None, "cpus must be a positive, finite number"

    # Kept as the caller gave it (a string stays that exact string) - the
    # registry's resize executors read action.cpus back through float()
    # themselves, so there's nothing to reformat, only validate.
    return (cpus if isinstance(cpus, str) else str(cpus)), None


def _validate_memory(memory):
    """memory must be a string docker.utils.parse_bytes() accepts, for a positive size."""

    if not isinstance(memory, str):
        return None, "memory must be a size string (e.g. '512m')"

    try:
        parsed = docker.utils.parse_bytes(memory)

    except Exception:
        return None, "memory must be a size string docker.utils.parse_bytes() accepts (e.g. '512m')"

    if not parsed or parsed <= 0:
        return None, "memory must be a positive size"

    return memory, None


def _validate_action_data(action_data):
    """
    The browser controls this input end to end, so every field is checked before it
    ever becomes a SuggestedAction - an unhashable type, a non-str target, or
    cpus/memory on the wrong kind of action must 400, never raise.
    """

    if not isinstance(action_data, dict):
        return None, "action must be a known action type with a target"

    action_type = action_data.get("type")

    if not isinstance(action_type, str) or action_type not in ACTIONS:
        return None, "action must be a known action type with a target"

    target = action_data.get("target")

    if not isinstance(target, str) or not target:
        return None, "action must be a known action type with a target"

    cpus, memory = action_data.get("cpus"), action_data.get("memory")

    if action_type in RESIZE_TYPES:

        if cpus is None and memory is None:
            return None, "a resize action needs cpus and/or memory"

        if cpus is not None:
            cpus, error = _validate_cpus(cpus)
            if error:
                return None, error

        if memory is not None:
            memory, error = _validate_memory(memory)
            if error:
                return None, error

    elif cpus is not None or memory is not None:
        return None, "cpus/memory only apply to a resize action"

    return SuggestedAction(type=action_type, target=target, cpus=cpus, memory=memory), None


def execute_step(action_data, environment_factory, executor=execute_action):
    """One approved step: re-ground against live state, run it, record it - same event as the CLI."""

    action, error = _validate_action_data(action_data)

    if error:
        return 400, {"error": error}

    if not is_action_grounded(action, environment_factory()):
        return 409, {"error": "target no longer exists / state changed"}

    try:
        result = executor(action)

    except Exception as error:  # the browser is waiting on a real response, not a 500
        result = {"success": False, "error": str(error)}

    event_type = PLAN_STEP_EVENT_TYPES.get(action.type, "atlas.action.executed")
    _publish(event_type, {"target": action.target, "result": result})

    return 200, {"ok": bool(result.get("success")), "result": result}
