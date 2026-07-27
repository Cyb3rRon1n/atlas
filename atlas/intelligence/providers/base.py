from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


Severity = Literal["info", "warning", "critical"]


@dataclass
class Recommendation:

    title: str
    detail: str
    severity: Severity


@dataclass
class AnalysisResult:

    summary: str
    recommendations: list[Recommendation] = field(
        default_factory=list
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
                    }
                },
                "required": ["title", "detail", "severity"],
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
    "significant stands out, say so and return an empty recommendations list."
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
