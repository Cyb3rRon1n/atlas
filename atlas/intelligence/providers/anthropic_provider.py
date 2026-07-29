import json

import anthropic

from atlas.intelligence.providers.base import (
    ANALYSIS_SCHEMA,
    CHAT_SCHEMA,
    CHAT_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    AIProvider,
    AIProviderError,
    AnalysisResult,
    ChatReply,
    chat_reply_from_dict,
    recommendation_from_dict,
)
from atlas.intelligence.tools import execute_tool


MAX_TOOL_ITERATIONS = 6


class AnthropicProvider(AIProvider):

    def __init__(self, model: str = "claude-opus-5"):

        self.model = model

        try:
            self.client = anthropic.Anthropic()
        except anthropic.AnthropicError as error:
            raise AIProviderError(
                f"Failed to initialize Anthropic client: {error}"
            ) from error

    def analyze(self, context: dict, tools: dict | None = None) -> AnalysisResult:

        messages = [
            {
                "role": "user",
                "content": json.dumps(context)
            }
        ]

        data = self._run_loop(messages, tools, ANALYSIS_SCHEMA, SYSTEM_PROMPT)

        return AnalysisResult(
            summary=data["summary"],
            recommendations=[
                recommendation_from_dict(item)
                for item in data["recommendations"]
            ]
        )

    def converse(self, messages: list, tools: dict | None = None) -> ChatReply:

        data = self._run_loop(messages, tools, CHAT_SCHEMA, CHAT_SYSTEM_PROMPT)

        messages.append({
            "role": "assistant",
            "content": data["text"]
        })

        return chat_reply_from_dict(data)

    def _run_loop(self, messages, tools, schema, system_prompt):
        """
        Sends messages, and if the model asks to call a tool
        (stop_reason == "tool_use"), executes it and loops - same
        request each time (tools + the schema-constrained final
        format both present), so the model can either call another
        tool or produce the final answer. Capped so a confused model
        can't loop forever burning API cost.
        """

        anthropic_tools = (
            [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema
                }
                for tool in tools.values()
            ]
            if tools else None
        )

        for _ in range(MAX_TOOL_ITERATIONS):

            response = self._request(
                messages, schema, system_prompt, anthropic_tools
            )

            if response.stop_reason != "tool_use":
                return self._parse(response)

            messages.append({
                "role": "assistant",
                "content": response.content
            })

            tool_results = [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(
                        execute_tool(tools, block.name, block.input)
                    )
                }
                for block in response.content
                if block.type == "tool_use"
            ]

            messages.append({
                "role": "user",
                "content": tool_results
            })

        raise AIProviderError(
            "Atlas gave up after too many tool calls without a final answer."
        )

    def _request(self, messages, schema, system_prompt, anthropic_tools):

        kwargs = {
            "model": self.model,
            "max_tokens": 4096,
            "thinking": {"type": "adaptive"},
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": schema
                }
            },
            "system": system_prompt,
            "messages": messages
        }

        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        try:
            return self.client.messages.create(**kwargs)
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

    def _parse(self, response):

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
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise AIProviderError(
                f"Anthropic response was not valid JSON: {error}"
            ) from error
