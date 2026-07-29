import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from atlas.intelligence.providers.anthropic_provider import AnthropicProvider
from atlas.intelligence.providers.base import AIProviderError
from atlas.intelligence.providers.ollama_provider import OllamaProvider
from atlas.intelligence.tools import ToolDefinition


SAMPLE_CONTEXT = {"system": {"hostname": "sentinel"}}

SAMPLE_CHAT_RESPONSE_JSON = json.dumps({
    "text": "Everything looks fine right now.",
    "action": None
})

FAKE_TOOLS = {
    "get_containers": ToolDefinition(
        name="get_containers",
        description="Get the current live list of Docker containers.",
        input_schema={"type": "object", "properties": {}},
        handler=lambda: {"containers": [{"name": "plex", "status": "running"}]}
    )
}

SAMPLE_RESPONSE_JSON = json.dumps({
    "summary": "One host, lightly loaded.",
    "recommendations": [
        {
            "title": "Enable swap",
            "detail": "No swap device was detected on sentinel.",
            "severity": "warning",
            "action": None
        },
        {
            "title": "Container 'plex' looks unhealthy",
            "detail": "Restarted 4 times in the last hour.",
            "severity": "warning",
            "action": {"type": "restart_container", "target": "plex"}
        }
    ]
})


def _fake_message(text: str, stop_reason: str = "end_turn"):

    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=text)]
    )


def _fake_tool_use_message(tool_name: str, tool_input: dict, tool_use_id: str = "tool_1"):

    return SimpleNamespace(
        stop_reason="tool_use",
        content=[
            SimpleNamespace(
                type="tool_use",
                id=tool_use_id,
                name=tool_name,
                input=tool_input
            )
        ]
    )


class TestAnthropicProvider:

    def test_analyze_sends_expected_request_shape(self):

        with patch("anthropic.Anthropic") as mock_client_cls:

            mock_client = MagicMock()
            mock_client.messages.create.return_value = _fake_message(
                SAMPLE_RESPONSE_JSON
            )
            mock_client_cls.return_value = mock_client

            provider = AnthropicProvider(model="claude-opus-5")
            result = provider.analyze(SAMPLE_CONTEXT)

            _, kwargs = mock_client.messages.create.call_args

            assert kwargs["model"] == "claude-opus-5"
            assert kwargs["thinking"] == {"type": "adaptive"}
            assert kwargs["output_config"]["format"]["type"] == "json_schema"
            assert json.loads(
                kwargs["messages"][0]["content"]
            ) == SAMPLE_CONTEXT

            recommendation_schema = (
                kwargs["output_config"]["format"]["schema"]
                ["properties"]["recommendations"]["items"]
            )
            assert "action" in recommendation_schema["properties"]
            assert "action" in recommendation_schema["required"]

            assert result.summary == "One host, lightly loaded."
            assert len(result.recommendations) == 2
            assert result.recommendations[0].severity == "warning"
            assert result.recommendations[0].action is None
            assert result.recommendations[1].action.type == "restart_container"
            assert result.recommendations[1].action.target == "plex"

    def test_refusal_raises_provider_error(self):

        with patch("anthropic.Anthropic") as mock_client_cls:

            mock_client = MagicMock()
            mock_client.messages.create.return_value = _fake_message(
                "", stop_reason="refusal"
            )
            mock_client_cls.return_value = mock_client

            provider = AnthropicProvider()

            with pytest.raises(AIProviderError):
                provider.analyze(SAMPLE_CONTEXT)

    def test_authentication_error_maps_to_provider_error(self):

        with patch("anthropic.Anthropic") as mock_client_cls:

            mock_client = MagicMock()
            mock_client.messages.create.side_effect = anthropic.AuthenticationError(
                message="invalid x-api-key",
                response=MagicMock(status_code=401, headers={}),
                body=None
            )
            mock_client_cls.return_value = mock_client

            provider = AnthropicProvider()

            with pytest.raises(AIProviderError, match="ANTHROPIC_API_KEY"):
                provider.analyze(SAMPLE_CONTEXT)

    def test_missing_credentials_type_error_maps_to_provider_error(self):
        """
        The SDK raises a bare TypeError (not AuthenticationError) when no
        credential source resolves at all - this happens at request-build
        time, not at Anthropic() construction time.
        """

        with patch("anthropic.Anthropic") as mock_client_cls:

            mock_client = MagicMock()
            mock_client.messages.create.side_effect = TypeError(
                "Could not resolve authentication method. Expected one of "
                "api_key, auth_token, or credentials to be set."
            )
            mock_client_cls.return_value = mock_client

            provider = AnthropicProvider()

            with pytest.raises(AIProviderError, match="ANTHROPIC_API_KEY"):
                provider.analyze(SAMPLE_CONTEXT)

    def test_unrelated_type_error_is_not_swallowed(self):

        with patch("anthropic.Anthropic") as mock_client_cls:

            mock_client = MagicMock()
            mock_client.messages.create.side_effect = TypeError(
                "unrelated bug"
            )
            mock_client_cls.return_value = mock_client

            provider = AnthropicProvider()

            with pytest.raises(TypeError, match="unrelated bug"):
                provider.analyze(SAMPLE_CONTEXT)

    def test_analyze_calls_tool_then_returns_final_answer(self):

        with patch("anthropic.Anthropic") as mock_client_cls:

            mock_client = MagicMock()
            mock_client.messages.create.side_effect = [
                _fake_tool_use_message("get_containers", {}),
                _fake_message(SAMPLE_RESPONSE_JSON)
            ]
            mock_client_cls.return_value = mock_client

            provider = AnthropicProvider(model="claude-opus-5")
            result = provider.analyze(SAMPLE_CONTEXT, tools=FAKE_TOOLS)

            assert mock_client.messages.create.call_count == 2

            first_kwargs = mock_client.messages.create.call_args_list[0].kwargs
            assert first_kwargs["tools"] == [
                {
                    "name": "get_containers",
                    "description": "Get the current live list of Docker containers.",
                    "input_schema": {"type": "object", "properties": {}}
                }
            ]

            second_kwargs = mock_client.messages.create.call_args_list[1].kwargs
            tool_result_message = second_kwargs["messages"][-1]
            assert tool_result_message["role"] == "user"
            assert tool_result_message["content"][0]["tool_use_id"] == "tool_1"
            assert json.loads(tool_result_message["content"][0]["content"]) == {
                "containers": [{"name": "plex", "status": "running"}]
            }

            assert result.summary == "One host, lightly loaded."

    def test_analyze_without_tools_never_sends_tools_kwarg(self):

        with patch("anthropic.Anthropic") as mock_client_cls:

            mock_client = MagicMock()
            mock_client.messages.create.return_value = _fake_message(
                SAMPLE_RESPONSE_JSON
            )
            mock_client_cls.return_value = mock_client

            provider = AnthropicProvider()
            provider.analyze(SAMPLE_CONTEXT)

            _, kwargs = mock_client.messages.create.call_args
            assert "tools" not in kwargs

    def test_analyze_gives_up_after_max_tool_iterations(self):

        with patch("anthropic.Anthropic") as mock_client_cls:

            mock_client = MagicMock()
            mock_client.messages.create.return_value = _fake_tool_use_message(
                "get_containers", {}
            )
            mock_client_cls.return_value = mock_client

            provider = AnthropicProvider()

            with pytest.raises(AIProviderError, match="too many tool calls"):
                provider.analyze(SAMPLE_CONTEXT, tools=FAKE_TOOLS)

    def test_converse_returns_reply_and_appends_assistant_turn(self):

        with patch("anthropic.Anthropic") as mock_client_cls:

            mock_client = MagicMock()
            mock_client.messages.create.return_value = _fake_message(
                SAMPLE_CHAT_RESPONSE_JSON
            )
            mock_client_cls.return_value = mock_client

            provider = AnthropicProvider()
            messages = [{"role": "user", "content": "how's everything?"}]

            reply = provider.converse(messages)

            _, kwargs = mock_client.messages.create.call_args
            assert kwargs["system"].startswith("You are Atlas, an infrastructure assistant")

            assert reply.text == "Everything looks fine right now."
            assert reply.action is None
            assert messages[-1] == {
                "role": "assistant",
                "content": "Everything looks fine right now."
            }


class TestOllamaProvider:

    def test_analyze_sends_expected_request_shape(self):

        with patch("requests.post") as mock_post:

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": SAMPLE_RESPONSE_JSON}
            }
            mock_post.return_value = mock_response

            provider = OllamaProvider(
                model="llama3.1",
                host="http://localhost:11434"
            )
            result = provider.analyze(SAMPLE_CONTEXT)

            _, kwargs = mock_post.call_args

            assert kwargs["json"]["model"] == "llama3.1"
            assert kwargs["json"]["stream"] is False
            assert kwargs["json"]["format"]["type"] == "object"

            assert result.summary == "One host, lightly loaded."
            assert result.recommendations[1].action.target == "plex"

    def test_connection_error_maps_to_provider_error(self):

        import requests

        with patch("requests.post", side_effect=requests.exceptions.ConnectionError()):

            provider = OllamaProvider(model="llama3.1")

            with pytest.raises(AIProviderError, match="Ollama"):
                provider.analyze(SAMPLE_CONTEXT)

    def test_analyze_calls_tool_then_returns_final_answer(self):
        """
        Verified against a real local Ollama (llama3.1): sending
        "tools" and "format" in the same request makes the model
        silently never call a tool at all (no error - it just
        answers directly, ungrounded). So the tool-gathering phase
        never sends "format", and a dedicated final request (no
        "tools") gets the schema-shaped answer once no more tool
        calls come back - three requests total for one tool call:
        the call, confirming nothing further is needed, then the
        formatted answer.
        """

        with patch("requests.post") as mock_post:

            tool_call_response = MagicMock()
            tool_call_response.json.return_value = {
                "message": {
                    "tool_calls": [
                        {"function": {"name": "get_containers", "arguments": {}}}
                    ]
                }
            }

            no_more_tools_response = MagicMock()
            no_more_tools_response.json.return_value = {
                "message": {"content": "Here's what I found."}
            }

            final_response = MagicMock()
            final_response.json.return_value = {
                "message": {"content": SAMPLE_RESPONSE_JSON}
            }

            mock_post.side_effect = [
                tool_call_response, no_more_tools_response, final_response
            ]

            provider = OllamaProvider(model="llama3.1")
            result = provider.analyze(SAMPLE_CONTEXT, tools=FAKE_TOOLS)

            assert mock_post.call_count == 3

            first_kwargs = mock_post.call_args_list[0].kwargs
            assert "format" not in first_kwargs["json"]
            assert first_kwargs["json"]["tools"] == [
                {
                    "type": "function",
                    "function": {
                        "name": "get_containers",
                        "description": "Get the current live list of Docker containers.",
                        "parameters": {"type": "object", "properties": {}}
                    }
                }
            ]

            second_kwargs = mock_post.call_args_list[1].kwargs
            tool_message = second_kwargs["json"]["messages"][-1]
            assert tool_message["role"] == "tool"
            assert json.loads(tool_message["content"]) == {
                "containers": [{"name": "plex", "status": "running"}]
            }
            assert "format" not in second_kwargs["json"]

            final_kwargs = mock_post.call_args_list[2].kwargs
            assert final_kwargs["json"]["format"]["type"] == "object"
            assert "tools" not in final_kwargs["json"]

            assert result.summary == "One host, lightly loaded."

    def test_analyze_without_tools_never_sends_tools_key(self):

        with patch("requests.post") as mock_post:

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": SAMPLE_RESPONSE_JSON}
            }
            mock_post.return_value = mock_response

            provider = OllamaProvider(model="llama3.1")
            provider.analyze(SAMPLE_CONTEXT)

            _, kwargs = mock_post.call_args
            assert "tools" not in kwargs["json"]

    def test_analyze_gives_up_after_max_tool_iterations(self):

        with patch("requests.post") as mock_post:

            tool_call_response = MagicMock()
            tool_call_response.json.return_value = {
                "message": {
                    "tool_calls": [
                        {"function": {"name": "get_containers", "arguments": {}}}
                    ]
                }
            }
            mock_post.return_value = tool_call_response

            provider = OllamaProvider(model="llama3.1")

            with pytest.raises(AIProviderError, match="too many tool calls"):
                provider.analyze(SAMPLE_CONTEXT, tools=FAKE_TOOLS)

    def test_converse_returns_reply_and_appends_assistant_turn(self):

        with patch("requests.post") as mock_post:

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": {"content": SAMPLE_CHAT_RESPONSE_JSON}
            }
            mock_post.return_value = mock_response

            provider = OllamaProvider(model="llama3.1")
            messages = [{"role": "user", "content": "how's everything?"}]

            reply = provider.converse(messages)

            _, kwargs = mock_post.call_args
            assert kwargs["json"]["messages"][0]["role"] == "system"

            assert reply.text == "Everything looks fine right now."
            assert messages[-1] == {
                "role": "assistant",
                "content": "Everything looks fine right now."
            }
