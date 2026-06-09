"""Core agent loop — orchestrates LLM provider + tools until done."""

import json
import sys

from .providers import get_provider, ProviderError
from .tools import get_tool_schemas, execute_tool
from .utils import env_int, env_str

SYSTEM_PROMPT = """You are a GitHub Issues Manager agent. Your job is to help users manage GitHub issues and pull requests efficiently.

You have access to the following tools:

Issues:
- list_issues: List/filter issues
- view_issue: View full issue details (body, comments, metadata)
- create_issue: Create new issues
- close_issue: Close issues (completed or not_planned)
- reopen_issue: Reopen closed issues
- comment_on_issue: Add comments to issues
- edit_issue: Edit title, body, labels, and assignees
- search_issues: Full-text search across issues

Pull Requests:
- list_pull_requests: List/filter PRs
- view_pull_request: View PR details (diff stats, reviews, files)
- create_pull_request: Create a PR from current branch
- merge_pull_request: Merge PRs (merge/squash/rebase)
- add_pr_review: Submit a review (APPROVE/COMMENT/REQUEST_CHANGES)

Labels:
- list_labels: List repo labels
- create_label: Create a new label

Milestones:
- list_milestones: List repo milestones

Repository:
- get_repo_info: Get repo stats, languages, topics, health overview

Other:
- add_issue_assignees: Add assignees to an issue

Guidelines:
1. When listing, default to open/20 unless specified otherwise.
2. Before creating an issue or PR, search to avoid duplicates.
3. Always ask for confirmation before destructive actions (close, merge, remove labels, unassign).
4. Use structured output to present information clearly.
5. If a repo is not specified, you can ask or it will be auto-detected.

Explain what you're doing before executing tools. Think step by step."""


def run_conversation(user_input: str) -> None:
    provider = get_provider()
    max_turns = env_int("MAX_TURNS", 20)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    for turn in range(max_turns):
        try:
            response = provider.chat(messages, tools=get_tool_schemas())
        except ProviderError as e:
            print(f"Provider error: {e}", file=sys.stderr)
            sys.exit(1)

        if response.content:
            print(response.content)

        if not response.tool_calls:
            break

        for tc in response.tool_calls:
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                ],
            })

            print(f"\n  → Calling tool: {tc.name}({json.dumps(tc.arguments)})")
            result = execute_tool(tc.name, tc.arguments)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

            print(f"  ← Result: {result[:500]}{'...' if len(result) > 500 else ''}")
            print()

    else:
        print("Reached maximum conversation turns. Results may be incomplete.")
