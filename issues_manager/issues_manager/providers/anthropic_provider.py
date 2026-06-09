"""Anthropic Claude provider."""

from anthropic import Anthropic

from ..utils import env_str
from .base import Provider, ProviderError, ChatResponse, ToolCall


class AnthropicProvider(Provider):
    def __init__(self, name: str):
        super().__init__(name)
        api_key = env_str("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ProviderError(
                "Missing ANTHROPIC_API_KEY environment variable for provider 'anthropic'"
            )
        self._client = Anthropic(api_key=api_key)
        self._model = env_str("MODEL", "claude-sonnet-4-20250514")

    @property
    def default_model(self) -> str:
        return self._model

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Convert OpenAI-style tool schemas to Anthropic format."""
        result = []
        for t in tools:
            f = t["function"]
            result.append({
                "name": f["name"],
                "description": f.get("description", ""),
                "input_schema": f["parameters"],
            })
        return result

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        """Convert OpenAI-style messages to Anthropic format.

        Handles: system, user, assistant, tool_result
        """
        converted = []
        system = None

        for msg in messages:
            role = msg["role"]
            content = msg.get("content", "")

            if role == "system":
                system = content
                continue

            if role == "user":
                converted.append({"role": "user", "content": content})
            elif role == "assistant":
                blocks = []
                if content:
                    blocks.append({"type": "text", "text": content})

                tool_calls = msg.get("tool_calls", []) or (
                    [msg.get("tool_call")] if msg.get("tool_call") else []
                )

                # Anthropic puts tool_use in content blocks
                if "tool_calls" in msg or "tool_call" in msg:
                    tc_list = msg.get("tool_calls", []) or (
                        [msg["tool_call"]] if "tool_call" in msg else []
                    )
                    for tc in tc_list:
                        blocks.append({
                            "type": "tool_use",
                            "id": tc["id"] if isinstance(tc, dict) else tc.id,
                            "name": tc["name"] if isinstance(tc, dict) else tc.name,
                            "input": tc["arguments"] if isinstance(tc, dict) else tc.arguments,
                        })

                if blocks:
                    converted.append({"role": "assistant", "content": blocks})
                else:
                    converted.append({"role": "assistant", "content": ""})

            elif role == "tool":
                converted.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.get("tool_call_id", ""),
                            "content": content,
                        }
                    ],
                })

        return converted, system

    def chat(
        self,
        messages: list[dict],
        tools: list | None = None,
        tool_choice: str | None = None,
        **kwargs,
    ) -> ChatResponse:
        converted_messages, system = self._convert_messages(messages)
        anthropic_tools = self._convert_tools(tools) if tools else None

        params = {
            "model": kwargs.get("model", self._model),
            "messages": converted_messages,
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        if system:
            params["system"] = system
        if anthropic_tools:
            params["tools"] = anthropic_tools

        try:
            resp = self._client.messages.create(**params)
        except Exception as e:
            raise ProviderError(f"Anthropic API error: {e}") from e

        response = ChatResponse(
            stop_reason=resp.stop_reason or "stop",
            usage={
                "input": resp.usage.input_tokens if resp.usage else 0,
                "output": resp.usage.output_tokens if resp.usage else 0,
            },
        )

        for block in resp.content:
            if block.type == "text":
                response.content = block.text
            elif block.type == "tool_use":
                response.tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=block.input)
                )

        return response
