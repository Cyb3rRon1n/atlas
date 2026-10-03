"""
The web chat: the same AtlasAgent as `atlas chat`, behind /api/chat, with
in-memory per-browser sessions, plus Approve, which executes exactly one
suggested step after re-grounding it against live state. Pure of HTTP:
callers pass factories, so tests never touch an LLM or Docker.
"""

import secrets
import threading
import time

from atlas.actions import ACTIONS, PLAN_STEP_EVENT_TYPES, execute_action, is_action_grounded
from atlas.core.application import application
from atlas.events import AtlasEvent
from atlas.intelligence.providers.base import AIProviderError, SuggestedAction


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

    with sessions.lock:
        session_id, session = sessions.get_or_create(session_id, now)

        if session["turns"] >= sessions.max_turns:
            del sessions.sessions[session_id]
            session_id, session = sessions.get_or_create(None, now)
            return 200, {"session": session_id, "text": "This conversation is full - starting a new one. Ask again.",
                         "action": None, "plan": None, "reset": True}

        messages = list(session["messages"]) + [{"role": "user", "content": message}]

    # The LLM call happens outside the lock: it can take 10-30 s and must not block other sessions.
    try:
        reply = agent_factory().converse(messages)

    except AIProviderError as error:
        return 502, {"error": str(error)}

    data = reply_to_dict(reply)

    with sessions.lock:
        session["messages"] = messages
        session["turns"] += 1

    _publish("atlas.chat.turn", {"session": session_id, "question": message, "answer": data["text"],
                                 "action": data["action"], "plan": data["plan"]})

    return 200, {"session": session_id, **data}


def execute_step(action_data, environment_factory, executor=execute_action):
    """One approved step: re-ground against live state, run it, record it - same event as the CLI."""

    if not isinstance(action_data, dict) or action_data.get("type") not in ACTIONS \
            or not isinstance(action_data.get("target"), str):
        return 400, {"error": "action must be a known action type with a target"}

    action = SuggestedAction(**{key: action_data.get(key) for key in ACTION_FIELDS})

    if not is_action_grounded(action, environment_factory()):
        return 409, {"error": "target no longer exists / state changed"}

    result = executor(action)
    event_type = PLAN_STEP_EVENT_TYPES.get(action.type, "atlas.action.executed")
    _publish(event_type, {"target": action.target, "result": result})

    return 200, {"ok": bool(result.get("success")), "result": result}
