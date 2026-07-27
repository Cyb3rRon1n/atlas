import json

import requests

from atlas.intelligence.providers.base import (
    ANALYSIS_SCHEMA,
    SYSTEM_PROMPT,
    AIProvider,
    AIProviderError,
    AnalysisResult,
    recommendation_from_dict,
)


class OllamaProvider(AIProvider):

    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        timeout: int = 120
    ):

        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def analyze(self, context: dict) -> AnalysisResult:

        try:
            response = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "format": ANALYSIS_SCHEMA,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(context)}
                    ]
                },
                timeout=self.timeout
            )
            response.raise_for_status()
        except requests.exceptions.ConnectionError as error:
            raise AIProviderError(
                f"Could not reach Ollama at {self.host}. "
                "Is Ollama running?"
            ) from error
        except requests.exceptions.Timeout as error:
            raise AIProviderError(
                f"Ollama request timed out after {self.timeout}s."
            ) from error
        except requests.exceptions.HTTPError as error:
            raise AIProviderError(
                f"Ollama API error: {error}"
            ) from error

        payload = response.json()
        text = payload.get("message", {}).get("content")

        if not text:
            raise AIProviderError(
                "Ollama response did not contain any message content."
            )

        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise AIProviderError(
                f"Ollama response was not valid JSON: {error}"
            ) from error

        return AnalysisResult(
            summary=data["summary"],
            recommendations=[
                recommendation_from_dict(item)
                for item in data["recommendations"]
            ]
        )
