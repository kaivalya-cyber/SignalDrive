"""CLI entry point — parse args and run the agent or direct commands."""

import argparse
import sys

from . import __version__
from .agent import run_conversation
from .tools import execute_tool
from .tools.github import (
    list_issues,
    view_issue,
    create_issue,
    close_issue,
    reopen_issue,
    comment_on_issue,
    edit_issue,
    search_issues,
)
from .utils import load_env


def _do_direct(args) -> None:
    """Execute a single tool directly without the agent loop."""
    tool_map = {
        "list": list_issues,
        "view": view_issue,
        "create": create_issue,
        "close": close_issue,
        "reopen": reopen_issue,
        "comment": comment_on_issue,
        "edit": edit_issue,
        "search": search_issues,
    }

    fn = tool_map.get(args.command)
    if fn:
        # Build kwargs from parsed args
        kwargs = {}
        for key in fn.__code__.co_varnames[: fn.__code__.co_argcount]:
            val = getattr(args, key, None)
            if val is not None:
                kwargs[key] = val
        print(fn(**kwargs))


def main() -> None:
    load_env()

    parser = argparse.ArgumentParser(
        prog="issues-manager",
        description="AI agent that manages GitHub issues using any LLM provider.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "instruction",
        nargs="*",
        help="Natural language instruction for the AI agent. If omitted, enters interactive mode.",
    )

    args, _ = parser.parse_known_args()

    if args.instruction:
        instruction = " ".join(args.instruction)
        run_conversation(instruction)
    else:
        print("GitHub Issues Manager — AI-powered issue management")
        print(f"Version {__version__}")
        print("Type 'exit' or 'quit' to stop.")
        print()
        try:
            while True:
                user_input = input(">> ").strip()
                if user_input.lower() in ("exit", "quit"):
                    break
                if not user_input:
                    continue
                run_conversation(user_input)
                print()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)


if __name__ == "__main__":
    main()
