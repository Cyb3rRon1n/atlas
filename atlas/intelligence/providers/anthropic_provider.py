import json

import anthropic

from atlas.intelligence.providers.base import (
    ANALYSIS_SCHEMA,
    SYSTEM_PROMPT,
    AIProvider,
    AIProviderError,
    AnalysisResult,
    recommendation_from_dict,
)


class AnthropicProvider(AIProvider):

    def __init__(self, model: str = "claude-opus-5"):

        self.model = model

        try:
            self.client = anthropic.Anthropic()
        except anthropic.AnthropicError as error:
            raise AIProviderError(
                f"Failed to initialize Anthropic client: {error}"
            ) from error

    def analyze(self, context: dict) -> AnalysisResult:

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                thinking={"type": "adaptive"},
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": ANALYSIS_SCHEMA
                    }
                },
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": json.dumps(context)
                    }
                ]
            )
        except anthropic.AuthenticationError as error:
            raise AIProviderError(
                "Anthropic authentication failed. Set the ANTHROPIC_API_KEY "
                "environment variable to a valid API key."
            ) from error
        except TypeError as error:
            if "authentication" not in str(error).lower():
                raise
            raise AIProviderError(
                "No Anthropic credentials found. Set the ANTHROPIC_API_KEY "
                "environment variable to a valid API key."
            ) from error
        except anthropic.APIConnectionError as error:
            raise AIProviderError(
                f"Could not reach the Anthropic API: {error}"
            ) from error
        except anthropic.APIStatusError as error:
            raise AIProviderError(
                f"Anthropic API error ({error.status_code}): {error.message}"
            ) from error

        if response.stop_reason == "refusal":
            raise AIProviderError(
                "Anthropic declined to analyze this environment."
            )

        text = next(
            (block.text for block in response.content if block.type == "text"),
            None
        )

        if text is None:
            raise AIProviderError(
                "Anthropic response did not contain any text content."
            )

        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise AIProviderError(
                f"Anthropic response was not valid JSON: {error}"
            ) from error

        return AnalysisResult(
            summary=data["summary"],
            recommendations=[
                recommendation_from_dict(item)
                for item in data["recommendations"]
            ]
        )
