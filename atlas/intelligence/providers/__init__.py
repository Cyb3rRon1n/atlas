from atlas.intelligence.providers.base import (
    AIProvider,
    AIProviderError,
    AnalysisResult,
    ChatReply,
    Recommendation,
)


def get_provider(config) -> AIProvider:
    """
    Build the configured AI provider from an IntelligenceConfig.
    """

    if config.provider == "anthropic":

        from atlas.intelligence.providers.anthropic_provider import (
            AnthropicProvider
        )

        return AnthropicProvider(model=config.model)

    if config.provider == "ollama":

        from atlas.intelligence.providers.ollama_provider import (
            OllamaProvider
        )

        return OllamaProvider(
            model=config.model,
            host=config.ollama_host
        )

    raise AIProviderError(
        f"Unknown intelligence provider: {config.provider!r}"
    )


__all__ = [
    "AIProvider",
    "AIProviderError",
    "AnalysisResult",
    "ChatReply",
    "Recommendation",
    "get_provider",
]
