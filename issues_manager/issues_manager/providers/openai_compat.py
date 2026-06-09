"""Provider for any OpenAI-compatible API (OpenAI, NVIDIA NIM, OpenRouter, Together, Groq, DeepSeek, etc.)."""

from openai import OpenAI

from ..utils import env_str
from .base import Provider, ProviderError, ChatResponse, ToolCall


class OpenAICompatProvider(Provider):
    MAP = {
        "openai": {
            "api_key": "OPENAI_API_KEY",
            "base_url": None,
            "default_model": "gpt-4o",
        },
        "nvidia": {
            "api_key": "NVIDIA_API_KEY",
            "base_url": "https://integrate.api.nvidia.com/v1",
            "default_model": "nvidia/llama-3.1-nemotron-70b-instruct",
        },
        "openrouter": {
            "api_key": "OPENROUTER_API_KEY",
            "base_url": "https://openrouter.ai/api/v1",
            "default_model": "anthropic/claude-sonnet-4-6",
        },
        "together": {
            "api_key": "TOGETHER_API_KEY",
            "base_url": "https://api.together.xyz/v1",
            "default_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        },
        "groq": {
            "api_key": "GROQ_API_KEY",
            "base_url": "https://api.groq.com/openai/v1",
            "default_model": "llama-3.3-70b-versatile",
        },
        "deepseek": {
            "api_key": "DEEPSEEK_API_KEY",
            "base_url": "https://api.deepseek.com",
            "default_model": "deepseek-chat",
        },
    }

    def __init__(self, name: str):
        super().__init__(name)
        cfg = self.MAP.get(name, self.MAP["openai"])
        api_key = env_str(cfg["api_key"], "")
        base_url = env_str("BASE_URL", cfg["base_url"] or "")

        if not api_key:
            raise ProviderError(
                f"Missing {cfg['api_key']} environment variable for provider '{name}'"
            )

        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url

        model = env_str("MODEL", cfg["default_model"])
        if env_str("MODEL"):
            model = env_str("MODEL")
        else:
            model = cfg["default_model"]

        self._client = OpenAI(**kwargs)
        self._model = model

    @property
    def default_model(self) -> str:
        return self._model

    def chat(
        self,
        messages: list[dict],
        tools: list | None = None,
        tool_choice: str | None = None,
        **kwargs,
    ) -> ChatResponse:
        params = {
            "model": kwargs.get("model", self._model),
            "messages": messages,
        }
        if tools:
            params["tools"] = tools
        if tool_choice:
            params["tool_choice"] = tool_choice

        try:
            resp = self._client.chat.completions.create(**params)
        except Exception as e:
            raise ProviderError(f"OpenAI-compatible API error: {e}") from e

        choice = resp.choices[0]
        msg = choice.message

        response = ChatResponse(
            content=msg.content or "",
            stop_reason=choice.finish_reason or "stop",
            usage={
                "input": resp.usage.prompt_tokens if resp.usage else 0,
                "output": resp.usage.completion_tokens if resp.usage else 0,
            },
        )

        if msg.tool_calls:
            for tc in msg.tool_calls:
                import json

                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                response.tool_calls.append(
                    ToolCall(id=tc.id, name=tc.function.name, arguments=args)
                )

        return response
