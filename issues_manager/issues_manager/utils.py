"""Shared utilities."""

import os
from pathlib import Path

ENV_PREFIX = "GH_MANAGER_"


def load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
        # Also try loading from the project root
        load_dotenv(Path.cwd() / ".env")
    except ImportError:
        pass


def env_str(key: str, default: str = "") -> str:
    return os.environ.get(f"{ENV_PREFIX}{key}", os.environ.get(key, default))


def env_int(key: str, default: int = 0) -> int:
    try:
        return int(os.environ.get(f"{ENV_PREFIX}{key}", os.environ.get(key, str(default))))
    except (TypeError, ValueError):
        return default
