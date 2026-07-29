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
class AnalysisResult:

    summary: str
    recommendations: list[Recommendation] = field(
        default_factory=list
    )


@dataclass
class ChatReply:

    text: str
    action: SuggestedAction | None = None


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
        action=SuggestedAction(**action_data) if action_data else None
    )


# Shared by ANALYSIS_SCHEMA and CHAT_SCHEMA so a field added to what an
# action can carry (e.g. cpus/memory for resize_container) only needs
# to change in one place. cpus/memory are required-but-nullable, same
# "structured output requires every key in `required` even when the
# value itself is nullable" reasoning that already applies to `action`
# on the parent object - they're only meaningful for resize_container,
# always null on every other action type.
ACTION_SCHEMA = {
    "anyOf": [
        {
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
        }
    },
    "required": ["summary", "recommendations"],
    "additionalProperties": False
}


CHAT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string"
        },
        "action": ACTION_SCHEMA
    },
    "required": ["text", "action"],
    "additionalProperties": False
}


ACTION_INSTRUCTIONS = (
    "Atlas can currently execute four actions. (1) Restart a Docker "
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
    "memory unchanged - at least one of the two must be non-null. For every "
    "action type, \"cpus\" and \"memory\" must both be null except for "
    "resize_container. Only include an action when it would genuinely "
    "address the problem described in that recommendation. Most "
    "recommendations are not actionable this way and should leave "
    "\"action\" as null. Never invent a container name or vmid that is not "
    "present in the provided data."
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
    "empty recommendations list.\n\n" + ACTION_INSTRUCTIONS
)


CHAT_SYSTEM_PROMPT = (
    "You are Atlas, an infrastructure assistant having a conversation with "
    "the person operating a self-hosted environment. You have tools "
    "available to look up live container, service, Proxmox, and monitoring "
    "state, plus recent Atlas history - use them whenever you need current "
    "information to answer accurately rather than guessing. Answer "
    "naturally and concisely. Only include a structured action suggestion "
    "when it is genuinely warranted by what you actually observed via a "
    "tool call - most replies should leave it null.\n\n" + ACTION_INSTRUCTIONS
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
