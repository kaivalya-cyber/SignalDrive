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


@tool(
    name="list_pr_checks",
    description="List all check runs / CI status for a pull request.",
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
def list_pr_checks(number: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        pr = _gh_json("pr", "view", str(number), "--json", "headRefName", repo=repo)
        branch = pr.get("headRefName", "")
        if not branch:
            return "Could not determine PR branch."
        # Use the check-runs API via the branch's commit status
        data = _gh_json("api", f"repos/{repo}/commits/{branch}/check-runs?per_page=20", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    runs = data.get("check_runs", [])
    if not runs:
        return "No check runs found for this PR."

    lines = []
    for r in runs:
        name = r.get("name", "?")
        conclusion = r.get("conclusion", r.get("status", "pending"))
        status = r.get("status", "?")
        icon_map = {
            "success": "✓", "failure": "✗", "cancelled": "—",
            "neutral": "•", "skipped": "…", "timed_out": "⏱",
            "in_progress": "►", "queued": "○", "pending": "○",
        }
        icon = icon_map.get(conclusion, icon_map.get(status, "?"))
        lines.append(f"- {icon} **{name}** → `{conclusion}` ({status})")
    return "\n".join(lines)


@tool(
    name="request_pr_reviewers",
    description="Request reviews from specific users on a pull request.",
    parameters={
        "number": {
            "type": "integer",
            "description": "PR number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "reviewers": {
            "type": "string",
            "description": "Comma-separated GitHub usernames to request review from.",
        },
        "team_reviewers": {
            "type": "string",
            "description": "Comma-separated team names (slug) to request review from.",
        },
    },
    required=["number", "reviewers"],
)
def request_pr_reviewers(number: int, repo: str = "", reviewers: str = "", team_reviewers: str = "") -> str:
    repo = repo or _get_repo()
    args = ["pr", "review", str(number), "--request"]
    for r in reviewers.split(","):
        r = r.strip()
        if r:
            args += ["--reviewer", r]
    for t in team_reviewers.split(","):
        t = t.strip()
        if t:
            args += ["--team", t]
    try:
        _gh(*args, repo=repo)
        return f"Requested reviews on PR #{number}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_milestone",
    description="Create a milestone in a repository.",
    parameters={
        "title": {
            "type": "string",
            "description": "Milestone title.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "description": {
            "type": "string",
            "description": "Milestone description.",
        },
        "due_date": {
            "type": "string",
            "description": "Due date in YYYY-MM-DD format.",
        },
    },
    required=["title"],
)
def create_milestone(title: str, repo: str = "", description: str = "", due_date: str = "") -> str:
    repo = repo or _get_repo()
    import urllib.parse
    args = ["api", f"repos/{repo}/milestones", "--method", "POST",
            "--raw-field", f'title={urllib.parse.quote(title)}']
    if description:
        args += ["--raw-field", f"description={urllib.parse.quote(description)}"]
    if due_date:
        args += ["--raw-field", f"due_on={urllib.parse.quote(due_date)}T23:59:59Z"]
    try:
        _gh(*args, timeout=15)
        return f"Created milestone '{title}'"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_comment",
    description="Edit an existing comment on an issue or pull request.",
    parameters={
        "comment_id": {
            "type": "integer",
            "description": "Comment ID to edit.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "body": {
            "type": "string",
            "description": "New comment body text.",
        },
    },
    required=["comment_id", "body"],
)
def update_comment(comment_id: int, body: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/issues/comments/{comment_id}", "--method", "PATCH",
            "--raw-field", f'body={body}', timeout=15)
        return f"Updated comment {comment_id}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_comment",
    description="Delete a comment on an issue or pull request.",
    parameters={
        "comment_id": {
            "type": "integer",
            "description": "Comment ID to delete.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["comment_id"],
)
def delete_comment(comment_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/issues/comments/{comment_id}", "--method", "DELETE", timeout=15)
        return f"Deleted comment {comment_id}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="search_repos",
    description="Search GitHub repositories by query.",
    parameters={
        "query": {
            "type": "string",
            "description": "Search query (supports qualifiers like language:python, stars:>100, topic:hacktoberfest).",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=["query"],
)
def search_repos(query: str, limit: int = 10) -> str:
    try:
        data = _gh_json("search", "repos", query, "--limit", str(limit),
                        "--json", "name,owner,description,stargazerCount,forkCount,language,url", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No repositories found."

    lines = []
    for r in data:
        owner = r.get("owner", {}).get("login", "?")
        lang = r.get("language", "") or ""
        lang_str = f" ({lang})" if lang else ""
        desc = r.get("description", "") or ""
        desc_short = f" — {desc[:80]}{'...' if len(desc) > 80 else ''}" if desc else ""
        lines.append(f"- **{owner}/{r['name']}** ⭐{r.get('stargazerCount', 0)}🍴{r.get('forkCount', 0)}{lang_str}{desc_short}")
    return "\n".join(lines)


@tool(
    name="search_code",
    description="Search code within a repository using GitHub's code search.",
    parameters={
        "query": {
            "type": "string",
            "description": "Search query.",
        },
        "repo": {
            "type": "string",
            "description": "Limit to a specific repository (owner/repo).",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=["query"],
)
def search_code(query: str, repo: str = "", limit: int = 10) -> str:
    full_query = f"repo:{repo} {query}" if repo else query
    try:
        data = _gh_json("search", "code", full_query, "--limit", str(limit),
                        "--json", "path,repository,name,url", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No code matches found."

    lines = []
    for r in data:
        repo_name = r.get("repository", {}).get("fullName", "?")
        path = r.get("path", "?")
        lines.append(f"- [{repo_name}] `{path}`")
    return "\n".join(lines)


@tool(
    name="fork_repo",
    description="Fork a repository to your account or an organization.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository to fork in owner/repo format.",
        },
        "organization": {
            "type": "string",
            "description": "Organization to fork to (defaults to personal account).",
        },
    },
    required=["repo"],
)
def fork_repo(repo: str = "", organization: str = "") -> str:
    args = ["api", f"repos/{repo}/forks", "--method", "POST"]
    if organization:
        args += ["--raw-field", f'organization={organization}']
    try:
        data = _gh_json(*args, timeout=30)
        full_name = data.get("full_name", data.get("name", "?"))
        return f"Forked {repo} → {full_name}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="star_repo",
    description="Star a repository for the authenticated user.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format.",
        },
    },
    required=["repo"],
)
def star_repo(repo: str) -> str:
    try:
        _gh("api", f"user/starred/{repo}", "--method", "PUT", "--silent", timeout=15)
        return f"Starred {repo} ⭐"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="unstar_repo",
    description="Unstar a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format.",
        },
    },
    required=["repo"],
)
def unstar_repo(repo: str) -> str:
    try:
        _gh("api", f"user/starred/{repo}", "--method", "DELETE", "--silent", timeout=15)
        return f"Unstarred {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_issue_comments",
    description="List all comments on an issue or pull request with author and timestamp.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue or PR number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=["number"],
)
def list_issue_comments(number: int, repo: str = "", limit: int = 20) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/issues/{number}/comments?per_page={limit}&sort=created&direction=asc", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No comments on this issue."

    lines = []
    for c in data:
        author = c.get("user", {}).get("login", "?")
        created = c.get("created_at", "?")
        body = (c.get("body", "") or "")[:120].replace("\n", " ")
        lines.append(f"- **{author}** ({created}): {body}{'...' if len(c.get('body','') or '') > 120 else ''}")
    return "\n".join(lines)


@tool(
    name="get_comment",
    description="Get a specific comment by its ID.",
    parameters={
        "comment_id": {
            "type": "integer",
            "description": "Comment ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["comment_id"],
)
def get_comment(comment_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        c = _gh_json("api", f"repos/{repo}/issues/comments/{comment_id}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    author = c.get("user", {}).get("login", "?")
    created = c.get("created_at", "?")
    updated = c.get("updated_at", "")
    body = c.get("body", "_No content_")
    return f"**Comment {comment_id}** by {author}\n**Created:** {created}\n**Updated:** {updated}\n\n{body}"


@tool(
    name="set_issue_milestone",
    description="Assign an issue or PR to a milestone.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue or PR number.",
        },
        "milestone": {
            "type": "string",
            "description": "Milestone title or number (number is more reliable).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number", "milestone"],
)
def set_issue_milestone(number: int, milestone: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    # If milestone is a title, look up its number
    milestone_num = milestone
    if not milestone.isdigit():
        try:
            ms = _gh_json("api", f"repos/{repo}/milestones?state=all&per_page=100", timeout=15)
            for m in ms:
                if m["title"].lower() == milestone.lower():
                    milestone_num = str(m["number"])
                    break
            else:
                return f"Error: milestone '{milestone}' not found. Use list_milestones to see available ones."
        except RuntimeError as e:
            return f"Error: {e}"

    try:
        _gh("issue", "edit", str(number), "--milestone", milestone_num, "--repo", repo)
        return f"Set milestone to '{milestone}' on #{number}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_repo",
    description="Create a new repository on GitHub.",
    parameters={
        "name": {
            "type": "string",
            "description": "Repository name.",
        },
        "description": {
            "type": "string",
            "description": "Repository description.",
        },
        "private": {
            "type": "boolean",
            "description": "Create as private repository.",
        },
        "init": {
            "type": "boolean",
            "description": "Initialize with README.",
        },
        "license": {
            "type": "string",
            "description": "License template (e.g. mit, apache-2.0, gpl-3.0).",
        },
        "gitignore": {
            "type": "string",
            "description": "Gitignore template (e.g. Python, Node, Rust).",
        },
    },
    required=["name"],
)
def create_repo(name: str, description: str = "", private: bool = False, init: bool = False, license: str = "", gitignore: str = "") -> str:
    args = ["repo", "create", name]
    if private:
        args.append("--private")
    else:
        args.append("--public")
    if description:
        args += ["--description", description]
    if init:
        args.append("--add-readme")
    if license:
        args += ["--license", license]
    if gitignore:
        args += ["--gitignore", gitignore]
    try:
        url = _gh(*args, timeout=30).strip()
        return f"Created repository: {url}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_gist",
    description="Create a new gist with the given files.",
    parameters={
        "description": {
            "type": "string",
            "description": "Gist description.",
        },
        "public": {
            "type": "boolean",
            "description": "Create as public gist.",
        },
        "files": {
            "type": "string",
            "description": "JSON string mapping filename to content, e.g. '{\"hello.py\": \"print(\\\"hi\\\")\"}'",
        },
    },
    required=["files"],
)
def create_gist(description: str = "", public: bool = False, files: str = "{}") -> str:
    import json as j
    try:
        file_data = j.loads(files)
    except j.JSONDecodeError:
        return "Error: files must be a valid JSON object mapping filenames to content"
    args = ["gist", "create"]
    if description:
        args += ["--desc", description]
    if public:
        args.append("--public")
    else:
        args.append("--private")
    try:
        url = _gh(*args, *file_data.keys(), timeout=30).strip()
        return f"Created gist: {url}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_gists",
    description="List gists for the authenticated user.",
    parameters={
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
        "public": {
            "type": "boolean",
            "description": "Only show public gists.",
        },
    },
    required=[],
)
def list_gists(limit: int = 10, public: bool = False) -> str:
    args = ["gist", "list", "--limit", str(limit)]
    if public:
        args.append("--public")
    try:
        data = _gh_json(*args, timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No gists found."

    lines = []
    for g in data:
        vis = "public" if g.get("isPublic") else "secret"
        files = ", ".join(g.get("files", {}).keys()) if isinstance(g.get("files"), dict) else ", ".join(f.get("name","?") for f in (g.get("files") or []))
        lines.append(f"- `{g.get('name', g.get('id','?'))}` [{vis}] — {files}")
    return "\n".join(lines)


@tool(
    name="compare_refs",
    description="Compare two git references (branches, tags, commits) in a repository.",
    parameters={
        "base": {
            "type": "string",
            "description": "Base ref (e.g. main, v1.0).",
        },
        "head": {
            "type": "string",
            "description": "Head ref to compare against base.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["base", "head"],
)
def compare_refs(base: str, head: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/compare/{base}...{head}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    ahead = data.get("ahead_by", 0)
    behind = data.get("behind_by", 0)
    files = data.get("files", [])
    total_changes = sum(f.get("changes", 0) for f in files)
    additions = sum(f.get("additions", 0) for f in files)
    deletions = sum(f.get("deletions", 0) for f in files)
    commits = data.get("total_commits", 0)
    status = data.get("status", "?")

    lines = [
        f"**{base}...{head}** — {status}",
        f"**Commits:** {commits} | **Files:** {len(files)} | **Changes:** +{additions}/-{deletions} ({total_changes} total)",
        f"**Ahead by:** {ahead} | **Behind by:** {behind}",
        "",
    ]
    for f in files[:30]:
        status_icon = {"added": "+", "removed": "-", "modified": "~", "renamed": "→"}.get(f.get("status", ""), " ")
        lines.append(f"  {status_icon} `{f['filename']}` (+{f.get('additions',0)}/-{f.get('deletions',0)})")
    if len(files) > 30:
        lines.append(f"  ... and {len(files) - 30} more files")
    return "\n".join(lines)


@tool(
    name="trigger_workflow",
    description="Trigger (dispatch) a GitHub Actions workflow by filename. Optionally pass inputs and target branch.",
    parameters={
        "workflow": {
            "type": "string",
            "description": "Workflow filename (e.g. 'ci.yml') or ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "ref": {
            "type": "string",
            "description": "Branch to run the workflow on (defaults to default branch).",
        },
        "inputs": {
            "type": "string",
            "description": "JSON string of workflow inputs, e.g. '{\"name\":\"value\"}'",
        },
    },
    required=["workflow"],
)
def trigger_workflow(workflow: str, repo: str = "", ref: str = "", inputs: str = "{}") -> str:
    repo = repo or _get_repo()
    import json as j
    try:
        input_data = j.loads(inputs) if inputs and inputs != "{}" else None
    except j.JSONDecodeError:
        return "Error: inputs must be valid JSON"
    # Resolve workflow filename to ID if needed
    wf_id = workflow
    if not workflow.isdigit():
        try:
            wfs = _gh_json("api", f"repos/{repo}/actions/workflows?per_page=100", timeout=15)
            for w in wfs.get("workflows", []):
                if w["name"] == workflow or w["path"].endswith("/" + workflow):
                    wf_id = str(w["id"])
                    break
            else:
                return f"Error: workflow '{workflow}' not found. Use list_workflows to see available ones."
        except RuntimeError as e:
            return f"Error: {e}"
    args = ["api", f"repos/{repo}/actions/workflows/{wf_id}/dispatches", "--method", "POST",
            "--raw-field", f'ref={ref or "main"}']
    if input_data:
        args[-1] += f',"inputs":{j.dumps(input_data)}'
    try:
        _gh(*args, timeout=15)
        return f"Triggered workflow '{workflow}' on {ref or 'default branch'}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_workflows",
    description="List all GitHub Actions workflow files in a repository.",
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
def list_workflows(repo: str = "", limit: int = 20) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/actions/workflows?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    workflows = data.get("workflows", [])
    if not workflows:
        return "No workflows found."

    lines = []
    for w in workflows:
        state = w.get("state", "?")
        badge = "✓" if state == "active" else ("✗" if state == "disabled" else "•")
        lines.append(f"- {badge} **{w['name']}** — `{w['path']}` [{state}]")
    return "\n".join(lines)


@tool(
    name="update_pr_branch",
    description="Update a pull request branch with the latest changes from the base branch.",
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
def update_pr_branch(number: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/pulls/{number}/update-branch", "--method", "PUT", "--silent", timeout=30)
        return f"Updated PR #{number} branch with latest base"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="search_users",
    description="Search GitHub users by query.",
    parameters={
        "query": {
            "type": "string",
            "description": "Search query (supports qualifiers like type:org, repos:>10, followers:>100).",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=["query"],
)
def search_users(query: str, limit: int = 10) -> str:
    try:
        data = _gh_json("search", "users", query, "--limit", str(limit),
                        "--json", "login,name,url", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No users found."

    lines = []
    for u in data:
        name = u.get("name", "") or ""
        name_str = f" ({name})" if name else ""
        lines.append(f"- **{u['login']}**{name_str}")
    return "\n".join(lines)


@tool(
    name="remove_issue_labels",
    description="Remove specific labels from an issue or pull request.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue or PR number.",
        },
        "labels": {
            "type": "string",
            "description": "Comma-separated label names to remove.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number", "labels"],
)
def remove_issue_labels(number: int, labels: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    args = ["issue", "edit", str(number), "--repo", repo]
    for l in labels.split(","):
        l = l.strip()
        if l:
            args += ["--remove-label", l]
    try:
        _gh(*args)
        return f"Removed labels from #{number}: {labels}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_repo_topics",
    description="List all topics on a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def list_repo_topics(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/topics", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    topics = data.get("names", [])
    if not topics:
        return "No topics."
    return "Topics: " + ", ".join(f"`{t}`" for t in topics)


@tool(
    name="add_repo_topic",
    description="Add topics to a repository (replaces all existing topics — include all current ones to preserve them).",
    parameters={
        "topics": {
            "type": "string",
            "description": "Comma-separated topic names.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["topics"],
)
def add_repo_topic(topics: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    topic_list = [t.strip() for t in topics.split(",") if t.strip()]
    try:
        _gh("api", f"repos/{repo}/topics", "--method", "PUT",
            "--raw-field", f'names={j.dumps(topic_list)}', timeout=15)
        return f"Set topics: {', '.join(topic_list)}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_dependabot_alerts",
    description="List Dependabot security alerts for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "state": {
            "type": "string",
            "enum": ["open", "dismissed", "fixed"],
            "description": "Filter by alert state.",
        },
        "severity": {
            "type": "string",
            "enum": ["low", "medium", "high", "critical"],
            "description": "Filter by severity.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=[],
)
def list_dependabot_alerts(repo: str = "", state: str = "", severity: str = "", limit: int = 10) -> str:
    repo = repo or _get_repo()
    query = f"state={state}&" if state else ""
    if severity:
        query += f"severity={severity}&"
    query += f"per_page={limit}"
    try:
        data = _gh_json("api", f"repos/{repo}/dependabot/alerts?{query}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No Dependabot alerts found."

    lines = []
    for a in data:
        pkg = a.get("security_advisory", {}).get("package", {}).get("name", "?") if a.get("security_advisory") else (a.get("security_vulnerability", {}).get("package", {}).get("name", "?") if a.get("security_vulnerability") else "?")
        sev = a.get("security_advisory", {}).get("severity", "?") if a.get("security_advisory") else "?"
        state_str = a.get("state", "?")
        lines.append(f"- **{pkg}** [{sev}] ({state_str}) — {a.get('html_url', '')}")
    return "\n".join(lines)


@tool(
    name="set_issue_priority",
    description="Set priority on an issue by adding a priority label. Creates the label if it doesn't exist.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue or PR number.",
        },
        "priority": {
            "type": "string",
            "enum": ["critical", "high", "medium", "low"],
            "description": "Priority level.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number", "priority"],
)
def set_issue_priority(number: int, priority: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    label_name = f"priority:{priority}"
    color_map = {"critical": "b60205", "high": "d93f0b", "medium": "fbca04", "low": "0e8a16"}
    # Try to create label if it doesn't exist (silently ignore if already exists)
    try:
        _gh("label", "create", label_name, "--color", color_map.get(priority, "cccccc"),
            "--repo", repo, "--silent")
    except RuntimeError:
        pass
    try:
        _gh("issue", "edit", str(number), "--add-label", label_name, "--repo", repo)
        return f"Set priority:{priority} on #{number}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_deployments",
    description="List deployments for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "environment": {
            "type": "string",
            "description": "Filter by environment name (e.g. production, staging).",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=[],
)
def list_deployments(repo: str = "", environment: str = "", limit: int = 10) -> str:
    repo = repo or _get_repo()
    query = f"per_page={limit}"
    if environment:
        query += f"&environment={environment}"
    try:
        data = _gh_json("api", f"repos/{repo}/deployments?{query}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No deployments found."

    lines = []
    for d in data:
        env = d.get("environment", "?")
        creator = d.get("creator", {}).get("login", "?")
        created = d.get("created_at", "?")
        ref = d.get("ref", "?")
        status = "active" if d.get("statuses_url") else "?"
        lines.append(f"- `{ref}` → **{env}** by {creator} ({created}) [{status}]")
    return "\n".join(lines)


@tool(
    name="archive_repo",
    description="Archive a repository (makes it read-only).",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def archive_repo(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}", "--method", "PATCH",
            "--raw-field", 'archived=true', timeout=15)
        return f"Archived {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="unarchive_repo",
    description="Unarchive a previously archived repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def unarchive_repo(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}", "--method", "PATCH",
            "--raw-field", 'archived=false', timeout=15)
        return f"Unarchived {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="change_repo_visibility",
    description="Change repository visibility (public/private/internal).",
    parameters={
        "visibility": {
            "type": "string",
            "enum": ["public", "private", "internal"],
            "description": "New visibility setting.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["visibility"],
)
def change_repo_visibility(visibility: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("repo", "edit", repo, f"--{visibility}")
        return f"Changed {repo} visibility to {visibility}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="pin_issue",
    description="Pin an issue or pull request to the repository overview page.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue or PR number to pin.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number"],
)
def pin_issue(number: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/issues/{number}/pin", "--method", "POST", "--silent", timeout=15)
        return f"Pinned #{number}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="unpin_issue",
    description="Unpin an issue or pull request from the repository overview.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue or PR number to unpin.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number"],
)
def unpin_issue(number: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/issues/{number}/pin", "--method", "DELETE", "--silent", timeout=15)
        return f"Unpinned #{number}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_label",
    description="Update a label's name, color, or description.",
    parameters={
        "current_name": {
            "type": "string",
            "description": "Current label name.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "new_name": {
            "type": "string",
            "description": "New label name (if renaming).",
        },
        "color": {
            "type": "string",
            "description": "New hex color code without # (e.g. 'ff0000').",
        },
        "description": {
            "type": "string",
            "description": "New description.",
        },
    },
    required=["current_name"],
)
def update_label(current_name: str, repo: str = "", new_name: str = "", color: str = "", description: str = "") -> str:
    repo = repo or _get_repo()
    import urllib.parse
    encoded_name = urllib.parse.quote(current_name, safe='')
    args = ["api", f"repos/{repo}/labels/{encoded_name}", "--method", "PATCH"]
    if new_name:
        args += ["--raw-field", f'new_name={new_name}']
    if color:
        args += ["--raw-field", f'color={color}']
    if description:
        args += ["--raw-field", f'description={description}']
    try:
        _gh(*args, timeout=15)
        return f"Updated label '{current_name}'"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_label",
    description="Delete a label from a repository.",
    parameters={
        "name": {
            "type": "string",
            "description": "Label name to delete.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["name"],
)
def delete_label(name: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    import urllib.parse
    encoded_name = urllib.parse.quote(name, safe='')
    try:
        _gh("api", f"repos/{repo}/labels/{encoded_name}", "--method", "DELETE", "--silent", timeout=15)
        return f"Deleted label '{name}'"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_collaborators",
    description="List collaborators (users with access) on a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "role": {
            "type": "string",
            "enum": ["admin", "maintain", "push", "triage", "pull"],
            "description": "Filter by role.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=[],
)
def list_collaborators(repo: str = "", role: str = "", limit: int = 20) -> str:
    repo = repo or _get_repo()
    query = f"per_page={limit}"
    if role:
        query += f"&role={role}"
    try:
        data = _gh_json("api", f"repos/{repo}/collaborators?{query}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No collaborators found."

    lines = []
    for c in data:
        perms = c.get("role_name", c.get("permissions", {}).get("admin", ""))
        lines.append(f"- **{c['login']}** — {perms}")
    return "\n".join(lines)


@tool(
    name="add_collaborator",
    description="Add a collaborator to a repository with a specific permission level.",
    parameters={
        "username": {
            "type": "string",
            "description": "GitHub username to add.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "permission": {
            "type": "string",
            "enum": ["pull", "push", "admin", "maintain", "triage"],
            "description": "Permission level (default: push).",
        },
    },
    required=["username"],
)
def add_collaborator(username: str, repo: str = "", permission: str = "push") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/collaborators/{username}", "--method", "PUT",
            "--raw-field", f'permission={permission}', "--silent", timeout=15)
        return f"Added {username} as {permission} to {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="cancel_workflow_run",
    description="Cancel a running GitHub Actions workflow run.",
    parameters={
        "run_id": {
            "type": "integer",
            "description": "Workflow run ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["run_id"],
)
def cancel_workflow_run(run_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/actions/runs/{run_id}/cancel", "--method", "POST", "--silent", timeout=15)
        return f"Cancelled workflow run {run_id}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="rerun_workflow",
    description="Rerun a failed or cancelled workflow run.",
    parameters={
        "run_id": {
            "type": "integer",
            "description": "Workflow run ID to rerun.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "failed_jobs": {
            "type": "boolean",
            "description": "Only rerun failed jobs.",
        },
    },
    required=["run_id"],
)
def rerun_workflow(run_id: int, repo: str = "", failed_jobs: bool = False) -> str:
    repo = repo or _get_repo()
    endpoint = f"repos/{repo}/actions/runs/{run_id}/rerun-failed-jobs" if failed_jobs else f"repos/{repo}/actions/runs/{run_id}/rerun"
    try:
        _gh("api", endpoint, "--method", "POST", "--silent", timeout=15)
        return f"Reran workflow run {run_id}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_repo_license",
    description="Get the license content for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def get_repo_license(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/license", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    license_name = data.get("license", {}).get("name", "Unknown") if data.get("license") else "Unknown"
    key = data.get("license", {}).get("key", "?") if data.get("license") else "?"
    content = data.get("content", "")
    import base64
    try:
        decoded = base64.b64decode(content).decode("utf-8") if content else "No content"
    except Exception:
        decoded = "Could not decode license content"
    return f"## License: {license_name} ({key})\n\n```\n{decoded[:2000]}{'...' if len(decoded) > 2000 else ''}\n```"


@tool(
    name="list_repo_languages",
    description="Get the programming language breakdown by bytes for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def list_repo_languages(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/languages", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No language data available."

    total = sum(data.values())
    sorted_langs = sorted(data.items(), key=lambda x: x[1], reverse=True)
    lines = []
    for lang, bytes_count in sorted_langs:
        pct = (bytes_count / total) * 100 if total > 0 else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        lines.append(f"- {bar} **{lang}** {pct:.1f}% ({bytes_count:,} bytes)")
    return "\n".join(lines)


@tool(
    name="list_environments",
    description="List deployment environments for a repository.",
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
def list_environments(repo: str = "", limit: int = 20) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/environments?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    envs = data.get("environments", [])
    if not envs:
        return "No environments found."

    lines = []
    for e in envs:
        protection = "🔒" if e.get("protection_rules") else "  "
        lines.append(f"- {protection} **{e['name']}**")
    return "\n".join(lines)


@tool(
    name="get_pr_diff",
    description="Get the diff content of a pull request.",
    parameters={
        "number": {
            "type": "integer",
            "description": "PR number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "max_lines": {
            "type": "integer",
            "description": "Max lines of diff to show (default 100).",
        },
    },
    required=["number"],
)
def get_pr_diff(number: int, repo: str = "", max_lines: int = 100) -> str:
    repo = repo or _get_repo()
    try:
        result = subprocess.run(
            ["gh", "pr", "diff", str(number), "--repo", repo],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        diff = result.stdout
    except RuntimeError as e:
        return f"Error: {e}"

    lines = diff.split("\n")
    total = len(lines)
    shown = "\n".join(lines[:max_lines])
    if total > max_lines:
        shown += f"\n\n... truncated, {total - max_lines} more lines"
    return shown


@tool(
    name="list_pr_review_comments",
    description="List inline review comments on a pull request.",
    parameters={
        "number": {
            "type": "integer",
            "description": "PR number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=["number"],
)
def list_pr_review_comments(number: int, repo: str = "", limit: int = 20) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/pulls/{number}/comments?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No review comments found."

    lines = []
    for c in data:
        author = c.get("user", {}).get("login", "?")
        path = c.get("path", "?")
        line = c.get("line", c.get("original_line", "?"))
        body = (c.get("body", "") or "")[:100].replace("\n", " ")
        lines.append(f"- **{author}** on `{path}:{line}`: {body}")
    return "\n".join(lines)


@tool(
    name="list_commits",
    description="List commits on a branch with author, SHA, and message.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "branch": {
            "type": "string",
            "description": "Branch name (defaults to default branch).",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=[],
)
def list_commits(repo: str = "", branch: str = "", limit: int = 10) -> str:
    repo = repo or _get_repo()
    sha = branch or ""
    try:
        data = _gh_json("api", f"repos/{repo}/commits?sha={sha}&per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No commits found."

    lines = []
    for c in data:
        short_sha = c["sha"][:7]
        author = c.get("commit", {}).get("author", {}).get("name", "?")
        msg = (c.get("commit", {}).get("message", "") or "").split("\n")[0]
        lines.append(f"- `{short_sha}` **{author}** — {msg}")
    return "\n".join(lines)


@tool(
    name="list_tags",
    description="List tags in a repository.",
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
def list_tags(repo: str = "", limit: int = 20) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/tags?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No tags found."

    lines = []
    for t in data:
        sha = t.get("commit", {}).get("sha", "?")[:7] if t.get("commit") else "?"
        lines.append(f"- `{t['name']}` ({sha})")
    return "\n".join(lines)


@tool(
    name="create_commit_status",
    description="Set a commit status (e.g. pending, success, failure, error) on a specific commit SHA.",
    parameters={
        "sha": {
            "type": "string",
            "description": "Full commit SHA.",
        },
        "state": {
            "type": "string",
            "enum": ["pending", "success", "failure", "error"],
            "description": "Status state.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "description": {
            "type": "string",
            "description": "Short description of the status.",
        },
        "context": {
            "type": "string",
            "description": "Context label (e.g. 'ci/github-issues-manager').",
        },
        "target_url": {
            "type": "string",
            "description": "Target URL for the status details.",
        },
    },
    required=["sha", "state"],
)
def create_commit_status(sha: str, state: str, repo: str = "", description: str = "", context: str = "", target_url: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload = {"state": state, "description": description, "context": context or "github-issues-manager"}
    if target_url:
        payload["target_url"] = target_url
    try:
        _gh("api", f"repos/{repo}/statuses/{sha}", "--method", "POST",
            "--raw-field", j.dumps(payload), timeout=15)
        return f"Set commit status to {state} on {sha[:7]}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="enable_auto_merge",
    description="Enable auto-merge on a pull request with a specific merge method.",
    parameters={
        "number": {
            "type": "integer",
            "description": "PR number.",
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
    },
    required=["number"],
)
def enable_auto_merge(number: int, repo: str = "", method: str = "merge") -> str:
    repo = repo or _get_repo()
    try:
        _gh("pr", "merge", str(number), "--auto", f"--{method}", "--repo", repo)
        return f"Enabled auto-merge on PR #{number} ({method})"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="disable_auto_merge",
    description="Disable auto-merge on a pull request.",
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
def disable_auto_merge(number: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("pr", "merge", str(number), "--disable-auto", "--repo", repo)
        return f"Disabled auto-merge on PR #{number}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="transfer_repo",
    description="Transfer a repository to another user or organization.",
    parameters={
        "new_owner": {
            "type": "string",
            "description": "New owner (username or organization name).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["new_owner"],
)
def transfer_repo(new_owner: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    try:
        _gh("api", f"repos/{repo}/transfer", "--method", "POST",
            "--raw-field", j.dumps({"new_owner": new_owner}), timeout=30)
        return f"Transferred {repo} to {new_owner}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_issue_events",
    description="List timeline events for an issue (labeled, unlabeled, assigned, closed, referenced, etc.).",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue or PR number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=["number"],
)
def list_issue_events(number: int, repo: str = "", limit: int = 20) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/issues/{number}/events?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No events found."

    lines = []
    for e in data:
        actor = e.get("actor", {}).get("login", "?")
        event = e.get("event", "?")
        created = e.get("created_at", "?")
        extra = ""
        if event == "labeled":
            extra = f" → {e.get('label', {}).get('name', '?')}"
        elif event == "assigned":
            extra = f" → {e.get('assignee', {}).get('login', '?')}"
        elif event == "milestoned":
            extra = f" → {e.get('milestone', {}).get('title', '?')}"
        lines.append(f"- **{actor}** {event}{extra} ({created})")
    return "\n".join(lines)


@tool(
    name="remove_collaborator",
    description="Remove a collaborator from a repository.",
    parameters={
        "username": {
            "type": "string",
            "description": "GitHub username to remove.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["username"],
)
def remove_collaborator(username: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/collaborators/{username}", "--method", "DELETE", "--silent", timeout=15)
        return f"Removed {username} from {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_code_scanning_alerts",
    description="List Code Scanning security alerts for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "state": {
            "type": "string",
            "enum": ["open", "dismissed", "fixed"],
            "description": "Filter by state.",
        },
        "severity": {
            "type": "string",
            "enum": ["error", "warning", "note"],
            "description": "Filter by severity.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=[],
)
def list_code_scanning_alerts(repo: str = "", state: str = "", severity: str = "", limit: int = 10) -> str:
    repo = repo or _get_repo()
    query = f"per_page={limit}"
    if state:
        query += f"&state={state}"
    if severity:
        query += f"&severity={severity}"
    try:
        data = _gh_json("api", f"repos/{repo}/code-scanning/alerts?{query}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No code scanning alerts found."

    lines = []
    for a in data:
        rule = a.get("rule", {}).get("name", a.get("rule", {}).get("id", "?"))
        sev = a.get("rule", {}).get("security_severity_level", a.get("rule", {}).get("severity", "?"))
        state_str = a.get("state", "?")
        lines.append(f"- **{rule}** [{sev}] ({state_str}) — {a.get('html_url', '')}")
    return "\n".join(lines)


@tool(
    name="list_secret_scanning_alerts",
    description="List Secret Scanning alerts for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "state": {
            "type": "string",
            "enum": ["open", "resolved"],
            "description": "Filter by state.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=[],
)
def list_secret_scanning_alerts(repo: str = "", state: str = "", limit: int = 10) -> str:
    repo = repo or _get_repo()
    query = f"per_page={limit}"
    if state:
        query += f"&state={state}"
    try:
        data = _gh_json("api", f"repos/{repo}/secret-scanning/alerts?{query}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No secret scanning alerts found."

    lines = []
    for a in data:
        secret_type = a.get("secret_type_display_name", a.get("secret_type", "?"))
        state_str = a.get("state", "?")
        created = a.get("created_at", "?")
        lines.append(f"- **{secret_type}** [{state_str}] — detected {created}")
    return "\n".join(lines)


@tool(
    name="list_webhooks",
    description="List webhooks configured on a repository.",
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
def list_webhooks(repo: str = "", limit: int = 20) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/hooks?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No webhooks found."

    lines = []
    for h in data:
        url = h.get("config", {}).get("url", "?")
        events = ", ".join(h.get("events", []))
        active = "✓" if h.get("active") else "✗"
        lines.append(f"- {active} **{h['name']}** → `{url}` [{events}]")
    return "\n".join(lines)


@tool(
    name="get_branch_protection",
    description="Get branch protection rules for a branch.",
    parameters={
        "branch": {
            "type": "string",
            "description": "Branch name.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["branch"],
)
def get_branch_protection(branch: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/branches/{branch}/protection", timeout=15)
    except RuntimeError:
        return "No branch protection rules found (or branch doesn't exist)."

    lines = [f"## Branch protection: `{branch}`"]
    checks = []

    if data.get("required_status_checks"):
        contexts = data["required_status_checks"].get("contexts", [])
        strict = data["required_status_checks"].get("strict", False)
        checks.append(f"- ✅ Required status checks: {', '.join(contexts) or 'none'} (strict: {strict})")
    else:
        checks.append("- ❌ No required status checks")

    if data.get("required_pull_request_reviews"):
        reviews = data["required_pull_request_reviews"]
        approvals = reviews.get("required_approving_review_count", 0)
        dismiss = "requires dismissal" if reviews.get("dismiss_stale_reviews") else ""
        checks.append(f"- ✅ Required reviews: {approvals} approval(s) {dismiss}")
    else:
        checks.append("- ❌ No required reviews")

    if data.get("enforce_admins", {}).get("enabled"):
        checks.append("- ✅ Admin enforcement enabled")
    else:
        checks.append("- ❌ No admin enforcement")

    if data.get("restrictions"):
        users = data["restrictions"].get("users", [])
        teams = data["restrictions"].get("teams", [])
        users_str = ", ".join(u["login"] for u in users) if users else "none"
        teams_str = ", ".join(t["slug"] for t in teams) if teams else "none"
        checks.append(f"- 🔒 Push restrictions: users={users_str}, teams={teams_str}")
    else:
        checks.append("- ❌ No push restrictions")

    if data.get("required_linear_history", {}).get("enabled"):
        checks.append("- ✅ Linear history required")
    if data.get("allow_force_pushes", {}).get("enabled"):
        checks.append("- ⚠️ Force pushes allowed")
    if data.get("allow_deletions", {}).get("enabled"):
        checks.append("- ⚠️ Deletions allowed")

    lines.extend(checks)
    return "\n".join(lines)


@tool(
    name="repo_traffic",
    description="Get repository traffic data (clones and views for the last 14 days).",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def repo_traffic(repo: str = "") -> str:
    repo = repo or _get_repo()
    lines = []
    try:
        views = _gh_json("api", f"repos/{repo}/traffic/views", timeout=15)
        view_count = views.get("count", 0)
        view_unique = views.get("uniques", 0)
        lines.append(f"**Views (14 days):** {view_count} total, {view_unique} unique")
    except RuntimeError:
        lines.append("**Views:** N/A")

    try:
        clones = _gh_json("api", f"repos/{repo}/traffic/clones", timeout=15)
        clone_count = clones.get("count", 0)
        clone_unique = clones.get("uniques", 0)
        lines.append(f"**Clones (14 days):** {clone_count} total, {clone_unique} unique")
    except RuntimeError:
        lines.append("**Clones:** N/A")

    try:
        referrers = _gh_json("api", f"repos/{repo}/traffic/popular/referrers", timeout=15)
        if referrers:
            top = referrers[0] if referrers else {}
            lines.append(f"**Top referrer:** {top.get('referrer', '?')} ({top.get('count', 0)} views)")
    except RuntimeError:
        pass

    try:
        paths = _gh_json("api", f"repos/{repo}/traffic/popular/paths", timeout=15)
        if paths:
            top = paths[0] if paths else {}
            lines.append(f"**Top path:** `{top.get('path', '?')}` ({top.get('count', 0)} views)")
    except RuntimeError:
        pass

    return "\n".join(lines)


@tool(
    name="list_licenses",
    description="List all available open source license templates.",
    parameters={},
    required=[],
)
def list_licenses() -> str:
    try:
        data = _gh_json("api", "licenses", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No licenses found."

    lines = []
    for l in data:
        desc = l.get("description", "")[:100]
        featured = " ★" if l.get("featured") else ""
        lines.append(f"- `{l['key']}`{featured} — **{l['name']}**")
    return "\n".join(lines)


@tool(
    name="render_markdown",
    description="Render GitHub Flavored Markdown text to HTML.",
    parameters={
        "text": {
            "type": "string",
            "description": "Markdown text to render.",
        },
        "mode": {
            "type": "string",
            "enum": ["markdown", "gfm"],
            "description": "Render mode: markdown or gfm (GitHub Flavored Markdown). Default: gfm.",
        },
        "context": {
            "type": "string",
            "description": "Repository context for GFM (owner/repo) to resolve issues/mentions.",
        },
    },
    required=["text"],
)
def render_markdown(text: str, mode: str = "gfm", context: str = "") -> str:
    import json as j
    payload = {"text": text, "mode": mode}
    if context:
        payload["context"] = context
    try:
        result = _gh("api", "markdown", "--method", "POST",
                      "--raw-field", j.dumps(payload), "--jq", ".", timeout=15)
        return result
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="watch_repo",
    description="Subscribe to notifications for a repository (watch).",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format.",
        },
    },
    required=["repo"],
)
def watch_repo(repo: str) -> str:
    try:
        _gh("api", f"repos/{repo}/subscription", "--method", "PUT",
            "--raw-field", '{"subscribed":true}', "--silent", timeout=15)
        return f"Watching {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="unwatch_repo",
    description="Unsubscribe from notifications for a repository (unwatch).",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format.",
        },
    },
    required=["repo"],
)
def unwatch_repo(repo: str) -> str:
    try:
        _gh("api", f"repos/{repo}/subscription", "--method", "DELETE", "--silent", timeout=15)
        return f"Unwatched {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="community_profile",
    description="Get the community health / profile metrics for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def community_profile(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/community/profile", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    health = data.get("health_percentage", 0)
    files = data.get("files", {})

    lines = [
        f"## Community Profile: {repo}",
        f"**Health:** {health}%",
        "",
        "### Files",
    ]

    file_status = {
        "code_of_conduct": "CODE_OF_CONDUCT",
        "contributing": "CONTRIBUTING",
        "issue_template": "Issue template",
        "pull_request_template": "PR template",
        "license": "License",
        "readme": "README",
        "funding": "FUNDING",
    }

    for key, label in file_status.items():
        f = files.get(key, {})
        if f:
            lines.append(f"- ✅ **{label}** — {f.get('url', 'present')}")
        else:
            lines.append(f"- ❌ **{label}** — missing")

    desc = data.get("description", "")
    if desc:
        lines.append(f"\n**Description:** {desc}")
    return "\n".join(lines)


@tool(
    name="list_deploy_keys",
    description="List deploy keys on a repository.",
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
def list_deploy_keys(repo: str = "", limit: int = 20) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/keys?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if not data:
        return "No deploy keys found."

    lines = []
    for k in data:
        title = k.get("title", "?")
        key_id = k.get("id", "?")
        read_only = "read-only" if k.get("read_only") else "read/write"
        lines.append(f"- **{title}** (id={key_id}, {read_only})")
    return "\n".join(lines)


@tool(
    name="add_deploy_key",
    description="Add a deploy key to a repository.",
    parameters={
        "title": {
            "type": "string",
            "description": "Title for the key.",
        },
        "key": {
            "type": "string",
            "description": "SSH public key content.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "read_only": {
            "type": "boolean",
            "description": "Restrict key to read-only access.",
        },
    },
    required=["title", "key"],
)
def add_deploy_key(title: str, key: str, repo: str = "", read_only: bool = True) -> str:
    repo = repo or _get_repo()
    import json as j
    payload = j.dumps({"title": title, "key": key, "read_only": read_only})
    try:
        _gh("api", f"repos/{repo}/keys", "--method", "POST",
            "--raw-field", payload, "--silent", timeout=15)
        return f"Added deploy key '{title}' to {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_actions_artifacts",
    description="List GitHub Actions artifacts for a repository.",
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
def list_actions_artifacts(repo: str = "", limit: int = 10) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/actions/artifacts?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    artifacts = data.get("artifacts", [])
    if not artifacts:
        return "No artifacts found."

    lines = []
    for a in artifacts:
        name = a.get("name", "?")
        size_kb = a.get("size_in_bytes", 0) // 1024
        created = a.get("created_at", "?")
        expired = "expired" if a.get("expired") else "active"
        lines.append(f"- **{name}** ({size_kb} KB, {expired}) — {created}")
    return "\n".join(lines)


@tool(
    name="list_repo_secrets",
    description="List names of secrets configured in a repository (values are never exposed).",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def list_repo_secrets(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/actions/secrets", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    secrets = data.get("secrets", [])
    if not secrets:
        return "No secrets found."

    lines = []
    for s in secrets:
        created = s.get("created_at", "?")
        updated = s.get("updated_at", "")
        lines.append(f"- `{s['name']}` (created: {created})")
    return "\n".join(lines)


@tool(
    name="list_repo_variables",
    description="List names of variables configured in a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def list_repo_variables(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/actions/variables", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    variables = data.get("variables", [])
    if not variables:
        return "No variables found."

    lines = []
    for v in variables:
        created = v.get("created_at", "?")
        lines.append(f"- `{v['name']}` (created: {created})")
    return "\n".join(lines)


@tool(
    name="get_workflow_logs",
    description="Get the download URL for workflow run logs.",
    parameters={
        "run_id": {
            "type": "integer",
            "description": "Workflow run ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["run_id"],
)
def get_workflow_logs(run_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/actions/runs/{run_id}/logs", repo="", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return f"Logs URL: {data.get('url', 'N/A')}"


@tool(
    name="remove_issue_assignees",
    description="Remove specific assignees from an issue or pull request.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue or PR number.",
        },
        "assignees": {
            "type": "string",
            "description": "Comma-separated GitHub usernames to remove.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number", "assignees"],
)
def remove_issue_assignees(number: int, assignees: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    args = ["issue", "edit", str(number), "--repo", repo]
    for a in assignees.split(","):
        a = a.strip()
        if a:
            args += ["--remove-assignee", a]
    try:
        _gh(*args)
        return f"Removed assignees from #{number}: {assignees}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_repo_merge_options",
    description="Configure which merge methods are allowed on a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "allow_merge_commit": {
            "type": "boolean",
            "description": "Allow merge commits.",
        },
        "allow_squash_merge": {
            "type": "boolean",
            "description": "Allow squash merging.",
        },
        "allow_rebase_merge": {
            "type": "boolean",
            "description": "Allow rebase merging.",
        },
        "delete_head_on_merge": {
            "type": "boolean",
            "description": "Automatically delete head branch on merge.",
        },
    },
    required=[],
)
def set_repo_merge_options(repo: str = "", allow_merge_commit: bool | None = None, allow_squash_merge: bool | None = None, allow_rebase_merge: bool | None = None, delete_head_on_merge: bool | None = None) -> str:
    repo = repo or _get_repo()
    import json as j
    payload = {}
    if allow_merge_commit is not None:
        payload["allow_merge_commit"] = allow_merge_commit
    if allow_squash_merge is not None:
        payload["allow_squash_merge"] = allow_squash_merge
    if allow_rebase_merge is not None:
        payload["allow_rebase_merge"] = allow_rebase_merge
    if delete_head_on_merge is not None:
        payload["delete_head_on_merge"] = delete_head_on_merge
    if not payload:
        return "No options specified to change."
    try:
        _gh("api", f"repos/{repo}", "--method", "PATCH",
            "--raw-field", j.dumps(payload), "--silent", timeout=15)
        return f"Updated merge options for {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_issue_templates",
    description="List available issue templates for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def list_issue_templates(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/issue-templates", timeout=15)
    except RuntimeError:
        pass
    else:
        if data:
            lines = []
            for t in data:
                name = t.get("name", "?")
                about = t.get("about", "")
                about_str = f" — {about}" if about else ""
                lines.append(f"- **{name}**{about_str}")
            if lines:
                return "\n".join(lines)

    # Fallback: check for template files in .github/
    try:
        templates = _gh_json("api", f"repos/{repo}/contents/.github/ISSUE_TEMPLATE", timeout=15)
        lines = []
        for t in templates:
            if t["type"] == "file":
                lines.append(f"- `{t['name']}`")
        if lines:
            return "Issue templates:\n" + "\n".join(lines)
    except RuntimeError:
        pass

    return "No issue templates found."


@tool(
    name="create_repo_from_template",
    description="Create a repository from a template repository.",
    parameters={
        "template_repo": {
            "type": "string",
            "description": "Template repository in owner/repo format.",
        },
        "name": {
            "type": "string",
            "description": "New repository name.",
        },
        "owner": {
            "type": "string",
            "description": "Owner of the new repo (defaults to authenticated user).",
        },
        "description": {
            "type": "string",
            "description": "Description for the new repo.",
        },
        "private": {
            "type": "boolean",
            "description": "Create as private.",
        },
    },
    required=["template_repo", "name"],
)
def create_repo_from_template(template_repo: str, name: str, owner: str = "", description: str = "", private: bool = False) -> str:
    import json as j
    payload = {"name": name, "private": private}
    if owner:
        payload["owner"] = owner
    if description:
        payload["description"] = description
    try:
        data = _gh_json("api", f"repos/{template_repo}/generate", "--method", "POST",
                        "--raw-field", j.dumps(payload), timeout=30)
        full_name = data.get("full_name", "?")
        return f"Created {full_name} from template {template_repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_workflow_run",
    description="Get detailed information about a specific workflow run.",
    parameters={
        "run_id": {
            "type": "integer",
            "description": "Workflow run ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["run_id"],
)
def get_workflow_run(run_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/actions/runs/{run_id}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    lines = [
        f"**Run:** {data.get('name', '?')} (#{data.get('run_number', '?')})",
        f"**Status:** {data.get('status', '?')} — {data.get('conclusion', '?')}",
        f"**Branch:** {data.get('head_branch', '?')}",
        f"**Trigger:** {data.get('event', '?')}",
        f"**Commit:** {data.get('head_sha', '?')[:7]}",
        f"**Created:** {data.get('created_at', '?')}",
        f"**Duration:** {data.get('run_started_at', '?')} → {data.get('updated_at', '?')}",
        f"**URL:** {data.get('html_url', '?')}",
    ]
    return "\n".join(lines)


@tool(
    name="delete_workflow_run",
    description="Delete a specific workflow run. Logs and artifacts are also deleted.",
    parameters={
        "run_id": {
            "type": "integer",
            "description": "Workflow run ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["run_id"],
)
def delete_workflow_run(run_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/actions/runs/{run_id}", "--method", "DELETE", "--silent", timeout=15)
        return f"Deleted workflow run #{run_id}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_artifact",
    description="Delete a specific workflow artifact.",
    parameters={
        "artifact_id": {
            "type": "integer",
            "description": "Artifact ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["artifact_id"],
)
def delete_artifact(artifact_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/actions/artifacts/{artifact_id}", "--method", "DELETE", "--silent", timeout=15)
        return f"Deleted artifact #{artifact_id}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_repo_secret",
    description="Create or update an Actions secret in a repository.",
    parameters={
        "name": {
            "type": "string",
            "description": "Secret name (uppercase, underscores).",
        },
        "value": {
            "type": "string",
            "description": "Secret value.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["name", "value"],
)
def set_repo_secret(name: str, value: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("secret", "set", name, "--repo", repo, "--body", value, timeout=15)
        return f"Secret '{name}' set on {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_repo_secret",
    description="Delete an Actions secret from a repository.",
    parameters={
        "name": {
            "type": "string",
            "description": "Secret name.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["name"],
)
def delete_repo_secret(name: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/actions/secrets/{name}", "--method", "DELETE", "--silent", timeout=15)
        return f"Secret '{name}' deleted from {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_repo_variable",
    description="Create or update an Actions variable in a repository.",
    parameters={
        "name": {
            "type": "string",
            "description": "Variable name.",
        },
        "value": {
            "type": "string",
            "description": "Variable value.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["name", "value"],
)
def set_repo_variable(name: str, value: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("variable", "set", name, "--repo", repo, "--body", value, timeout=15)
        return f"Variable '{name}' set on {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_repo_variable",
    description="Delete an Actions variable from a repository.",
    parameters={
        "name": {
            "type": "string",
            "description": "Variable name.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["name"],
)
def delete_repo_variable(name: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/actions/variables/{name}", "--method", "DELETE", "--silent", timeout=15)
        return f"Variable '{name}' deleted from {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_webhook",
    description="Create a repository webhook.",
    parameters={
        "url": {
            "type": "string",
            "description": "Payload URL for the webhook.",
        },
        "events": {
            "type": "string",
            "description": "Comma-separated event names to trigger on (default: push).",
        },
        "secret": {
            "type": "string",
            "description": "Secret token for webhook verification.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "active": {
            "type": "boolean",
            "description": "Deliver payloads when events occur.",
        },
    },
    required=["url"],
)
def create_webhook(url: str, events: str = "push", secret: str = "", repo: str = "", active: bool = True) -> str:
    repo = repo or _get_repo()
    import json as j
    config = {"url": url, "content_type": "json"}
    if secret:
        config["secret"] = secret
    event_list = [e.strip() for e in events.split(",") if e.strip()]
    payload = j.dumps({"name": "web", "config": config, "events": event_list, "active": active})
    try:
        data = _gh_json("api", f"repos/{repo}/hooks", "--method", "POST",
                        "--raw-field", payload, timeout=15)
        hook_id = data.get("id", "?")
        return f"Webhook #{hook_id} created on {repo} (events: {events})"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_webhook",
    description="Delete a repository webhook.",
    parameters={
        "hook_id": {
            "type": "integer",
            "description": "Webhook ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["hook_id"],
)
def delete_webhook(hook_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/hooks/{hook_id}", "--method", "DELETE", "--silent", timeout=15)
        return f"Webhook #{hook_id} deleted from {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="ping_webhook",
    description="Send a ping event to a repository webhook.",
    parameters={
        "hook_id": {
            "type": "integer",
            "description": "Webhook ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["hook_id"],
)
def ping_webhook(hook_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/hooks/{hook_id}/pings", "--method", "POST", "--silent", timeout=15)
        return f"Ping sent to webhook #{hook_id}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_milestone",
    description="Get a specific milestone.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Milestone number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number"],
)
def get_milestone(number: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/milestones/{number}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**Milestone #{data.get('number')}:** {data.get('title', '?')}\n"
        f"**State:** {data.get('state', '?')} — {data.get('open_issues', 0)} open / {data.get('closed_issues', 0)} closed\n"
        f"**Due:** {data.get('due_on', 'none')}\n"
        f"**Description:** {data.get('description', '')}"
    )


@tool(
    name="update_milestone",
    description="Update a milestone.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Milestone number.",
        },
        "title": {
            "type": "string",
            "description": "New title.",
        },
        "state": {
            "type": "string",
            "enum": ["open", "closed"],
            "description": "New state.",
        },
        "description": {
            "type": "string",
            "description": "New description.",
        },
        "due_on": {
            "type": "string",
            "description": "New due date (ISO 8601, e.g. 2026-07-01T00:00:00Z).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number"],
)
def update_milestone(number: int, title: str = "", state: str = "", description: str = "", due_on: str = "", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload = {}
    if title:
        payload["title"] = title
    if state:
        payload["state"] = state
    if description:
        payload["description"] = description
    if due_on:
        payload["due_on"] = due_on
    if not payload:
        return "Nothing to update."
    try:
        _gh("api", f"repos/{repo}/milestones/{number}", "--method", "PATCH",
            "--raw-field", j.dumps(payload), "--silent", timeout=15)
        return f"Milestone #{number} updated"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_milestone",
    description="Delete a milestone.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Milestone number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number"],
)
def delete_milestone(number: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/milestones/{number}", "--method", "DELETE", "--silent", timeout=15)
        return f"Milestone #{number} deleted"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_deploy_key",
    description="Delete a deploy key from a repository.",
    parameters={
        "key_id": {
            "type": "integer",
            "description": "Deploy key ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["key_id"],
)
def delete_deploy_key(key_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/keys/{key_id}", "--method", "DELETE", "--silent", timeout=15)
        return f"Deploy key #{key_id} deleted"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_branch",
    description="Get a single branch with protection and commit info.",
    parameters={
        "branch": {
            "type": "string",
            "description": "Branch name.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["branch"],
)
def get_branch(branch: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/branches/{branch}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    commit = data.get("commit", {})
    protected = data.get("protected", False)
    protection = data.get("protection", {})
    lines = [
        f"**Branch:** {data.get('name', '?')}",
        f"**Protected:** {protected}",
        f"**Latest commit:** {commit.get('sha', '?')[:7]} — {commit.get('commit', {}).get('message', '?').split(chr(10))[0]}",
        f"**Author:** {commit.get('commit', {}).get('author', {}).get('name', '?')}",
        f"**Date:** {commit.get('commit', {}).get('author', {}).get('date', '?')}",
    ]
    if protection:
        urls = protection.get("url", "")
        if urls:
            lines.append(f"**Protection rules:** applied")
    return "\n".join(lines)


@tool(
    name="create_environment",
    description="Create or update a deployment environment.",
    parameters={
        "name": {
            "type": "string",
            "description": "Environment name.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "wait_timer": {
            "type": "integer",
            "description": "Wait timer in minutes (for required reviewers).",
        },
        "prevent_self_review": {
            "type": "boolean",
            "description": "Prevent authors from approving their own deployments.",
        },
    },
    required=["name"],
)
def create_environment(name: str, repo: str = "", wait_timer: int = 0, prevent_self_review: bool = False) -> str:
    repo = repo or _get_repo()
    import json as j
    payload: dict = {}
    if wait_timer > 0 or prevent_self_review:
        revision = {}
        if wait_timer > 0:
            revision["wait_timer"] = wait_timer * 60
        if prevent_self_review:
            revision["prevent_self_review"] = True
        payload["deployment_branch_policy"] = {"protected_branches": False, "custom_branch_policies": False}
    try:
        _gh("api", f"repos/{repo}/environments/{name}", "--method", "PUT",
            "--raw-field", j.dumps(payload) if payload else "{}", "--silent", timeout=15)
        return f"Environment '{name}' created/updated on {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_environment",
    description="Delete a deployment environment.",
    parameters={
        "name": {
            "type": "string",
            "description": "Environment name.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["name"],
)
def delete_environment(name: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/environments/{name}", "--method", "DELETE", "--silent", timeout=15)
        return f"Environment '{name}' deleted"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_deployment",
    description="Create a deployment.",
    parameters={
        "ref": {
            "type": "string",
            "description": "Branch, tag, or SHA to deploy.",
        },
        "environment": {
            "type": "string",
            "description": "Environment name (production, staging, etc.).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "description": {
            "type": "string",
            "description": "Deployment description.",
        },
        "auto_merge": {
            "type": "boolean",
            "description": "Auto-merge the ref if behind the base.",
        },
    },
    required=["ref", "environment"],
)
def create_deployment(ref: str, environment: str, repo: str = "", description: str = "", auto_merge: bool = True) -> str:
    repo = repo or _get_repo()
    import json as j
    payload = j.dumps({
        "ref": ref,
        "environment": environment,
        "description": description,
        "auto_merge": auto_merge,
        "production_environment": environment == "production",
    })
    try:
        data = _gh_json("api", f"repos/{repo}/deployments", "--method", "POST",
                        "--raw-field", payload, timeout=15)
        deploy_id = data.get("id", "?")
        return f"Deployment #{deploy_id} created on {repo} ({environment})"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_deployment_statuses",
    description="List statuses for a deployment.",
    parameters={
        "deployment_id": {
            "type": "integer",
            "description": "Deployment ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=["deployment_id"],
)
def list_deployment_statuses(deployment_id: int, repo: str = "", limit: int = 10) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/deployments/{deployment_id}/statuses?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No deployment statuses found."
    lines = []
    for s in data:
        state = s.get("state", "?")
        creator = s.get("creator", {}).get("login", "?")
        created = s.get("created_at", "?")
        desc = s.get("description", "")
        desc_str = f" — {desc}" if desc else ""
        lines.append(f"- **{state}** by {creator}{desc_str} ({created})")
    return "\n".join(lines)


@tool(
    name="get_commit",
    description="Get a single commit by SHA with details.",
    parameters={
        "sha": {
            "type": "string",
            "description": "Commit SHA.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["sha"],
)
def get_commit(sha: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/commits/{sha}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    commit = data.get("commit", {})
    author = commit.get("author", {})
    lines = [
        f"**SHA:** {data.get('sha', '?')}",
        f"**Author:** {author.get('name', '?')} <{author.get('email', '?')}>",
        f"**Date:** {author.get('date', '?')}",
        f"**Message:** {commit.get('message', '?').split(chr(10))[0]}",
        f"**Files:** {len(data.get('files', []))} changed",
    ]
    stats = commit.get("stats", {})
    if stats:
        lines.append(f"**Stats:** +{stats.get('additions', 0)} / -{stats.get('deletions', 0)}")
    return "\n".join(lines)


@tool(
    name="get_repo_content",
    description="Get the content of a file or directory from a repository.",
    parameters={
        "path": {
            "type": "string",
            "description": "File or directory path.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "ref": {
            "type": "string",
            "description": "Branch or tag name. Defaults to default branch.",
        },
    },
    required=["path"],
)
def get_repo_content(path: str, repo: str = "", ref: str = "") -> str:
    repo = repo or _get_repo()
    url = f"repos/{repo}/contents/{path}"
    if ref:
        url += f"?ref={ref}"
    try:
        data = _gh_json("api", url, timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"

    if isinstance(data, list):
        lines = [f"## Contents of `{path}`\n"]
        for item in data:
            icon = "📄" if item["type"] == "file" else "📁"
            lines.append(f"- {icon} `{item['name']}`")
        return "\n".join(lines)

    content_b64 = data.get("content", "")
    if data.get("encoding") == "base64" and content_b64:
        import base64
        try:
            decoded = base64.b64decode(content_b64).decode("utf-8")
            size = data.get("size", 0)
            if len(decoded) > 2000:
                decoded = decoded[:2000] + f"\n\n... (truncated, {size} bytes total)"
            if data.get("type") == "symlink":
                return f"**Symlink:** {data.get('target', '?')}\n\nContent:\n{decoded}"
            if data.get("type") == "submodule":
                return f"**Submodule:** {data.get('submodule_git_url', '?')}"
            return f"## `{path}`\n\n{decoded}"
        except Exception:
            pass
    return f"{data.get('name', '?')} — {data.get('type', '?')} ({data.get('size', 0)} bytes)"


@tool(
    name="list_forks",
    description="List forks of a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
        "sort": {
            "type": "string",
            "description": "Sort by: newest, oldest, stargazers, watchers.",
        },
    },
    required=[],
)
def list_forks(repo: str = "", limit: int = 10, sort: str = "newest") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/forks?per_page={limit}&sort={sort}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No forks found."
    lines = []
    for f in data:
        full_name = f.get("full_name", "?")
        stars = f.get("stargazers_count", 0)
        forks = f.get("forks_count", 0)
        owner = f.get("owner", {}).get("login", "?")
        lines.append(f"- **{full_name}** (⭐{stars}, 🍴{forks}) by {owner}")
    return "\n".join(lines)


@tool(
    name="list_commit_statuses",
    description="List commit statuses for a given reference.",
    parameters={
        "ref": {
            "type": "string",
            "description": "Branch, tag, or SHA.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=["ref"],
)
def list_commit_statuses(ref: str, repo: str = "", limit: int = 20) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/commits/{ref}/statuses?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No statuses found."
    lines = []
    for s in data:
        state = s.get("state", "?")
        context = s.get("context", "?")
        desc = s.get("description", "")
        target = s.get("target_url", "")
        desc_str = f" — {desc}" if desc else ""
        lines.append(f"- **{context}**: {state}{desc_str}")
    return "\n".join(lines)


@tool(
    name="get_combined_commit_status",
    description="Get the combined commit status for a given reference.",
    parameters={
        "ref": {
            "type": "string",
            "description": "Branch, tag, or SHA.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["ref"],
)
def get_combined_commit_status(ref: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/commits/{ref}/status", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    state = data.get("state", "?")
    statuses = data.get("statuses", [])
    total = data.get("total_count", 0)
    lines = [
        f"**Combined state:** {state}",
        f"**Total statuses:** {total}",
        "",
    ]
    for s in statuses:
        context = s.get("context", "?")
        st = s.get("state", "?")
        lines.append(f"- **{context}**: {st}")
    return "\n".join(lines)


@tool(
    name="create_git_ref",
    description="Create a git reference (branch or tag).",
    parameters={
        "ref": {
            "type": "string",
            "description": "Full reference name (e.g. refs/heads/new-branch or refs/tags/v1.0).",
        },
        "sha": {
            "type": "string",
            "description": "SHA to point the reference to.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["ref", "sha"],
)
def create_git_ref(ref: str, sha: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload = j.dumps({"ref": ref, "sha": sha})
    try:
        data = _gh_json("api", f"repos/{repo}/git/refs", "--method", "POST",
                        "--raw-field", payload, timeout=15)
        return f"Created ref: {data.get('ref', '?')} → {data.get('object', {}).get('sha', '?')[:7]}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_git_ref",
    description="Delete a git reference (branch, tag, etc.).",
    parameters={
        "ref": {
            "type": "string",
            "description": "Full reference (e.g. refs/heads/branch-name).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["ref"],
)
def delete_git_ref(ref: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    # GitHub API expects ref without 'refs/' prefix
    ref_path = ref[5:] if ref.startswith("refs/") else ref
    try:
        _gh("api", f"repos/{repo}/git/refs/{ref_path}", "--method", "DELETE", "--silent", timeout=15)
        return f"Ref '{ref}' deleted"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_reactions",
    description="List reactions for an issue, comment, or PR review comment.",
    parameters={
        "issue_number": {
            "type": "integer",
            "description": "Issue or PR number (mutually exclusive with comment_id).",
        },
        "comment_id": {
            "type": "integer",
            "description": "Comment ID (mutually exclusive with issue_number).",
        },
        "content": {
            "type": "string",
            "description": "Filter by reaction type (+1, -1, laugh, confused, heart, hooray, rocket, eyes).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def list_reactions(issue_number: int = 0, comment_id: int = 0, content: str = "", repo: str = "") -> str:
    repo = repo or _get_repo()
    url_suffix = f"?content={content}" if content else ""
    if comment_id:
        url = f"repos/{repo}/issues/comments/{comment_id}/reactions{url_suffix}"
    elif issue_number:
        url = f"repos/{repo}/issues/{issue_number}/reactions{url_suffix}"
    else:
        return "Provide either issue_number or comment_id."
    try:
        data = _gh_json("api", url, timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No reactions found."
    counts: dict[str, int] = {}
    for r in data:
        c = r.get("content", "?")
        counts[c] = counts.get(c, 0) + 1
    lines = [f"Reactions on issue/comment:"]
    for c, n in sorted(counts.items(), key=lambda x: -x[1]):
        lines.append(f"- :{c}: × {n}")
    return "\n".join(lines)


@tool(
    name="delete_reaction",
    description="Delete a reaction (by the authenticated user).",
    parameters={
        "reaction_id": {
            "type": "integer",
            "description": "Reaction ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["reaction_id"],
)
def delete_reaction(reaction_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/reactions/{reaction_id}", "--method", "DELETE", "--silent", timeout=15)
        return f"Reaction #{reaction_id} deleted"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_release",
    description="Update a release.",
    parameters={
        "release_id": {
            "type": "integer",
            "description": "Release ID.",
        },
        "tag_name": {
            "type": "string",
            "description": "New tag name.",
        },
        "name": {
            "type": "string",
            "description": "New release title.",
        },
        "body": {
            "type": "string",
            "description": "New release body.",
        },
        "draft": {
            "type": "boolean",
            "description": "Mark as draft.",
        },
        "prerelease": {
            "type": "boolean",
            "description": "Mark as prerelease.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["release_id"],
)
def update_release(release_id: int, tag_name: str = "", name: str = "", body: str = "", draft: bool | None = None, prerelease: bool | None = None, repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload: dict = {}
    if tag_name:
        payload["tag_name"] = tag_name
    if name:
        payload["name"] = name
    if body:
        payload["body"] = body
    if draft is not None:
        payload["draft"] = draft
    if prerelease is not None:
        payload["prerelease"] = prerelease
    if not payload:
        return "Nothing to update."
    try:
        _gh("api", f"repos/{repo}/releases/{release_id}", "--method", "PATCH",
            "--raw-field", j.dumps(payload), "--silent", timeout=15)
        return f"Release #{release_id} updated"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_release",
    description="Delete a release.",
    parameters={
        "release_id": {
            "type": "integer",
            "description": "Release ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["release_id"],
)
def delete_release(release_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/releases/{release_id}", "--method", "DELETE", "--silent", timeout=15)
        return f"Release #{release_id} deleted"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_release_assets",
    description="List assets for a release.",
    parameters={
        "release_id": {
            "type": "integer",
            "description": "Release ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["release_id"],
)
def list_release_assets(release_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/releases/{release_id}/assets", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No assets found."
    lines = []
    for a in data:
        name = a.get("name", "?")
        size_kb = a.get("size", 0) // 1024
        downloads = a.get("download_count", 0)
        created = a.get("created_at", "?")
        lines.append(f"- **{name}** ({size_kb} KB, downloaded {downloads} times) — {created}")
    return "\n".join(lines)


@tool(
    name="upload_release_asset",
    description="Upload a release asset file. Provide the local file path.",
    parameters={
        "release_id": {
            "type": "integer",
            "description": "Release ID.",
        },
        "file": {
            "type": "string",
            "description": "Local file path to upload.",
        },
        "name": {
            "type": "string",
            "description": "Output filename. Defaults to the basename of the file.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["release_id", "file"],
)
def upload_release_asset(release_id: int, file: str, name: str = "", repo: str = "") -> str:
    repo = repo or _get_repo()
    import os
    if not os.path.isfile(file):
        return f"Error: file not found: {file}"
    label = name or os.path.basename(file)
    try:
        _gh("release", "upload", str(release_id), file,
            "--repo", repo, "--clobber", timeout=120)
        return f"Uploaded '{label}' to release #{release_id}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_code_scanning_alert",
    description="Update the status of a code scanning alert (dismiss or reopen).",
    parameters={
        "alert_number": {
            "type": "integer",
            "description": "Code scanning alert number.",
        },
        "state": {
            "type": "string",
            "enum": ["dismissed", "open"],
            "description": "New alert state.",
        },
        "dismissed_reason": {
            "type": "string",
            "enum": ["false positive", "won't fix", "used in tests"],
            "description": "Required when dismissing.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["alert_number", "state"],
)
def update_code_scanning_alert(alert_number: int, state: str, dismissed_reason: str = "", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload: dict = {"state": state}
    if state == "dismissed" and dismissed_reason:
        payload["dismissed_reason"] = dismissed_reason
    try:
        _gh("api", f"repos/{repo}/code-scanning/alerts/{alert_number}", "--method", "PATCH",
            "--raw-field", j.dumps(payload), "--silent", timeout=15)
        return f"Code scanning alert #{alert_number} set to {state}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_dependabot_alert",
    description="Update the status of a Dependabot alert (dismiss or reopen).",
    parameters={
        "alert_number": {
            "type": "integer",
            "description": "Dependabot alert number.",
        },
        "state": {
            "type": "string",
            "enum": ["dismissed", "open"],
            "description": "New alert state.",
        },
        "dismissed_reason": {
            "type": "string",
            "enum": ["fix_started", "inaccurate", "no_bandwidth", "not_used", "tolerable_risk"],
            "description": "Required when dismissing.",
        },
        "dismissed_comment": {
            "type": "string",
            "description": "Optional comment for dismissal.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["alert_number", "state"],
)
def update_dependabot_alert(alert_number: int, state: str, dismissed_reason: str = "", dismissed_comment: str = "", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload: dict = {"state": state}
    if state == "dismissed":
        if dismissed_reason:
            payload["dismissed_reason"] = dismissed_reason
        if dismissed_comment:
            payload["dismissed_comment"] = dismissed_comment
    try:
        _gh("api", f"repos/{repo}/dependabot/alerts/{alert_number}", "--method", "PATCH",
            "--raw-field", j.dumps(payload), "--silent", timeout=15)
        return f"Dependabot alert #{alert_number} set to {state}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_secret_scanning_alert",
    description="Update the status of a secret scanning alert (dismiss or reopen).",
    parameters={
        "alert_number": {
            "type": "integer",
            "description": "Secret scanning alert number.",
        },
        "state": {
            "type": "string",
            "enum": ["dismissed", "open"],
            "description": "New alert state.",
        },
        "dismissed_reason": {
            "type": "string",
            "enum": ["false_positive", "won't_fix", "revoked", "used_in_tests"],
            "description": "Required when dismissing.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["alert_number", "state"],
)
def update_secret_scanning_alert(alert_number: int, state: str, dismissed_reason: str = "", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload: dict = {"state": state}
    if state == "dismissed" and dismissed_reason:
        payload["dismissed_reason"] = dismissed_reason
    try:
        _gh("api", f"repos/{repo}/secret-scanning/alerts/{alert_number}", "--method", "PATCH",
            "--raw-field", j.dumps(payload), "--silent", timeout=15)
        return f"Secret scanning alert #{alert_number} set to {state}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_orgs",
    description="List organizations for the authenticated user.",
    parameters={
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=[],
)
def list_orgs(limit: int = 20) -> str:
    try:
        data = _gh_json("api", f"user/orgs?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No organizations found."
    lines = []
    for o in data:
        login = o.get("login", "?")
        desc = o.get("description", "")
        desc_str = f" — {desc}" if desc else ""
        lines.append(f"- **{login}**{desc_str}")
    return "\n".join(lines)


@tool(
    name="get_org",
    description="Get details about an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
    },
    required=["org"],
)
def get_org(org: str) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**{data.get('login', '?')}**\n"
        f"**Name:** {data.get('name', '?')}\n"
        f"**Description:** {data.get('description', '')}\n"
        f"**Public repos:** {data.get('public_repos', 0)}\n"
        f"**Followers:** {data.get('followers', 0)}\n"
        f"**Location:** {data.get('location', '?')}\n"
        f"**Blog:** {data.get('blog', '?')}\n"
        f"**Email:** {data.get('email', '?')}\n"
        f"**Verified:** {data.get('is_verified', False)}"
    )


@tool(
    name="list_org_members",
    description="List members of an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=["org"],
)
def list_org_members(org: str, limit: int = 20) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/members?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No members found."
    lines = []
    for m in data:
        login = m.get("login", "?")
        lines.append(f"- **{login}**")
    return f"Members of {org}:\n" + "\n".join(lines)


@tool(
    name="list_org_repos",
    description="List repositories in an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "type": {
            "type": "string",
            "description": "Type: all, public, private, forks, sources, member (default: all).",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=["org"],
)
def list_org_repos(org: str, type: str = "all", limit: int = 20) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/repos?per_page={limit}&type={type}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No repos found."
    lines = []
    for r in data:
        name = r.get("full_name", "?")
        stars = r.get("stargazers_count", 0)
        forks = r.get("forks_count", 0)
        private = "🔒" if r.get("private") else "🔓"
        lines.append(f"- {private} **{name}** (⭐{stars}, 🍴{forks})")
    return "\n".join(lines)


@tool(
    name="get_user",
    description="Get a GitHub user's public profile.",
    parameters={
        "username": {
            "type": "string",
            "description": "GitHub username. Defaults to authenticated user if omitted.",
        },
    },
    required=[],
)
def get_user(username: str = "") -> str:
    url = f"users/{username}" if username else "user"
    try:
        data = _gh_json("api", url, timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**{data.get('login', '?')}** ({data.get('name', '?')})\n"
        f"**Bio:** {data.get('bio', '')}\n"
        f"**Location:** {data.get('location', '?')}\n"
        f"**Company:** {data.get('company', '?')}\n"
        f"**Public repos:** {data.get('public_repos', 0)}\n"
        f"**Followers:** {data.get('followers', 0)} · **Following:** {data.get('following', 0)}\n"
        f"**Blog:** {data.get('blog', '?')}\n"
        f"**Twitter:** {data.get('twitter_username', '?')}\n"
        f"**Joined:** {data.get('created_at', '?')}"
    )


@tool(
    name="list_user_repos",
    description="List repositories for a user.",
    parameters={
        "username": {
            "type": "string",
            "description": "GitHub username. Defaults to authenticated user if omitted.",
        },
        "type": {
            "type": "string",
            "description": "Type: all, owner, member (default: owner).",
        },
        "sort": {
            "type": "string",
            "description": "Sort: created, updated, pushed, full_name.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=[],
)
def list_user_repos(username: str = "", type: str = "owner", sort: str = "updated", limit: int = 20) -> str:
    if username:
        url = f"users/{username}/repos?per_page={limit}&type={type}&sort={sort}"
    else:
        url = f"user/repos?per_page={limit}&type={type}&sort={sort}"
    try:
        data = _gh_json("api", url, timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No repos found."
    lines = []
    for r in data:
        name = r.get("full_name", "?")
        stars = r.get("stargazers_count", 0)
        private = "🔒" if r.get("private") else "🔓"
        desc = r.get("description", "")
        desc_str = f" — {desc}" if desc else ""
        lines.append(f"- {private} **{name}** (⭐{stars}){desc_str}")
    return "\n".join(lines)


@tool(
    name="list_followers",
    description="List followers of a user.",
    parameters={
        "username": {
            "type": "string",
            "description": "GitHub username. Defaults to authenticated user if omitted.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=[],
)
def list_followers(username: str = "", limit: int = 20) -> str:
    url = f"users/{username}/followers" if username else f"user/followers"
    try:
        data = _gh_json("api", f"{url}?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No followers found."
    lines = [f"**Followers{' of ' + username if username else ''}:**"]
    for u in data:
        lines.append(f"- {u.get('login', '?')}")
    return "\n".join(lines)


@tool(
    name="list_following",
    description="List who a user is following.",
    parameters={
        "username": {
            "type": "string",
            "description": "GitHub username. Defaults to authenticated user if omitted.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=[],
)
def list_following(username: str = "", limit: int = 20) -> str:
    url = f"users/{username}/following" if username else f"user/following"
    try:
        data = _gh_json("api", f"{url}?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "Not following anyone."
    lines = [f"**Following{' of ' + username if username else ''}:**"]
    for u in data:
        lines.append(f"- {u.get('login', '?')}")
    return "\n".join(lines)


@tool(
    name="follow_user",
    description="Follow a GitHub user.",
    parameters={
        "username": {
            "type": "string",
            "description": "Username to follow.",
        },
    },
    required=["username"],
)
def follow_user(username: str) -> str:
    try:
        _gh("api", f"user/following/{username}", "--method", "PUT", "--silent", timeout=15)
        return f"Now following {username}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="unfollow_user",
    description="Unfollow a GitHub user.",
    parameters={
        "username": {
            "type": "string",
            "description": "Username to unfollow.",
        },
    },
    required=["username"],
)
def unfollow_user(username: str) -> str:
    try:
        _gh("api", f"user/following/{username}", "--method", "DELETE", "--silent", timeout=15)
        return f"Unfollowed {username}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_projects",
    description="List project boards in a repository (classic Projects).",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "state": {
            "type": "string",
            "description": "State: open, closed, all (default: open).",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=[],
)
def list_projects(repo: str = "", state: str = "open", limit: int = 10) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/projects?state={state}&per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No project boards found."
    lines = []
    for p in data:
        name = p.get("name", "?")
        body = p.get("body", "") or ""
        body_str = f" — {body[:60]}" if body else ""
        columns_url = p.get("columns_url", "")
        lines.append(f"- **{name}** (id={p.get('id', '?')}){body_str}")
    return "\n".join(lines)


@tool(
    name="create_project",
    description="Create a project board in a repository.",
    parameters={
        "name": {
            "type": "string",
            "description": "Project name.",
        },
        "body": {
            "type": "string",
            "description": "Project description.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["name"],
)
def create_project(name: str, body: str = "", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload = j.dumps({"name": name, "body": body})
    try:
        data = _gh_json("api", f"repos/{repo}/projects", "--method", "POST",
                        "--raw-field", payload, timeout=15)
        project_id = data.get("id", "?")
        return f"Project '{name}' created (id={project_id})"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_actions_caches",
    description="List GitHub Actions caches for a repository.",
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
def list_actions_caches(repo: str = "", limit: int = 10) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/actions/caches?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    caches = data.get("actions_caches", [])
    if not caches:
        return "No caches found."
    total = data.get("total_count", 0)
    lines = [f"**Total caches:** {total}\n"]
    for c in caches:
        key = c.get("key", "?")
        size_mb = c.get("size_in_bytes", 0) // (1024 * 1024)
        ref = c.get("ref", "?")
        created = c.get("created_at", "?")
        lines.append(f"- `{key}` ({size_mb} MB, ref: {ref}) — {created}")
    return "\n".join(lines)


@tool(
    name="delete_actions_caches",
    description="Delete GitHub Actions caches by key or ref.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "cache_key": {
            "type": "string",
            "description": "Delete caches with this key prefix.",
        },
        "ref": {
            "type": "string",
            "description": "Delete caches for this branch/ref.",
        },
    },
    required=[],
)
def delete_actions_caches(repo: str = "", cache_key: str = "", ref: str = "") -> str:
    repo = repo or _get_repo()
    if not cache_key and not ref:
        return "Provide cache_key or ref to delete."
    params = []
    if cache_key:
        params.append(f"key={cache_key}")
    if ref:
        params.append(f"ref={ref}")
    qs = "&".join(params)
    try:
        result = _gh_json("api", f"repos/{repo}/actions/caches?{qs}", "--method", "DELETE", timeout=15)
        count = result.get("total_count", 0)
        return f"Deleted {count} cache(s)"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_runners",
    description="List self-hosted runners for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def list_runners(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/actions/runners", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    runners = data.get("runners", [])
    if not runners:
        return "No runners found."
    lines = []
    for r in runners:
        name = r.get("name", "?")
        os = r.get("os", "?")
        status = r.get("status", "?")
        busy = r.get("busy", False)
        busy_str = "🔴 busy" if busy else "🟢 idle"
        lines.append(f"- **{name}** ({os}, {busy_str}) — {status}")
    return "\n".join(lines)


@tool(
    name="list_rulesets",
    description="List repository rulesets (beta).",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def list_rulesets(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/rulesets", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No rulesets found."
    lines = []
    for r in data:
        name = r.get("name", "?")
        target = r.get("target", "?")
        enforcement = r.get("enforcement", "?")
        lines.append(f"- **{name}** (target: {target}, enforcement: {enforcement})")
    return "\n".join(lines)


@tool(
    name="list_autolinks",
    description="List autolink references for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def list_autolinks(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/autolinks", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No autolinks found."
    lines = []
    for a in data:
        prefix = a.get("key_prefix", "?")
        pattern = a.get("url_template", "")
        lines.append(f"- `{prefix}` → {pattern}")
    return "\n".join(lines)


@tool(
    name="list_commit_comments",
    description="List comments on a commit.",
    parameters={
        "ref": {
            "type": "string",
            "description": "Commit SHA, branch, or tag.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=["ref"],
)
def list_commit_comments(ref: str, repo: str = "", limit: int = 10) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/commits/{ref}/comments?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No comments on this commit."
    lines = []
    for c in data:
        user = c.get("user", {}).get("login", "?")
        body = c.get("body", "")[:120]
        created = c.get("created_at", "?")
        lines.append(f"- **{user}** ({created}): {body}")
    return "\n".join(lines)


@tool(
    name="get_emojis",
    description="Get GitHub emoji URLs and codes.",
    parameters={},
    required=[],
)
def get_emojis() -> str:
    try:
        data = _gh_json("api", "emojis", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    emojis = list(data.keys())[:50]
    preview = ", ".join(f":{e}:" for e in emojis[:20])
    return f"**Total emojis:** {len(data)}\n**Sample:** {preview}\n\nUse `:{name}:` in comments."


@tool(
    name="list_codes_of_conduct",
    description="List all codes of conduct.",
    parameters={},
    required=[],
)
def list_codes_of_conduct() -> str:
    try:
        data = _gh_json("api", "codes_of_conduct", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    lines = []
    for c in data:
        key = c.get("key", "?")
        name = c.get("name", "?")
        lines.append(f"- `{key}` — {name}")
    return "\n".join(lines)


@tool(
    name="list_gitignore_templates",
    description="List all .gitignore templates.",
    parameters={},
    required=[],
)
def list_gitignore_templates() -> str:
    try:
        data = _gh_json("api", "gitignore/templates", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return "Available .gitignore templates:\n" + ", ".join(data)


@tool(
    name="get_gitignore_template",
    description="Get a specific .gitignore template.",
    parameters={
        "name": {
            "type": "string",
            "description": "Template name (e.g. Python, Node, Rust).",
        },
    },
    required=["name"],
)
def get_gitignore_template(name: str) -> str:
    try:
        data = _gh_json("api", f"gitignore/templates/{name}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return f"# {data.get('name', '?')}\n```\n{data.get('source', '?')}\n```"


@tool(
    name="get_license",
    description="Get a specific open source license template.",
    parameters={
        "key": {
            "type": "string",
            "description": "License key (e.g. mit, apache-2.0, gpl-3.0).",
        },
    },
    required=["key"],
)
def get_license(key: str) -> str:
    try:
        data = _gh_json("api", f"licenses/{key}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**{data.get('name', '?')}** ({data.get('spdx_id', '?')})\n"
        f"**Description:** {data.get('description', '')}\n"
        f"**Permissions:** {', '.join(data.get('permissions', []))}\n"
        f"**Conditions:** {', '.join(data.get('conditions', []))}\n"
        f"**Limitations:** {', '.join(data.get('limitations', []))}\n"
        f"**Implementation:** {data.get('implementation', '')}\n"
        f"\n```\n{data.get('body', '')[:2000]}\n```"
    )


@tool(
    name="get_repo_archive",
    description="Get the download URL for a repository archive (zip or tar).",
    parameters={
        "ref": {
            "type": "string",
            "description": "Branch or tag name (default: default branch).",
        },
        "format": {
            "type": "string",
            "enum": ["zipball", "tarball"],
            "description": "Archive format (default: zipball).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def get_repo_archive(ref: str = "", format: str = "zipball", repo: str = "") -> str:
    repo = repo or _get_repo()
    url = f"repos/{repo}/{format}"
    if ref:
        url += f"/{ref}"
    try:
        data = _gh_json("api", url, timeout=15)
    except RuntimeError:
        pass
    return f"`{repo}/{format}/{ref or 'HEAD'}` — use `gh api {url}` to download."


@tool(
    name="get_dependency_sbom",
    description="Get the dependency SBOM (Software Bill of Materials) for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def get_dependency_sbom(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/dependency-graph/sbom", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    sbom = data.get("sbom", {})
    deps = sbom.get("packages", [])
    if not deps:
        return "No dependency data found."
    lines = [
        f"**SBOM for {repo}**",
        f"**SPDX ID:** {sbom.get('spdxId', '?')}",
        f"**Created:** {sbom.get('creationInfo', {}).get('created', '?')}",
        f"**Total dependencies:** {len(deps)}",
        "",
    ]
    for d in deps[:30]:
        name = d.get("name", "?")
        ver = d.get("versionInfo", "?")
        supplier = d.get("supplier", "")
        lines.append(f"- `{name}@{ver}`")
    if len(deps) > 30:
        lines.append(f"\n... and {len(deps) - 30} more.")
    return "\n".join(lines)


@tool(
    name="create_check_run",
    description="Create a check run on a commit.",
    parameters={
        "name": {
            "type": "string",
            "description": "Check run name.",
        },
        "head_sha": {
            "type": "string",
            "description": "Commit SHA to run the check on.",
        },
        "status": {
            "type": "string",
            "enum": ["queued", "in_progress", "completed"],
            "description": "Check run status.",
        },
        "conclusion": {
            "type": "string",
            "enum": ["success", "failure", "neutral", "cancelled", "timed_out", "action_required"],
            "description": "Required when status is completed.",
        },
        "details_url": {
            "type": "string",
            "description": "URL for details.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["name", "head_sha"],
)
def create_check_run(name: str, head_sha: str, status: str = "queued", conclusion: str = "", details_url: str = "", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload: dict = {"name": name, "head_sha": head_sha, "status": status}
    if conclusion:
        payload["conclusion"] = conclusion
        payload["status"] = "completed"
    if details_url:
        payload["details_url"] = details_url
    try:
        data = _gh_json("api", f"repos/{repo}/check-runs", "--method", "POST",
                        "--raw-field", j.dumps(payload), timeout=15)
        check_id = data.get("id", "?")
        return f"Check run '{name}' created (id={check_id})"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_tag_protection",
    description="List tag protection rules for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def list_tag_protection(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/tags/protection", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No tag protection rules."
    lines = []
    for t in data:
        pattern = t.get("pattern", "?")
        tid = t.get("id", "?")
        lines.append(f"- `{pattern}` (id={tid})")
    return "\n".join(lines)


@tool(
    name="get_pages_info",
    description="Get GitHub Pages site information for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def get_pages_info(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/pages", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**GitHub Pages for {repo}**\n"
        f"**URL:** {data.get('html_url', '?')}\n"
        f"**Status:** {data.get('status', '?')}\n"
        f"**Branch:** {data.get('source', {}).get('branch', '?')} — `{data.get('source', {}).get('path', '/')}`\n"
        f"**CNAME:** {data.get('cname', 'none')}\n"
        f"**HTTPS enforced:** {data.get('https_enforced', False)}"
    )


@tool(
    name="get_release_by_tag",
    description="Get a release by tag name.",
    parameters={
        "tag": {
            "type": "string",
            "description": "Git tag name.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["tag"],
)
def get_release_by_tag(tag: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/releases/tags/{tag}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**Release:** {data.get('name', '?')} (tag: {data.get('tag_name', '?')})\n"
        f"**Draft:** {data.get('draft', False)}  **Prerelease:** {data.get('prerelease', False)}\n"
        f"**Published:** {data.get('published_at', '?')}\n"
        f"**Assets:** {len(data.get('assets', []))}\n"
        f"**Body:** {data.get('body', '')[:500]}"
    )


@tool(
    name="delete_release_asset",
    description="Delete a release asset.",
    parameters={
        "asset_id": {
            "type": "integer",
            "description": "Asset ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["asset_id"],
)
def delete_release_asset(asset_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/releases/assets/{asset_id}", "--method", "DELETE", "--silent", timeout=15)
        return f"Asset #{asset_id} deleted"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_pull_request",
    description="Update a pull request (title, body, state, base branch).",
    parameters={
        "number": {
            "type": "integer",
            "description": "PR number.",
        },
        "title": {
            "type": "string",
            "description": "New title.",
        },
        "body": {
            "type": "string",
            "description": "New body text.",
        },
        "state": {
            "type": "string",
            "enum": ["open", "closed"],
            "description": "New state.",
        },
        "base": {
            "type": "string",
            "description": "New base branch name.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number"],
)
def update_pull_request(number: int, title: str = "", body: str = "", state: str = "", base: str = "", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload: dict = {}
    if title:
        payload["title"] = title
    if body:
        payload["body"] = body
    if state:
        payload["state"] = state
    if base:
        payload["base"] = base
    if not payload:
        return "Nothing to update."
    try:
        _gh("api", f"repos/{repo}/pulls/{number}", "--method", "PATCH",
            "--raw-field", j.dumps(payload), "--silent", timeout=15)
        return f"PR #{number} updated"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_pr_commits",
    description="List commits in a pull request.",
    parameters={
        "number": {
            "type": "integer",
            "description": "PR number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=["number"],
)
def list_pr_commits(number: int, repo: str = "", limit: int = 20) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/pulls/{number}/commits?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No commits found."
    lines = [f"**Commits in PR #{number}:**\n"]
    for c in data:
        sha = c.get("sha", "?")[:7]
        msg = c.get("commit", {}).get("message", "?").split("\n")[0]
        author = c.get("commit", {}).get("author", {}).get("name", "?")
        lines.append(f"- `{sha}` {msg} — {author}")
    return "\n".join(lines)


@tool(
    name="list_pr_files",
    description="List files changed in a pull request.",
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
def list_pr_files(number: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/pulls/{number}/files", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No files changed."
    lines = [f"**Files changed in PR #{number}:**\n"]
    for f in data:
        fname = f.get("filename", "?")
        status = f.get("status", "?")
        additions = f.get("additions", 0)
        deletions = f.get("deletions", 0)
        lines.append(f"- `{fname}` ({status}, +{additions}/-{deletions})")
    return "\n".join(lines)


@tool(
    name="dismiss_pr_review",
    description="Dismiss a PR review.",
    parameters={
        "review_id": {
            "type": "integer",
            "description": "Review ID.",
        },
        "message": {
            "type": "string",
            "description": "Dismissal message.",
        },
        "number": {
            "type": "integer",
            "description": "PR number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["review_id", "message", "number"],
)
def dismiss_pr_review(review_id: int, message: str, number: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload = j.dumps({"message": message})
    try:
        _gh("api", f"repos/{repo}/pulls/{number}/reviews/{review_id}/dismissals",
            "--method", "PUT", "--raw-field", payload, "--silent", timeout=15)
        return f"Review #{review_id} dismissed on PR #{number}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="add_issue_labels",
    description="Add labels to an issue without removing existing ones.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue number.",
        },
        "labels": {
            "type": "string",
            "description": "Comma-separated label names.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number", "labels"],
)
def add_issue_labels(number: int, labels: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    label_list = [l.strip() for l in labels.split(",") if l.strip()]
    payload = j.dumps({"labels": label_list})
    try:
        _gh("api", f"repos/{repo}/issues/{number}/labels", "--method", "POST",
            "--raw-field", payload, "--silent", timeout=15)
        return f"Labels added to #{number}: {', '.join(label_list)}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_issue_labels",
    description="Replace all labels on an issue (removes existing, sets new).",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue number.",
        },
        "labels": {
            "type": "string",
            "description": "Comma-separated label names.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number", "labels"],
)
def set_issue_labels(number: int, labels: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    label_list = [l.strip() for l in labels.split(",") if l.strip()]
    payload = j.dumps({"labels": label_list})
    try:
        _gh("api", f"repos/{repo}/issues/{number}/labels", "--method", "PUT",
            "--raw-field", payload, "--silent", timeout=15)
        return f"Labels set on #{number}: {', '.join(label_list)}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_team",
    description="Get team information from an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "team_slug": {
            "type": "string",
            "description": "Team slug (name in URL form).",
        },
    },
    required=["org", "team_slug"],
)
def get_team(org: str, team_slug: str) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/teams/{team_slug}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**Team:** {data.get('name', '?')} ({data.get('slug', '?')})\n"
        f"**Description:** {data.get('description', '')}\n"
        f"**Privacy:** {data.get('privacy', '?')}\n"
        f"**Members:** {data.get('members_count', 0)}  **Repos:** {data.get('repos_count', 0)}\n"
        f"**Parent:** {data.get('parent', {}).get('name', 'none')}"
    )


@tool(
    name="list_team_repos",
    description="List repositories a team has access to.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "team_slug": {
            "type": "string",
            "description": "Team slug.",
        },
    },
    required=["org", "team_slug"],
)
def list_team_repos(org: str, team_slug: str) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/teams/{team_slug}/repos", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No repos found."
    lines = []
    for r in data:
        name = r.get("full_name", "?")
        perm = r.get("permissions", {})
        perms = ", ".join(k for k, v in perm.items() if v)
        lines.append(f"- **{name}** ({perms})")
    return "\n".join(lines)


@tool(
    name="create_commit_comment",
    description="Create a comment on a commit.",
    parameters={
        "sha": {
            "type": "string",
            "description": "Commit SHA.",
        },
        "body": {
            "type": "string",
            "description": "Comment body.",
        },
        "path": {
            "type": "string",
            "description": "File path to comment on (optional).",
        },
        "position": {
            "type": "integer",
            "description": "Line position in the diff (optional).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["sha", "body"],
)
def create_commit_comment(sha: str, body: str, path: str = "", position: int = 0, repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload: dict = {"body": body}
    if path:
        payload["path"] = path
    if position:
        payload["position"] = position
    try:
        _gh("api", f"repos/{repo}/commits/{sha}/comments", "--method", "POST",
            "--raw-field", j.dumps(payload), "--silent", timeout=15)
        return f"Comment posted on commit {sha[:7]}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_or_update_file",
    description="Create or update a file in the repository.",
    parameters={
        "path": {
            "type": "string",
            "description": "File path in the repo.",
        },
        "content": {
            "type": "string",
            "description": "File content (plain text, will be base64-encoded).",
        },
        "message": {
            "type": "string",
            "description": "Commit message.",
        },
        "branch": {
            "type": "string",
            "description": "Branch name (default: default branch).",
        },
        "sha": {
            "type": "string",
            "description": "Current file SHA (required when updating an existing file).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["path", "content", "message"],
)
def create_or_update_file(path: str, content: str, message: str, branch: str = "", sha: str = "", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j, base64
    encoded = base64.b64encode(content.encode()).decode()
    payload: dict = {"message": message, "content": encoded}
    if branch:
        payload["branch"] = branch
    if sha:
        payload["sha"] = sha
    try:
        data = _gh_json("api", f"repos/{repo}/contents/{path}", "--method", "PUT",
                        "--raw-field", j.dumps(payload), timeout=15)
        commit_sha = data.get("commit", {}).get("sha", "?")[:7]
        action = "updated" if sha else "created"
        return f"File '{path}' {action} (commit: {commit_sha})"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_repo_file",
    description="Delete a file from the repository.",
    parameters={
        "path": {
            "type": "string",
            "description": "File path in the repo.",
        },
        "message": {
            "type": "string",
            "description": "Commit message.",
        },
        "sha": {
            "type": "string",
            "description": "Current file SHA (required). Get it from get_repo_content.",
        },
        "branch": {
            "type": "string",
            "description": "Branch name (default: default branch).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["path", "message", "sha"],
)
def delete_repo_file(path: str, message: str, sha: str, branch: str = "", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload: dict = {"message": message, "sha": sha}
    if branch:
        payload["branch"] = branch
    try:
        _gh("api", f"repos/{repo}/contents/{path}", "--method", "DELETE",
            "--raw-field", j.dumps(payload), "--silent", timeout=15)
        return f"File '{path}' deleted"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_blob",
    description="Get a git blob (file content) by SHA.",
    parameters={
        "sha": {
            "type": "string",
            "description": "Blob SHA.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["sha"],
)
def get_blob(sha: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/git/blobs/{sha}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    encoding = data.get("encoding", "?")
    content = data.get("content", "")
    size = data.get("size", 0)
    if encoding == "base64" and content:
        import base64
        try:
            decoded = base64.b64decode(content).decode("utf-8", errors="replace")
            if len(decoded) > 2000:
                decoded = decoded[:2000] + f"\n\n... (truncated, {size} bytes)"
            return f"**Blob {sha[:7]}** ({size} bytes)\n\n{decoded}"
        except Exception:
            pass
    return f"Blob {sha[:7]}: {size} bytes, encoded as {encoding}"


@tool(
    name="get_tree",
    description="Get a git tree by SHA with file listing.",
    parameters={
        "sha": {
            "type": "string",
            "description": "Tree SHA.",
        },
        "recursive": {
            "type": "boolean",
            "description": "Recursively list tree entries.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["sha"],
)
def get_tree(sha: str, recursive: bool = False, repo: str = "") -> str:
    repo = repo or _get_repo()
    url = f"repos/{repo}/git/trees/{sha}"
    if recursive:
        url += "?recursive=1"
    try:
        data = _gh_json("api", url, timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    tree = data.get("tree", [])
    truncated = data.get("truncated", False)
    lines = [f"**Tree {sha[:7]}** — {len(tree)} entries"]
    if truncated:
        lines.append("*(truncated)*")
    lines.append("")
    for entry in tree[:100]:
        mode = entry.get("mode", "?")
        etype = entry.get("type", "?")
        path = entry.get("path", "?")
        e_sha = entry.get("sha", "?")[:7]
        icon = "📁" if etype == "tree" else "📄"
        lines.append(f"- {icon} `{path}` ({etype}, {e_sha})")
    if len(tree) > 100:
        lines.append(f"\n... and {len(tree) - 100} more.")
    return "\n".join(lines)


@tool(
    name="list_codespaces",
    description="List codespaces for the authenticated user.",
    parameters={},
    required=[],
)
def list_codespaces() -> str:
    try:
        data = _gh_json("api", "user/codespaces", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    codespaces = data.get("codespaces", [])
    if not codespaces:
        return "No codespaces."
    lines = []
    for c in codespaces:
        name = c.get("name", "?")
        repo = c.get("repository", {}).get("full_name", "?")
        branch = c.get("branch", "?")
        state = c.get("state", "?")
        machine = c.get("machine", {}).get("display_name", "?")
        created = c.get("created_at", "?")
        lines.append(f"- **{name}** ({repo}#{branch}, {state}) — {machine}")
    return "\n".join(lines)


@tool(
    name="get_actions_billing",
    description="Get GitHub Actions billing for a repository or organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name. If omitted, gets billing for the current repo's owner.",
        },
        "repo": {
            "type": "string",
            "description": "Repository (only used if org is not set).",
        },
    },
    required=[],
)
def get_actions_billing(org: str = "", repo: str = "") -> str:
    if org:
        url = f"orgs/{org}/settings/billing/actions"
    else:
        r = repo or _get_repo()
        owner = r.split("/")[0]
        url = f"orgs/{owner}/settings/billing/actions"
    try:
        data = _gh_json("api", url, timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**Minutes used (included):** {data.get('total_minutes_used', 0)} / {data.get('total_paid_minutes_used', 0)} paid\n"
        f"**Minutes remaining:** {data.get('included_minutes', 0)}\n"
        f"**Minutes used breakdown:**\n"
        f"{json.dumps(data.get('minutes_used_breakdown', {}), indent=2)}"
    )


@tool(
    name="list_repo_invitations",
    description="List invitations to a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def list_repo_invitations(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/invitations", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No pending invitations."
    lines = []
    for i in data:
        inviter = i.get("inviter", {}).get("login", "?")
        invitee = i.get("invitee", {}).get("login", "?")
        perm = i.get("permissions", "?")
        created = i.get("created_at", "?")
        lines.append(f"- **{invitee}** by {inviter} ({perm}) — {created}")
    return "\n".join(lines)


@tool(
    name="create_autolink",
    description="Create an autolink reference for a repository.",
    parameters={
        "key_prefix": {
            "type": "string",
            "description": "Prefix for the autolink (e.g. TICKET-).",
        },
        "url_template": {
            "type": "string",
            "description": "URL template with <num> placeholder (e.g. https://example.com/ticket/<num>).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["key_prefix", "url_template"],
)
def create_autolink(key_prefix: str, url_template: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload = j.dumps({"key_prefix": key_prefix, "url_template": url_template})
    try:
        data = _gh_json("api", f"repos/{repo}/autolinks", "--method", "POST",
                        "--raw-field", payload, timeout=15)
        link_id = data.get("id", "?")
        return f"Autolink '{key_prefix}' created (id={link_id})"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_autolink",
    description="Delete an autolink reference from a repository.",
    parameters={
        "autolink_id": {
            "type": "integer",
            "description": "Autolink ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["autolink_id"],
)
def delete_autolink(autolink_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/autolinks/{autolink_id}", "--method", "DELETE", "--silent", timeout=15)
        return f"Autolink #{autolink_id} deleted"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_webhook",
    description="Get a single webhook configuration.",
    parameters={
        "hook_id": {
            "type": "integer",
            "description": "Webhook ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["hook_id"],
)
def get_webhook(hook_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/hooks/{hook_id}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    config = data.get("config", {})
    events = data.get("events", [])
    return (
        f"**Webhook #{hook_id}**\n"
        f"**URL:** {config.get('url', '?')}\n"
        f"**Content type:** {config.get('content_type', '?')}\n"
        f"**Active:** {data.get('active', False)}\n"
        f"**Events:** {', '.join(events)}\n"
        f"**Created:** {data.get('created_at', '?')}"
    )


@tool(
    name="update_webhook",
    description="Update a webhook configuration.",
    parameters={
        "hook_id": {
            "type": "integer",
            "description": "Webhook ID.",
        },
        "url": {
            "type": "string",
            "description": "New payload URL.",
        },
        "events": {
            "type": "string",
            "description": "Comma-separated events.",
        },
        "active": {
            "type": "boolean",
            "description": "Whether the webhook is active.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["hook_id"],
)
def update_webhook(hook_id: int, url: str = "", events: str = "", active: bool | None = None, repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload: dict = {}
    if url:
        payload["config"] = {"url": url, "content_type": "json"}
    if events:
        payload["events"] = [e.strip() for e in events.split(",") if e.strip()]
    if active is not None:
        payload["active"] = active
    if not payload:
        return "Nothing to update."
    try:
        _gh("api", f"repos/{repo}/hooks/{hook_id}", "--method", "PATCH",
            "--raw-field", j.dumps(payload), "--silent", timeout=15)
        return f"Webhook #{hook_id} updated"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_deploy_key",
    description="Get a single deploy key by ID.",
    parameters={
        "key_id": {
            "type": "integer",
            "description": "Deploy key ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["key_id"],
)
def get_deploy_key(key_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/keys/{key_id}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**Deploy Key #{key_id}:** {data.get('title', '?')}\n"
        f"**Read-only:** {data.get('read_only', True)}\n"
        f"**Created:** {data.get('created_at', '?')}\n"
        f"**Key:** `{data.get('key', '?')[:50]}...`"
    )


@tool(
    name="list_pr_reviews",
    description="List reviews on a pull request.",
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
def list_pr_reviews(number: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/pulls/{number}/reviews", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No reviews yet."
    lines = [f"**Reviews on PR #{number}:**\n"]
    for r in data:
        user = r.get("user", {}).get("login", "?")
        state = r.get("state", "?")
        submitted = r.get("submitted_at", "?")
        body = r.get("body", "")[:80]
        body_str = f" — {body}" if body else ""
        lines.append(f"- **{user}** ({state}){body_str} — {submitted}")
    return "\n".join(lines)


@tool(
    name="list_commit_prs",
    description="List pull requests that contain a specific commit.",
    parameters={
        "sha": {
            "type": "string",
            "description": "Commit SHA.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["sha"],
)
def list_commit_prs(sha: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/commits/{sha}/pulls", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No PRs contain this commit."
    lines = [f"**PRs containing {sha[:7]}:**\n"]
    for p in data:
        num = p.get("number", "?")
        title = p.get("title", "?")
        state = p.get("state", "?")
        lines.append(f"- **#{num}** ({state}): {title}")
    return "\n".join(lines)


@tool(
    name="get_weekly_commit_activity",
    description="Get weekly commit activity for a repository (last year).",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def get_weekly_commit_activity(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/stats/commit_activity", timeout=30)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No data available."
    total = sum(w.get("total", 0) for w in data[-52:])
    avg_weekly = total // max(len(data[-52:]), 1)
    weeks_with_commits = sum(1 for w in data[-52:] if w.get("total", 0) > 0)
    days = data[-1].get("days", []) if data else []
    recent_days = ", ".join(str(d) for d in days)
    return (
        f"**Weekly commit activity for {repo}**\n"
        f"**Total (last 52 weeks):** {total}\n"
        f"**Average per week:** {avg_weekly}\n"
        f"**Weeks with commits:** {weeks_with_commits}\n"
        f"**Latest week daily breakdown:** [{recent_days}]\n"
        f"**Data range:** {data[0].get('week', '?') if data else '?'} to {data[-1].get('week', '?') if data else '?'}"
    )


@tool(
    name="get_code_frequency",
    description="Get code frequency (weekly additions/deletions) for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "weeks": {
            "type": "integer",
            "description": "Number of weeks to show (default 10).",
        },
    },
    required=[],
)
def get_code_frequency(repo: str = "", weeks: int = 10) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/stats/code_frequency", timeout=30)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No data available."
    lines = [f"**Code frequency for {repo}** (last {min(weeks, len(data))} weeks):\n"]
    for w in data[-weeks:]:
        add, delete = w[1], abs(w[2])
        lines.append(f"- Week of {w[0]}: +{add} / -{delete}")
    total_add = sum(w[1] for w in data)
    total_del = sum(abs(w[2]) for w in data)
    lines.append(f"\n**Totals:** +{total_add} / -{total_del}")
    return "\n".join(lines)


@tool(
    name="create_gist_comment",
    description="Add a comment to a gist.",
    parameters={
        "gist_id": {
            "type": "string",
            "description": "Gist ID (the hex hash).",
        },
        "body": {
            "type": "string",
            "description": "Comment body.",
        },
    },
    required=["gist_id", "body"],
)
def create_gist_comment(gist_id: str, body: str) -> str:
    import json as j
    payload = j.dumps({"body": body})
    try:
        _gh("api", f"gists/{gist_id}/comments", "--method", "POST",
            "--raw-field", payload, "--silent", timeout=15)
        return f"Comment added to gist {gist_id[:7]}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_gist_comments",
    description="List comments on a gist.",
    parameters={
        "gist_id": {
            "type": "string",
            "description": "Gist ID (the hex hash).",
        },
    },
    required=["gist_id"],
)
def list_gist_comments(gist_id: str) -> str:
    try:
        data = _gh_json("api", f"gists/{gist_id}/comments", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No comments on this gist."
    lines = []
    for c in data:
        user = c.get("user", {}).get("login", "?")
        body = c.get("body", "")[:120]
        created = c.get("created_at", "?")
        lines.append(f"- **{user}** ({created}): {body}")
    return "\n".join(lines)


@tool(
    name="list_org_webhooks",
    description="List webhooks for an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
    },
    required=["org"],
)
def list_org_webhooks(org: str) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/hooks", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No org webhooks."
    lines = []
    for h in data:
        h_id = h.get("id", "?")
        url = h.get("config", {}).get("url", "?")
        active = h.get("active", False)
        events = ", ".join(h.get("events", []))
        lines.append(f"- **#{h_id}** ({'✅' if active else '❌'}) {url} — [{events}]")
    return "\n".join(lines)


@tool(
    name="create_org_webhook",
    description="Create a webhook for an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "url": {
            "type": "string",
            "description": "Payload URL.",
        },
        "events": {
            "type": "string",
            "description": "Comma-separated event names.",
        },
        "secret": {
            "type": "string",
            "description": "Webhook secret.",
        },
    },
    required=["org", "url"],
)
def create_org_webhook(org: str, url: str, events: str = "push", secret: str = "") -> str:
    import json as j
    config = {"url": url, "content_type": "json"}
    if secret:
        config["secret"] = secret
    event_list = [e.strip() for e in events.split(",") if e.strip()]
    payload = j.dumps({"name": "web", "config": config, "events": event_list, "active": True})
    try:
        data = _gh_json("api", f"orgs/{org}/hooks", "--method", "POST",
                        "--raw-field", payload, timeout=15)
        hook_id = data.get("id", "?")
        return f"Org webhook #{hook_id} created for {org}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_org_webhook",
    description="Delete an organization webhook.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "hook_id": {
            "type": "integer",
            "description": "Webhook ID.",
        },
    },
    required=["org", "hook_id"],
)
def delete_org_webhook(org: str, hook_id: int) -> str:
    try:
        _gh("api", f"orgs/{org}/hooks/{hook_id}", "--method", "DELETE", "--silent", timeout=15)
        return f"Org webhook #{hook_id} deleted from {org}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="check_org_membership",
    description="Check if a user is a member of an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "username": {
            "type": "string",
            "description": "GitHub username.",
        },
    },
    required=["org", "username"],
)
def check_org_membership(org: str, username: str) -> str:
    try:
        _gh("api", f"orgs/{org}/members/{username}", "--method", "GET", "--silent", timeout=15)
        return f"✅ **{username}** is a member of **{org}**"
    except RuntimeError as e:
        return f"❌ **{username}** is not a member of **{org}**"


@tool(
    name="get_org_membership",
    description="Get organization membership details for a user.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "username": {
            "type": "string",
            "description": "GitHub username.",
        },
    },
    required=["org", "username"],
)
def get_org_membership(org: str, username: str) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/memberships/{username}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**User:** {data.get('user', {}).get('login', '?')}\n"
        f"**Role:** {data.get('role', '?')}\n"
        f"**State:** {data.get('state', '?')}"
    )


@tool(
    name="set_team_membership",
    description="Add or update a user's role on a team.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "team_slug": {
            "type": "string",
            "description": "Team slug.",
        },
        "username": {
            "type": "string",
            "description": "GitHub username.",
        },
        "role": {
            "type": "string",
            "enum": ["member", "maintainer"],
            "description": "Team role (default: member).",
        },
    },
    required=["org", "team_slug", "username"],
)
def set_team_membership(org: str, team_slug: str, username: str, role: str = "member") -> str:
    import json as j
    payload = j.dumps({"role": role})
    try:
        _gh("api", f"orgs/{org}/teams/{team_slug}/memberships/{username}",
            "--method", "PUT", "--raw-field", payload, "--silent", timeout=15)
        return f"{username} added to team {team_slug} as {role}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="remove_team_member",
    description="Remove a user from a team.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "team_slug": {
            "type": "string",
            "description": "Team slug.",
        },
        "username": {
            "type": "string",
            "description": "GitHub username.",
        },
    },
    required=["org", "team_slug", "username"],
)
def remove_team_member(org: str, team_slug: str, username: str) -> str:
    try:
        _gh("api", f"orgs/{org}/teams/{team_slug}/memberships/{username}",
            "--method", "DELETE", "--silent", timeout=15)
        return f"{username} removed from team {team_slug}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="generate_release_notes",
    description="Generate release notes from a git tag or commit range.",
    parameters={
        "tag_name": {
            "type": "string",
            "description": "Name of the new tag.",
        },
        "previous_tag": {
            "type": "string",
            "description": "Previous tag to compare against.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["tag_name"],
)
def generate_release_notes(tag_name: str, previous_tag: str = "", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload: dict = {"tag_name": tag_name}
    if previous_tag:
        payload["target_commitish"] = previous_tag
    try:
        data = _gh_json("api", f"repos/{repo}/releases/generate-notes", "--method", "POST",
                        "--raw-field", j.dumps(payload), timeout=15)
        return data.get("body", "No notes generated.")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="trigger_workflow_with_inputs",
    description="Trigger a workflow dispatch event with custom inputs.",
    parameters={
        "workflow": {
            "type": "string",
            "description": "Workflow file name (e.g. ci.yml) or ID.",
        },
        "ref": {
            "type": "string",
            "description": "Branch or tag name (default: default branch).",
        },
        "inputs": {
            "type": "string",
            "description": "JSON string of key-value inputs (e.g. {\"key\":\"value\"}).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["workflow"],
)
def trigger_workflow_with_inputs(workflow: str, ref: str = "", inputs: str = "{}", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload = {"ref": ref or f"refs/heads/{_default_branch(repo)}"}
    parsed = j.loads(inputs)
    if parsed:
        payload["inputs"] = parsed
    try:
        _gh("api", f"repos/{repo}/actions/workflows/{workflow}/dispatches",
            "--method", "POST", "--raw-field", j.dumps(payload), "--silent", timeout=15)
        inputs_desc = f" with inputs: {inputs}" if parsed else ""
        return f"Workflow '{workflow}' triggered on {payload['ref']}{inputs_desc}"
    except RuntimeError as e:
        return f"Error: {e}"


def _default_branch(repo: str) -> str:
    """Helper: get default branch name for a repo."""
    try:
        data = _gh_json("api", f"repos/{repo}", timeout=10)
        return data.get("default_branch", "main")
    except Exception:
        return "main"


@tool(
    name="enable_vulnerability_alerts",
    description="Enable Dependabot vulnerability alerts for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def enable_vulnerability_alerts(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/vulnerability-alerts", "--method", "PUT", "--silent", timeout=15)
        return f"Vulnerability alerts enabled for {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="disable_vulnerability_alerts",
    description="Disable Dependabot vulnerability alerts for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def disable_vulnerability_alerts(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/vulnerability-alerts", "--method", "DELETE", "--silent", timeout=15)
        return f"Vulnerability alerts disabled for {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="enable_automatic_security_fixes",
    description="Enable automatic security fixes for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def enable_automatic_security_fixes(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/automated-security-fixes", "--method", "PUT", "--silent", timeout=15)
        return f"Automatic security fixes enabled for {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="disable_automatic_security_fixes",
    description="Disable automatic security fixes for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def disable_automatic_security_fixes(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/automated-security-fixes", "--method", "DELETE", "--silent", timeout=15)
        return f"Automatic security fixes disabled for {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_merge_queue_entries",
    description="List entries in the merge queue for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def list_merge_queue_entries(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/merge-queue/entries", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No merge queue entries."
    lines = []
    for e in data:
        pr_num = e.get("pull_request", {}).get("number", "?")
        title = e.get("pull_request", {}).get("title", "?")
        state = e.get("state", "?")
        enqueued = e.get("enqueued_at", "?")
        lines.append(f"- **#{pr_num}** ({state}): {title} — enqueued {enqueued}")
    return "\n".join(lines)


@tool(
    name="get_repo_interaction_limits",
    description="Get interaction limits for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def get_repo_interaction_limits(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/interaction-limits", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    limit = data.get("limit", "none")
    origin = data.get("origin", "?")
    expires = data.get("expires_at", "?")
    return f"**Interaction limit:** {limit} (set by: {origin}, expires: {expires})"


@tool(
    name="set_repo_interaction_limits",
    description="Set interaction limits for a repository.",
    parameters={
        "limit": {
            "type": "string",
            "enum": ["collaborators_only", "contributors_only", "existing_users"],
            "description": "Interaction limit level.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["limit"],
)
def set_repo_interaction_limits(limit: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload = j.dumps({"limit": limit})
    try:
        _gh("api", f"repos/{repo}/interaction-limits", "--method", "PUT",
            "--raw-field", payload, "--silent", timeout=15)
        return f"Interaction limit set to '{limit}' for {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="remove_repo_interaction_limits",
    description="Remove interaction limits for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def remove_repo_interaction_limits(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/interaction-limits", "--method", "DELETE", "--silent", timeout=15)
        return f"Interaction limits removed for {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_release",
    description="Get a specific release by ID.",
    parameters={
        "release_id": {
            "type": "integer",
            "description": "Release ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["release_id"],
)
def get_release(release_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/releases/{release_id}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**Release:** {data.get('name', '?')} (tag: {data.get('tag_name', '?')})\n"
        f"**Draft:** {data.get('draft', False)}  **Prerelease:** {data.get('prerelease', False)}\n"
        f"**Published:** {data.get('published_at', '?')}\n"
        f"**Assets:** {len(data.get('assets', []))}\n"
        f"**Body:** {data.get('body', '')[:500]}"
    )


@tool(
    name="get_workflow_usage",
    description="Get workflow usage statistics (billable minutes).",
    parameters={
        "workflow_id": {
            "type": "integer",
            "description": "Workflow ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["workflow_id"],
)
def get_workflow_usage(workflow_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/actions/workflows/{workflow_id}/timing", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    billable = data.get("billable", {})
    lines = [f"**Workflow #{workflow_id} usage:**"]
    for os_name, minutes in billable.items():
        total_ms = minutes.get("total_ms", 0)
        total_min = total_ms / 60000
        lines.append(f"- **{os_name}**: {total_min:.1f} min ({total_ms} ms)")
    return "\n".join(lines)


@tool(
    name="get_app",
    description="Get info about the currently authenticated GitHub App.",
    parameters={},
    required=[],
)
def get_app() -> str:
    try:
        data = _gh_json("api", "app", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**App:** {data.get('name', '?')}\n"
        f"**Slug:** {data.get('slug', '?')}\n"
        f"**Description:** {data.get('description', '')}\n"
        f"**URL:** {data.get('html_url', '?')}\n"
        f"**Permissions:** {json.dumps(data.get('permissions', {}), indent=2)}"
    )


@tool(
    name="list_app_installations",
    description="List installations of the authenticated GitHub App.",
    parameters={},
    required=[],
)
def list_app_installations() -> str:
    try:
        data = _gh_json("api", "app/installations", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No installations."
    lines = []
    for i in data:
        app_slug = i.get("app_slug", "?")
        account = i.get("account", {}).get("login", "?")
        target_type = i.get("target_type", "?")
        repo_selection = i.get("repository_selection", "?")
        lines.append(f"- **{app_slug}** on {account} ({target_type}, {repo_selection})")
    return "\n".join(lines)


@tool(
    name="create_commit",
    description="Create a git commit object (low-level Git API).",
    parameters={
        "message": {
            "type": "string",
            "description": "Commit message.",
        },
        "tree_sha": {
            "type": "string",
            "description": "SHA of the tree for this commit.",
        },
        "parents": {
            "type": "string",
            "description": "Comma-separated parent commit SHAs.",
        },
        "author_name": {
            "type": "string",
            "description": "Author name (default: authenticated user).",
        },
        "author_email": {
            "type": "string",
            "description": "Author email.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["message", "tree_sha"],
)
def create_commit(message: str, tree_sha: str, parents: str = "", author_name: str = "", author_email: str = "", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload: dict = {"message": message, "tree": tree_sha}
    if parents:
        payload["parents"] = [p.strip() for p in parents.split(",") if p.strip()]
    if author_name or author_email:
        author = {}
        if author_name:
            author["name"] = author_name
        if author_email:
            author["email"] = author_email
        if author:
            payload["author"] = author
    try:
        data = _gh_json("api", f"repos/{repo}/git/commits", "--method", "POST",
                        "--raw-field", j.dumps(payload), timeout=15)
        sha = data.get("sha", "?")
        return f"Commit created: {sha[:7]}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="check_if_following",
    description="Check if the authenticated user is following another user.",
    parameters={
        "username": {
            "type": "string",
            "description": "GitHub username to check.",
        },
    },
    required=["username"],
)
def check_if_following(username: str) -> str:
    try:
        _gh("api", f"user/following/{username}", "--method", "GET", "--silent", timeout=15)
        return f"✅ You are following **{username}**"
    except RuntimeError as e:
        return f"❌ You are not following **{username}**"


@tool(
    name="list_org_secrets",
    description="List Dependabot secrets for an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
    },
    required=["org"],
)
def list_org_secrets(org: str) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/dependabot/secrets", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    secrets = data.get("secrets", [])
    if not secrets:
        return "No Dependabot secrets for this org."
    lines = []
    for s in secrets:
        created = s.get("created_at", "?")
        visibility = s.get("visibility", "?")
        lines.append(f"- `{s['name']}` (visibility: {visibility}, created: {created})")
    return "\n".join(lines)


@tool(
    name="get_repo_custom_properties",
    description="Get custom property values for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def get_repo_custom_properties(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/properties/values", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No custom property values."
    lines = []
    for p in data:
        prop_name = p.get("property_name", "?")
        value = p.get("value", "?")
        source = p.get("source_type", "?")
        lines.append(f"- **{prop_name}**: {value} (source: {source})")
    return "\n".join(lines)


@tool(
    name="get_org_teams",
    description="List all teams in an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=["org"],
)
def get_org_teams(org: str, limit: int = 20) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/teams?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No teams found."
    lines = []
    for t in data:
        name = t.get("name", "?")
        slug = t.get("slug", "?")
        privacy = t.get("privacy", "?")
        members = t.get("members_count", 0)
        repos = t.get("repos_count", 0)
        lines.append(f"- **{name}** (`{slug}`, {privacy}, {members} members, {repos} repos)")
    return "\n".join(lines)


@tool(
    name="get_environment",
    description="Get a single deployment environment.",
    parameters={
        "name": {
            "type": "string",
            "description": "Environment name.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["name"],
)
def get_environment(name: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/environments/{name}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**Environment:** {data.get('name', '?')}\n"
        f"**Deployment branch policy:** {data.get('deployment_branch_policy', {})}\n"
        f"**Protection rules:** {len(data.get('protection_rules', []))}"
    )


@tool(
    name="list_stargazers",
    description="List users who have starred a repository.",
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
def list_stargazers(repo: str = "", limit: int = 20) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/stargazers?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No stargazers found."
    lines = []
    for s in data:
        login = s.get("login", "?")
        lines.append(f"- **{login}**")
    return "\n".join(lines)


@tool(
    name="list_watchers",
    description="List users watching (subscribed to) a repository.",
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
def list_watchers(repo: str = "", limit: int = 20) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/subscribers?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No watchers found."
    lines = []
    for s in data:
        login = s.get("login", "?")
        lines.append(f"- **{login}**")
    return "\n".join(lines)


@tool(
    name="get_latest_release",
    description="Get the latest published release for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def get_latest_release(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/releases/latest", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**Latest Release:** {data.get('name', '?')}\n"
        f"**Tag:** {data.get('tag_name', '?')}\n"
        f"**Published:** {data.get('published_at', '?')}\n"
        f"**Assets:** {len(data.get('assets', []))}\n"
        f"**Body:** {data.get('body', '')[:500]}"
    )


@tool(
    name="get_meta",
    description="Get GitHub API meta info (IP ranges, SSH keys, etc.).",
    parameters={},
    required=[],
)
def get_meta() -> str:
    try:
        data = _gh_json("api", "meta", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**GH Actions IPs:** {len(data.get('actions', []))} ranges\n"
        f"**GH Pages IPs:** {len(data.get('pages', []))} ranges\n"
        f"**API IPs:** {len(data.get('api', []))} ranges\n"
        f"**Git IPs:** {len(data.get('git', []))} ranges\n"
        f"**Hook IPs:** {len(data.get('hooks', []))} ranges\n"
        f"**Web IPs:** {len(data.get('web', []))} ranges\n"
        f"**SSH key fingerprints:** {list(data.get('ssh_key_fingerprints', {}).keys())}\n"
        f"**Verifiable password:** {data.get('verifiable_password_authentication', False)}"
    )


@tool(
    name="get_octocat",
    description="Get a random Zen saying or Octocat ASCII art from GitHub.",
    parameters={
        "say": {
            "type": "string",
            "description": "Custom message for the Octocat.",
        },
    },
    required=[],
)
def get_octocat(say: str = "") -> str:
    args = ["api", "octocat"]
    if say:
        args += ["--raw-field", f"say={say}"]
    try:
        return _gh(*args, timeout=15).strip()
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_zen",
    description="Get a random Zen of GitHub design philosophy.",
    parameters={},
    required=[],
)
def get_zen() -> str:
    try:
        return _gh("api", "zen", "--raw-field", "--silent", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_secret_scanning_locations",
    description="List locations for a secret scanning alert.",
    parameters={
        "alert_number": {
            "type": "integer",
            "description": "Secret scanning alert number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["alert_number"],
)
def list_secret_scanning_locations(alert_number: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/secret-scanning/alerts/{alert_number}/locations", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No locations found."
    lines = []
    for loc in data:
        location_type = loc.get("type", "?")
        path = loc.get("details", {}).get("path", "?")
        start_line = loc.get("details", {}).get("start_line", "?")
        lines.append(f"- **{location_type}:** `{path}` line {start_line}")
    return "\n".join(lines)


@tool(
    name="list_code_scanning_analyses",
    description="List code scanning analyses for a repository.",
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
def list_code_scanning_analyses(repo: str = "", limit: int = 10) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/code-scanning/analyses?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No analyses found."
    lines = []
    for a in data:
        analysis_id = a.get("id", "?")
        ref = a.get("ref", "?")
        tool = a.get("tool", {}).get("name", "?")
        results = a.get("results_count", 0)
        warning = a.get("warning_count", 0)
        created = a.get("created_at", "?")
        lines.append(f"- **#{analysis_id}** ({tool}) — {results} results, {warning} warnings — {ref} ({created})")
    return "\n".join(lines)


@tool(
    name="delete_code_scanning_analysis",
    description="Delete a code scanning analysis from a repository.",
    parameters={
        "analysis_id": {
            "type": "integer",
            "description": "Analysis ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["analysis_id"],
)
def delete_code_scanning_analysis(analysis_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/code-scanning/analyses/{analysis_id}", "--method", "DELETE", "--silent", timeout=15)
        return f"Code scanning analysis #{analysis_id} deleted"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="upload_sarif",
    description="Upload a SARIF file from code scanning analysis.",
    parameters={
        "sarif_file": {
            "type": "string",
            "description": "Path to SARIF JSON file.",
        },
        "commit_sha": {
            "type": "string",
            "description": "SHA of the commit being analyzed.",
        },
        "ref": {
            "type": "string",
            "description": "Git ref (e.g. refs/heads/main).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["sarif_file", "commit_sha", "ref"],
)
def upload_sarif(sarif_file: str, commit_sha: str, ref: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j, base64
    with open(sarif_file) as f:
        sarif_content = f.read()
    encoded = base64.b64encode(sarif_content.encode()).decode()
    payload = j.dumps({"commit_sha": commit_sha, "ref": ref, "sarif": encoded})
    try:
        _gh("api", f"repos/{repo}/code-scanning/sarifs", "--method", "POST",
            "--raw-field", payload, "--silent", timeout=30)
        return f"SARIF uploaded for {commit_sha[:7]}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_dependency_diff",
    description="Get a dependency diff between two refs (dependency review).",
    parameters={
        "basehead": {
            "type": "string",
            "description": "Base...head range (e.g. main...feature).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["basehead"],
)
def get_dependency_diff(basehead: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/dependency-graph/compare/{basehead}", timeout=30)
    except RuntimeError as e:
        return f"Error: {e}"
    changes = data.get("change_type", [])
    if isinstance(changes, list):
        return f"Dependency diff for {basehead}: {len(changes)} changes" + "\n" + json.dumps(changes[:20], indent=2)
    return json.dumps(data, indent=2)[:2000]


@tool(
    name="create_tag_protection",
    description="Create a tag protection rule for a repository.",
    parameters={
        "pattern": {
            "type": "string",
            "description": "Tag name pattern (e.g. v*).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["pattern"],
)
def create_tag_protection(pattern: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload = j.dumps({"pattern": pattern})
    try:
        data = _gh_json("api", f"repos/{repo}/tags/protection", "--method", "POST",
                        "--raw-field", payload, timeout=15)
        tid = data.get("id", "?")
        return f"Tag protection created for '{pattern}' (id={tid})"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_tag_protection",
    description="Delete a tag protection rule.",
    parameters={
        "protection_id": {
            "type": "integer",
            "description": "Tag protection ID (get from list_tag_protection).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["protection_id"],
)
def delete_tag_protection(protection_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/tags/protection/{protection_id}", "--method", "DELETE", "--silent", timeout=15)
        return f"Tag protection #{protection_id} deleted"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_ruleset",
    description="Get a specific ruleset by ID.",
    parameters={
        "ruleset_id": {
            "type": "integer",
            "description": "Ruleset ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["ruleset_id"],
)
def get_ruleset(ruleset_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/rulesets/{ruleset_id}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**Ruleset:** {data.get('name', '?')} (id={data.get('id', '?')})\n"
        f"**Target:** {data.get('target', '?')}\n"
        f"**Enforcement:** {data.get('enforcement', '?')}\n"
        f"**Rules:** {len(data.get('rules', []))}\n"
        f"**Bypass actors:** {len(data.get('bypass_actors', []))}"
    )


@tool(
    name="create_ruleset",
    description="Create a repository ruleset (beta).",
    parameters={
        "name": {
            "type": "string",
            "description": "Ruleset name.",
        },
        "enforcement": {
            "type": "string",
            "enum": ["active", "disabled", "evaluate"],
            "description": "Enforcement status.",
        },
        "target": {
            "type": "string",
            "enum": ["branch", "tag"],
            "description": "Ruleset target (default: branch).",
        },
        "rules": {
            "type": "string",
            "description": "JSON array of rule objects (e.g. [{\"type\":\"creation\"}]).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["name", "enforcement"],
)
def create_ruleset(name: str, enforcement: str, target: str = "branch", rules: str = "[]", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload = j.dumps({"name": name, "enforcement": enforcement, "target": target, "rules": j.loads(rules)})
    try:
        data = _gh_json("api", f"repos/{repo}/rulesets", "--method", "POST",
                        "--raw-field", payload, timeout=15)
        rid = data.get("id", "?")
        return f"Ruleset '{name}' created (id={rid})"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_issue_timeline",
    description="Get the full timeline of an issue including cross-references.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "limit": {
            "type": "integer",
            "description": "Max events (default 30).",
        },
    },
    required=["number"],
)
def get_issue_timeline(number: int, repo: str = "", limit: int = 30) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/issues/{number}/timeline?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No timeline events."
    lines = [f"**Timeline for #{number}:**\n"]
    for e in data:
        event = e.get("event", "?")
        actor = e.get("actor", {}).get("login", "?")
        created = e.get("created_at", "?")
        label = e.get("label", {}).get("name", "")
        milestone = e.get("milestone", {}).get("title", "") if isinstance(e.get("milestone"), dict) else ""
        detail = label or milestone or ""
        detail_str = f" ({detail})" if detail else ""
        lines.append(f"- **{actor}** {event}{detail_str} — {created}")
    return "\n".join(lines)


@tool(
    name="get_org_blocked_users",
    description="List users blocked from an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
    },
    required=["org"],
)
def get_org_blocked_users(org: str) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/blocks", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No blocked users."
    lines = []
    for u in data:
        login = u.get("login", "?")
        lines.append(f"- **{login}**")
    return "\n".join(lines)


@tool(
    name="get_org_outside_collaborators",
    description="List outside collaborators for an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
    },
    required=["org"],
)
def get_org_outside_collaborators(org: str) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/outside_collaborators", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No outside collaborators."
    lines = []
    for u in data:
        login = u.get("login", "?")
        repos = u.get("repositories", [])
        lines.append(f"- **{login}** ({len(repos)} repos)")
    return "\n".join(lines)


@tool(
    name="list_org_invitations",
    description="List pending invitations for an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
    },
    required=["org"],
)
def list_org_invitations(org: str) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/invitations", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No pending invitations."
    lines = []
    for i in data:
        login = i.get("login", "?")
        email = i.get("email", "?")
        role = i.get("role", "?")
        created = i.get("created_at", "?")
        lines.append(f"- **{login or email}** ({role}) — {created}")
    return "\n".join(lines)


@tool(
    name="list_user_gpg_keys",
    description="List GPG keys for the authenticated user.",
    parameters={},
    required=[],
)
def list_user_gpg_keys() -> str:
    try:
        data = _gh_json("api", "user/gpg_keys", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No GPG keys."
    lines = []
    for k in data:
        key_id = k.get("key_id", "?")
        primary = k.get("primary_key_id", "?")
        can_sign = k.get("can_sign", False)
        created = k.get("created_at", "?")
        raw = k.get("raw_key", "")[:40]
        lines.append(f"- **{key_id}** (`{raw}...`, sign: {can_sign}) — {created}")
    return "\n".join(lines)


@tool(
    name="list_user_ssh_keys",
    description="List SSH keys for the authenticated user.",
    parameters={},
    required=[],
)
def list_user_ssh_keys() -> str:
    try:
        data = _gh_json("api", "user/keys", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No SSH keys."
    lines = []
    for k in data:
        title = k.get("title", "?")
        key_id = k.get("id", "?")
        created = k.get("created_at", "?")
        key = k.get("key", "")[:40]
        lines.append(f"- **{title}** (#{key_id}, `{key}...`) — {created}")
    return "\n".join(lines)


@tool(
    name="copy_issue_to_repo",
    description="Copy an issue to another repository (creates a new issue with same body/labels, creates a reference).",
    parameters={
        "number": {
            "type": "integer",
            "description": "Issue number in the source repository.",
        },
        "target": {
            "type": "string",
            "description": "Target repository in owner/repo format.",
        },
        "repo": {
            "type": "string",
            "description": "Source repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number", "target"],
)
def copy_issue_to_repo(number: int, target: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    try:
        issue = _gh_json("api", f"repos/{repo}/issues/{number}", timeout=15)
    except RuntimeError as e:
        return f"Error reading source issue: {e}"
    title = issue.get("title", "")
    body = issue.get("body", "") or ""
    labels = [l.get("name", "") for l in issue.get("labels", []) if l.get("name")]
    body += f"\n\n---\n*Copied from {repo}#{number}*"
    payload = j.dumps({"title": title, "body": body})
    try:
        new_issue = _gh_json("api", f"repos/{target}/issues", "--method", "POST",
                            "--raw-field", payload, timeout=15)
        new_num = new_issue.get("number", "?")
        return f"Copied issue #{number} from {repo} to {target}#{new_num}: {title}"
    except RuntimeError as e:
        return f"Error creating issue in {target}: {e}"


@tool(
    name="create_sub_issue",
    description="Create a sub-issue on an issue.",
    parameters={
        "parent": {
            "type": "integer",
            "description": "Parent issue number.",
        },
        "title": {
            "type": "string",
            "description": "Sub-issue title.",
        },
        "body": {
            "type": "string",
            "description": "Sub-issue body.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["parent", "title"],
)
def create_sub_issue(parent: int, title: str, body: str = "", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload = j.dumps({"title": title, "body": body})
    try:
        sub = _gh_json("api", f"repos/{repo}/issues", "--method", "POST",
                       "--raw-field", payload, timeout=15)
    except RuntimeError as e:
        return f"Error creating sub-issue: {e}"
    sub_num = sub.get("number", "?")
    link_payload = j.dumps({"sub_issue_url": f"https://github.com/{repo}/issues/{sub_num}"})
    try:
        _gh("api", f"repos/{repo}/issues/{parent}/sub_issues", "--method", "POST",
            "--raw-field", link_payload, "--silent", timeout=15)
        return f"Sub-issue #{sub_num} created and linked to #{parent}"
    except RuntimeError as e:
        return f"Sub-issue #{sub_num} created (but linking failed: {e})"


@tool(
    name="list_sub_issues",
    description="List sub-issues for a parent issue.",
    parameters={
        "number": {
            "type": "integer",
            "description": "Parent issue number.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["number"],
)
def list_sub_issues(number: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/issues/{number}/sub_issues", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No sub-issues."
    lines = []
    for s in data:
        s_num = s.get("number", "?")
        s_title = s.get("title", "?")
        s_state = s.get("state", "?")
        lines.append(f"- **#{s_num}** ({s_state}): {s_title}")
    return "\n".join(lines)


@tool(
    name="get_copilot_billing",
    description="Get Copilot billing and seat information for an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
    },
    required=["org"],
)
def get_copilot_billing(org: str) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/copilot/billing", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**Seat breakdown for {org}:**\n"
        f"**Total seats:** {data.get('seat_breakdown', {}).get('total', 0)}\n"
        f"**Used:** {data.get('seat_breakdown', {}).get('used', 0)}\n"
        f"**Remaining:** {data.get('seat_breakdown', {}).get('remaining', 0)}\n"
        f"**Purchased:** {data.get('seat_breakdown', {}).get('purchased_this_cycle', 0)}\n"
        f"**Pending invite:** {data.get('seat_breakdown', {}).get('pending_invitation', 0)}\n"
        f"**Active:** {data.get('seat_breakdown', {}).get('active_this_cycle', 0)}\n"
        f"**Plan:** {data.get('plan_type', '?')}"
    )


@tool(
    name="list_copilot_seats",
    description="List Copilot seats assigned in an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=["org"],
)
def list_copilot_seats(org: str, limit: int = 20) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/copilot/billing/seats?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    seats = data.get("seats", [])
    if not seats:
        return "No Copilot seats."
    lines = []
    for s in seats:
        assignee = s.get("assignee", {}).get("login", "?")
        created = s.get("created_at", "?")
        team = s.get("assigning_team", {})
        team_str = f" (via {team.get('name', '?')})" if team else ""
        lines.append(f"- **{assignee}**{team_str} — {created}")
    return "\n".join(lines)


@tool(
    name="assign_copilot_seat",
    description="Assign a Copilot seat to a user in an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "username": {
            "type": "string",
            "description": "GitHub username.",
        },
    },
    required=["org", "username"],
)
def assign_copilot_seat(org: str, username: str) -> str:
    import json as j
    payload = j.dumps({"selected_usernames": [username]})
    try:
        result = _gh_json("api", f"orgs/{org}/copilot/billing/selected_users", "--method", "POST",
                          "--raw-field", payload, timeout=15)
        created = result.get("seats_created", 0)
        return f"Copilot seat assigned to {username} (seats created: {created})"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="remove_copilot_seat",
    description="Remove a Copilot seat from a user in an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "username": {
            "type": "string",
            "description": "GitHub username.",
        },
    },
    required=["org", "username"],
)
def remove_copilot_seat(org: str, username: str) -> str:
    import json as j
    payload = j.dumps({"selected_usernames": [username]})
    try:
        result = _gh_json("api", f"orgs/{org}/copilot/billing/selected_users", "--method", "DELETE",
                          "--raw-field", payload, timeout=15)
        deleted = result.get("seats_cancelled", 0)
        return f"Copilot seat removed from {username} (seats cancelled: {deleted})"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_audit_log",
    description="Get the audit log for an organization (requires admin permissions).",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "phrase": {
            "type": "string",
            "description": "Search phrase/query (e.g. 'action:repo.create').",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=["org"],
)
def get_audit_log(org: str, phrase: str = "", limit: int = 10) -> str:
    url = f"orgs/{org}/audit-log?per_page={limit}"
    if phrase:
        url += f"&phrase={phrase}"
    try:
        data = _gh_json("api", url, timeout=30)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No audit log entries."
    lines = [f"**Audit log for {org}:**\n"]
    for entry in data[:limit]:
        action = entry.get("action", "?")
        actor = entry.get("actor", "?")
        created = entry.get("created_at", "?")
        repo = entry.get("repo", "")
        repo_str = f" in {repo}" if repo else ""
        lines.append(f"- **{actor}** → `{action}`{repo_str} — {created}")
    return "\n".join(lines)


@tool(
    name="get_notification_thread",
    description="Get a single notification thread.",
    parameters={
        "thread_id": {
            "type": "string",
            "description": "Notification thread ID.",
        },
    },
    required=["thread_id"],
)
def get_notification_thread(thread_id: str) -> str:
    try:
        data = _gh_json("api", f"notifications/threads/{thread_id}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    subject = data.get("subject", {})
    return (
        f"**{subject.get('title', '?')}**\n"
        f"**Type:** {subject.get('type', '?')} (url: {subject.get('url', '?')})\n"
        f"**Reason:** {data.get('reason', '?')}\n"
        f"**Unread:** {data.get('unread', False)}\n"
        f"**Updated:** {data.get('updated_at', '?')}"
    )


@tool(
    name="mark_thread_done",
    description="Mark a notification thread as done (dismisses it).",
    parameters={
        "thread_id": {
            "type": "string",
            "description": "Notification thread ID.",
        },
    },
    required=["thread_id"],
)
def mark_thread_done(thread_id: str) -> str:
    try:
        _gh("api", f"notifications/threads/{thread_id}", "--method", "DELETE", "--silent", timeout=15)
        return f"Thread {thread_id} marked as done"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_thread_subscription",
    description="Set notification thread subscription (watch/unwatch/ignore).",
    parameters={
        "thread_id": {
            "type": "string",
            "description": "Notification thread ID.",
        },
        "subscribed": {
            "type": "boolean",
            "description": "Whether to subscribe.",
        },
        "ignored": {
            "type": "boolean",
            "description": "Whether to ignore the thread.",
        },
    },
    required=["thread_id", "subscribed"],
)
def set_thread_subscription(thread_id: str, subscribed: bool, ignored: bool = False) -> str:
    import json as j
    payload = j.dumps({"subscribed": subscribed, "ignored": ignored})
    try:
        _gh("api", f"notifications/threads/{thread_id}/subscription", "--method", "PUT",
            "--raw-field", payload, "--silent", timeout=15)
        return f"Thread {thread_id} subscription set (subscribed: {subscribed}, ignored: {ignored})"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_feeds",
    description="Get GitHub feeds available to the authenticated user.",
    parameters={},
    required=[],
)
def get_feeds() -> str:
    try:
        data = _gh_json("api", "feeds", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    lines = []
    for key, value in data.items():
        if key.endswith("_url"):
            label = key.replace("_url", "").replace("_", " ").title()
            lines.append(f"- **{label}:** {value}")
    return "\n".join(lines)


@tool(
    name="create_check_suite",
    description="Create a check suite for a commit SHA.",
    parameters={
        "head_sha": {
            "type": "string",
            "description": "Commit SHA.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["head_sha"],
)
def create_check_suite(head_sha: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload = j.dumps({"head_sha": head_sha})
    try:
        data = _gh_json("api", f"repos/{repo}/check-suites", "--method", "POST",
                        "--raw-field", payload, timeout=15)
        suite_id = data.get("id", "?")
        return f"Check suite #{suite_id} created for {head_sha[:7]}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="rerequest_check_suite",
    description="Re-request a check suite (re-run checks).",
    parameters={
        "suite_id": {
            "type": "integer",
            "description": "Check suite ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["suite_id"],
)
def rerequest_check_suite(suite_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/check-suites/{suite_id}/rerequest", "--method", "POST", "--silent", timeout=15)
        return f"Check suite #{suite_id} re-requested"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_check_runs_for_ref",
    description="List check runs for a commit SHA.",
    parameters={
        "sha": {
            "type": "string",
            "description": "Commit SHA.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["sha"],
)
def list_check_runs_for_ref(sha: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/commits/{sha}/check-runs", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    runs = data.get("check_runs", [])
    if not runs:
        return "No check runs."
    lines = [f"**Check runs for {sha[:7]}:**\n"]
    for cr in runs:
        name = cr.get("name", "?")
        status = cr.get("status", "?")
        conclusion = cr.get("conclusion", "")
        concl = f" — {conclusion}" if conclusion else ""
        lines.append(f"- **{name}**: {status}{concl}")
    return "\n".join(lines)


@tool(
    name="get_repo_security_advisories",
    description="List repository security advisories.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "state": {
            "type": "string",
            "description": "Filter by state: open, closed, published.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=[],
)
def get_repo_security_advisories(repo: str = "", state: str = "", limit: int = 10) -> str:
    repo = repo or _get_repo()
    url = f"repos/{repo}/security-advisories?per_page={limit}"
    if state:
        url += f"&state={state}"
    try:
        data = _gh_json("api", url, timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No security advisories."
    lines = [f"**Security advisories for {repo}:**\n"]
    for a in data:
        ghsa = a.get("ghsa_id", "?")
        cve = a.get("cve_id", "none") or "none"
        summary = a.get("summary", "?")[:80]
        severity = a.get("severity", "?")
        state = a.get("state", "?")
        published = a.get("published_at", "?")
        lines.append(f"- **{ghsa}** (CVE: {cve}) — {summary} — {severity}/{state} — {published}")
    return "\n".join(lines)


@tool(
    name="list_environment_secrets",
    description="List secrets for a deployment environment.",
    parameters={
        "env": {
            "type": "string",
            "description": "Environment name.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["env"],
)
def list_environment_secrets(env: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/environments/{env}/secrets", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    secrets = data.get("secrets", [])
    if not secrets:
        return "No environment secrets."
    lines = []
    for s in secrets:
        lines.append(f"- `{s['name']}` (created: {s.get('created_at', '?')})")
    return "\n".join(lines)


@tool(
    name="get_merge_queue_config",
    description="Get the merge queue configuration for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def get_merge_queue_config(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/merge-queue/configuration", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return json.dumps(data, indent=2)


@tool(
    name="list_org_custom_roles",
    description="List custom repository roles for an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
    },
    required=["org"],
)
def list_org_custom_roles(org: str) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/custom-repo-roles", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    roles = data.get("roles", [])
    if not roles:
        return "No custom roles."
    lines = []
    for r in roles:
        name = r.get("name", "?")
        rid = r.get("id", "?")
        desc = r.get("description", "")
        base = r.get("base_role", "?")
        desc_str = f" — {desc}" if desc else ""
        lines.append(f"- **{name}** (id={rid}, base: {base}){desc_str}")
    return "\n".join(lines)


@tool(
    name="update_review_comment",
    description="Update a pull request review comment.",
    parameters={
        "comment_id": {
            "type": "integer",
            "description": "Review comment ID.",
        },
        "body": {
            "type": "string",
            "description": "New comment body.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["comment_id", "body"],
)
def update_review_comment(comment_id: int, body: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload = j.dumps({"body": body})
    try:
        _gh("api", f"repos/{repo}/pulls/comments/{comment_id}", "--method", "PATCH",
            "--raw-field", payload, "--silent", timeout=15)
        return f"Review comment #{comment_id} updated"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_review_comment",
    description="Delete a pull request review comment.",
    parameters={
        "comment_id": {
            "type": "integer",
            "description": "Review comment ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["comment_id"],
)
def delete_review_comment(comment_id: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/pulls/comments/{comment_id}", "--method", "DELETE", "--silent", timeout=15)
        return f"Review comment #{comment_id} deleted"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_enterprise_billing",
    description="Get GitHub Actions billing for an enterprise.",
    parameters={
        "enterprise": {
            "type": "string",
            "description": "Enterprise slug.",
        },
    },
    required=["enterprise"],
)
def get_enterprise_billing(enterprise: str) -> str:
    try:
        data = _gh_json("api", f"enterprises/{enterprise}/settings/billing/actions", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**Enterprise:** {enterprise}\n"
        f"**Total minutes:** {data.get('total_minutes_used', 0)}\n"
        f"**Included minutes:** {data.get('included_minutes', 0)}\n"
        f"**Paid minutes:** {data.get('total_paid_minutes_used', 0)}\n"
        f"**Breakdown:** {json.dumps(data.get('minutes_used_breakdown', {}), indent=2)}"
    )


@tool(
    name="list_packages",
    description="List packages in a repository or for a user/org.",
    parameters={
        "package_type": {
            "type": "string",
            "enum": ["container", "docker", "maven", "npm", "nuget", "rubygems", "pypi"],
            "description": "Type of package.",
        },
        "org": {
            "type": "string",
            "description": "Organization name (mutually exclusive with repo).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format (mutually exclusive with org).",
        },
        "username": {
            "type": "string",
            "description": "Username for user packages (defaults to auth user).",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=["package_type"],
)
def list_packages(package_type: str = "container", org: str = "", repo: str = "", username: str = "", limit: int = 10) -> str:
    if org:
        url = f"orgs/{org}/packages?package_type={package_type}&per_page={limit}"
    elif repo:
        url = f"repos/{repo}/packages?package_type={package_type}&per_page={limit}"
    elif username:
        url = f"users/{username}/packages?package_type={package_type}&per_page={limit}"
    else:
        url = f"user/packages?package_type={package_type}&per_page={limit}"
    try:
        data = _gh_json("api", url, timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No packages found."
    lines = []
    for p in data:
        name = p.get("name", "?")
        pkg_type = p.get("package_type", "?")
        visibility = p.get("visibility", "?")
        updated = p.get("updated_at", "?")
        lines.append(f"- **{name}** ({pkg_type}, {visibility}) — {updated}")
    return "\n".join(lines)


@tool(
    name="delete_package",
    description="Delete a package (version).",
    parameters={
        "package_type": {
            "type": "string",
            "description": "Package type (container, npm, pypi, etc.).",
        },
        "package_name": {
            "type": "string",
            "description": "Package name.",
        },
        "org": {
            "type": "string",
            "description": "Organization (if org-scoped).",
        },
        "repo": {
            "type": "string",
            "description": "Repository (if repo-scoped).",
        },
    },
    required=["package_type", "package_name"],
)
def delete_package(package_type: str, package_name: str, org: str = "", repo: str = "") -> str:
    if org:
        url = f"orgs/{org}/packages/{package_type}/{package_name}"
    elif repo:
        url = f"repos/{repo}/packages/{package_type}/{package_name}"
    else:
        url = f"user/packages/{package_type}/{package_name}"
    try:
        _gh("api", url, "--method", "DELETE", "--silent", timeout=15)
        return f"Package '{package_name}' deleted"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_package_versions",
    description="List versions for a package.",
    parameters={
        "package_type": {
            "type": "string",
            "description": "Package type.",
        },
        "package_name": {
            "type": "string",
            "description": "Package name.",
        },
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "repo": {
            "type": "string",
            "description": "Repository name.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=["package_type", "package_name"],
)
def list_package_versions(package_type: str, package_name: str, org: str = "", repo: str = "", limit: int = 10) -> str:
    if org:
        url = f"orgs/{org}/packages/{package_type}/{package_name}/versions?per_page={limit}"
    elif repo:
        url = f"repos/{repo}/packages/{package_type}/{package_name}/versions?per_page={limit}"
    else:
        url = f"user/packages/{package_type}/{package_name}/versions?per_page={limit}"
    try:
        data = _gh_json("api", url, timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No versions found."
    lines = []
    for v in data:
        vid = v.get("id", "?")
        name = v.get("name", "?")
        created = v.get("created_at", "?")
        tags = v.get("metadata", {}).get("package_type", "")
        lines.append(f"- `{name}` (id={vid}) — {created}")
    return "\n".join(lines)


@tool(
    name="list_user_emails",
    description="List email addresses for the authenticated user.",
    parameters={},
    required=[],
)
def list_user_emails() -> str:
    try:
        data = _gh_json("api", "user/emails", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No emails found."
    lines = []
    for e in data:
        email = e.get("email", "?")
        primary = "✅" if e.get("primary") else "  "
        verified = "✓" if e.get("verified") else "✗"
        visibility = e.get("visibility", "?")
        lines.append(f"- {primary} **{email}** ({verified}, {visibility})")
    return "\n".join(lines)


@tool(
    name="add_user_email",
    description="Add an email address to the authenticated user's account.",
    parameters={
        "email": {
            "type": "string",
            "description": "Email address to add.",
        },
    },
    required=["email"],
)
def add_user_email(email: str) -> str:
    import json as j
    payload = j.dumps({"emails": [email]})
    try:
        _gh("api", "user/emails", "--method", "POST", "--raw-field", payload, "--silent", timeout=15)
        return f"Email '{email}' added"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_user_email",
    description="Delete an email address from the authenticated user's account.",
    parameters={
        "email": {
            "type": "string",
            "description": "Email address to remove.",
        },
    },
    required=["email"],
)
def delete_user_email(email: str) -> str:
    import json as j
    payload = j.dumps({"emails": [email]})
    try:
        _gh("api", "user/emails", "--method", "DELETE", "--raw-field", payload, "--silent", timeout=15)
        return f"Email '{email}' removed"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_workflow",
    description="Get a single workflow by filename or ID.",
    parameters={
        "workflow": {
            "type": "string",
            "description": "Workflow filename (e.g. ci.yml) or ID.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["workflow"],
)
def get_workflow(workflow: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/actions/workflows/{workflow}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**Workflow:** {data.get('name', '?')} (id={data.get('id', '?')})\n"
        f"**State:** {data.get('state', '?')}\n"
        f"**Path:** {data.get('path', '?')}\n"
        f"**Badge URL:** {data.get('badge_url', '?')}\n"
        f"**Created:** {data.get('created_at', '?')}\n"
        f"**Updated:** {data.get('updated_at', '?')}"
    )


@tool(
    name="list_workflow_runs_for_workflow",
    description="List workflow runs for a specific workflow.",
    parameters={
        "workflow": {
            "type": "string",
            "description": "Workflow filename or ID.",
        },
        "branch": {
            "type": "string",
            "description": "Filter by branch.",
        },
        "status": {
            "type": "string",
            "description": "Filter by status (completed, in_progress, queued, etc.).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=["workflow"],
)
def list_workflow_runs_for_workflow(workflow: str, branch: str = "", status: str = "", repo: str = "", limit: int = 10) -> str:
    repo = repo or _get_repo()
    url = f"repos/{repo}/actions/workflows/{workflow}/runs?per_page={limit}"
    if branch:
        url += f"&branch={branch}"
    if status:
        url += f"&status={status}"
    try:
        data = _gh_json("api", url, timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    runs = data.get("workflow_runs", [])
    if not runs:
        return "No runs."
    lines = [f"**Runs for workflow #{workflow}:**\n"]
    for r in runs:
        num = r.get("run_number", "?")
        status = r.get("status", "?")
        conclusion = r.get("conclusion", "")
        branch = r.get("head_branch", "?")
        created = r.get("created_at", "?")
        concl = f" → {conclusion}" if conclusion else ""
        lines.append(f"- **#{num}** ({status}{concl}, {branch}) — {created}")
    return "\n".join(lines)


@tool(
    name="get_punch_card",
    description="Get the punch card (commit count by hour/day) for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def get_punch_card(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/stats/punch_card", timeout=30)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No data."
    days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    lines = [f"**Commit punch card for {repo}:**\n"]
    for entry in data:
        day, hour, count = entry[0], entry[1], entry[2]
        if count > 0:
            hour_str = f"{hour:02d}:00"
            bars = "█" * min(count, 40)
            lines.append(f"  {days[day]:10s} {hour_str}: {bars} {count}")
    return "\n".join(lines)


@tool(
    name="get_participation_stats",
    description="Get participation stats (commits by author, per week) for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def get_participation_stats(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/stats/participation", timeout=30)
    except RuntimeError as e:
        return f"Error: {e}"
    all_data = data.get("all", [])
    owner = data.get("owner", [])
    total_all = sum(all_data) if all_data else 0
    total_owner = sum(owner) if owner else 0
    return (
        f"**Participation stats for {repo}:**\n"
        f"**Total commits (52 weeks):** {total_all}\n"
        f"**Owner commits:** {total_owner}\n"
        f"**Contributor commits:** {total_all - total_owner}\n"
        f"**Latest 10 weeks (all):** {all_data[-10:] if all_data else 'N/A'}\n"
        f"**Latest 10 weeks (owner):** {owner[-10:] if owner else 'N/A'}"
    )


@tool(
    name="get_contributor_stats",
    description="Get contributor statistics (additions/deletions per contributor).",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
        "limit": {
            "type": "integer",
            "description": "Max contributors (default 20).",
        },
    },
    required=[],
)
def get_contributor_stats(repo: str = "", limit: int = 20) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/stats/contributors", timeout=30)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No data."
    lines = [f"**Contributors for {repo}:**\n"]
    for c in data[:limit]:
        author = c.get("author", {}).get("login", "?")
        total = c.get("total", 0)
        weeks = c.get("weeks", [])
        additions = sum(w.get("a", 0) for w in weeks)
        deletions = sum(w.get("d", 0) for w in weeks)
        lines.append(f"- **{author}**: {total} commits (+{additions}/-{deletions})")
    return "\n".join(lines)


@tool(
    name="list_org_public_members",
    description="List public members of an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
    },
    required=["org"],
)
def list_org_public_members(org: str) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/public_members", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No public members."
    lines = []
    for m in data:
        lines.append(f"- **{m.get('login', '?')}**")
    return "\n".join(lines)


@tool(
    name="check_org_public_membership",
    description="Check if a user is a public member of an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "username": {
            "type": "string",
            "description": "GitHub username.",
        },
    },
    required=["org", "username"],
)
def check_org_public_membership(org: str, username: str) -> str:
    try:
        _gh("api", f"orgs/{org}/public_members/{username}", "--method", "GET", "--silent", timeout=15)
        return f"✅ **{username}** is a public member of **{org}**"
    except RuntimeError as e:
        return f"❌ **{username}** is not a public member of **{org}**"


@tool(
    name="get_repo_code_of_conduct",
    description="Get the code of conduct for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def get_repo_code_of_conduct(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/community/code_of_conduct", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**Code of Conduct:** {data.get('name', '?')}\n"
        f"**URL:** {data.get('html_url', '?')}\n"
        f"**Key:** {data.get('key', '?')}"
    )


@tool(
    name="create_repository_dispatch",
    description="Create a repository dispatch event (for webhook-triggered CI).",
    parameters={
        "event_type": {
            "type": "string",
            "description": "Custom event type name.",
        },
        "client_payload": {
            "type": "string",
            "description": "JSON payload to deliver (default: {}).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["event_type"],
)
def create_repository_dispatch(event_type: str, client_payload: str = "{}", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload = j.dumps({"event_type": event_type, "client_payload": j.loads(client_payload)})
    try:
        _gh("api", f"repos/{repo}/dispatches", "--method", "POST",
            "--raw-field", payload, "--silent", timeout=15)
        return f"Dispatch event '{event_type}' sent to {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_org_security_managers",
    description="List teams with security manager role in an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
    },
    required=["org"],
)
def get_org_security_managers(org: str) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/security-managers", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No security manager teams."
    lines = []
    for t in data:
        name = t.get("slug", "?")
        lines.append(f"- **{name}**")
    return "\n".join(lines)


@tool(
    name="create_blob",
    description="Create a git blob and return its SHA.",
    parameters={
        "content": {
            "type": "string",
            "description": "File content (will be base64-encoded).",
        },
        "encoding": {
            "type": "string",
            "description": "Content encoding (default: utf-8).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["content"],
)
def create_blob(content: str, encoding: str = "utf-8", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j, base64
    encoded = base64.b64encode(content.encode()).decode()
    payload = j.dumps({"content": encoded, "encoding": encoding})
    try:
        data = _gh_json("api", f"repos/{repo}/git/blobs", "--method", "POST",
                        "--raw-field", payload, timeout=15)
        sha = data.get("sha", "?")
        return f"Blob created: {sha[:7]}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_tree",
    description="Create a git tree object from a list of paths/SHAs.",
    parameters={
        "tree_spec": {
            "type": "string",
            "description": "JSON array of tree entries: [{\"path\":\"file.txt\",\"mode\":\"100644\",\"type\":\"blob\",\"sha\":\"...\"}]",
        },
        "base_tree": {
            "type": "string",
            "description": "SHA of base tree (optional).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["tree_spec"],
)
def create_tree(tree_spec: str, base_tree: str = "", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload: dict = {"tree": j.loads(tree_spec)}
    if base_tree:
        payload["base_tree"] = base_tree
    try:
        data = _gh_json("api", f"repos/{repo}/git/trees", "--method", "POST",
                        "--raw-field", j.dumps(payload), timeout=15)
        sha = data.get("sha", "?")
        return f"Tree created: {sha[:7]}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_matching_refs",
    description="List matching git refs (e.g., all branches matching a pattern).",
    parameters={
        "ref": {
            "type": "string",
            "description": "Ref prefix to match (e.g. heads/feature, tags/v).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["ref"],
)
def list_matching_refs(ref: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/git/matching-refs/{ref}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No refs found."
    lines = []
    for r in data:
        r_ref = r.get("ref", "?")
        sha = r.get("object", {}).get("sha", "?")[:7]
        lines.append(f"- `{r_ref}` → {sha}")
    return "\n".join(lines)


@tool(
    name="rename_branch",
    description="Rename a branch in a repository.",
    parameters={
        "branch": {
            "type": "string",
            "description": "Current branch name.",
        },
        "new_name": {
            "type": "string",
            "description": "New branch name.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["branch", "new_name"],
)
def rename_branch(branch: str, new_name: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload = j.dumps({"new_name": new_name})
    try:
        _gh("api", f"repos/{repo}/branches/{branch}/rename", "--method", "POST",
            "--raw-field", payload, "--silent", timeout=15)
        return f"Branch '{branch}' renamed to '{new_name}'"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_pull_review_requests",
    description="List requested reviewers on a pull request.",
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
def list_pull_review_requests(number: int, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/pulls/{number}/requested_reviewers", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    users = data.get("users", [])
    teams = data.get("teams", [])
    lines = [f"**Review requests for PR #{number}:**\n"]
    for u in users:
        lines.append(f"- 👤 **{u.get('login', '?')}**")
    for t in teams:
        lines.append(f"- 🏢 **{t.get('slug', '?')}** (team)")
    if not users and not teams:
        return "No reviewers requested."
    return "\n".join(lines)


@tool(
    name="get_vulnerability_alerts",
    description="Check if vulnerability alerts are enabled for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def get_vulnerability_alerts(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/vulnerability-alerts", "--method", "GET", "--silent", timeout=15)
        return f"✅ Vulnerability alerts are **enabled** for {repo}"
    except RuntimeError as e:
        return f"❌ Vulnerability alerts are **disabled** for {repo} (or insufficient permissions)"


@tool(
    name="get_enterprise_audit_log",
    description="Get the audit log for an enterprise (requires enterprise admin).",
    parameters={
        "enterprise": {
            "type": "string",
            "description": "Enterprise slug.",
        },
        "phrase": {
            "type": "string",
            "description": "Search phrase/query.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=["enterprise"],
)
def get_enterprise_audit_log(enterprise: str, phrase: str = "", limit: int = 10) -> str:
    url = f"enterprises/{enterprise}/audit-log?per_page={limit}"
    if phrase:
        url += f"&phrase={phrase}"
    try:
        data = _gh_json("api", url, timeout=30)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No audit log entries."
    lines = [f"**Enterprise audit log for {enterprise}:**\n"]
    for entry in data[:limit]:
        action = entry.get("action", "?")
        actor = entry.get("actor", "?")
        created = entry.get("created_at", "?")
        lines.append(f"- **{actor}** → `{action}` — {created}")
    return "\n".join(lines)


@tool(
    name="get_enterprise_consumed_licenses",
    description="Get consumed licenses for an enterprise.",
    parameters={
        "enterprise": {
            "type": "string",
            "description": "Enterprise slug.",
        },
    },
    required=["enterprise"],
)
def get_enterprise_consumed_licenses(enterprise: str) -> str:
    try:
        data = _gh_json("api", f"enterprises/{enterprise}/consumed-licenses", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No license data."
    lines = [f"**Consumed licenses for {enterprise}:**\n"]
    for u in data[:30]:
        login = u.get("login", "?")
        lines.append(f"- **{login}**")
    if len(data) > 30:
        lines.append(f"\n... and {len(data) - 30} more.")
    return "\n".join(lines)


@tool(
    name="list_org_code_scanning_alerts",
    description="List code scanning alerts for an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=["org"],
)
def list_org_code_scanning_alerts(org: str, limit: int = 10) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/code-scanning/alerts?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No alerts."
    lines = []
    for a in data[:limit]:
        repo = a.get("repository", {}).get("full_name", "?")
        num = a.get("number", "?")
        state = a.get("state", "?")
        severity = a.get("rule", {}).get("severity", "?")
        desc = a.get("rule", {}).get("description", "?")[:50]
        lines.append(f"- **{repo}** #{num} ({severity}/{state}): {desc}")
    return "\n".join(lines)


@tool(
    name="list_org_secret_scanning_alerts",
    description="List secret scanning alerts for an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=["org"],
)
def list_org_secret_scanning_alerts(org: str, limit: int = 10) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/secret-scanning/alerts?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No alerts."
    lines = []
    for a in data[:limit]:
        repo = a.get("repository", {}).get("full_name", "?")
        num = a.get("number", "?")
        state = a.get("state", "?")
        secret_type = a.get("secret_type_display_name", "?")
        lines.append(f"- **{repo}** #{num} ({secret_type}, {state})")
    return "\n".join(lines)


@tool(
    name="list_org_dependabot_alerts",
    description="List Dependabot alerts for an organization.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 10).",
        },
    },
    required=["org"],
)
def list_org_dependabot_alerts(org: str, limit: int = 10) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/dependabot/alerts?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No alerts."
    lines = []
    for a in data[:limit]:
        repo = a.get("repository", {}).get("full_name", "?")
        num = a.get("number", "?")
        state = a.get("state", "?")
        severity = a.get("security_advisory", {}).get("severity", "?")
        summary = a.get("security_advisory", {}).get("summary", "?")[:50]
        lines.append(f"- **{repo}** #{num} ({severity}/{state}): {summary}")
    return "\n".join(lines)


@tool(
    name="get_git_tag",
    description="Get an annotated git tag object by SHA.",
    parameters={
        "sha": {
            "type": "string",
            "description": "Tag object SHA.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["sha"],
)
def get_git_tag(sha: str, repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/git/tags/{sha}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**Tag:** {data.get('tag', '?')}\n"
        f"**SHA:** {data.get('sha', '?')[:7]}\n"
        f"**Tagger:** {data.get('tagger', {}).get('name', '?')}\n"
        f"**Message:** {data.get('message', '?')}\n"
        f"**Object:** {data.get('object', {}).get('sha', '?')[:7]} ({data.get('object', {}).get('type', '?')})"
    )


@tool(
    name="create_git_tag",
    description="Create an annotated git tag object.",
    parameters={
        "tag": {
            "type": "string",
            "description": "Tag name.",
        },
        "message": {
            "type": "string",
            "description": "Tag message.",
        },
        "object_sha": {
            "type": "string",
            "description": "SHA of the object to tag.",
        },
        "object_type": {
            "type": "string",
            "enum": ["commit", "tree", "blob"],
            "description": "Type of object to tag (default: commit).",
        },
        "tagger_name": {
            "type": "string",
            "description": "Tagger name.",
        },
        "tagger_email": {
            "type": "string",
            "description": "Tagger email.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["tag", "message", "object_sha"],
)
def create_git_tag(tag: str, message: str, object_sha: str, object_type: str = "commit", tagger_name: str = "", tagger_email: str = "", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload: dict = {"tag": tag, "message": message, "object": object_sha, "type": object_type}
    if tagger_name or tagger_email:
        tagger = {}
        if tagger_name:
            tagger["name"] = tagger_name
        if tagger_email:
            tagger["email"] = tagger_email
        payload["tagger"] = tagger
    try:
        data = _gh_json("api", f"repos/{repo}/git/tags", "--method", "POST",
                        "--raw-field", j.dumps(payload), timeout=15)
        sha = data.get("sha", "?")
        return f"Git tag '{tag}' created: {sha[:7]}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="check_starred",
    description="Check if the authenticated user has starred a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def check_starred(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"user/starred/{repo}", "--method", "GET", "--silent", timeout=15)
        return f"✅ You have starred **{repo}**"
    except RuntimeError as e:
        return f"❌ You have not starred **{repo}**"


@tool(
    name="check_watching",
    description="Check if the authenticated user is watching (subscribed to) a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def check_watching(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/subscription", "--method", "GET", "--silent", timeout=15)
        return f"✅ You are watching **{repo}**"
    except RuntimeError as e:
        return f"❌ You are not watching **{repo}**"


@tool(
    name="get_root",
    description="Get GitHub API root endpoint info.",
    parameters={},
    required=[],
)
def get_root() -> str:
    try:
        data = _gh_json("api", "", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return (
        f"**API Root:** {data.get('current_user_url', '?')}\n"
        f"**Repos URL:** {data.get('repository_url', '?')}\n"
        f"**Feeds URL:** {data.get('feeds_url', '?')}\n"
        f"**Emojis:** {data.get('emojis_url', '?')}\n"
        f"**Rate limit:** {data.get('rate_limit_url', '?')}\n"
        f"**Verifiable password:** {data.get('verifiable_password_authentication', False)}"
    )


@tool(
    name="get_rate_limit_details",
    description="Get detailed rate limit status for the authenticated user.",
    parameters={},
    required=[],
)
def get_rate_limit_details() -> str:
    try:
        data = _gh_json("api", "rate_limit", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    resources = data.get("resources", {})
    lines = [f"**Rate limit details:**\n"]
    for name, rl in resources.items():
        limit = rl.get("limit", "?")
        remaining = rl.get("remaining", "?")
        reset = rl.get("reset", 0)
        used = rl.get("used", 0)
        import datetime
        reset_str = datetime.datetime.fromtimestamp(reset).strftime("%H:%M:%S") if reset else "?"
        lines.append(f"- **{name}**: {used}/{limit} used, {remaining} remaining (resets {reset_str})")
    return "\n".join(lines)


@tool(
    name="list_team_members",
    description="List members of a team.",
    parameters={
        "org": {
            "type": "string",
            "description": "Organization name.",
        },
        "team_slug": {
            "type": "string",
            "description": "Team slug.",
        },
        "role": {
            "type": "string",
            "enum": ["member", "maintainer", "all"],
            "description": "Filter by role (default: all).",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 20).",
        },
    },
    required=["org", "team_slug"],
)
def list_team_members(org: str, team_slug: str, role: str = "all", limit: int = 20) -> str:
    try:
        data = _gh_json("api", f"orgs/{org}/teams/{team_slug}/members?per_page={limit}&role={role}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No members found."
    lines = [f"**Members of {org}/{team_slug}:**\n"]
    for m in data:
        login = m.get("login", "?")
        lines.append(f"- **{login}**")
    return "\n".join(lines)


@tool(
    name="list_pages_builds",
    description="List GitHub Pages builds for a repository.",
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
def list_pages_builds(repo: str = "", limit: int = 10) -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/pages/builds?per_page={limit}", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    if not data:
        return "No builds."
    lines = [f"**Pages builds for {repo}:**\n"]
    for b in data:
        status = b.get("status", "?")
        commit = b.get("commit", "?")[:7]
        created = b.get("created_at", "?")
        duration = b.get("duration", 0)
        lines.append(f"- **{status}** ({commit}) — {duration}s — {created}")
    return "\n".join(lines)


@tool(
    name="request_pages_build",
    description="Request a GitHub Pages build for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def request_pages_build(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        _gh("api", f"repos/{repo}/pages/builds", "--method", "POST", "--silent", timeout=15)
        return f"Pages build requested for {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_actions_permissions",
    description="Get GitHub Actions permissions for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def get_actions_permissions(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/actions/permissions", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return json.dumps(data, indent=2)


@tool(
    name="set_actions_permissions",
    description="Set GitHub Actions permissions for a repository.",
    parameters={
        "enabled": {
            "type": "boolean",
            "description": "Whether Actions is enabled.",
        },
        "allowed_actions": {
            "type": "string",
            "enum": ["all", "local_only", "selected"],
            "description": "Allow actions policy.",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["enabled"],
)
def set_actions_permissions(enabled: bool, allowed_actions: str = "all", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload = j.dumps({"enabled": enabled, "allowed_actions": allowed_actions})
    try:
        _gh("api", f"repos/{repo}/actions/permissions", "--method", "PUT",
            "--raw-field", payload, "--silent", timeout=15)
        return f"Actions permissions set for {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_code_scanning_default_setup",
    description="Get the code scanning default setup configuration for a repository.",
    parameters={
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=[],
)
def get_code_scanning_default_setup(repo: str = "") -> str:
    repo = repo or _get_repo()
    try:
        data = _gh_json("api", f"repos/{repo}/code-scanning/default-setup", timeout=15)
    except RuntimeError as e:
        return f"Error: {e}"
    return json.dumps(data, indent=2)


@tool(
    name="update_code_scanning_default_setup",
    description="Update the code scanning default setup configuration for a repository.",
    parameters={
        "state": {
            "type": "string",
            "enum": ["configured", "not-configured"],
            "description": "New state.",
        },
        "languages": {
            "type": "string",
            "description": "Comma-separated languages to scan (e.g. python,javascript).",
        },
        "query_suite": {
            "type": "string",
            "description": "CodeQL query suite (default, extended).",
        },
        "repo": {
            "type": "string",
            "description": "Repository in owner/repo format. Auto-detected if omitted.",
        },
    },
    required=["state"],
)
def update_code_scanning_default_setup(state: str, languages: str = "", query_suite: str = "default", repo: str = "") -> str:
    repo = repo or _get_repo()
    import json as j
    payload: dict = {"state": state, "query_suite": query_suite}
    if languages:
        payload["languages"] = [l.strip() for l in languages.split(",") if l.strip()]
    try:
        _gh("api", f"repos/{repo}/code-scanning/default-setup", "--method", "PATCH",
            "--raw-field", j.dumps(payload), "--silent", timeout=15)
        return f"Code scanning default setup updated for {repo}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_environment_secret",
    description="Get a single environment-level secret.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "env": {"type": "string", "description": "Environment name"},
        "name": {"type": "string", "description": "Secret name"},
    },
    required=["repo", "env", "name"],
)
def get_environment_secret(repo: str, env: str, name: str) -> str:
    try:
        d = _gh_json("secret", "list", "--env", env, "--repo", repo)
        for s in d.get("secrets", []):
            if s.get("name") == name:
                return json.dumps(s, indent=2)
        return f"Secret '{name}' not found in environment '{env}'."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_environment_secret",
    description="Create or update a secret in an environment.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "env": {"type": "string", "description": "Environment name"},
        "name": {"type": "string", "description": "Secret name"},
        "value": {"type": "string", "description": "Secret value"},
    },
    required=["repo", "env", "name", "value"],
)
def create_environment_secret(repo: str, env: str, name: str, value: str) -> str:
    try:
        _gh("secret", "set", name, "--env", env, "--repo", repo, "--body", value, timeout=15)
        return f"Secret '{name}' set in environment '{env}'."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_environment_secret",
    description="Delete a secret from an environment.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "env": {"type": "string", "description": "Environment name"},
        "name": {"type": "string", "description": "Secret name"},
    },
    required=["repo", "env", "name"],
)
def delete_environment_secret(repo: str, env: str, name: str) -> str:
    try:
        _gh("secret", "delete", name, "--env", env, "--repo", repo, timeout=15)
        return f"Secret '{name}' deleted from environment '{env}'."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_environment_variable",
    description="Create or update a variable in an environment.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "env": {"type": "string", "description": "Environment name"},
        "name": {"type": "string", "description": "Variable name"},
        "value": {"type": "string", "description": "Variable value"},
    },
    required=["repo", "env", "name", "value"],
)
def create_environment_variable(repo: str, env: str, name: str, value: str) -> str:
    try:
        _gh("variable", "set", name, "--env", env, "--repo", repo, "--body", value, timeout=15)
        return f"Variable '{name}' set in environment '{env}'."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_environment_variable",
    description="Delete a variable from an environment.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "env": {"type": "string", "description": "Environment name"},
        "name": {"type": "string", "description": "Variable name"},
    },
    required=["repo", "env", "name"],
)
def delete_environment_variable(repo: str, env: str, name: str) -> str:
    try:
        _gh("variable", "delete", name, "--env", env, "--repo", repo, timeout=15)
        return f"Variable '{name}' deleted from environment '{env}'."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_workflow_run_jobs",
    description="List jobs for a workflow run.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "run_id": {"type": "string", "description": "Workflow run ID"},
        "filter": {"type": "string", "description": "Filter by status: latest, all (default: latest)"},
    },
    required=["repo", "run_id"],
)
def list_workflow_run_jobs(repo: str, run_id: str, filter: str = "latest") -> str:
    try:
        args = ["run", "view", run_id, "--repo", repo, "--json", "jobs"]
        result = _gh_json(*args)
        jobs = result.get("jobs", [])
        if not jobs:
            return f"No jobs found for run #{run_id}."
        return json.dumps(jobs, indent=2)
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_workflow_run_job",
    description="Get details of a specific job in a workflow run.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "job_id": {"type": "string", "description": "Job ID"},
    },
    required=["repo", "job_id"],
)
def get_workflow_run_job(repo: str, job_id: str) -> str:
    try:
        return _gh("run", "view", "--job", job_id, "--repo", repo, "--json",
                    "steps,started_at,completed_at,conclusion,status,name")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="download_workflow_run_job_logs",
    description="Download logs for a specific workflow run job.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "job_id": {"type": "string", "description": "Job ID"},
    },
    required=["repo", "job_id"],
)
def download_workflow_run_job_logs(repo: str, job_id: str) -> str:
    try:
        result = _gh("run", "view", "--job", job_id, "--repo", repo, "--log")
        return f"Logs for job #{job_id}:\n{result[:2000]}" + ("\n...(truncated)" if len(result) > 2000 else "")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="approve_workflow_run",
    description="Approve a workflow run that requires approval.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "run_id": {"type": "string", "description": "Workflow run ID"},
    },
    required=["repo", "run_id"],
)
def approve_workflow_run(repo: str, run_id: str) -> str:
    try:
        _gh("api", f"repos/{repo}/actions/runs/{run_id}/approve", "--method", "POST",
            "--silent", timeout=15)
        return f"Workflow run #{run_id} approved."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="rerun_workflow_failed_jobs",
    description="Rerun only the failed jobs in a workflow run.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "run_id": {"type": "string", "description": "Workflow run ID"},
    },
    required=["repo", "run_id"],
)
def rerun_workflow_failed_jobs(repo: str, run_id: str) -> str:
    try:
        _gh("run", "rerun", run_id, "--repo", repo, "--failed", timeout=15)
        return f"Rerunning failed jobs for run #{run_id}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_runner_applications",
    description="List runner applications available for download.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def list_runner_applications(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/actions/runners/downloads")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_registration_token",
    description="Create a registration token for adding a new self-hosted runner.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def create_registration_token(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/actions/runners/registration-token", "--method", "POST")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_remove_token",
    description="Create a remove token for removing a self-hosted runner.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def create_remove_token(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/actions/runners/remove-token", "--method", "POST")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_runner",
    description="Get details of a specific self-hosted runner.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "runner_id": {"type": "string", "description": "Runner ID"},
    },
    required=["repo", "runner_id"],
)
def get_runner(repo: str, runner_id: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/actions/runners/{runner_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="remove_runner",
    description="Remove a self-hosted runner from a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "runner_id": {"type": "string", "description": "Runner ID"},
    },
    required=["repo", "runner_id"],
)
def remove_runner(repo: str, runner_id: str) -> str:
    try:
        _gh("api", f"repos/{repo}/actions/runners/{runner_id}", "--method", "DELETE", "--silent", timeout=15)
        return f"Runner #{runner_id} removed from {repo}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_runner_groups",
    description="List self-hosted runner groups for a repository.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
    },
    required=["org"],
)
def list_runner_groups(org: str) -> str:
    try:
        return _gh("api", f"orgs/{org}/actions/runner-groups")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_team",
    description="Create a new team in an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "name": {"type": "string", "description": "Team name"},
        "description": {"type": "string", "description": "Team description"},
        "privacy": {"type": "string", "description": "Privacy level: secret or closed"},
        "parent_team_id": {"type": "string", "description": "Parent team ID (optional)"},
    },
    required=["org", "name"],
)
def create_team(org: str, name: str, description: str = "", privacy: str = "", parent_team_id: str = "") -> str:
    try:
        import json as j
        payload: dict = {"name": name}
        if description:
            payload["description"] = description
        if privacy:
            payload["privacy"] = privacy
        if parent_team_id:
            payload["parent_team_id"] = int(parent_team_id)
        return _gh("api", f"orgs/{org}/teams", "--method", "POST", "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_team",
    description="Update a team's settings in an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "team_slug": {"type": "string", "description": "Team slug"},
        "name": {"type": "string", "description": "New team name"},
        "description": {"type": "string", "description": "New team description"},
        "privacy": {"type": "string", "description": "Privacy level: secret or closed"},
    },
    required=["org", "team_slug"],
)
def update_team(org: str, team_slug: str, name: str = "", description: str = "", privacy: str = "") -> str:
    try:
        import json as j
        payload: dict = {}
        if name:
            payload["name"] = name
        if description:
            payload["description"] = description
        if privacy:
            payload["privacy"] = privacy
        return _gh("api", f"orgs/{org}/teams/{team_slug}", "--method", "PATCH", "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_team",
    description="Delete a team from an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "team_slug": {"type": "string", "description": "Team slug"},
    },
    required=["org", "team_slug"],
)
def delete_team(org: str, team_slug: str) -> str:
    try:
        _gh("api", f"orgs/{org}/teams/{team_slug}", "--method", "DELETE", "--silent", timeout=15)
        return f"Team '{team_slug}' deleted."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="add_team_repo",
    description="Add a repository to a team (granting access).",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "team_slug": {"type": "string", "description": "Team slug"},
        "owner": {"type": "string", "description": "Repo owner"},
        "repo": {"type": "string", "description": "Repo name"},
        "permission": {"type": "string", "description": "Permission level: pull, push, admin, maintain, triage"},
    },
    required=["org", "team_slug", "owner", "repo"],
)
def add_team_repo(org: str, team_slug: str, owner: str, repo: str, permission: str = "") -> str:
    try:
        args = ["api", f"orgs/{org}/teams/{team_slug}/repos/{owner}/{repo}", "--method", "PUT", "--silent"]
        if permission:
            import json as j
            args += ["--raw-field", j.dumps({"permission": permission})]
        _gh(*args, timeout=15)
        return f"Repo {owner}/{repo} added to team '{team_slug}'."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="remove_team_repo",
    description="Remove a repository from a team.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "team_slug": {"type": "string", "description": "Team slug"},
        "owner": {"type": "string", "description": "Repo owner"},
        "repo": {"type": "string", "description": "Repo name"},
    },
    required=["org", "team_slug", "owner", "repo"],
)
def remove_team_repo(org: str, team_slug: str, owner: str, repo: str) -> str:
    try:
        _gh("api", f"orgs/{org}/teams/{team_slug}/repos/{owner}/{repo}", "--method", "DELETE", "--silent", timeout=15)
        return f"Repo {owner}/{repo} removed from team '{team_slug}'."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_team_projects",
    description="List projects associated with a team.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "team_slug": {"type": "string", "description": "Team slug"},
    },
    required=["org", "team_slug"],
)
def list_team_projects(org: str, team_slug: str) -> str:
    try:
        return _gh("api", f"orgs/{org}/teams/{team_slug}/projects")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_gist",
    description="Get a single gist by its ID.",
    parameters={
        "gist_id": {"type": "string", "description": "Gist ID"},
    },
    required=["gist_id"],
)
def get_gist(gist_id: str) -> str:
    try:
        return _gh("gist", "view", gist_id)
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_gist",
    description="Update a gist (replaces all content).",
    parameters={
        "gist_id": {"type": "string", "description": "Gist ID"},
        "description": {"type": "string", "description": "New description"},
        "add_file": {"type": "string", "description": "Path to file to add or update"},
    },
    required=["gist_id"],
)
def update_gist(gist_id: str, description: str = "", add_file: str = "") -> str:
    try:
        args = ["gist", "edit", gist_id]
        if description:
            args += ["--desc", description]
        if add_file:
            args += ["--add", add_file]
        _gh(*args)
        return f"Gist {gist_id} updated."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_gist",
    description="Delete a gist by its ID.",
    parameters={
        "gist_id": {"type": "string", "description": "Gist ID"},
    },
    required=["gist_id"],
)
def delete_gist(gist_id: str) -> str:
    try:
        _gh("gist", "delete", gist_id, timeout=15)
        return f"Gist {gist_id} deleted."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="fork_gist",
    description="Fork a gist.",
    parameters={
        "gist_id": {"type": "string", "description": "Gist ID"},
    },
    required=["gist_id"],
)
def fork_gist(gist_id: str) -> str:
    try:
        return _gh("gist", "fork", gist_id)
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="star_gist",
    description="Star a gist.",
    parameters={
        "gist_id": {"type": "string", "description": "Gist ID"},
    },
    required=["gist_id"],
)
def star_gist(gist_id: str) -> str:
    try:
        _gh("api", f"gists/{gist_id}/star", "--method", "PUT", "--silent", timeout=15)
        return f"Gist {gist_id} starred."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="unstar_gist",
    description="Unstar a gist.",
    parameters={
        "gist_id": {"type": "string", "description": "Gist ID"},
    },
    required=["gist_id"],
)
def unstar_gist(gist_id: str) -> str:
    try:
        _gh("api", f"gists/{gist_id}/star", "--method", "DELETE", "--silent", timeout=15)
        return f"Gist {gist_id} unstarred."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_webhook_deliveries",
    description="List deliveries for a repository webhook.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "hook_id": {"type": "string", "description": "Webhook ID"},
        "limit": {"type": "string", "description": "Max results (default: 10)"},
    },
    required=["repo", "hook_id"],
)
def list_webhook_deliveries(repo: str, hook_id: str, limit: str = "10") -> str:
    try:
        return _gh("api", f"repos/{repo}/hooks/{hook_id}/deliveries?per_page={limit}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_webhook_delivery",
    description="Get a specific webhook delivery by ID.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "hook_id": {"type": "string", "description": "Webhook ID"},
        "delivery_id": {"type": "string", "description": "Delivery ID"},
    },
    required=["repo", "hook_id", "delivery_id"],
)
def get_webhook_delivery(repo: str, hook_id: str, delivery_id: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/hooks/{hook_id}/deliveries/{delivery_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="redeliver_webhook_delivery",
    description="Redeliver a webhook delivery.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "hook_id": {"type": "string", "description": "Webhook ID"},
        "delivery_id": {"type": "string", "description": "Delivery ID"},
    },
    required=["repo", "hook_id", "delivery_id"],
)
def redeliver_webhook_delivery(repo: str, hook_id: str, delivery_id: str) -> str:
    try:
        _gh("api", f"repos/{repo}/hooks/{hook_id}/deliveries/{delivery_id}/attempts",
            "--method", "POST", "--silent", timeout=15)
        return f"Webhook delivery {delivery_id} redelivered."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_project",
    description="Get a project (classic) by its ID.",
    parameters={
        "project_id": {"type": "string", "description": "Project ID"},
    },
    required=["project_id"],
)
def get_project(project_id: str) -> str:
    try:
        return _gh("api", f"projects/{project_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_project",
    description="Update a project (classic).",
    parameters={
        "project_id": {"type": "string", "description": "Project ID"},
        "name": {"type": "string", "description": "New project name"},
        "body": {"type": "string", "description": "New project body/description"},
        "state": {"type": "string", "description": "Project state: open or closed"},
    },
    required=["project_id"],
)
def update_project(project_id: str, name: str = "", body: str = "", state: str = "") -> str:
    try:
        import json as j
        payload: dict = {}
        if name:
            payload["name"] = name
        if body:
            payload["body"] = body
        if state:
            payload["state"] = state
        return _gh("api", f"projects/{project_id}", "--method", "PATCH", "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_project",
    description="Delete a project (classic).",
    parameters={
        "project_id": {"type": "string", "description": "Project ID"},
    },
    required=["project_id"],
)
def delete_project(project_id: str) -> str:
    try:
        _gh("api", f"projects/{project_id}", "--method", "DELETE", "--silent", timeout=15)
        return f"Project {project_id} deleted."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_project_columns",
    description="List columns in a project (classic).",
    parameters={
        "project_id": {"type": "string", "description": "Project ID"},
    },
    required=["project_id"],
)
def list_project_columns(project_id: str) -> str:
    try:
        return _gh("api", f"projects/{project_id}/columns")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_project_card",
    description="Create a card in a project column (classic).",
    parameters={
        "column_id": {"type": "string", "description": "Column ID"},
        "content_id": {"type": "string", "description": "Issue or PR ID (leave empty for note)"},
        "content_type": {"type": "string", "description": "Content type: Issue or PullRequest"},
        "note": {"type": "string", "description": "Note text (if not linked to issue/PR)"},
    },
    required=["column_id"],
)
def create_project_card(column_id: str, content_id: str = "", content_type: str = "", note: str = "") -> str:
    try:
        import json as j
        if note:
            payload: dict = {"note": note}
        else:
            payload = {"content_id": int(content_id), "content_type": content_type}
        return _gh("api", f"projects/columns/{column_id}/cards", "--method", "POST",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="move_project_card",
    description="Move a card within a project column.",
    parameters={
        "card_id": {"type": "string", "description": "Card ID"},
        "position": {"type": "string", "description": "Position: top, bottom, or after:<card-id>"},
        "column_id": {"type": "string", "description": "Target column ID"},
    },
    required=["card_id", "position"],
)
def move_project_card(card_id: str, position: str, column_id: str = "") -> str:
    try:
        import json as j
        payload: dict = {"position": position}
        if column_id:
            payload["column_id"] = int(column_id)
        return _gh("api", f"projects/columns/cards/{card_id}/moves", "--method", "POST",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_check_suite",
    description="Get a single check suite by its ID.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "suite_id": {"type": "string", "description": "Check suite ID"},
    },
    required=["repo", "suite_id"],
)
def get_check_suite(repo: str, suite_id: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/check-suites/{suite_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_check_suite_annotations",
    description="List annotations for a check run.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "run_id": {"type": "string", "description": "Check run ID"},
    },
    required=["repo", "run_id"],
)
def list_check_suite_annotations(repo: str, run_id: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/check-runs/{run_id}/annotations")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_check_run",
    description="Update a check run's output, status, or conclusion.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "run_id": {"type": "string", "description": "Check run ID"},
        "status": {"type": "string", "description": "Status: queued, in_progress, completed"},
        "conclusion": {"type": "string", "description": "Conclusion: success, failure, neutral, cancelled, skipped, timed_out, action_required"},
        "output": {"type": "string", "description": "Output summary JSON (title, summary, text)"},
    },
    required=["repo", "run_id"],
)
def update_check_run(repo: str, run_id: str, status: str = "", conclusion: str = "", output: str = "") -> str:
    try:
        import json as j
        payload: dict = {}
        if status:
            payload["status"] = status
        if conclusion:
            payload["conclusion"] = conclusion
        if output:
            payload["output"] = j.loads(output)
        return _gh("api", f"repos/{repo}/check-runs/{run_id}", "--method", "PATCH",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_package",
    description="Get details of a package in an organization.",
    parameters={
        "package_type": {"type": "string", "description": "Package type: container, docker, npm, maven, rubygems, nuget, pypi"},
        "package_name": {"type": "string", "description": "Package name"},
        "org": {"type": "string", "description": "Organization name"},
    },
    required=["package_type", "package_name", "org"],
)
def get_package(package_type: str, package_name: str, org: str) -> str:
    try:
        return _gh("api", f"orgs/{org}/packages/{package_type}/{package_name}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_package_version",
    description="Get details of a specific package version.",
    parameters={
        "package_type": {"type": "string", "description": "Package type: container, docker, npm, maven, rubygems, nuget, pypi"},
        "package_name": {"type": "string", "description": "Package name"},
        "org": {"type": "string", "description": "Organization name"},
        "version_id": {"type": "string", "description": "Package version ID"},
    },
    required=["package_type", "package_name", "org", "version_id"],
)
def get_package_version(package_type: str, package_name: str, org: str, version_id: str) -> str:
    try:
        return _gh("api", f"orgs/{org}/packages/{package_type}/{package_name}/versions/{version_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_package_version",
    description="Delete a specific version of a package.",
    parameters={
        "package_type": {"type": "string", "description": "Package type: container, docker, npm, maven, rubygems, nuget, pypi"},
        "package_name": {"type": "string", "description": "Package name"},
        "org": {"type": "string", "description": "Organization name"},
        "version_id": {"type": "string", "description": "Package version ID"},
    },
    required=["package_type", "package_name", "org", "version_id"],
)
def delete_package_version(package_type: str, package_name: str, org: str, version_id: str) -> str:
    try:
        _gh("api", f"orgs/{org}/packages/{package_type}/{package_name}/versions/{version_id}",
            "--method", "DELETE", "--silent", timeout=15)
        return f"Package version {version_id} deleted."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="restore_package",
    description="Restore a deleted package.",
    parameters={
        "package_type": {"type": "string", "description": "Package type: container, docker, npm, maven, rubygems, nuget, pypi"},
        "package_name": {"type": "string", "description": "Package name"},
        "org": {"type": "string", "description": "Organization name"},
    },
    required=["package_type", "package_name", "org"],
)
def restore_package(package_type: str, package_name: str, org: str) -> str:
    try:
        _gh("api", f"orgs/{org}/packages/{package_type}/{package_name}/restore",
            "--method", "POST", "--silent", timeout=15)
        return f"Package '{package_name}' restored."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="restore_package_version",
    description="Restore a specific deleted package version.",
    parameters={
        "package_type": {"type": "string", "description": "Package type: container, docker, npm, maven, rubygems, nuget, pypi"},
        "package_name": {"type": "string", "description": "Package name"},
        "org": {"type": "string", "description": "Organization name"},
        "version_id": {"type": "string", "description": "Package version ID"},
    },
    required=["package_type", "package_name", "org", "version_id"],
)
def restore_package_version(package_type: str, package_name: str, org: str, version_id: str) -> str:
    try:
        _gh("api", f"orgs/{org}/packages/{package_type}/{package_name}/versions/{version_id}/restore",
            "--method", "POST", "--silent", timeout=15)
        return f"Package version {version_id} restored."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_codespace",
    description="Create a codespace for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "branch": {"type": "string", "description": "Branch name (optional)"},
        "machine": {"type": "string", "description": "Machine type (optional)"},
        "location": {"type": "string", "description": "Location (optional)"},
    },
    required=["repo"],
)
def create_codespace(repo: str, branch: str = "", machine: str = "", location: str = "") -> str:
    try:
        import json as j
        payload: dict = {"repository": repo}
        if branch:
            payload["git_ref"] = branch
        if machine:
            payload["machine"] = machine
        if location:
            payload["location"] = location
        return _gh("api", "user/codespaces", "--method", "POST", "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_codespace",
    description="Get details of a codespace.",
    parameters={
        "codespace_name": {"type": "string", "description": "Codespace name"},
    },
    required=["codespace_name"],
)
def get_codespace(codespace_name: str) -> str:
    try:
        return _gh("api", f"user/codespaces/{codespace_name}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_codespace",
    description="Delete a codespace.",
    parameters={
        "codespace_name": {"type": "string", "description": "Codespace name"},
    },
    required=["codespace_name"],
)
def delete_codespace(codespace_name: str) -> str:
    try:
        _gh("api", f"user/codespaces/{codespace_name}", "--method", "DELETE", "--silent", timeout=15)
        return f"Codespace {codespace_name} deleted."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="start_codespace",
    description="Start a codespace.",
    parameters={
        "codespace_name": {"type": "string", "description": "Codespace name"},
    },
    required=["codespace_name"],
)
def start_codespace(codespace_name: str) -> str:
    try:
        _gh("api", f"user/codespaces/{codespace_name}/start", "--method", "POST", "--silent", timeout=30)
        return f"Codespace {codespace_name} started."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="stop_codespace",
    description="Stop a running codespace.",
    parameters={
        "codespace_name": {"type": "string", "description": "Codespace name"},
    },
    required=["codespace_name"],
)
def stop_codespace(codespace_name: str) -> str:
    try:
        _gh("api", f"user/codespaces/{codespace_name}/stop", "--method", "POST", "--silent", timeout=30)
        return f"Codespace {codespace_name} stopped."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_branch_protection",
    description="Update branch protection rules.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "branch": {"type": "string", "description": "Branch name"},
        "required_status_checks": {"type": "string", "description": "JSON: list of contexts that must pass"},
        "enforce_admins": {"type": "string", "description": "true/false: include admins"},
        "require_pull_request": {"type": "string", "description": "true/false: require PR reviews"},
        "dismiss_stale_reviews": {"type": "string", "description": "true/false: dismiss stale reviews"},
        "require_code_owner_reviews": {"type": "string", "description": "true/false: require code owner review"},
        "required_approving_review_count": {"type": "string", "description": "Number of required approvals"},
    },
    required=["repo", "branch"],
)
def update_branch_protection(repo: str, branch: str,
                              required_status_checks: str = "", enforce_admins: str = "",
                              require_pull_request: str = "", dismiss_stale_reviews: str = "",
                              require_code_owner_reviews: str = "", required_approving_review_count: str = "") -> str:
    try:
        import json as j
        payload: dict = {}
        if required_status_checks:
            payload["required_status_checks"] = {
                "strict": True,
                "contexts": j.loads(required_status_checks) if isinstance(required_status_checks, str) else required_status_checks
            }
        if enforce_admins:
            payload["enforce_admins"] = enforce_admins.lower() == "true"
        if require_pull_request:
            pr: dict = {}
            if dismiss_stale_reviews:
                pr["dismiss_stale_reviews"] = dismiss_stale_reviews.lower() == "true"
            if require_code_owner_reviews:
                pr["require_code_owner_reviews"] = require_code_owner_reviews.lower() == "true"
            if required_approving_review_count:
                pr["required_approving_review_count"] = int(required_approving_review_count)
            payload["required_pull_request_reviews"] = pr
        return _gh("api", f"repos/{repo}/branches/{branch}/protection", "--method", "PUT",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_branch_protection",
    description="Delete branch protection for a branch.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "branch": {"type": "string", "description": "Branch name"},
    },
    required=["repo", "branch"],
)
def delete_branch_protection(repo: str, branch: str) -> str:
    try:
        _gh("api", f"repos/{repo}/branches/{branch}/protection", "--method", "DELETE", "--silent", timeout=15)
        return f"Branch protection removed from '{branch}'."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_branches_for_head_commit",
    description="List branches that contain a specific commit SHA.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "sha": {"type": "string", "description": "Commit SHA"},
    },
    required=["repo", "sha"],
)
def list_branches_for_head_commit(repo: str, sha: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/commits/{sha}/branches-where-head")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_deployment_status",
    description="Create a deployment status for a deployment.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "deployment_id": {"type": "string", "description": "Deployment ID"},
        "state": {"type": "string", "description": "State: error, failure, inactive, in_progress, queued, pending, success"},
        "log_url": {"type": "string", "description": "Log URL (optional)"},
        "description": {"type": "string", "description": "Description (optional)"},
        "environment": {"type": "string", "description": "Environment name (optional)"},
        "environment_url": {"type": "string", "description": "Environment URL (optional)"},
    },
    required=["repo", "deployment_id", "state"],
)
def create_deployment_status(repo: str, deployment_id: str, state: str,
                              log_url: str = "", description: str = "",
                              environment: str = "", environment_url: str = "") -> str:
    try:
        import json as j
        payload: dict = {"state": state}
        if log_url:
            payload["log_url"] = log_url
        if description:
            payload["description"] = description
        if environment:
            payload["environment"] = environment
        if environment_url:
            payload["environment_url"] = environment_url
        return _gh("api", f"repos/{repo}/deployments/{deployment_id}/statuses", "--method", "POST",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_deployment",
    description="Get a specific deployment by ID.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "deployment_id": {"type": "string", "description": "Deployment ID"},
    },
    required=["repo", "deployment_id"],
)
def get_deployment(repo: str, deployment_id: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/deployments/{deployment_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_deployment_status",
    description="Get a specific deployment status by ID.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "deployment_id": {"type": "string", "description": "Deployment ID"},
        "status_id": {"type": "string", "description": "Deployment status ID"},
    },
    required=["repo", "deployment_id", "status_id"],
)
def get_deployment_status(repo: str, deployment_id: str, status_id: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/deployments/{deployment_id}/statuses/{status_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_oidc_subject_claims_customization",
    description="Get the OIDC subject claim customization for an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
    },
    required=["org"],
)
def get_oidc_subject_claims_customization(org: str) -> str:
    try:
        return _gh("api", f"orgs/{org}/actions/oidc/customization/sub")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_oidc_subject_claims_customization",
    description="Update the OIDC subject claim customization for an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "use_default": {"type": "string", "description": "true/false: use default claims"},
        "include_claim_keys": {"type": "string", "description": "JSON array of claim keys to include"},
    },
    required=["org", "use_default"],
)
def update_oidc_subject_claims_customization(org: str, use_default: str, include_claim_keys: str = "") -> str:
    try:
        import json as j
        payload: dict = {"use_default": use_default.lower() == "true"}
        if include_claim_keys:
            payload["include_claim_keys"] = j.loads(include_claim_keys)
        return _gh("api", f"orgs/{org}/actions/oidc/customization/sub", "--method", "PUT",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="search_commits",
    description="Search for commits with a query.",
    parameters={
        "q": {"type": "string", "description": "Search query (e.g., repo:owner/name commit message)"},
        "limit": {"type": "string", "description": "Max results (default: 10)"},
    },
    required=["q"],
)
def search_commits(q: str, limit: str = "10") -> str:
    try:
        return _gh("api", f"search/commits?q={q.replace(' ', '+')}&per_page={limit}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="search_topics",
    description="Search for topics on GitHub.",
    parameters={
        "q": {"type": "string", "description": "Search query"},
        "limit": {"type": "string", "description": "Max results (default: 10)"},
    },
    required=["q"],
)
def search_topics(q: str, limit: str = "10") -> str:
    try:
        return _gh("api", f"search/topics?q={q.replace(' ', '+')}&per_page={limit}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="search_labels",
    description="Search for labels in a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "q": {"type": "string", "description": "Search query for label name"},
        "limit": {"type": "string", "description": "Max results (default: 10)"},
    },
    required=["repo", "q"],
)
def search_labels(repo: str, q: str, limit: str = "10") -> str:
    try:
        return _gh("api", f"search/labels?repository_id={repo.replace('/', '%2F')}&q={q.replace(' ', '+')}&per_page={limit}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_org_webhook",
    description="Update an organization webhook.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "hook_id": {"type": "string", "description": "Webhook ID"},
        "config_url": {"type": "string", "description": "New payload URL"},
        "config_secret": {"type": "string", "description": "New secret"},
        "events": {"type": "string", "description": "Comma-separated events"},
        "active": {"type": "string", "description": "true/false: webhook active"},
    },
    required=["org", "hook_id"],
)
def update_org_webhook(org: str, hook_id: str, config_url: str = "", config_secret: str = "",
                        events: str = "", active: str = "") -> str:
    try:
        import json as j
        payload: dict = {}
        config: dict = {}
        if config_url:
            config["url"] = config_url
        if config_secret:
            config["secret"] = config_secret
        if config:
            payload["config"] = config
        if events:
            payload["events"] = [e.strip() for e in events.split(",") if e.strip()]
        if active:
            payload["active"] = active.lower() == "true"
        return _gh("api", f"orgs/{org}/hooks/{hook_id}", "--method", "PATCH",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="replace_all_repo_topics",
    description="Replace all topics on a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "topics": {"type": "string", "description": "Comma-separated list of topic names"},
    },
    required=["repo", "topics"],
)
def replace_all_repo_topics(repo: str, topics: str) -> str:
    try:
        import json as j
        topic_list = [t.strip() for t in topics.split(",") if t.strip()]
        return _gh("api", f"repos/{repo}/topics", "--method", "PUT",
                    "--raw-field", j.dumps({"names": topic_list}))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_commit_comment",
    description="Get a specific commit comment by ID.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "comment_id": {"type": "string", "description": "Comment ID"},
    },
    required=["repo", "comment_id"],
)
def get_commit_comment(repo: str, comment_id: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/comments/{comment_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_commit_comment",
    description="Update a commit comment.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "comment_id": {"type": "string", "description": "Comment ID"},
        "body": {"type": "string", "description": "Updated comment body"},
    },
    required=["repo", "comment_id", "body"],
)
def update_commit_comment(repo: str, comment_id: str, body: str) -> str:
    try:
        import json as j
        return _gh("api", f"repos/{repo}/comments/{comment_id}", "--method", "PATCH",
                    "--raw-field", j.dumps({"body": body}))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_commit_comment",
    description="Delete a commit comment.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "comment_id": {"type": "string", "description": "Comment ID"},
    },
    required=["repo", "comment_id"],
)
def delete_commit_comment(repo: str, comment_id: str) -> str:
    try:
        _gh("api", f"repos/{repo}/comments/{comment_id}", "--method", "DELETE", "--silent", timeout=15)
        return f"Commit comment {comment_id} deleted."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_label",
    description="Get a specific label by name.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "name": {"type": "string", "description": "Label name"},
    },
    required=["repo", "name"],
)
def get_label(repo: str, name: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/labels/{name.replace(' ', '%20').replace('/', '%2F')}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_issue_labels_for_milestone",
    description="List labels for every issue in a milestone.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "milestone_number": {"type": "string", "description": "Milestone number"},
    },
    required=["repo", "milestone_number"],
)
def list_issue_labels_for_milestone(repo: str, milestone_number: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/milestones/{milestone_number}/labels")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_org_hook",
    description="Get a single organization webhook by ID.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "hook_id": {"type": "string", "description": "Webhook ID"},
    },
    required=["org", "hook_id"],
)
def get_org_hook(org: str, hook_id: str) -> str:
    try:
        return _gh("api", f"orgs/{org}/hooks/{hook_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="ping_org_webhook",
    description="Ping an organization webhook to trigger a test delivery.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "hook_id": {"type": "string", "description": "Webhook ID"},
    },
    required=["org", "hook_id"],
)
def ping_org_webhook(org: str, hook_id: str) -> str:
    try:
        _gh("api", f"orgs/{org}/hooks/{hook_id}/pings", "--method", "POST", "--silent", timeout=15)
        return f"Org webhook {hook_id} pinged."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_org_membership",
    description="Set organization membership for a user.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "username": {"type": "string", "description": "GitHub username"},
        "role": {"type": "string", "description": "Role: member (default) or admin"},
    },
    required=["org", "username"],
)
def set_org_membership(org: str, username: str, role: str = "member") -> str:
    try:
        import json as j
        return _gh("api", f"orgs/{org}/memberships/{username}", "--method", "PUT",
                    "--raw-field", j.dumps({"role": role}))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="remove_org_membership",
    description="Remove a user from an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "username": {"type": "string", "description": "GitHub username"},
    },
    required=["org", "username"],
)
def remove_org_membership(org: str, username: str) -> str:
    try:
        _gh("api", f"orgs/{org}/memberships/{username}", "--method", "DELETE", "--silent", timeout=15)
        return f"User '{username}' removed from {org}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="block_org_user",
    description="Block a user from an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "username": {"type": "string", "description": "GitHub username"},
    },
    required=["org", "username"],
)
def block_org_user(org: str, username: str) -> str:
    try:
        _gh("api", f"orgs/{org}/blocks/{username}", "--method", "PUT", "--silent", timeout=15)
        return f"User '{username}' blocked from {org}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="unblock_org_user",
    description="Unblock a user from an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "username": {"type": "string", "description": "GitHub username"},
    },
    required=["org", "username"],
)
def unblock_org_user(org: str, username: str) -> str:
    try:
        _gh("api", f"orgs/{org}/blocks/{username}", "--method", "DELETE", "--silent", timeout=15)
        return f"User '{username}' unblocked from {org}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_repo_topics",
    description="Set repository topics (replaces existing).",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "topics": {"type": "string", "description": "Comma-separated topic names"},
    },
    required=["repo", "topics"],
)
def set_repo_topics(repo: str, topics: str) -> str:
    try:
        import json as j
        topic_list = [t.strip() for t in topics.split(",") if t.strip()]
        return _gh("api", f"repos/{repo}/topics", "--method", "PUT",
                    "--raw-field", j.dumps({"names": topic_list}))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_repo_environment",
    description="Get a repository environment (single).",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "env": {"type": "string", "description": "Environment name"},
    },
    required=["repo", "env"],
)
def get_repo_environment(repo: str, env: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/environments/{env}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_or_update_repo_environment",
    description="Create or update a repository environment.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "env": {"type": "string", "description": "Environment name"},
        "wait_timer": {"type": "string", "description": "Wait timer in minutes (optional)"},
        "reviewers": {"type": "string", "description": "JSON array of reviewer objects (optional)"},
        "deployment_branch_policy": {"type": "string", "description": "JSON deployment branch policy (optional)"},
    },
    required=["repo", "env"],
)
def create_or_update_repo_environment(repo: str, env: str, wait_timer: str = "",
                                       reviewers: str = "", deployment_branch_policy: str = "") -> str:
    try:
        import json as j
        payload: dict = {}
        if wait_timer:
            payload["wait_timer"] = int(wait_timer)
        if reviewers:
            payload["reviewers"] = j.loads(reviewers)
        if deployment_branch_policy:
            payload["deployment_branch_policy"] = j.loads(deployment_branch_policy)
        return _gh("api", f"repos/{repo}/environments/{env}", "--method", "PUT",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_repo_license_content",
    description="Get the license contents for a repository (includes the full license text).",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_repo_license_content(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/license")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_repo_all_topics",
    description="Get all topics for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_repo_all_topics(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/topics")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="replace_repo_topics",
    description="Replace all topics for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "topics": {"type": "string", "description": "Comma-separated list of topics"},
    },
    required=["repo", "topics"],
)
def replace_repo_topics(repo: str, topics: str) -> str:
    try:
        topic_list = [t.strip() for t in topics.split(",") if t.strip()]
        return _gh("api", f"repos/{repo}/topics", "--method", "PUT",
                    "--raw-field", json.dumps({"names": topic_list}))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_repo_gitignore",
    description="Get the gitignore template for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_repo_gitignore(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/gitignore")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_repo_gitignore",
    description="Set the gitignore template for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "gitignore_template": {"type": "string", "description": "Gitignore template name (e.g., Python)"},
        "message": {"type": "string", "description": "Commit message"},
        "branch": {"type": "string", "description": "Branch (default: default branch)"},
    },
    required=["repo", "gitignore_template", "message"],
)
def set_repo_gitignore(repo: str, gitignore_template: str, message: str, branch: str = "") -> str:
    try:
        import base64
        content = _gh("api", f"gitignore/templates/{gitignore_template}")
        data = json.loads(content)
        source = data.get("source", "")
        b64 = base64.b64encode(source.encode()).decode()
        payload = {"message": message, "content": b64}
        if branch:
            payload["branch"] = branch
        return _gh("api", f"repos/{repo}/contents/.gitignore", "--method", "PUT",
                    "--raw-field", json.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="trigger_deployment",
    description="Trigger a new deployment for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "ref": {"type": "string", "description": "Ref (branch, tag, or SHA) to deploy"},
        "environment": {"type": "string", "description": "Environment name"},
        "task": {"type": "string", "description": "Task to run (default: deploy)"},
        "payload": {"type": "string", "description": "Optional JSON payload"},
        "auto_merge": {"type": "boolean", "description": "Auto-merge the ref if needed"},
    },
    required=["repo", "ref", "environment"],
)
def trigger_deployment(repo: str, ref: str, environment: str, task: str = "deploy",
                        payload: str = "", auto_merge: bool = True) -> str:
    try:
        body: dict = {"ref": ref, "environment": environment, "task": task, "auto_merge": auto_merge}
        if payload:
            body["payload"] = json.loads(payload)
        return _gh("api", f"repos/{repo}/deployments", "--method", "POST",
                    "--raw-field", json.dumps(body))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_dependabot_alert",
    description="Get a single Dependabot alert by number.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "alert_number": {"type": "string", "description": "Alert number"},
    },
    required=["repo", "alert_number"],
)
def get_dependabot_alert(repo: str, alert_number: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/dependabot/alerts/{alert_number}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_code_scanning_alert",
    description="Get a single code scanning alert by number.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "alert_number": {"type": "string", "description": "Alert number"},
    },
    required=["repo", "alert_number"],
)
def get_code_scanning_alert(repo: str, alert_number: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/code-scanning/alerts/{alert_number}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_secret_scanning_alert",
    description="Get a single secret scanning alert by number.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "alert_number": {"type": "string", "description": "Alert number"},
    },
    required=["repo", "alert_number"],
)
def get_secret_scanning_alert(repo: str, alert_number: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/secret-scanning/alerts/{alert_number}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="enable_private_vulnerability_reporting",
    description="Enable private vulnerability reporting for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def enable_private_vulnerability_reporting(repo: str) -> str:
    try:
        _gh("api", f"repos/{repo}/private-vulnerability-reporting", "--method", "PUT",
            "--silent", timeout=15)
        return f"Private vulnerability reporting enabled for {repo}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="disable_private_vulnerability_reporting",
    description="Disable private vulnerability reporting for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def disable_private_vulnerability_reporting(repo: str) -> str:
    try:
        _gh("api", f"repos/{repo}/private-vulnerability-reporting", "--method", "DELETE",
            "--silent", timeout=15)
        return f"Private vulnerability reporting disabled for {repo}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_workflow_dispatch_inputs",
    description="Get the input schema for a workflow that supports workflow_dispatch.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "workflow_id": {"type": "string", "description": "Workflow ID or filename"},
    },
    required=["repo", "workflow_id"],
)
def get_workflow_dispatch_inputs(repo: str, workflow_id: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/actions/workflows/{workflow_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_repo_ruleset",
    description="Get a single ruleset for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "ruleset_id": {"type": "string", "description": "Ruleset ID"},
    },
    required=["repo", "ruleset_id"],
)
def get_repo_ruleset(repo: str, ruleset_id: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/rulesets/{ruleset_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_ruleset",
    description="Update a repository ruleset.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "ruleset_id": {"type": "string", "description": "Ruleset ID"},
        "name": {"type": "string", "description": "New ruleset name"},
        "enforcement": {"type": "string", "description": "Enforcement level: active, disabled, evaluate"},
        "bypass_mode": {"type": "string", "description": "Bypass mode: always, none"},
        "conditions": {"type": "string", "description": "JSON conditions (optional)"},
        "rules": {"type": "string", "description": "JSON rules array (optional)"},
    },
    required=["repo", "ruleset_id"],
)
def update_ruleset(repo: str, ruleset_id: str, name: str = "", enforcement: str = "",
                    bypass_mode: str = "", conditions: str = "", rules: str = "") -> str:
    try:
        import json as j
        payload: dict = {}
        if name:
            payload["name"] = name
        if enforcement:
            payload["enforcement"] = enforcement
        if conditions:
            payload["conditions"] = j.loads(conditions)
        if rules:
            payload["rules"] = j.loads(rules)
        return _gh("api", f"repos/{repo}/rulesets/{ruleset_id}", "--method", "PUT",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_ruleset",
    description="Delete a repository ruleset.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "ruleset_id": {"type": "string", "description": "Ruleset ID"},
    },
    required=["repo", "ruleset_id"],
)
def delete_ruleset(repo: str, ruleset_id: str) -> str:
    try:
        _gh("api", f"repos/{repo}/rulesets/{ruleset_id}", "--method", "DELETE", "--silent", timeout=15)
        return f"Ruleset {ruleset_id} deleted."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_org_audit_log",
    description="Get the audit log for an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "phrase": {"type": "string", "description": "Search phrase (optional)"},
        "limit": {"type": "string", "description": "Max results (default: 10)"},
    },
    required=["org"],
)
def get_org_audit_log(org: str, phrase: str = "", limit: str = "10") -> str:
    try:
        args = ["api", f"orgs/{org}/audit-log?per_page={limit}"]
        if phrase:
            args[1] += f"&phrase={phrase.replace(' ', '+')}"
        return _gh(*args)
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_issue_comment",
    description="Create a comment on an issue. Alias for comment_on_issue.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "number": {"type": "string", "description": "Issue number"},
        "body": {"type": "string", "description": "Comment body text"},
    },
    required=["repo", "number", "body"],
)
def create_issue_comment(repo: str, number: str, body: str) -> str:
    try:
        _gh("issue", "comment", number, "--repo", repo, "--body", body)
        return f"Commented on issue #{number}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_repo_collaborator_permission",
    description="Get the permission level for a collaborator on a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "username": {"type": "string", "description": "GitHub username"},
    },
    required=["repo", "username"],
)
def get_repo_collaborator_permission(repo: str, username: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/collaborators/{username}/permission")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="check_collaborator",
    description="Check if a user is a collaborator on a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "username": {"type": "string", "description": "GitHub username"},
    },
    required=["repo", "username"],
)
def check_collaborator(repo: str, username: str) -> str:
    try:
        _gh("api", f"repos/{repo}/collaborators/{username}", "--silent", timeout=15)
        return f"Yes, '{username}' is a collaborator on {repo}."
    except RuntimeError as e:
        return f"No, '{username}' is not a collaborator (or insufficient permissions)."


@tool(
    name="set_collaborator_permission",
    description="Set the permission level for a collaborator on a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "username": {"type": "string", "description": "GitHub username"},
        "permission": {"type": "string", "description": "Permission: pull, push, triage, maintain, admin"},
    },
    required=["repo", "username"],
)
def set_collaborator_permission(repo: str, username: str, permission: str = "push") -> str:
    try:
        _gh("api", f"repos/{repo}/collaborators/{username}", "--method", "PUT",
            "--raw-field", json.dumps({"permission": permission}), timeout=15)
        return f"Permission set to '{permission}' for '{username}' on {repo}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_repo_invitation",
    description="Cancel a repository invitation.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "invitation_id": {"type": "string", "description": "Invitation ID"},
    },
    required=["repo", "invitation_id"],
)
def delete_repo_invitation(repo: str, invitation_id: str) -> str:
    try:
        _gh("api", f"repos/{repo}/invitations/{invitation_id}", "--method", "DELETE",
            "--silent", timeout=15)
        return f"Invitation {invitation_id} cancelled."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_team_discussions",
    description="List discussions for a team.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "team_slug": {"type": "string", "description": "Team slug"},
        "limit": {"type": "string", "description": "Max results (default: 10)"},
    },
    required=["org", "team_slug"],
)
def get_team_discussions(org: str, team_slug: str, limit: str = "10") -> str:
    try:
        return _gh("api", f"orgs/{org}/teams/{team_slug}/discussions?per_page={limit}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_team_membership",
    description="Get team membership for a user.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "team_slug": {"type": "string", "description": "Team slug"},
        "username": {"type": "string", "description": "GitHub username"},
    },
    required=["org", "team_slug", "username"],
)
def get_team_membership(org: str, team_slug: str, username: str) -> str:
    try:
        return _gh("api", f"orgs/{org}/teams/{team_slug}/memberships/{username}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_repo_custom_properties",
    description="List custom property values for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def list_repo_custom_properties(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/properties/values")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_repo_custom_properties",
    description="Set custom property values for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "properties": {"type": "string", "description": "JSON object of property_name: value pairs"},
    },
    required=["repo", "properties"],
)
def set_repo_custom_properties(repo: str, properties: str) -> str:
    try:
        import json as j
        props = j.loads(properties)
        payload = [{"property_name": k, "value": v} for k, v in props.items()]
        return _gh("api", f"repos/{repo}/properties/values", "--method", "PATCH",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_org_custom_properties",
    description="Get all custom property definitions for an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
    },
    required=["org"],
)
def get_org_custom_properties(org: str) -> str:
    try:
        return _gh("api", f"orgs/{org}/properties/schema")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_org_custom_property",
    description="Create a new custom property definition in an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "property_name": {"type": "string", "description": "Property name"},
        "value_type": {"type": "string", "description": "Value type: string, single_select, multi_select, true_false, date"},
        "description": {"type": "string", "description": "Property description"},
        "allowed_values": {"type": "string", "description": "Comma-separated allowed values (for select types)"},
        "default_value": {"type": "string", "description": "Default value"},
        "required": {"type": "string", "description": "true/false: whether this property is required"},
    },
    required=["org", "property_name", "value_type"],
)
def create_org_custom_property(org: str, property_name: str, value_type: str,
                                description: str = "", allowed_values: str = "",
                                default_value: str = "", required: str = "") -> str:
    try:
        import json as j
        payload: dict = {"property_name": property_name, "value_type": value_type}
        if description:
            payload["description"] = description
        if allowed_values:
            payload["allowed_values"] = [v.strip() for v in allowed_values.split(",") if v.strip()]
        if default_value:
            payload["default_value"] = default_value
        if required:
            payload["required"] = required.lower() == "true"
        return _gh("api", f"orgs/{org}/properties/schema", "--method", "POST",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_org_custom_property",
    description="Update an existing custom property definition in an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "property_name": {"type": "string", "description": "Property name"},
        "value_type": {"type": "string", "description": "Value type"},
        "description": {"type": "string", "description": "Property description"},
        "allowed_values": {"type": "string", "description": "Comma-separated allowed values"},
        "default_value": {"type": "string", "description": "Default value"},
        "required": {"type": "string", "description": "true/false"},
    },
    required=["org", "property_name"],
)
def update_org_custom_property(org: str, property_name: str, value_type: str = "",
                                description: str = "", allowed_values: str = "",
                                default_value: str = "", required: str = "") -> str:
    try:
        import json as j
        payload: dict = {"property_name": property_name}
        if value_type:
            payload["value_type"] = value_type
        if description:
            payload["description"] = description
        if allowed_values:
            payload["allowed_values"] = [v.strip() for v in allowed_values.split(",") if v.strip()]
        if default_value:
            payload["default_value"] = default_value
        if required:
            payload["required"] = required.lower() == "true"
        return _gh("api", f"orgs/{org}/properties/schema", "--method", "PATCH",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="remove_org_custom_property",
    description="Remove a custom property definition from an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "property_name": {"type": "string", "description": "Property name"},
    },
    required=["org", "property_name"],
)
def remove_org_custom_property(org: str, property_name: str) -> str:
    try:
        _gh("api", f"orgs/{org}/properties/schema/{property_name}",
            "--method", "DELETE", "--silent", timeout=15)
        return f"Custom property '{property_name}' removed from {org}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="org_custom_property_values",
    description="Get custom property values for all repos in an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "limit": {"type": "string", "description": "Max repos (default: 30)"},
    },
    required=["org"],
)
def org_custom_property_values(org: str, limit: str = "30") -> str:
    try:
        return _gh("api", f"orgs/{org}/properties/values?per_page={limit}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_org_custom_role",
    description="Create a custom repository role in an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "name": {"type": "string", "description": "Role name"},
        "description": {"type": "string", "description": "Role description"},
        "base_role": {"type": "string", "description": "Base role: read, triage, write, maintain"},
        "permissions": {"type": "string", "description": "JSON array of permission strings (e.g., [\"pull_requests:write\"])"},
    },
    required=["org", "name", "base_role"],
)
def create_org_custom_role(org: str, name: str, base_role: str, description: str = "", permissions: str = "") -> str:
    try:
        import json as j
        payload: dict = {"name": name, "base_role": base_role}
        if description:
            payload["description"] = description
        if permissions:
            payload["permissions"] = j.loads(permissions)
        return _gh("api", f"orgs/{org}/custom-repository-roles", "--method", "POST",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_org_custom_role",
    description="Update a custom repository role in an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "role_id": {"type": "string", "description": "Role ID"},
        "name": {"type": "string", "description": "New role name"},
        "description": {"type": "string", "description": "New role description"},
        "base_role": {"type": "string", "description": "Base role"},
        "permissions": {"type": "string", "description": "JSON array of permission strings"},
    },
    required=["org", "role_id"],
)
def update_org_custom_role(org: str, role_id: str, name: str = "", description: str = "",
                            base_role: str = "", permissions: str = "") -> str:
    try:
        import json as j
        payload: dict = {}
        if name:
            payload["name"] = name
        if description:
            payload["description"] = description
        if base_role:
            payload["base_role"] = base_role
        if permissions:
            payload["permissions"] = j.loads(permissions)
        return _gh("api", f"orgs/{org}/custom-repository-roles/{role_id}", "--method", "PATCH",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_org_custom_role",
    description="Delete a custom repository role from an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "role_id": {"type": "string", "description": "Role ID"},
    },
    required=["org", "role_id"],
)
def delete_org_custom_role(org: str, role_id: str) -> str:
    try:
        _gh("api", f"orgs/{org}/custom-repository-roles/{role_id}",
            "--method", "DELETE", "--silent", timeout=15)
        return f"Custom role {role_id} deleted from {org}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_org_custom_role",
    description="Get a single custom repository role from an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "role_id": {"type": "string", "description": "Role ID"},
    },
    required=["org", "role_id"],
)
def get_org_custom_role(org: str, role_id: str) -> str:
    try:
        return _gh("api", f"orgs/{org}/custom-repository-roles/{role_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="add_org_security_manager",
    description="Add a team as a security manager for an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "team_slug": {"type": "string", "description": "Team slug"},
    },
    required=["org", "team_slug"],
)
def add_org_security_manager(org: str, team_slug: str) -> str:
    try:
        _gh("api", f"orgs/{org}/security-managers/teams/{team_slug}",
            "--method", "PUT", "--silent", timeout=15)
        return f"Team '{team_slug}' added as security manager in {org}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="remove_org_security_manager",
    description="Remove a team as a security manager from an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "team_slug": {"type": "string", "description": "Team slug"},
    },
    required=["org", "team_slug"],
)
def remove_org_security_manager(org: str, team_slug: str) -> str:
    try:
        _gh("api", f"orgs/{org}/security-managers/teams/{team_slug}",
            "--method", "DELETE", "--silent", timeout=15)
        return f"Team '{team_slug}' removed as security manager from {org}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_org_interaction_limits",
    description="Get interaction limits for an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
    },
    required=["org"],
)
def get_org_interaction_limits(org: str) -> str:
    try:
        return _gh("api", f"orgs/{org}/interaction-limits")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_org_interaction_limits",
    description="Set interaction limits for an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "limit": {"type": "string", "description": "Limit type: existing_users, contributors_only, collaborators_only"},
        "expiry": {"type": "string", "description": "Expiry: one_day, three_days, one_week, one_month, six_months"},
    },
    required=["org", "limit"],
)
def set_org_interaction_limits(org: str, limit: str, expiry: str = "") -> str:
    try:
        import json as j
        payload: dict = {"limit": limit}
        if expiry:
            payload["expiry"] = expiry
        return _gh("api", f"orgs/{org}/interaction-limits", "--method", "PUT",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="remove_org_interaction_limits",
    description="Remove interaction limits for an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
    },
    required=["org"],
)
def remove_org_interaction_limits(org: str) -> str:
    try:
        _gh("api", f"orgs/{org}/interaction-limits", "--method", "DELETE",
            "--silent", timeout=15)
        return f"Interaction limits removed for {org}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_org_secret",
    description="Create or update an organization-level secret.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "name": {"type": "string", "description": "Secret name"},
        "value": {"type": "string", "description": "Secret value"},
        "visibility": {"type": "string", "description": "Visibility: all, private, selected"},
        "selected_repos": {"type": "string", "description": "Comma-separated repo names (for selected visibility)"},
    },
    required=["org", "name", "value", "visibility"],
)
def set_org_secret(org: str, name: str, value: str, visibility: str = "all", selected_repos: str = "") -> str:
    try:
        _gh("secret", "set", name, "--org", org, "--body", value,
            "--visibility", visibility, timeout=15)
        return f"Org secret '{name}' set in {org}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_org_secret",
    description="Delete an organization-level secret.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "name": {"type": "string", "description": "Secret name"},
    },
    required=["org", "name"],
)
def delete_org_secret(org: str, name: str) -> str:
    try:
        _gh("secret", "delete", name, "--org", org, timeout=15)
        return f"Org secret '{name}' deleted from {org}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_org_variable",
    description="Create or update an organization-level variable.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "name": {"type": "string", "description": "Variable name"},
        "value": {"type": "string", "description": "Variable value"},
        "visibility": {"type": "string", "description": "Visibility: all, private, selected"},
    },
    required=["org", "name", "value", "visibility"],
)
def set_org_variable(org: str, name: str, value: str, visibility: str = "all") -> str:
    try:
        _gh("variable", "set", name, "--org", org, "--body", value,
            "--visibility", visibility, timeout=15)
        return f"Org variable '{name}' set in {org}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_org_variable",
    description="Delete an organization-level variable.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "name": {"type": "string", "description": "Variable name"},
    },
    required=["org", "name"],
)
def delete_org_variable(org: str, name: str) -> str:
    try:
        _gh("variable", "delete", name, "--org", org, timeout=15)
        return f"Org variable '{name}' deleted from {org}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_org_variables",
    description="List organization-level variables.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
    },
    required=["org"],
)
def list_org_variables(org: str) -> str:
    try:
        return _gh("api", f"orgs/{org}/actions/variables")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_allowed_actions",
    description="Get the allowed actions for an organization or repository.",
    parameters={
        "org": {"type": "string", "description": "Organization name (optional)"},
        "repo": {"type": "string", "description": "Owner/repo (optional)"},
    },
    required=[],
)
def get_allowed_actions(org: str = "", repo: str = "") -> str:
    try:
        if org:
            return _gh("api", f"orgs/{org}/actions/permissions/selected-actions")
        elif repo:
            return _gh("api", f"repos/{repo}/actions/permissions/selected-actions")
        else:
            return "Specify either org or repo."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_allowed_actions",
    description="Set the allowed actions for an organization or repository.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "github_owned_allowed": {"type": "string", "description": "true/false: allow GitHub-owned actions"},
        "verified_allowed": {"type": "string", "description": "true/false: allow verified creator actions"},
        "patterns_allowed": {"type": "string", "description": "Comma-separated action patterns (e.g., actions/*)"},
    },
    required=["org"],
)
def set_allowed_actions(org: str, github_owned_allowed: str = "",
                         verified_allowed: str = "", patterns_allowed: str = "") -> str:
    try:
        import json as j
        payload: dict = {}
        if github_owned_allowed:
            payload["github_owned_allowed"] = github_owned_allowed.lower() == "true"
        if verified_allowed:
            payload["verified_allowed"] = verified_allowed.lower() == "true"
        if patterns_allowed:
            payload["patterns_allowed"] = [p.strip() for p in patterns_allowed.split(",") if p.strip()]
        return _gh("api", f"orgs/{org}/actions/permissions/selected-actions", "--method", "PUT",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_org_actions_permissions",
    description="Get the Actions permissions for an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
    },
    required=["org"],
)
def get_org_actions_permissions(org: str) -> str:
    try:
        return _gh("api", f"orgs/{org}/actions/permissions")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_org_actions_permissions",
    description="Set the Actions permissions for an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "enabled_repos": {"type": "string", "description": "true/false: enable Actions for all repos"},
        "allowed_actions": {"type": "string", "description": "all, local_only, selected"},
    },
    required=["org"],
)
def set_org_actions_permissions(org: str, enabled_repos: str = "", allowed_actions: str = "") -> str:
    try:
        import json as j
        payload: dict = {}
        if enabled_repos:
            payload["enabled_repositories"] = "all" if enabled_repos.lower() == "true" else "selected"
        if allowed_actions:
            payload["allowed_actions"] = allowed_actions
        return _gh("api", f"orgs/{org}/actions/permissions", "--method", "PUT",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_org_required_workflows",
    description="List all required workflows in an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
    },
    required=["org"],
)
def list_org_required_workflows(org: str) -> str:
    try:
        return _gh("api", f"orgs/{org}/actions/required_workflows")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_artifact_retention",
    description="Get the artifact and log retention policy for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_artifact_retention(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/actions/retention")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_artifact_retention",
    description="Set the artifact and log retention period for a repository (in days).",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "days": {"type": "string", "description": "Retention period in days (1-90)"},
    },
    required=["repo", "days"],
)
def set_artifact_retention(repo: str, days: str) -> str:
    try:
        import json as j
        return _gh("api", f"repos/{repo}/actions/retention", "--method", "PUT",
                    "--raw-field", j.dumps({"retention_days": int(days)}))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_org_artifact_retention",
    description="Get the artifact and log retention policy for an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
    },
    required=["org"],
)
def get_org_artifact_retention(org: str) -> str:
    try:
        return _gh("api", f"orgs/{org}/actions/retention")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_org_artifact_retention",
    description="Set the artifact and log retention period for an organization (in days).",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
        "days": {"type": "string", "description": "Retention period in days (1-90)"},
    },
    required=["org", "days"],
)
def set_org_artifact_retention(org: str, days: str) -> str:
    try:
        import json as j
        return _gh("api", f"orgs/{org}/actions/retention", "--method", "PUT",
                    "--raw-field", j.dumps({"retention_days": int(days)}))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_cache_usage",
    description="Get GitHub Actions cache usage for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_cache_usage(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/actions/cache/usage")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_repo_security_advisory",
    description="Create a repository security advisory.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "summary": {"type": "string", "description": "Advisory summary"},
        "description": {"type": "string", "description": "Advisory description"},
        "severity": {"type": "string", "description": "Severity: critical, high, medium, low"},
        "cve_id": {"type": "string", "description": "CVE ID (optional)"},
        "vulnerabilities": {"type": "string", "description": "JSON array of vulnerability objects (optional)"},
        "credits": {"type": "string", "description": "Comma-separated usernames to credit (optional)"},
    },
    required=["repo", "summary", "description", "severity"],
)
def create_repo_security_advisory(repo: str, summary: str, description: str, severity: str,
                                   cve_id: str = "", vulnerabilities: str = "", credits: str = "") -> str:
    try:
        import json as j
        payload: dict = {
            "summary": summary,
            "description": description,
            "severity": severity,
        }
        if cve_id:
            payload["cve_id"] = cve_id
        if vulnerabilities:
            payload["vulnerabilities"] = j.loads(vulnerabilities)
        if credits:
            payload["credits"] = [{"login": u.strip()} for u in credits.split(",") if u.strip()]
        return _gh("api", f"repos/{repo}/security-advisories", "--method", "POST",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_repo_security_advisory",
    description="Update a repository security advisory.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "ghsa_id": {"type": "string", "description": "GHSA ID of the advisory"},
        "summary": {"type": "string", "description": "New summary"},
        "description": {"type": "string", "description": "New description"},
        "severity": {"type": "string", "description": "New severity"},
    },
    required=["repo", "ghsa_id"],
)
def update_repo_security_advisory(repo: str, ghsa_id: str, summary: str = "",
                                    description: str = "", severity: str = "") -> str:
    try:
        import json as j
        payload: dict = {}
        if summary:
            payload["summary"] = summary
        if description:
            payload["description"] = description
        if severity:
            payload["severity"] = severity
        return _gh("api", f"repos/{repo}/security-advisories/{ghsa_id}", "--method", "PATCH",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_repo_security_advisories",
    description="List all security advisories in a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "state": {"type": "string", "description": "Filter by state: published, closed, draft"},
        "limit": {"type": "string", "description": "Max results (default: 10)"},
    },
    required=["repo"],
)
def list_repo_security_advisories(repo: str, state: str = "", limit: str = "10") -> str:
    try:
        args = f"repos/{repo}/security-advisories?per_page={limit}"
        if state:
            args += f"&state={state}"
        return _gh("api", args)
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_codespace_machines",
    description="List machine types available for a codespace.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "branch": {"type": "string", "description": "Branch (optional)"},
        "location": {"type": "string", "description": "Location (optional)"},
    },
    required=["repo"],
)
def list_codespace_machines(repo: str, branch: str = "", location: str = "") -> str:
    try:
        args = f"repos/{repo}/codespaces/machines"
        params = []
        if branch:
            params.append(f"ref={branch}")
        if location:
            params.append(f"location={location}")
        if params:
            args += "?" + "&".join(params)
        return _gh("api", args)
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_codespace_repo_secret",
    description="Get a codespace secret for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "name": {"type": "string", "description": "Secret name"},
    },
    required=["repo", "name"],
)
def get_codespace_repo_secret(repo: str, name: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/codespaces/secrets/{name}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_codespace_repo_secret",
    description="Create or update a codespace secret for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "name": {"type": "string", "description": "Secret name"},
        "value": {"type": "string", "description": "Secret value"},
    },
    required=["repo", "name", "value"],
)
def set_codespace_repo_secret(repo: str, name: str, value: str) -> str:
    try:
        _gh("secret", "set", name, "--repo", repo, "--codespace", "--body", value, timeout=15)
        return f"Codespace secret '{name}' set in {repo}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_codespace_repo_secret",
    description="Delete a codespace secret from a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "name": {"type": "string", "description": "Secret name"},
    },
    required=["repo", "name"],
)
def delete_codespace_repo_secret(repo: str, name: str) -> str:
    try:
        _gh("secret", "delete", name, "--repo", repo, "--codespace", timeout=15)
        return f"Codespace secret '{name}' deleted from {repo}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_codespace_secrets",
    description="List codespace secrets for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def list_codespace_secrets(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/codespaces/secrets")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="merge_branch",
    description="Merge a branch into the default branch via the API.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "head": {"type": "string", "description": "Head branch to merge from"},
        "base": {"type": "string", "description": "Base branch to merge into (default: repo default)"},
        "commit_message": {"type": "string", "description": "Commit message (optional)"},
    },
    required=["repo", "head"],
)
def merge_branch(repo: str, head: str, base: str = "", commit_message: str = "") -> str:
    try:
        import json as j
        payload: dict = {"head": head}
        if base:
            payload["base"] = base
        if commit_message:
            payload["commit_message"] = commit_message
        return _gh("api", f"repos/{repo}/merges", "--method", "POST",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="sync_fork",
    description="Sync a fork branch with the upstream repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "branch": {"type": "string", "description": "Branch to sync (default: default branch)"},
    },
    required=["repo"],
)
def sync_fork(repo: str, branch: str = "") -> str:
    try:
        import json as j
        payload: dict = {}
        if branch:
            payload["branch"] = branch
        return _gh("api", f"repos/{repo}/merge-upstream", "--method", "POST",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_repo_commit_activity",
    description="Get the last year of commit activity data for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_repo_commit_activity(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/stats/commit_activity")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_repo_code_frequency_stats",
    description="Get the code frequency (weekly additions/deletions) for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_repo_code_frequency_stats(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/stats/code_frequency")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_repo_participation_stats",
    description="Get the weekly commit count by owner and by contributors for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_repo_participation_stats(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/stats/participation")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_repo_code_of_conduct",
    description="Set the code of conduct for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "code_of_conduct_key": {"type": "string", "description": "Key of the code of conduct (e.g., contributor_covenant)"},
    },
    required=["repo", "code_of_conduct_key"],
)
def set_repo_code_of_conduct(repo: str, code_of_conduct_key: str) -> str:
    try:
        import json as j
        payload = {"code_of_conduct": {"key": code_of_conduct_key}}
        _gh("api", f"repos/{repo}/community/code_of_conduct", "--method", "PUT",
            "--raw-field", j.dumps(payload), "--silent", timeout=15)
        return f"Code of conduct set to '{code_of_conduct_key}' for {repo}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_repo_community_profile",
    description="Get the community profile for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_repo_community_profile(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/community/profile")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_repo_contributing_guidelines",
    description="Create or update CONTRIBUTING.md in a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "content": {"type": "string", "description": "Content of CONTRIBUTING.md"},
        "message": {"type": "string", "description": "Commit message"},
        "branch": {"type": "string", "description": "Branch (default: default branch)"},
    },
    required=["repo", "content", "message"],
)
def create_repo_contributing_guidelines(repo: str, content: str, message: str, branch: str = "") -> str:
    try:
        import json as j, base64
        b64 = base64.b64encode(content.encode()).decode()
        payload = {"message": message, "content": b64}
        if branch:
            payload["branch"] = branch
        return _gh("api", f"repos/{repo}/contents/CONTRIBUTING.md", "--method", "PUT",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_repo_support_guidelines",
    description="Create or update SUPPORT.md in a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "content": {"type": "string", "description": "Content of SUPPORT.md"},
        "message": {"type": "string", "description": "Commit message"},
        "branch": {"type": "string", "description": "Branch (default: default branch)"},
    },
    required=["repo", "content", "message"],
)
def create_repo_support_guidelines(repo: str, content: str, message: str, branch: str = "") -> str:
    try:
        import json as j, base64
        b64 = base64.b64encode(content.encode()).decode()
        payload = {"message": message, "content": b64}
        if branch:
            payload["branch"] = branch
        return _gh("api", f"repos/{repo}/contents/SUPPORT.md", "--method", "PUT",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_org_push_protection",
    description="Get push protection status for an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
    },
    required=["org"],
)
def get_org_push_protection(org: str) -> str:
    try:
        return _gh("api", f"orgs/{org}/org-secret-scanning/push-protection")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="enable_secret_push_protection",
    description="Enable push protection for secret scanning at the organization level.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
    },
    required=["org"],
)
def enable_secret_push_protection(org: str) -> str:
    try:
        _gh("api", f"orgs/{org}/org-secret-scanning/push-protection", "--method", "POST",
            "--silent", timeout=15)
        return f"Push protection enabled for {org}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="disable_secret_push_protection",
    description="Disable push protection for secret scanning at the organization level.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
    },
    required=["org"],
)
def disable_secret_push_protection(org: str) -> str:
    try:
        _gh("api", f"orgs/{org}/org-secret-scanning/push-protection", "--method", "DELETE",
            "--silent", timeout=15)
        return f"Push protection disabled for {org}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="set_repo_security_and_analysis",
    description="Set security and analysis settings for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "advanced_security": {"type": "string", "description": "true/false: enable GitHub Advanced Security"},
        "secret_scanning": {"type": "string", "description": "true/false: enable secret scanning"},
        "secret_scanning_push_protection": {"type": "string", "description": "true/false: enable push protection"},
    },
    required=["repo"],
)
def set_repo_security_and_analysis(repo: str, advanced_security: str = "",
                                    secret_scanning: str = "",
                                    secret_scanning_push_protection: str = "") -> str:
    try:
        import json as j
        payload: dict = {}
        if advanced_security:
            payload["advanced_security"] = {"status": "enabled" if advanced_security.lower() == "true" else "disabled"}
        if secret_scanning:
            payload["secret_scanning"] = {"status": "enabled" if secret_scanning.lower() == "true" else "disabled"}
        if secret_scanning_push_protection:
            payload["secret_scanning_push_protection"] = {"status": "enabled" if secret_scanning_push_protection.lower() == "true" else "disabled"}
        return _gh("api", f"repos/{repo}/security-and-analysis", "--method", "PATCH",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_issue_template",
    description="Create an issue template file in a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "filename": {"type": "string", "description": "Template filename (e.g., bug_report.md)"},
        "content": {"type": "string", "description": "Template content in YAML frontmatter + Markdown"},
        "message": {"type": "string", "description": "Commit message"},
        "branch": {"type": "string", "description": "Branch (default: default branch)"},
    },
    required=["repo", "filename", "content", "message"],
)
def create_issue_template(repo: str, filename: str, content: str, message: str, branch: str = "") -> str:
    try:
        import json as j, base64
        b64 = base64.b64encode(content.encode()).decode()
        payload = {"message": message, "content": b64}
        if branch:
            payload["branch"] = branch
        return _gh("api", f"repos/{repo}/contents/.github/ISSUE_TEMPLATE/{filename}",
                    "--method", "PUT", "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_pr_template",
    description="Create or update a pull request template file in a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "content": {"type": "string", "description": "Template content in Markdown"},
        "message": {"type": "string", "description": "Commit message"},
        "branch": {"type": "string", "description": "Branch (default: default branch)"},
    },
    required=["repo", "content", "message"],
)
def create_pr_template(repo: str, content: str, message: str, branch: str = "") -> str:
    try:
        import json as j, base64
        b64 = base64.b64encode(content.encode()).decode()
        payload = {"message": message, "content": b64}
        if branch:
            payload["branch"] = branch
        return _gh("api", f"repos/{repo}/contents/.github/PULL_REQUEST_TEMPLATE.md",
                    "--method", "PUT", "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_issue_template",
    description="Get the content of a specific issue template file.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "filename": {"type": "string", "description": "Template filename"},
    },
    required=["repo", "filename"],
)
def get_issue_template(repo: str, filename: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/contents/.github/ISSUE_TEMPLATE/{filename}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_repo_readme",
    description="Create or update README.md in a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "content": {"type": "string", "description": "README content"},
        "message": {"type": "string", "description": "Commit message"},
        "branch": {"type": "string", "description": "Branch (default: default branch)"},
    },
    required=["repo", "content", "message"],
)
def create_repo_readme(repo: str, content: str, message: str, branch: str = "") -> str:
    try:
        import json as j, base64
        b64 = base64.b64encode(content.encode()).decode()
        payload = {"message": message, "content": b64}
        if branch:
            payload["branch"] = branch
        return _gh("api", f"repos/{repo}/contents/README.md",
                    "--method", "PUT", "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_repo_teams",
    description="List teams with access to a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_repo_teams(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/teams")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="add_team_to_repo",
    description="Add a team to a repository with a specific permission level.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "team_slug": {"type": "string", "description": "Team slug"},
        "permission": {"type": "string", "description": "Permission: pull, push, admin, maintain, triage"},
    },
    required=["repo", "team_slug"],
)
def add_team_to_repo(repo: str, team_slug: str, permission: str = "push") -> str:
    try:
        import json as j
        payload = {"permission": permission}
        return _gh("api", f"repos/{repo}/teams/{team_slug}", "--method", "PUT",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="remove_team_from_repo",
    description="Remove a team from a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "team_slug": {"type": "string", "description": "Team slug"},
    },
    required=["repo", "team_slug"],
)
def remove_team_from_repo(repo: str, team_slug: str) -> str:
    try:
        _gh("api", f"repos/{repo}/teams/{team_slug}", "--method", "DELETE",
            "--silent", timeout=15)
        return f"Team '{team_slug}' removed from {repo}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_repo_team_permission",
    description="Get the permission level for a team on a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "team_slug": {"type": "string", "description": "Team slug"},
    },
    required=["repo", "team_slug"],
)
def get_repo_team_permission(repo: str, team_slug: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/teams/{team_slug}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="check_team_permission",
    description="Check if a team has a specific permission level on a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "team_slug": {"type": "string", "description": "Team slug"},
        "permission": {"type": "string", "description": "Permission to check: pull, push, admin, maintain, triage"},
    },
    required=["repo", "team_slug", "permission"],
)
def check_team_permission(repo: str, team_slug: str, permission: str) -> str:
    try:
        result = _gh("api", f"repos/{repo}/teams/{team_slug}")
        data = json.loads(result)
        perms = data.get("permissions", {})
        if perms.get(permission):
            return f"Yes, team '{team_slug}' has '{permission}' permission on {repo}."
        else:
            return f"No, team '{team_slug}' does not have '{permission}' permission on {repo}. Has: {', '.join(p for p, v in perms.items() if v)}"
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_traffic_clones",
    description="Get the number of clones for a repository in the last 14 days.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_traffic_clones(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/traffic/clones")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_traffic_views",
    description="Get the number of views for a repository in the last 14 days.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_traffic_views(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/traffic/views")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_repo_languages",
    description="Get the language breakdown for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_repo_languages(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/languages")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_top_referrer_paths",
    description="Get the top referrer sources for a repository over the last 14 days.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_top_referrer_paths(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/traffic/popular/referrers")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_top_popular_paths",
    description="Get the top popular paths for a repository over the last 14 days.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_top_popular_paths(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/traffic/popular/paths")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_repo_environments",
    description="List environments for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def list_repo_environments(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/environments")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_repo_environment",
    description="Create or update an environment in a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "environment_name": {"type": "string", "description": "Environment name"},
        "wait_timer": {"type": "number", "description": "Wait timer in minutes (optional)"},
        "reviewers": {"type": "string", "description": "Comma-separated list of reviewer teams (slugs) or users (optional)"},
        "deployment_branch_policy": {"type": "string", "description": "Branch policy: all, selected, or empty for none"},
    },
    required=["repo", "environment_name"],
)
def create_repo_environment(repo: str, environment_name: str, wait_timer: int = 0,
                             reviewers: str = "", deployment_branch_policy: str = "") -> str:
    try:
        import json as j
        payload: dict = {"deployment_branch_policy": None}
        if wait_timer > 0:
            payload["wait_timer"] = wait_timer
        if reviewers:
            reviewer_list = []
            for r in reviewers.split(","):
                r = r.strip()
                if r:
                    reviewer_list.append({"type": "Team" if r.islower() else "User", "id": None, "slug": r})
            payload["reviewers"] = reviewer_list
        if deployment_branch_policy:
            payload["deployment_branch_policy"] = {"protected_branches": True, "custom_branch_policies": deployment_branch_policy == "selected"}
        return _gh("api", f"repos/{repo}/environments/{environment_name}", "--method", "PUT",
                    "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_repo_environment",
    description="Delete an environment from a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "environment_name": {"type": "string", "description": "Environment name"},
    },
    required=["repo", "environment_name"],
)
def delete_repo_environment(repo: str, environment_name: str) -> str:
    try:
        _gh("api", f"repos/{repo}/environments/{environment_name}", "--method", "DELETE",
            "--silent", timeout=15)
        return f"Environment '{environment_name}' deleted from {repo}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_deployment_branch_policies",
    description="List deployment branch policies for an environment.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "environment_name": {"type": "string", "description": "Environment name"},
    },
    required=["repo", "environment_name"],
)
def list_deployment_branch_policies(repo: str, environment_name: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/environments/{environment_name}/deployment-branch-policies")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_deployment_branch_policy",
    description="Create a deployment branch policy for an environment.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "environment_name": {"type": "string", "description": "Environment name"},
        "name": {"type": "string", "description": "Branch name pattern (e.g., main, release/*)"},
        "type": {"type": "string", "description": "Branch type: branch or tag"},
    },
    required=["repo", "environment_name", "name"],
)
def create_deployment_branch_policy(repo: str, environment_name: str, name: str, type: str = "branch") -> str:
    try:
        import json as j
        payload = {"name": name, "type": type}
        return _gh("api", f"repos/{repo}/environments/{environment_name}/deployment-branch-policies",
                    "--method", "POST", "--raw-field", j.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_deployment_branch_policy",
    description="Delete a deployment branch policy for an environment.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "environment_name": {"type": "string", "description": "Environment name"},
        "policy_id": {"type": "number", "description": "Policy ID"},
    },
    required=["repo", "environment_name", "policy_id"],
)
def delete_deployment_branch_policy(repo: str, environment_name: str, policy_id: int) -> str:
    try:
        _gh("api", f"repos/{repo}/environments/{environment_name}/deployment-branch-policies/{policy_id}",
            "--method", "DELETE", "--silent", timeout=15)
        return f"Deployment branch policy {policy_id} deleted."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_environment_secrets",
    description="List environment secrets for an environment.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "environment_name": {"type": "string", "description": "Environment name"},
    },
    required=["repo", "environment_name"],
)
def get_environment_secrets(repo: str, environment_name: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/environments/{environment_name}/secrets")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_rate_limit",
    description="Get the current rate limit status for the authenticated user.",
)
def get_rate_limit() -> str:
    try:
        return _gh("api", "rate_limit")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_pages",
    description="Get information about a GitHub Pages site for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_pages(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/pages")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_pages",
    description="Update information about a GitHub Pages site for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "source_branch": {"type": "string", "description": "Source branch for Pages (e.g., main)"},
        "source_path": {"type": "string", "description": "Source path: / or /docs"},
        "build_type": {"type": "string", "description": "Build type: legacy or workflow"},
    },
    required=["repo"],
)
def update_pages(repo: str, source_branch: str = "main", source_path: str = "/",
                  build_type: str = "legacy") -> str:
    try:
        body = {"source": {"branch": source_branch, "path": source_path},
                "build_type": build_type}
        return _gh("api", f"repos/{repo}/pages", "--method", "PUT",
                    "--raw-field", json.dumps(body))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_pages_build",
    description="Get the latest Pages build for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_pages_build(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/pages/builds/latest")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_repo_events",
    description="List events for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def list_repo_events(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/events")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_org_events",
    description="List public events for an organization.",
    parameters={
        "org": {"type": "string", "description": "Organization name"},
    },
    required=["org"],
)
def list_org_events(org: str) -> str:
    try:
        return _gh("api", f"orgs/{org}/events")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_codeowners_errors",
    description="Get CODEOWNERS file errors for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "ref": {"type": "string", "description": "Branch (default: default branch)"},
    },
    required=["repo"],
)
def get_codeowners_errors(repo: str, ref: str = "") -> str:
    try:
        path = f"repos/{repo}/codeowners/errors"
        if ref:
            path += f"?ref={ref}"
        return _gh("api", path)
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_collaborator_permission_level",
    description="Get the permission level for a collaborator on a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "username": {"type": "string", "description": "Username"},
    },
    required=["repo", "username"],
)
def get_collaborator_permission_level(repo: str, username: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/collaborators/{username}/permission")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_merge_queue_entry",
    description="Get a specific merge queue entry for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "entry_id": {"type": "number", "description": "Merge queue entry ID"},
    },
    required=["repo", "entry_id"],
)
def get_merge_queue_entry(repo: str, entry_id: int) -> str:
    try:
        return _gh("api", f"repos/{repo}/merge-queue/entries/{entry_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_repo_security_advisory",
    description="Get a specific repository security advisory.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "ghsa_id": {"type": "string", "description": "GHSA ID of the advisory"},
    },
    required=["repo", "ghsa_id"],
)
def get_repo_security_advisory(repo: str, ghsa_id: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/security-advisories/{ghsa_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="export_sbom",
    description="Export the SBOM for a repository in SPDX format.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def export_sbom(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/dependency-graph/sbom")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="enable_automated_security_fixes",
    description="Enable automated security fixes for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def enable_automated_security_fixes(repo: str) -> str:
    try:
        _gh("api", f"repos/{repo}/automated-security-fixes", "--method", "PUT",
            "--silent", timeout=15)
        return f"Automated security fixes enabled for {repo}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="disable_automated_security_fixes",
    description="Disable automated security fixes for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def disable_automated_security_fixes(repo: str) -> str:
    try:
        _gh("api", f"repos/{repo}/automated-security-fixes", "--method", "DELETE",
            "--silent", timeout=15)
        return f"Automated security fixes disabled for {repo}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="accept_repo_invitation",
    description="Accept a repository invitation.",
    parameters={
        "invitation_id": {"type": "number", "description": "Invitation ID"},
    },
    required=["invitation_id"],
)
def accept_repo_invitation(invitation_id: int) -> str:
    try:
        _gh("api", f"user/repository_invitations/{invitation_id}", "--method", "PATCH",
            "--silent", timeout=15)
        return f"Invitation {invitation_id} accepted."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="decline_repo_invitation",
    description="Decline a repository invitation.",
    parameters={
        "invitation_id": {"type": "number", "description": "Invitation ID"},
    },
    required=["invitation_id"],
)
def decline_repo_invitation(invitation_id: int) -> str:
    try:
        _gh("api", f"user/repository_invitations/{invitation_id}", "--method", "DELETE",
            "--silent", timeout=15)
        return f"Invitation {invitation_id} declined."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_issue_event",
    description="Get a specific issue event by ID.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "event_id": {"type": "number", "description": "Event ID"},
    },
    required=["repo", "event_id"],
)
def get_issue_event(repo: str, event_id: int) -> str:
    try:
        return _gh("api", f"repos/{repo}/issues/events/{event_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_pull_request_review",
    description="Create a review on a pull request.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "pr_number": {"type": "number", "description": "Pull request number"},
        "body": {"type": "string", "description": "Review body text"},
        "event": {"type": "string", "description": "Review action: APPROVE, REQUEST_CHANGES, COMMENT"},
        "commit_id": {"type": "string", "description": "SHA of commit to review (optional)"},
    },
    required=["repo", "pr_number", "body", "event"],
)
def create_pull_request_review(repo: str, pr_number: int, body: str, event: str,
                                commit_id: str = "") -> str:
    try:
        payload: dict = {"body": body, "event": event}
        if commit_id:
            payload["commit_id"] = commit_id
        return _gh("api", f"repos/{repo}/pulls/{pr_number}/reviews", "--method", "POST",
                    "--raw-field", json.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="submit_pull_request_review",
    description="Submit a pending review on a pull request.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "pr_number": {"type": "number", "description": "Pull request number"},
        "review_id": {"type": "number", "description": "Review ID"},
        "body": {"type": "string", "description": "Review body text (optional)"},
        "event": {"type": "string", "description": "Review action: APPROVE, REQUEST_CHANGES, COMMENT"},
    },
    required=["repo", "pr_number", "review_id", "event"],
)
def submit_pull_request_review(repo: str, pr_number: int, review_id: int, event: str,
                                body: str = "") -> str:
    try:
        payload: dict = {"event": event}
        if body:
            payload["body"] = body
        return _gh("api", f"repos/{repo}/pulls/{pr_number}/reviews/{review_id}/events",
                    "--method", "POST", "--raw-field", json.dumps(payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_pull_request_review",
    description="Delete a pull request review.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "pr_number": {"type": "number", "description": "Pull request number"},
        "review_id": {"type": "number", "description": "Review ID"},
    },
    required=["repo", "pr_number", "review_id"],
)
def delete_pull_request_review(repo: str, pr_number: int, review_id: int) -> str:
    try:
        _gh("api", f"repos/{repo}/pulls/{pr_number}/reviews/{review_id}", "--method", "DELETE",
            "--silent", timeout=15)
        return f"Review {review_id} deleted from PR #{pr_number}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_pull_request_review_comment",
    description="Create a review comment on a pull request diff.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "pr_number": {"type": "number", "description": "Pull request number"},
        "body": {"type": "string", "description": "Comment text"},
        "commit_id": {"type": "string", "description": "SHA of the commit to comment on"},
        "path": {"type": "string", "description": "File path to comment on"},
        "line": {"type": "number", "description": "Line number in the file"},
        "side": {"type": "string", "description": "Side of the diff: LEFT or RIGHT"},
    },
    required=["repo", "pr_number", "body", "commit_id", "path", "line"],
)
def create_pull_request_review_comment(repo: str, pr_number: int, body: str,
                                        commit_id: str, path: str, line: int,
                                        side: str = "RIGHT") -> str:
    try:
        body_payload = {"body": body, "commit_id": commit_id, "path": path,
                        "line": line, "side": side}
        return _gh("api", f"repos/{repo}/pulls/{pr_number}/comments", "--method", "POST",
                    "--raw-field", json.dumps(body_payload))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_app_slug",
    description="Get the authenticated app using its slug.",
    parameters={
        "app_slug": {"type": "string", "description": "App slug"},
    },
    required=["app_slug"],
)
def get_app_slug(app_slug: str) -> str:
    try:
        return _gh("api", f"apps/{app_slug}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_app_installation",
    description="Get an app installation by ID.",
    parameters={
        "installation_id": {"type": "number", "description": "Installation ID"},
    },
    required=["installation_id"],
)
def get_app_installation(installation_id: int) -> str:
    try:
        return _gh("api", f"app/installations/{installation_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_installation_access_token",
    description="Create an access token for an app installation.",
    parameters={
        "installation_id": {"type": "number", "description": "Installation ID"},
        "repositories": {"type": "string", "description": "Comma-separated repo names (optional)"},
        "permissions": {"type": "string", "description": "JSON object of permissions (optional)"},
    },
    required=["installation_id"],
)
def create_installation_access_token(installation_id: int, repositories: str = "", permissions: str = "") -> str:
    try:
        body: dict = {}
        if repositories:
            body["repositories"] = [r.strip() for r in repositories.split(",") if r.strip()]
        if permissions:
            body["permissions"] = json.loads(permissions)
        return _gh("api", f"app/installations/{installation_id}/access_tokens", "--method", "POST",
                    "--raw-field", json.dumps(body))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_sarif",
    description="Get a SARIF upload by its ID.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "sarif_id": {"type": "string", "description": "SARIF ID"},
    },
    required=["repo", "sarif_id"],
)
def get_sarif(repo: str, sarif_id: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/code-scanning/sarifs/{sarif_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_lfs_settings",
    description="Get Git LFS settings for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
    },
    required=["repo"],
)
def get_lfs_settings(repo: str) -> str:
    try:
        return _gh("api", f"repos/{repo}/lfs")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="update_lfs_settings",
    description="Enable or disable Git LFS for a repository.",
    parameters={
        "repo": {"type": "string", "description": "Owner/repo"},
        "enabled": {"type": "boolean", "description": "Enable or disable LFS"},
    },
    required=["repo", "enabled"],
)
def update_lfs_settings(repo: str, enabled: bool) -> str:
    try:
        _gh("api", f"repos/{repo}/lfs", "--method", "PATCH",
            "--raw-field", json.dumps({"enabled": enabled}),
            "--silent", timeout=15)
        status = "enabled" if enabled else "disabled"
        return f"Git LFS {status} for {repo}."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="create_project_column",
    description="Create a column in a project board.",
    parameters={
        "project_id": {"type": "number", "description": "Project ID"},
        "name": {"type": "string", "description": "Column name"},
    },
    required=["project_id", "name"],
)
def create_project_column(project_id: int, name: str) -> str:
    try:
        return _gh("api", f"projects/{project_id}/columns", "--method", "POST",
                    "--raw-field", json.dumps({"name": name}))
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_project_cards",
    description="List cards in a project column.",
    parameters={
        "column_id": {"type": "number", "description": "Column ID"},
        "archived_state": {"type": "string", "description": "Filter by archived state: archived, not_archived, all"},
    },
    required=["column_id"],
)
def list_project_cards(column_id: int, archived_state: str = "") -> str:
    try:
        path = f"projects/columns/{column_id}/cards"
        if archived_state:
            path += f"?archived_state={archived_state}"
        return _gh("api", path)
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_gpg_key",
    description="Get a specific GPG key for the authenticated user.",
    parameters={
        "gpg_key_id": {"type": "number", "description": "GPG key ID"},
    },
    required=["gpg_key_id"],
)
def get_gpg_key(gpg_key_id: int) -> str:
    try:
        return _gh("api", f"user/gpg_keys/{gpg_key_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_gpg_key",
    description="Delete a GPG key for the authenticated user.",
    parameters={
        "gpg_key_id": {"type": "number", "description": "GPG key ID"},
    },
    required=["gpg_key_id"],
)
def delete_gpg_key(gpg_key_id: int) -> str:
    try:
        _gh("api", f"user/gpg_keys/{gpg_key_id}", "--method", "DELETE",
            "--silent", timeout=15)
        return f"GPG key {gpg_key_id} deleted."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="get_ssh_key",
    description="Get a specific SSH key for the authenticated user.",
    parameters={
        "ssh_key_id": {"type": "number", "description": "SSH key ID"},
    },
    required=["ssh_key_id"],
)
def get_ssh_key(ssh_key_id: int) -> str:
    try:
        return _gh("api", f"user/keys/{ssh_key_id}")
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="delete_ssh_key",
    description="Delete an SSH key for the authenticated user.",
    parameters={
        "ssh_key_id": {"type": "number", "description": "SSH key ID"},
    },
    required=["ssh_key_id"],
)
def delete_ssh_key(ssh_key_id: int) -> str:
    try:
        _gh("api", f"user/keys/{ssh_key_id}", "--method", "DELETE",
            "--silent", timeout=15)
        return f"SSH key {ssh_key_id} deleted."
    except RuntimeError as e:
        return f"Error: {e}"


@tool(
    name="list_tools",
    description="List all available tools in the GitHub Issues Manager with descriptions.",
    parameters={
        "category": {
            "type": "string",
            "description": "Optional category to filter by (issues, prs, labels, workflows, etc.).",
        },
    },
    required=[],
)
def list_tools(category: str = "") -> str:
    from . import REGISTRY
    if not REGISTRY:
        return "No tools registered."

    # Group by prefix keywords
    groups: dict[str, list[str]] = {}
    for name, entry in REGISTRY.items():
        desc = entry["schema"]["function"]["description"]
        cat = "other"
        if any(name.startswith(p) for p in ("list_issue", "view_issue", "create_issue", "close_issue", "reopen_", "comment_", "edit_issue", "search_issue", "add_issue", "remove_issue_", "lock_", "unlock_", "pin_", "unpin_", "transfer_issue", "set_issue_", "add_reaction")):
            cat = "issues"
        elif any(name.startswith(p) for p in ("list_pull", "view_pull", "create_pull", "merge_pull", "add_pr", "list_pr", "request_pr", "update_pr", "enable_auto_merge", "disable_auto_merge", "get_pr", "dismiss_pr", "list_pr_")):
            cat = "prs"
        elif any(name.startswith(p) for p in ("list_label", "create_label", "update_label", "delete_label")):
            cat = "labels"
        elif any(name.startswith(p) for p in ("list_milestone", "create_milestone", "set_issue_milestone", "get_milestone", "update_milestone", "delete_milestone")):
            cat = "milestones"
        elif any(name.startswith(p) for p in ("list_release", "create_release", "update_release", "delete_release", "list_release_assets", "upload_release", "get_release_by", "delete_release_asset")):
            cat = "releases"
        elif any(name.startswith(p) for p in ("list_workflow", "trigger_", "cancel_", "rerun_", "get_wor", "delete_workflow_run", "get_workflow_run", "get_workflow_usage")):
            cat = "workflows"
        elif any(name.startswith(p) for p in ("search_",)):
            cat = "search"
        elif any(name.startswith(p) for p in ("list_notif", "mark_notif", "get_notification", "mark_thread", "set_thread")):
            cat = "notifications"
        elif any(name.startswith(p) for p in ("list_gist", "create_gist")):
            cat = "gists"
        elif any(name.startswith(p) for p in ("list_deploy", "add_deploy", "delete_deploy")):
            cat = "deploy_keys"
        elif any(name.startswith(p) for p in ("list_actions", "delete_artifact")):
            cat = "artifacts"
        elif any(name.startswith(p) for p in ("list_dependabot", "list_code_", "list_secret_", "update_code_scanning", "update_dependabot", "update_secret_scanning", "list_code_scanning_ana", "delete_code_scanning_ana", "upload_sarif")):
            cat = "security"
        elif any(name.startswith(p) for p in ("list_webhook", "create_webhook", "delete_webhook", "ping_webhook")):
            cat = "webhooks"
        elif any(name.startswith(p) for p in ("get_branch",)):
            cat = "branch_protection"
        elif any(name.startswith(p) for p in ("repo_traffic",)):
            cat = "traffic"
        elif any(name.startswith(p) for p in ("list_repo_", "add_repo_", "get_repo_", "star_", "unstar_", "fork_", "create_repo", "archive_", "unarchive_", "change_repo_", "transfer_repo", "get_repo_archive", "get_dependency")):
            cat = "repo_management"
        elif any(name.startswith(p) for p in ("watch_", "unwatch_", "community_")):
            cat = "community"
        elif any(name.startswith(p) for p in ("render_", "list_licenses", "list_issue_events", "list_issue_template", "list_comment", "get_comment", "update_comment", "delete_comment", "list_commit", "list_tag", "create_commit_status", "compare_refs", "whoami", "rate_limit", "list_collab", "add_collab", "remove_collab", "list_branches", "delete_branch", "bulk_", "get_repo_content", "list_forks", "list_commit_statuses", "get_combined_commit_status", "create_git_ref", "delete_git_ref", "list_reactions", "delete_reaction", "get_commit", "list_commit_comments", "get_emojis", "list_codes_of_conduct", "list_gitignore", "get_gitignore", "get_license", "list_tag_protection", "create_tag_protection", "delete_tag_protection", "get_pages", "get_blob", "get_tree", "create_or_update_file", "delete_repo_file", "create_commit_comment", "get_weekly", "get_code_frequency", "create_gist_comment", "list_gist_comments", "list_commit_prs", "get_meta", "get_octocat", "get_zen", "list_user_gpg", "list_user_ssh", "copy_issue")):
            cat = "other"
        elif any(name.startswith(p) for p in ("list_org", "get_org", "list_org_", "get_team", "list_team")):
            cat = "organizations"
        elif any(name.startswith(p) for p in ("get_user", "list_user_repos", "list_followers", "list_following", "follow_", "unfollow_", "list_codespaces", "list_user_gpg", "list_user_ssh", "list_user_email", "add_user_email", "delete_user_email")):
            cat = "users"
        elif any(name.startswith(p) for p in ("list_projects", "create_project")):
            cat = "projects"
        elif any(name.startswith(p) for p in ("list_actions_caches", "delete_actions_caches")):
            cat = "caches"
        elif any(name.startswith(p) for p in ("list_runners",)):
            cat = "runners"
        elif any(name.startswith(p) for p in ("list_rulesets",)):
            cat = "rulesets"
        elif any(name.startswith(p) for p in ("list_autolinks", "create_autolink", "delete_autolink")):
            cat = "autolinks"
        elif any(name.startswith(p) for p in ("create_check_run", "create_check_suite", "rerequest_check_suite", "list_check_runs")):
            cat = "checks"
        elif any(name.startswith(p) for p in ("get_webhook", "update_webhook")):
            cat = "webhooks"
        elif any(name.startswith(p) for p in ("get_deploy_key",)):
            cat = "deploy_keys"
        elif any(name.startswith(p) for p in ("add_issue_labels", "set_issue_labels")):
            cat = "issues"
        elif any(name.startswith(p) for p in ("get_actions_billing", "get_copilot_billing", "list_copilot_seats", "assign_copilot", "remove_copilot", "get_enterprise_billing")):
            cat = "billing"
        elif any(name.startswith(p) for p in ("list_repo_invitations", "enable_vulnerability", "disable_vulnerability", "enable_automatic", "disable_automatic", "get_repo_interaction", "set_repo_interaction", "remove_repo_interaction", "get_repo_custom")):
            cat = "repo_management"
        elif any(name.startswith(p) for p in ("list_org_webhook", "create_org_webhook", "delete_org_webhook")):
            cat = "webhooks"
        elif any(name.startswith(p) for p in ("check_org_membership", "get_org_membership", "get_org_teams", "list_org_secrets", "get_org_blocked", "get_org_outside", "list_org_invitations", "get_audit", "list_org_custom", "list_org_vulnerability", "list_org_public", "check_org_public", "get_org_security")):
            cat = "organizations"
        elif any(name.startswith(p) for p in ("set_team_membership", "remove_team_member")):
            cat = "teams"
        elif any(name.startswith(p) for p in ("generate_release_notes", "get_release", "get_latest_release")):
            cat = "releases"
        elif any(name.startswith(p) for p in ("trigger_workflow_with_inputs", "get_workflow_usage")):
            cat = "workflows"
        elif any(name.startswith(p) for p in ("list_merge_queue_entries",)):
            cat = "merge_queue"
        elif any(name.startswith(p) for p in ("get_app", "list_app_installations")):
            cat = "apps"
        elif any(name.startswith(p) for p in ("create_commit",)):
            cat = "git"
        elif any(name.startswith(p) for p in ("check_if_following", "list_stargazers", "list_watchers", "get_dependency_diff", "update_review_comment", "delete_review_comment", "get_feeds", "get_merge_queue_config", "get_punch_card", "get_participation", "get_contributor", "create_repository_dispatch", "get_repo_code_of_conduct", "create_blob", "create_tree", "list_matching_refs", "rename_branch", "list_pull_review_requests", "get_vulnerability_alerts")):
            cat = "other"
        elif any(name.startswith(p) for p in ("get_issue_timeline",)):
            cat = "issues"
        elif any(name.startswith(p) for p in ("get_ruleset", "create_ruleset")):
            cat = "rulesets"
        elif any(name.startswith(p) for p in ("get_meta", "get_octocat", "get_zen")):
            cat = "utility"
        elif any(name.startswith(p) for p in ("copy_issue", "create_sub_issue", "list_sub_issues")):
            cat = "issues"
        elif any(name.startswith(p) for p in ("update_pull_request",)):
            cat = "prs"
        elif any(name.startswith(p) for p in ("set_repo_secret", "delete_repo_secret", "set_repo_variable", "delete_repo_variable")):
            cat = "secrets_vars"
        elif any(name.startswith(p) for p in ("create_environment", "delete_environment", "get_environment")):
            cat = "environments"
        elif any(name.startswith(p) for p in ("create_deployment", "list_deployment_statuses")):
            cat = "deployments"
        elif any(name.startswith(p) for p in ("get_branch",)):
            cat = "branches"
        groups.setdefault(cat, []).append(f"  - `{name}`: {desc}")

    if category:
        category = category.lower()
        for c, tools in groups.items():
            if c.startswith(category) or category.startswith(c):
                return "\n".join([f"## {c.upper()}"] + tools)
        return f"No tools found in category '{category}'."

    result = []
    for c in sorted(groups.keys()):
        result.append(f"\n## {c.upper()}")
        result.extend(groups[c])
    return "\n".join(result).strip()
