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


@tool(
    name="create_pull_request",
    description="Create a pull request from the current branch or specified head branch.",
    parameters={
        "title": {
            "type": "string",
            "description": "PR title.",
        },
        "body": {
            "type": "string",
            "description": "PR body/description.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "head": {
            "type": "string",
            "description": "Head branch name (defaults to current branch).",
        },
        "base": {
            "type": "string",
            "description": "Base branch name (defaults to default branch).",
        },
        "draft": {
            "type": "boolean",
            "description": "Create as draft PR.",
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
def create_pull_request(title: str, body: str = "", repo: str = "", head: str = "", base: str = "", draft: bool = False, labels: str = "", assignees: str = "") -> str:
    repo = repo or _get_repo()
    args = ["pr", "create", "--title", title]
    if body:
        args += ["--body", body]
    if repo:
        args += ["--repo", repo]
    if head:
        args += ["--head", head]
    if base:
        args += ["--base", base]
    if draft:
        args.append("--draft")
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
        return f"Created PR #{number}: {url}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="add_pr_review",
    description="Submit a review on a pull request (approve, comment, or request changes).",
    parameters={
        "number": {
            "type": "integer",
            "description": "PR number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "body": {
            "type": "string",
            "description": "Review comment body.",
        },
        "event": {
            "type": "string",
            "enum": ["APPROVE", "COMMENT", "REQUEST_CHANGES"],
            "description": "Review event type.",
        },
    },
    required=["number", "event"],
)
def add_pr_review(number: int, repo: str = "", body: str = "", event: str = "COMMENT") -> str:
    repo = repo or _get_repo()
    args = ["pr", "review", str(number), "--request", event]
    if body:
        args += ["--body", body]
    try:
        _gh(*args, repo=repo)
        return f"Submitted {event} review on PR #{number}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="add_issue_assignees",
    description="Add assignees to a GitHub issue.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "assignees": {
            "type": "string",
            "description": "Comma-separated GitHub usernames to assign.",
        },
    },
    required=["number", "assignees"],
)
def add_issue_assignees(number: int, repo: str = "", assignees: str = "") -> str:
    repo = repo or _get_repo()
    args = ["issue", "edit", str(number)]
    for a in assignees.split(","):
        a = a.strip()
        if a:
            args += ["--add-assignee", a]
    try:
        _gh(*args, repo=repo)
        return f"Added assignees to issue #{number}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_repo_info",
    description="Get repository metadata, stats, and health overview.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def get_repo_info(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("repo", "view", "--json",
                        "name,owner,description,url,defaultBranch,createdAt,updatedAt,pushedAt,homepageUrl,stargazerCount,forkCount,openIssueCount,openPullRequestCount,languages,topics,isFork,isArchived,licenseInfo,milestones",
                        repo=repo)
    except RuntimeError as e:
        return f"Error: {e}"

    owner = data.get("owner", {}).get("login", "?")
    langs = ", ".join(data.get("languages", [])) if data.get("languages") else "none"
    topics = ", ".join(data.get("topics", [])) if data.get("topics") else "none"
    license_name = data.get("licenseInfo", {}).get("name", "none") if data.get("licenseInfo") else "none"
    milestones = data.get("milestones", {}).get("totalCount", 0)

    status = "archived" if data.get("isArchived") else ("fork" if data.get("isFork") else "active")

    lines = [
        f"# {owner}/{data['name']}",
        f"**Description:** {data.get('description', 'No description')}",
        f"**Status:** {status}",
        f"**Default branch:** {data['defaultBranch']}",
        f"**License:** {license_name}",
        f"**Stars:** {data.get('stargazerCount', 0)}",
        f"**Forks:** {data.get('forkCount', 0)}",
        f"**Open issues:** {data.get('openIssueCount', 0)}",
        f"**Open PRs:** {data.get('openPullRequestCount', 0)}",
        f"**Milestones:** {milestones}",
        f"**Topics:** {topics}",
        f"**Languages:** {langs}",
        f"**Created:** {data.get('createdAt', '?')}",
        f"**Last push:** {data.get('pushedAt', '?')}",
        f"**URL:** {data.get('url', '')}",
    ]
    return "\n".join(lines)


@tool(
    name="whoami",
    description="Show the currently authenticated GitHub user.",
    parameters={},
    required=[],
)
def whoami() -> str:
    try:
        user = _gh_json("api", "user", timeout=10)
        lines = [
            f"**Logged in as:** {user.get('login', '?')}",
            f"**Name:** {user.get('name', 'N/A')}",
            f"**Bio:** {user.get('bio', 'N/A')}",
            f"**Public repos:** {user.get('public_repos', 0)}",
            f"**Public gists:** {user.get('public_gists', 0)}",
            f"**Followers:** {user.get('followers', 0)} / **Following:** {user.get('following', 0)}",
            f"**Profile:** {user.get('html_url', '')}",
        ]
        return "\n".join(lines)
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_workflow_runs",
    description="List recent GitHub Actions workflow runs with their status and conclusion.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "branch": {
            "type": "string",
            "description": "Filter by branch name.",
        },
        "status": {
            "type": "string",
            "enum": ["", "queued", "in_progress", "completed", "action_required", "cancelled", "failure", "neutral", "skipped", "stale", "success", "timed_out"],
            "description": "Filter by run status or conclusion.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=[],
)
def list_workflow_runs(repo: str = "", branch: str = "", status: str = "", limit: int = 10) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("run", "list", "--limit", str(limit), repo=repo, timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    runs = data.get("workflow_runs", data) if isinstance(data, dict) else data
    if not runs:
        return "No workflow runs found."

    lines = []
    for r in (runs if isinstance(runs, list) else []):
        if branch and r.get("headBranch", "") != branch:
            continue
        if status and r.get("status", "") != status and r.get("conclusion", "") != status:
            continue
        name = r.get("name", r.get("workflow", {}).get("name", "?"))
        conclusion = r.get("conclusion", r.get("status", "?"))
        branch_name = r.get("headBranch", "?")
        icon = {"success": "✓", "failure": "✗", "cancelled": "—", "in_progress": "►"}.get(conclusion, "•")
        lines.append(f"- {icon} **{name}** ({branch_name}) → `{conclusion}`")
    return "\n".join(lines) if lines else "No matching runs found."


@tool(
    name="list_releases",
    description="List releases in a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=[],
)
def list_releases(repo: str = "", limit: int = 10) -> str:
    repo = repo or _get_repo()
    try:
        releases = _gh_json("release", "list", "--limit", str(limit),
                            "--json", "tagName,name,isDraft,isPrerelease,createdAt,url",
                            repo=repo)
    except RuntimeError as e:
        return f"Error: {e}"

    if not releases:
        return "No releases found."

    lines = []
    for r in releases:
        tag = r.get("tagName", "?")
        name = r.get("name", tag)
        badges = []
        if r.get("isDraft"):
            badges.append("draft")
        if r.get("isPrerelease"):
            badges.append("pre-release")
        badge_str = f" [{', '.join(badges)}]" if badges else ""
        lines.append(f"- **{name}** (`{tag}`){badge_str} — {r.get('createdAt', '?')}")
    return "\n".join(lines)


@tool(
    name="create_release",
    description="Create a new release in a repository.",
    parameters={
        "tag": {
            "type": "string",
            "description": "Tag name for the release (e.g. v1.0.0).",
        },
        "name": {
            "type": "string",
            "description": "Release title.",
        },
        "notes": {
            "type": "string",
            "description": "Release notes/body.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "target": {
            "type": "string",
            "description": "Commit SHA or branch to target (defaults to default branch).",
        },
        "draft": {
            "type": "boolean",
            "description": "Create as a draft release.",
        },
        "prerelease": {
            "type": "boolean",
            "description": "Mark as pre-release.",
        },
    },
    required=["tag"],
)
def create_release(tag: str, name: str = "", notes: str = "", repo: str = "", target: str = "", draft: bool = False, prerelease: bool = False) -> str:
    repo = repo or _get_repo()
    args = ["release", "create", tag, "--title", name or tag]
    if notes:
        args += ["--notes", notes]
    if repo:
        args += ["--repo", repo]
    if target:
        args += ["--target", target]
    if draft:
        args.append("--draft")
    if prerelease:
        args.append("--prerelease")
    try:
        url = _gh(*args).strip()
        return f"Created release: {url}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_branch",
    description="Delete a branch from the repository.",
    parameters={
        "branch": {
            "type": "string",
            "description": "Branch name to delete.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["branch"],
)
def delete_branch(branch: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    args = ["api", f"repos/{repo}/git/refs/heads/{branch}", "--method", "DELETE"]
    try:
        _gh(*args, timeout=15)
        return f"Deleted branch '{branch}'"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_branches",
    description="List branches in the repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=[],
)
def list_branches(repo: str = "", limit: int = 20) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/branches?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No branches found."

    lines = []
    for b in data:
        protection = "🔒" if b.get("protected") else "  "
        lines.append(f"- {protection} `{b['name']}`")
    return "\n".join(lines)


@tool(
    name="lock_issue",
    description="Lock conversation on an issue or pull request.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue or PR number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "reason": {
            "type": "string",
            "enum": ["off_topic", "too_heated", "resolved", "spam"],
            "description": "Reason for locking.",
        },
    },
    required=["number"],
)
def lock_issue(number: int, repo: str = "", reason: str = "resolved") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/issues/{number}/lock", "--method", "PUT",
            "--raw-field", f"lock_reason={reason}", timeout=15)
        return f"Locked #{number} (reason: {reason})"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="unlock_issue",
    description="Unlock conversation on an issue or pull request.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue or PR number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number"],
)
def unlock_issue(number: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/issues/{number}/lock", "--method", "DELETE", timeout=15)
        return f"Unlocked #{number}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="add_reaction",
    description="Add a reaction to an issue, PR, or comment. Uses the comment ID if specified, otherwise targets the issue/PR.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue or PR number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "content": {
            "type": "string",
            "enum": ["+1", "-1", "laugh", "confused", "heart", "hooray", "rocket", "eyes"],
            "description": "Reaction type.",
        },
        "comment_id": {
            "type": "integer",
            "description": "Optional comment ID to react to (instead of the issue).",
        },
    },
    required=["number", "content"],
)
def add_reaction(number: int, repo: str = "", content: str = "+1", comment_id: int = 0) -> str:
    repo = repo or _get_repo()
    endpoint = f"repos/{repo}/issues/comments/{comment_id}/reactions" if comment_id else f"repos/{repo}/issues/{number}/reactions"
    emoji_map = {
        "+1": "👍", "-1": "👎", "laugh": "😄", "confused": "😕",
        "heart": "❤️", "hooray": "🎉", "rocket": "🚀", "eyes": "👀",
    }
    try:
        _gh("api", endpoint, "--method", "POST",
            "--raw-field", f'content="{content}"', timeout=15)
        return f"Added {emoji_map.get(content, content)} reaction to #{number}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_notifications",
    description="List unread GitHub notifications for the authenticated user.",
    parameters={
        "all": {
            "type": "boolean",
            "description": "Include all notifications, not just unread.",
        },
        "participating": {
            "type": "boolean",
            "description": "Only show notifications where user is participating.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=[],
)
def list_notifications(all: bool = False, participating: bool = False, limit: int = 10) -> str:
    args = ["api", f"notifications?per_page={limit}"]
    if all:
        args[0] += "&all=true"
    if participating:
        args[0] += "&participating=true"
    try:
        notifs = _gh_json(*args, timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not notifs:
        return "No notifications."

    lines = []
    for n in notifs[:limit]:
        repo_name = n.get("repository", {}).get("full_name", "?")
        subject = n.get("subject", {})
        title = subject.get("title", "?")
        ntype = subject.get("type", "?")
        reason = n.get("reason", "?")
        url = subject.get("url", "")
        lines.append(f"- [{repo_name}] **{ntype}** — {title} ({reason})")
    return "\n".join(lines)


@tool(
    name="mark_notifications_read",
    description="Mark all notifications as read, or mark a specific thread by ID.",
    parameters={
        "thread_id": {
            "type": "string",
            "description": "Specific notification thread ID to mark as read. Omit to mark all.",
        },
        "last_read_at": {
            "type": "string",
            "description": "ISO 8601 timestamp to mark everything before as read.",
        },
    },
    required=[],
)
def mark_notifications_read(thread_id: str = "", last_read_at: str = "") -> str:
    try:
        if thread_id:
            _gh("api", f"notifications/threads/{thread_id}/read", "--method", "PATCH", "--silent", timeout=15)
            return f"Marked notification {thread_id} as read"
        else:
            args = ["api", "notifications", "--method", "PUT"]
            if last_read_at:
                args += ["--raw-field", f'last_read_at={last_read_at}']
            _gh(*args, timeout=15)
            return "Marked all notifications as read"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_contributors",
    description="List contributors to a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=[],
)
def list_contributors(repo: str = "", limit: int = 20) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/contributors?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No contributors found."

    lines = []
    for c in data:
        lines.append(f"- **{c['login']}** — {c.get('contributions', 0)} commits")
    return "\n".join(lines)


@tool(
    name="rate_limit",
    description="Check GitHub API rate limit status for the authenticated user.",
    parameters={},
    required=[],
)
def rate_limit() -> str:
    try:
        data = _gh_json("api", "rate_limit", timeout=10)
    except RuntimeError as e:
        return f"Error: {e}"

    core = data.get("resources", {}).get("core", {})
    search = data.get("resources", {}).get("search", {})
    graphql = data.get("resources", {}).get("graphql", {})

    lines = [
        "## API Rate Limits",
        f"**Core:** {core.get('remaining', '?')}/{core.get('limit', '?')} remaining (resets {core.get('reset', '?')})",
        f"**Search:** {search.get('remaining', '?')}/{search.get('limit', '?')} remaining",
        f"**GraphQL:** {graphql.get('remaining', '?')}/{graphql.get('limit', '?')} remaining",
    ]
    return "\n".join(lines)


@tool(
    name="transfer_issue",
    description="Transfer an issue to another repository.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue number to transfer.",
        },
        "destination": {
            "type": "string",
            "description": "Destination repository in owner/repo format.",
        },
        "repo": {
            "type": "string",
            "description": "Current repository. Auto-detected if omitted.",
        },
    },
    required=["number", "destination"],
)
def transfer_issue(number: int, destination: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/issues/{number}/transfer", "--method", "POST",
            "--raw-field", f'{{"new_owner":"{destination.split("/")[0]}","new_name":"{destination.split("/")[1]}"}}',
            timeout=15)
        return f"Transferred #{number} to {destination}"
    except RuntimeError as e:
        return f"Error: {e}"
