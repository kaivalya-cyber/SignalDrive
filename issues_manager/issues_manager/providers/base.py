"""Abstract provider interface + shared types."""

from dataclasses import dataclass, field
from typing import Any


class ProviderError(Exception):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": str,
        "description": str,
        "parameters": {"type": "object", "properties": dict, "required": list},
    },
}

ToolSchema = dict  # OpenAI-style tool definition


class Provider:
    name: str

    def __init__(self, name: str):
        self.name = name

    def chat(
        self,
        messages: list[dict],
        tools: list[ToolSchema] | None = None,
        tool_choice: str | None = None,
        **kwargs,
    ) -> ChatResponse:
        raise NotImplementedError

    @property
    def default_model(self) -> str:
        raise NotImplementedError
