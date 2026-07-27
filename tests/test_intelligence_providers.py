import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from atlas.intelligence.providers.anthropic_provider import AnthropicProvider
from atlas.intelligence.providers.base import AIProviderError
from atlas.intelligence.providers.ollama_provider import OllamaProvider


SAMPLE_CONTEXT = {"system": {"hostname": "sentinel"}}

SAMPLE_RESPONSE_JSON = json.dumps({
    "summary": "One host, lightly loaded.",
    "recommendations": [
        {
            "title": "Enable swap",
            "detail": "No swap device was detected on sentinel.",
            "severity": "warning"
        }
    ]
})


def _fake_message(text: str, stop_reason: str = "end_turn"):

    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=text)]
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

            assert result.summary == "One host, lightly loaded."
            assert len(result.recommendations) == 1
            assert result.recommendations[0].severity == "warning"

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

    def test_connection_error_maps_to_provider_error(self):

        import requests

        with patch("requests.post", side_effect=requests.exceptions.ConnectionError()):

            provider = OllamaProvider(model="llama3.1")

            with pytest.raises(AIProviderError, match="Ollama"):
                provider.analyze(SAMPLE_CONTEXT)
