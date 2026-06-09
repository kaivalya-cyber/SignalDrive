"""GitHub issue tools — wraps the gh CLI for issue management."""

import json
import os
import subprocess
from typing import Optional

from . import tool


def _gh(*args: str, timeout: int = 30) -> str:
    result = subprocess.run(
        ["gh"] + list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def _get_repo() -> str:
    """Detect the current repo from git remote if --repo not given."""
    try:
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        url = out.stdout.strip()
        for prefix in ("https://github.com/", "git@github.com:"):
            if url.startswith(prefix):
                suffix = url[len(prefix) :]
                return suffix.removesuffix(".git")
    except Exception:
        pass
    return os.environ.get("GH_REPO", "")


@tool(
    name="list_issues",
    description="List GitHub issues with optional filters. Returns markdown-formatted list.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "state": {
            "type": "string",
            "enum": ["open", "closed", "all"],
            "description": "Filter by state.",
        },
        "label": {
            "type": "string",
            "description": "Filter by label name.",
        },
        "assignee": {
            "type": "string",
            "description": "Filter by assignee login.",
        },
        "search": {
            "type": "string",
            "description": "Full-text search query.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=[],
)
def list_issues(
    repo: str = "",
    state: str = "open",
    label: str = "",
    assignee: str = "",
    search: str = "",
    limit: int = 20,
) -> str:
    repo = repo or _get_repo()
    args = ["issue", "list", "--state", state, "--limit", str(limit),
            "--json", "number,title,state,labels,assignees,createdAt,updatedAt,url"]
    if repo:
        args += ["--repo", repo]
    if label:
        args += ["--label", label]
    if assignee:
        args += ["--assignee", assignee]
    if search:
        args += ["--search", search]

    try:
        out = _gh(*args)
        issues = json.loads(out)
    except RuntimeError as e:
        return f"Error: {e}"
    except json.JSONDecodeError:
        return "Error: failed to parse gh output"

    if not issues:
        return "No issues found."

    lines = []
    for issue in issues:
        labels_str = f" [{', '.join(l['name'] for l in issue['labels'])}]" if issue["labels"] else ""
        assignees_str = f" (assigned: {', '.join(a['login'] for a in issue['assignees'])})" if issue["assignees"] else ""
        lines.append(f"- **#{issue['number']}** [{issue['state']}] {issue['title']}{labels_str}{assignees_str}")
    return "\n".join(lines)


@tool(
    name="view_issue",
    description="View full details of a specific GitHub issue, including body and comments.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number"],
)
def view_issue(number: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    args = ["issue", "view", str(number), "--json",
            "number,title,state,body,labels,assignees,createdAt,updatedAt,url,comments"]
    if repo:
        args += ["--repo", repo]

    try:
        out = _gh(*args)
        issue = json.loads(out)
    except RuntimeError as e:
        return f"Error: {e}"

    labels_str = ", ".join(l["name"] for l in issue["labels"]) if issue["labels"] else "none"
    assignees_str = ", ".join(a["login"] for a in issue["assignees"]) if issue["assignees"] else "none"
    comments = issue.get("comments", [])

    lines = [
        f"## #{issue['number']} [{issue['state']}] {issue['title']}",
        f"**Labels:** {labels_str}",
        f"**Assignees:** {assignees_str}",
        f"**Created:** {issue['createdAt']}",
        f"**Updated:** {issue['updatedAt']}",
        f"**URL:** {issue['url']}",
        "",
        issue.get("body", "_No description_"),
    ]

    if comments:
        lines.append("")
        lines.append("### Comments")
        for c in comments:
            author = c.get("author", {}).get("login", "unknown")
            lines.append(f"**{author}:** {c.get('body', '')}")
            lines.append("")

    return "\n".join(lines)


@tool(
    name="create_issue",
    description="Create a new GitHub issue with title, body, labels, and assignees.",
    parameters={
        "title": {
            "type": "string",
            "description": "Issue title.",
        },
        "body": {
            "type": "string",
            "description": "Issue body/description.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "labels": {
            "type": "string",
            "description": "Comma-separated label names.",
        },
        "assignees": {
            "type": "string",
            "description": "Comma-separated GitHub usernames.",
        },
    },
    required=["title"],
)
def create_issue(title: str, body: str = "", repo: str = "", labels: str = "", assignees: str = "") -> str:
    repo = repo or _get_repo()
    args = ["issue", "create", "--title", title]
    if body:
        args += ["--body", body]
    if repo:
        args += ["--repo", repo]
    if labels:
        for l in labels.split(","):
            l = l.strip()
            if l:
                args += ["--label", l]
    if assignees:
        for a in assignees.split(","):
            a = a.strip()
            if a:
                args += ["--assignee", a]

    try:
        url = _gh(*args).strip()
        number = url.rstrip("/").split("/")[-1]
        return f"Created issue #{number}: {url}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="close_issue",
    description="Close a GitHub issue.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue number to close.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "reason": {
            "type": "string",
            "enum": ["completed", "not_planned"],
            "description": "Reason for closing.",
        },
    },
    required=["number"],
)
def close_issue(number: int, repo: str = "", reason: str = "completed") -> str:
    repo = repo or _get_repo()
    args = ["issue", "close", str(number), "--reason", reason]
    if repo:
        args += ["--repo", repo]
    try:
        _gh(*args)
        return f"Closed issue #{number}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="reopen_issue",
    description="Reopen a closed GitHub issue.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue number to reopen.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number"],
)
def reopen_issue(number: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    args = ["issue", "reopen", str(number)]
    if repo:
        args += ["--repo", repo]
    try:
        _gh(*args)
        return f"Reopened issue #{number}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="comment_on_issue",
    description="Add a comment to an existing GitHub issue.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue number to comment on.",
        },
        "body": {
            "type": "string",
            "description": "Comment text.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number", "body"],
)
def comment_on_issue(number: int, body: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    args = ["issue", "comment", str(number), "--body", body]
    if repo:
        args += ["--repo", repo]
    try:
        _gh(*args)
        return f"Commented on issue #{number}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="edit_issue",
    description="Edit a GitHub issue: update title, body, add/remove labels, add/remove assignees.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue number to edit.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "title": {
            "type": "string",
            "description": "New title.",
        },
        "body": {
            "type": "string",
            "description": "New body text.",
        },
        "add_labels": {
            "type": "string",
            "description": "Comma-separated labels to add.",
        },
        "remove_labels": {
            "type": "string",
            "description": "Comma-separated labels to remove.",
        },
        "add_assignees": {
            "type": "string",
            "description": "Comma-separated usernames to assign.",
        },
        "remove_assignees": {
            "type": "string",
            "description": "Comma-separated usernames to unassign.",
        },
    },
    required=["number"],
)
def edit_issue(
    number: int,
    repo: str = "",
    title: str = "",
    body: str = "",
    add_labels: str = "",
    remove_labels: str = "",
    add_assignees: str = "",
    remove_assignees: str = "",
) -> str:
    repo = repo or _get_repo()
    args = ["issue", "edit", str(number)]
    if repo:
        args += ["--repo", repo]
    if title:
        args += ["--title", title]
    if body:
        args += ["--body", body]
    if add_labels:
        for l in add_labels.split(","):
            l = l.strip()
            if l:
                args += ["--add-label", l]
    if remove_labels:
        for l in remove_labels.split(","):
            l = l.strip()
            if l:
                args += ["--remove-label", l]
    if add_assignees:
        for a in add_assignees.split(","):
            a = a.strip()
            if a:
                args += ["--add-assignee", a]
    if remove_assignees:
        for a in remove_assignees.split(","):
            a = a.strip()
            if a:
                args += ["--remove-assignee", a]

    try:
        _gh(*args)
        return f"Edited issue #{number}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="search_issues",
    description="Search GitHub issues across repositories using full-text search.",
    parameters={
        "query": {
            "type": "string",
            "description": "Search query (supports qualifiers like label:bug, state:open, is:issue, is:pr).",
        },
        "repo": {
            "type": "string",
            "description": "Limit search to a specific repository (owner/repo). Omit to search globally.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=["query"],
)
def search_issues(query: str, repo: str = "", limit: int = 20) -> str:
    full_query = f"repo:{repo} {query}" if repo else query
    args = ["search", "issues", full_query, "--limit", str(limit),
            "--json", "number,title,state,repository,labels,createdAt,url"]

    try:
        out = _gh(*args)
        results = json.loads(out)
    except RuntimeError as e:
        return f"Error: {e}"

    if not results:
        return "No results found."

    lines = []
    for r in results:
        repo_name = r.get("repository", {}).get("nameWithOwner", "")
        labels_str = f" [{', '.join(l['name'] for l in r['labels'])}]" if r["labels"] else ""
        lines.append(f"- [{repo_name}] **#{r['number']}** [{r['state']}] {r['title']}{labels_str}")
    return "\n".join(lines)
