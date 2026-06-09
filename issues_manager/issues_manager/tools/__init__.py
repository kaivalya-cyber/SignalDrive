"""Tool registry and execution."""

from typing import Any

from ..providers.base import ToolSchema

REGISTRY: dict[str, dict] = {}


def tool(name: str, description: str, parameters: dict, required: list[str] | None = None):
    """Decorator that registers a callable as a tool."""

    def decorator(fn):
        REGISTRY[name] = {
            "fn": fn,
            "schema": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": parameters,
                        "required": required or list(parameters.keys()),
                    },
                },
            },
        }
        return fn

    return decorator


def get_tool_schemas() -> list[ToolSchema]:
    return [entry["schema"] for entry in REGISTRY.values()]


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    entry = REGISTRY.get(name)
    if not entry:
        return f"Error: unknown tool '{name}'"
    try:
        result = entry["fn"](**arguments)
        return str(result)
    except Exception as e:
        return f"Error executing '{name}': {e}"
