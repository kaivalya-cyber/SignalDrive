from .base import Provider, ProviderError, ChatResponse, ToolCall
from .openai_compat import OpenAICompatProvider
from .anthropic_provider import AnthropicProvider


def get_provider() -> Provider:
    from ..utils import env_str

    provider_name = env_str("PROVIDER", "openai").lower()

    registry = {
        "openai": OpenAICompatProvider,
        "nvidia": OpenAICompatProvider,
        "openrouter": OpenAICompatProvider,
        "together": OpenAICompatProvider,
        "groq": OpenAICompatProvider,
        "deepseek": OpenAICompatProvider,
        "anthropic": AnthropicProvider,
        "claude": AnthropicProvider,
    }

    cls = registry.get(provider_name)
    if cls is None:
        available = ", ".join(sorted(registry))
        raise ProviderError(f"Unknown provider '{provider_name}'. Available: {available}")

    return cls(provider_name)
