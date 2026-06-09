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


def _gh_json(*args: str, timeout: int = 30, repo: str = "") -> list | dict:
    args = list(args)
    if repo:
        args += ["--repo", repo]
    out = _gh(*args, timeout=timeout)
    return json.loads(out)


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


@tool(
    name="list_pull_requests",
    description="List GitHub pull requests with optional filters.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "state": {
            "type": "string",
            "enum": ["open", "closed", "merged", "all"],
            "description": "Filter by PR state.",
        },
        "label": {
            "type": "string",
            "description": "Filter by label name.",
        },
        "assignee": {
            "type": "string",
            "description": "Filter by assignee login.",
        },
        "author": {
            "type": "string",
            "description": "Filter by author login.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=[],
)
def list_pull_requests(repo: str = "", state: str = "open", label: str = "", assignee: str = "", author: str = "", limit: int = 20) -> str:
    repo = repo or _get_repo()
    args = ["pr", "list", "--state", state, "--limit", str(limit),
            "--json", "number,title,state,headRefName,baseRefName,author,labels,createdAt,url"]
    if label:
        args += ["--label", label]
    if assignee:
        args += ["--assignee", assignee]
    if author:
        args += ["--author", author]
    try:
        prs = _gh_json(*args, repo=repo)
    except RuntimeError as e:
        return f"Error: {e}"

    if not prs:
        return "No pull requests found."

    lines = []
    for pr in prs:
        labels_str = f" [{', '.join(l['name'] for l in pr['labels'])}]" if pr.get("labels") else ""
        author_str = pr.get("author", {}).get("login", "unknown") if pr.get("author") else "unknown"
        lines.append(f"- **#{pr['number']}** [{pr['state']}] {pr['title']} ({pr['headRefName']} → {pr['baseRefName']}) by {author_str}{labels_str}")
    return "\n".join(lines)


@tool(
    name="view_pull_request",
    description="View full details of a specific GitHub pull request, including diff summary and reviews.",
    parameters={
        "number": {
            "type": "integer",
            "description": "PR number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number"],
)
def view_pull_request(number: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        pr = _gh_json("pr", "view", str(number), "--json",
                       "number,title,state,body,headRefName,baseRefName,author,labels,assignees,mergedBy,createdAt,updatedAt,mergedAt,additions,deletions,files,reviews,url",
                       repo=repo)
    except RuntimeError as e:
        return f"Error: {e}"

    labels_str = ", ".join(l["name"] for l in pr["labels"]) if pr.get("labels") else "none"
    assignees_str = ", ".join(a["login"] for a in pr["assignees"]) if pr.get("assignees") else "none"
    author_str = pr.get("author", {}).get("login", "unknown")
    files_count = len(pr.get("files", []))
    reviews = pr.get("reviews", [])

    lines = [
        f"## #{pr['number']} [{pr['state']}] {pr['title']}",
        f"**Author:** {author_str}",
        f"**Branch:** {pr['headRefName']} → {pr['baseRefName']}",
        f"**Labels:** {labels_str}",
        f"**Assignees:** {assignees_str}",
        f"**Changes:** +{pr.get('additions', 0)} / -{pr.get('deletions', 0)} across {files_count} files",
        f"**Created:** {pr['createdAt']}",
        f"**Updated:** {pr['updatedAt']}",
        f"**URL:** {pr['url']}",
        "",
        pr.get("body", "_No description_"),
    ]

    if pr.get("mergedBy"):
        lines.append(f"\n**Merged by:** {pr['mergedBy']['login']} at {pr.get('mergedAt', 'unknown')}")

    if reviews:
        lines.append("")
        lines.append("### Reviews")
        for r in reviews:
            reviewer = r.get("author", {}).get("login", "unknown")
            state = r.get("state", "COMMENTED")
            body = r.get("body", "")
            lines.append(f"**{reviewer}** ({state}): {body[:200]}" + ("..." if len(body) > 200 else ""))

    return "\n".join(lines)


@tool(
    name="merge_pull_request",
    description="Merge a GitHub pull request. Supports merge, squash, and rebase strategies.",
    parameters={
        "number": {
            "type": "integer",
            "description": "PR number to merge.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "method": {
            "type": "string",
            "enum": ["merge", "squash", "rebase"],
            "description": "Merge method (default: merge).",
        },
        "delete_branch": {
            "type": "boolean",
            "description": "Delete the head branch after merge.",
        },
    },
    required=["number"],
)
def merge_pull_request(number: int, repo: str = "", method: str = "merge", delete_branch: bool = False) -> str:
    repo = repo or _get_repo()
    args = ["pr", "merge", str(number), "--" + method]
    if delete_branch:
        args.append("--delete-branch")
    try:
        _gh(*args, repo=repo)
        return f"Merged PR #{number} using {method} strategy"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_labels",
    description="List all labels in a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def list_labels(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        labels = _gh_json("label", "list", "--json", "name,color,description", repo=repo)
    except RuntimeError as e:
        return f"Error: {e}"

    if not labels:
        return "No labels found."

    lines = []
    for l in labels:
        desc = f" — {l['description']}" if l.get("description") else ""
        lines.append(f"- `{l['name']}` (color: #{l['color']}){desc}")
    return "\n".join(lines)


@tool(
    name="create_label",
    description="Create a new label in a repository.",
    parameters={
        "name": {
            "type": "string",
            "description": "Label name.",
        },
        "color": {
            "type": "string",
            "description": "Hex color code without # (e.g. 'ff0000').",
        },
        "description": {
            "type": "string",
            "description": "Label description.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["name", "color"],
)
def create_label(name: str, color: str, description: str = "", repo: str = "") -> str:
    repo = repo or _get_repo()
    args = ["label", "create", name, "--color", color]
    if description:
        args += ["--description", description]
    try:
        _gh(*args, repo=repo)
        return f"Created label '{name}'"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_milestones",
    description="List milestones in a repository.",
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
    },
    required=[],
)
def list_milestones(repo: str = "", state: str = "open") -> str:
    repo = repo or _get_repo()
    try:
        milestones = _gh_json("api", f"repos/{repo}/milestones?state={state}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not milestones:
        return "No milestones found."

    lines = []
    for m in milestones:
        progress = f" ({m.get('open_issues', 0)} open / {m.get('closed_issues', 0)} closed)"
        due = f" due {m['due_on']}" if m.get("due_on") else ""
        lines.append(f"- **{m['title']}** [{m['state']}]{due}{progress}")
        if m.get("description"):
            lines.append(f"  {m['description']}")
    return "\n".join(lines)
