from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

from atlas.actions import ACTIONS


Severity = Literal["info", "warning", "critical"]


@dataclass
class SuggestedAction:

    type: str
    target: str
    cpus: str | None = None
    memory: str | None = None


@dataclass
class Recommendation:

    title: str
    detail: str
    severity: Severity
    action: SuggestedAction | None = None


@dataclass
class PlanStep:

    action: SuggestedAction
    rationale: str


@dataclass
class SuggestedPlan:

    summary: str
    steps: list[PlanStep]


@dataclass
class AnalysisResult:

    summary: str
    recommendations: list[Recommendation] = field(
        default_factory=list
    )
    plan: SuggestedPlan | None = None


@dataclass
class ChatReply:

    text: str
    action: SuggestedAction | None = None
    plan: SuggestedPlan | None = None


def recommendation_from_dict(item: dict) -> Recommendation:
    """
    Shared by every provider so the action dict -> SuggestedAction
    conversion lives in one place rather than being duplicated per
    provider.
    """

    action_data = item.get("action")

    return Recommendation(
        title=item["title"],
        detail=item["detail"],
        severity=item["severity"],
        action=SuggestedAction(**action_data) if action_data else None
    )


def chat_reply_from_dict(item: dict) -> ChatReply:
    """
    Same shared-conversion role as recommendation_from_dict(), for the
    chat path's smaller {text, action} shape.
    """

    action_data = item.get("action")

    return ChatReply(
        text=item["text"],
        action=SuggestedAction(**action_data) if action_data else None,
        plan=plan_from_dict(item.get("plan"))
    )


def plan_from_dict(data: dict | None) -> SuggestedPlan | None:
    """
    Shared by every provider so the plan dict -> SuggestedPlan
    conversion lives in one place, same role recommendation_from_dict()/
    chat_reply_from_dict() play for the single-action shape.
    """

    if not data:
        return None

    return SuggestedPlan(
        summary=data["summary"],
        steps=[
            PlanStep(
                action=SuggestedAction(**step["action"]),
                rationale=step["rationale"]
            )
            for step in data["steps"]
        ]
    )


# The action-object shape itself, factored out so both the single
# optional `action` field (ACTION_SCHEMA, nullable) and each plan
# step's action (PLAN_SCHEMA, not nullable - a step without an action
# doesn't mean anything) reference the same definition rather than
# duplicating it a third time. cpus/memory are required-but-nullable,
# same "structured output requires every key in `required` even when
# the value itself is nullable" reasoning that already applies to
# `action` on the parent object - they're only meaningful for
# resize_container, always null on every other action type.
ACTION_OBJECT_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": list(ACTIONS.keys())
        },
        "target": {"type": "string"},
        "cpus": {
            "anyOf": [{"type": "string"}, {"type": "null"}]
        },
        "memory": {
            "anyOf": [{"type": "string"}, {"type": "null"}]
        }
    },
    "required": ["type", "target", "cpus", "memory"],
    "additionalProperties": False
}


# Shared by ANALYSIS_SCHEMA and CHAT_SCHEMA so a field added to what an
# action can carry only needs to change in one place.
ACTION_SCHEMA = {
    "anyOf": [
        ACTION_OBJECT_SCHEMA,
        {"type": "null"}
    ]
}


# Shared by ANALYSIS_SCHEMA and CHAT_SCHEMA, same reuse rationale as
# ACTION_SCHEMA. A plan is reserved for a genuine ordered, multi-target
# sequence - most responses leave it null and use the single `action`
# field on a Recommendation/ChatReply instead. See PLAN_INSTRUCTIONS.
PLAN_SCHEMA = {
    "anyOf": [
        {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": ACTION_OBJECT_SCHEMA,
                            "rationale": {"type": "string"}
                        },
                        "required": ["action", "rationale"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["summary", "steps"],
            "additionalProperties": False
        },
        {"type": "null"}
    ]
}


ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string"
        },
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["info", "warning", "critical"]
                    },
                    "action": ACTION_SCHEMA
                },
                "required": ["title", "detail", "severity", "action"],
                "additionalProperties": False
            }
        },
        "plan": PLAN_SCHEMA
    },
    "required": ["summary", "recommendations", "plan"],
    "additionalProperties": False
}


CHAT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string"
        },
        "action": ACTION_SCHEMA,
        "plan": PLAN_SCHEMA
    },
    "required": ["text", "action", "plan"],
    "additionalProperties": False
}


ACTION_INSTRUCTIONS = (
    "Atlas can currently execute six actions. (1) Restart a Docker "
    "container (action type \"restart_container\", with \"target\" set to a "
    "container name that literally appears in the provided containers data) "
    "- use when that container is crash-looping, unhealthy, unexpectedly "
    "exited, or stopped when it should be running. (2) Restart a Proxmox VM "
    "or LXC container (action type \"restart_guest\", with \"target\" set to "
    "the guest's vmid, as a string, that literally appears in the provided "
    "virtualization guest data - use the vmid, not the guest's name, since "
    "that is its stable identifier) - same trigger conditions as (1). (3) "
    "Stop a Docker container (action type \"stop_container\", with "
    "\"target\" set to a container name that literally appears in the "
    "provided containers data) - use only when a running container is "
    "itself the problem (e.g. consuming excessive resources, or should not "
    "be running at all), not as a way to fix a crash-looping container - "
    "that calls for restart_container instead. (4) Resize a Docker "
    "container's CPU and/or memory limit (action type \"resize_container\", "
    "with \"target\" set to a container name that literally appears in the "
    "provided containers data) - use when a container is being throttled by "
    "its own configured limit while it genuinely needs more (e.g. pinned "
    "near 100% of its own CPU or memory allocation), or is significantly "
    "over-provisioned relative to its actual usage and could safely be "
    "reduced. Set \"cpus\" to the new CPU limit in cores as a string (e.g. "
    "\"1.5\") or null to leave CPU unchanged, and \"memory\" to the new "
    "memory limit as a string (e.g. \"512m\", \"1g\") or null to leave "
    "memory unchanged - at least one of the two must be non-null. (5) Stop "
    "a Proxmox VM or LXC guest (action type \"stop_guest\", with \"target\" "
    "set to the guest's vmid as a string) - same trigger conditions as (3): "
    "the running guest itself is the problem, not a way to fix a "
    "crash-looping one. (6) Resize a Proxmox guest's CPU and/or memory "
    "limit (action type \"resize_guest\", with \"target\" set to the "
    "guest's vmid as a string) - same trigger conditions and \"cpus\"/"
    "\"memory\" rules as (4); note this changes the guest's cpulimit/memory "
    "cap, not how many CPUs or how much RAM the guest OS sees. For every "
    "action type, \"cpus\" and \"memory\" must both be null except for "
    "resize_container and resize_guest. Only include an action when it "
    "would genuinely address the problem described in that recommendation. "
    "Most recommendations are not actionable this way and should leave "
    "\"action\" as null. Never invent a container name or vmid that is not "
    "present in the provided data."
)


PLAN_INSTRUCTIONS = (
    "You may also propose a \"plan\": an ordered sequence of steps toward "
    "one goal, each step an action plus a short rationale. Use a plan ONLY "
    "when the situation genuinely needs multiple actions in a specific "
    "order because later steps depend on earlier ones (e.g. a container "
    "needs to be stopped before restarting a different one that was "
    "failing because of it). Do NOT use a plan for several independent, "
    "unrelated issues - each of those should be its own separate "
    "recommendation with its own single action instead. Every step's "
    "action must follow the exact same rules as a single action above "
    "(grounded target, correct fields for that action type). When you "
    "propose a plan, leave the standalone \"action\" field null - a plan "
    "step's action must not also be repeated as the standalone action. "
    "Most responses should leave \"plan\" as null."
)


SYSTEM_PROMPT = (
    "You are Atlas, an infrastructure advisor for a self-hosted homelab. "
    "You are given a JSON snapshot of the environment's discovered state "
    "(system, hardware, storage, network, services, containers, virtualization). "
    "You may also have tools available to pull live data beyond that fixed "
    "snapshot - use them when you need current information the snapshot "
    "doesn't have. Write a short plain-language summary of the environment's "
    "current state, then list concrete, actionable recommendations grounded "
    "in specifics from the data (exact device names, container names, "
    "utilization figures). Do not give generic advice that isn't backed by "
    "the data. If nothing significant stands out, say so and return an "
    "empty recommendations list.\n\n" + ACTION_INSTRUCTIONS + "\n\n" + PLAN_INSTRUCTIONS
)


CHAT_SYSTEM_PROMPT = (
    "You are Atlas, an infrastructure assistant having a conversation with "
    "the person operating a self-hosted environment. You have tools "
    "available to look up live container, service, Proxmox, and monitoring "
    "state, plus recent Atlas history - use them whenever you need current "
    "information to answer accurately rather than guessing. Answer "
    "naturally and concisely. Only include a structured action suggestion "
    "when it is genuinely warranted by what you actually observed via a "
    "tool call - most replies should leave it null.\n\n" + ACTION_INSTRUCTIONS + "\n\n" + PLAN_INSTRUCTIONS
)


class AIProviderError(Exception):
    """
    Raised when an AI provider cannot complete an analysis
    (missing credentials, unreachable service, malformed response).
    """


class AIProvider(ABC):
    """
    Common interface for AI backends that can analyze
    an Atlas environment context and return recommendations.
    """

    @abstractmethod
    def analyze(self, context: dict, tools: dict | None = None) -> AnalysisResult:
        ...

    def converse(self, messages: list, tools: dict | None = None) -> ChatReply:
        """
        Multi-turn chat with optional tool use, backing atlas chat. Not
        abstract - a provider (or a test double) that only implements
        analyze() is still a valid AIProvider; it just can't back chat.
        """

        raise NotImplementedError(
            f"{type(self).__name__} does not support conversational chat."
        )
