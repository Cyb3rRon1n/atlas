import json

import requests

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


class OllamaProvider(AIProvider):

    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        timeout: int = 240
    ):
        """
        timeout default was 120 before tool-use existed, when analyze()
        was always exactly one request. With tools enabled by default,
        a single analyze() call can now be several sequential requests
        (see _run_loop), each with a larger prompt (tool schemas) than
        before - measured against a real local llama3.1 with all six
        tools enabled, a single analyze() call took ~166s end to end,
        so 120s per individual request cut it close enough to actually
        fail. Doubled with headroom rather than tuned to the exact
        measurement.
        """

        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def analyze(self, context: dict, tools: dict | None = None) -> AnalysisResult:

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(context)}
        ]

        data = self._run_loop(messages, tools, ANALYSIS_SCHEMA)

        return AnalysisResult(
            summary=data["summary"],
            recommendations=[
                recommendation_from_dict(item)
                for item in data["recommendations"]
            ]
        )

    def converse(self, messages: list, tools: dict | None = None) -> ChatReply:

        full_messages = [
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
            *messages
        ]

        data = self._run_loop(full_messages, tools, CHAT_SCHEMA)

        messages.append({
            "role": "assistant",
            "content": data["text"]
        })

        return chat_reply_from_dict(data)

    def _run_loop(self, messages, tools, schema):
        """
        Unlike AnthropicProvider, tools and the schema-constrained
        format are never sent in the same request - verified against
        a real local llama3.1: with both present, the model silently
        never emits tool_calls and just answers directly (not an
        error, just quietly wrong), rather than calling a tool first.
        So this runs a tools-only round-trip loop (no format) until
        the model stops asking for tools, then one dedicated
        format-only request (no tools) to get the final schema-shaped
        answer from whatever the conversation now contains. When no
        tools are offered at all, that reduces to the original single
        request - unchanged from before tool support existed.
        """

        if not tools:
            return self._parse(self._request(messages, schema, None))

        ollama_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema
                }
            }
            for tool in tools.values()
        ]

        for _ in range(MAX_TOOL_ITERATIONS):

            message = self._request(messages, None, ollama_tools)

            tool_calls = message.get("tool_calls")

            if not tool_calls:
                break

            messages.append(message)

            for call in tool_calls:

                function = call.get("function", {})

                result = execute_tool(
                    tools,
                    function.get("name"),
                    function.get("arguments") or {}
                )

                messages.append({
                    "role": "tool",
                    "content": json.dumps(result)
                })

        else:

            raise AIProviderError(
                "Atlas gave up after too many tool calls without a final answer."
            )

        return self._parse(self._request(messages, schema, None))

    def _request(self, messages, schema, ollama_tools):

        payload = {
            "model": self.model,
            "stream": False,
            "messages": messages
        }

        if schema:
            payload["format"] = schema

        if ollama_tools:
            payload["tools"] = ollama_tools

        try:
            response = requests.post(
                f"{self.host}/api/chat",
                json=payload,
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

        return response.json().get("message", {})

    def _parse(self, message):

        text = message.get("content")

        if not text:
            raise AIProviderError(
                "Ollama response did not contain any message content."
            )

        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise AIProviderError(
                f"Ollama response was not valid JSON: {error}"
            ) from error
