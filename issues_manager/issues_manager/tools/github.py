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
