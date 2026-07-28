from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


Severity = Literal["info", "warning", "critical"]


@dataclass
class SuggestedAction:

    type: str
    target: str


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
                    "action": {
                        "anyOf": [
                            {
                                "type": "object",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "enum": ["restart_container", "restart_guest"]
                                    },
                                    "target": {"type": "string"}
                                },
                                "required": ["type", "target"],
                                "additionalProperties": False
                            },
                            {"type": "null"}
                        ]
                    }
                },
                "required": ["title", "detail", "severity", "action"],
                "additionalProperties": False
            }
        }
    },
    "required": ["summary", "recommendations"],
    "additionalProperties": False
}


SYSTEM_PROMPT = (
    "You are Atlas, an infrastructure advisor for a self-hosted homelab. "
    "You are given a JSON snapshot of the environment's discovered state "
    "(system, hardware, storage, network, services, containers, virtualization). "
    "Write a short plain-language summary of the environment's current state, "
    "then list concrete, actionable recommendations grounded in specifics from "
    "the provided data (exact device names, container names, utilization figures). "
    "Do not give generic advice that isn't backed by the data. If nothing "
    "significant stands out, say so and return an empty recommendations list.\n\n"
    "Atlas can currently execute two actions. (1) Restart a Docker container "
    "(action type \"restart_container\", with \"target\" set to a container "
    "name that literally appears in the provided containers data). (2) "
    "Restart a Proxmox VM or LXC container (action type \"restart_guest\", "
    "with \"target\" set to the guest's vmid, as a string, that literally "
    "appears in the provided virtualization guest data - use the vmid, not "
    "the guest's name, since that is its stable identifier). Only include "
    "an action when restarting that specific container or guest would "
    "genuinely address the problem described in that recommendation - it "
    "is crash-looping, unhealthy, unexpectedly exited, or stopped when it "
    "should be running. Most recommendations are not actionable this way "
    "and should leave \"action\" as null. Never invent a container name or "
    "vmid that is not present in the provided data."
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
    def analyze(self, context: dict) -> AnalysisResult:
        ...
