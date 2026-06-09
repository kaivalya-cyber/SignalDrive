#!/usr/bin/env python3
"""Structured interface for managing GitHub issues via the gh CLI."""

import json
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Issue:
    number: int
    title: str
    state: str
    body: str = ""
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    url: str = ""
    comments_count: int = 0

    @classmethod
    def from_json(cls, data: dict) -> "Issue":
        return cls(
            number=data["number"],
            title=data["title"],
            state=data.get("state", "open"),
            body=data.get("body", ""),
            labels=[l["name"] for l in data.get("labels", [])],
            assignees=[a["login"] for a in data.get("assignees", [])],
            created_at=data.get("createdAt"),
            updated_at=data.get("updatedAt"),
            url=data.get("url", ""),
            comments_count=data.get("comments", 0),
        )


def _run_gh(args: list[str]) -> str:
    result = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def get_default_repo() -> str:
    out = _run_gh(["repo", "view", "--json", "nameWithOwner"])
    return json.loads(out)["nameWithOwner"]


def list_issues(
    repo: Optional[str] = None,
    state: str = "open",
    label: Optional[str] = None,
    assignee: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 20,
) -> list[Issue]:
    args = ["issue", "list", "--state", state, "--limit", str(limit), "--json", "number,title,state,labels,assignees,createdAt,updatedAt,url,body,comments"]
    if repo:
        args += ["--repo", repo]
    if label:
        args += ["--label", label]
    if assignee:
        args += ["--assignee", assignee]
    if search:
        args += ["--search", search]
    out = _run_gh(args)
    return [Issue.from_json(item) for item in json.loads(out)]


def view_issue(number: int, repo: Optional[str] = None, comments: bool = False) -> Issue:
    args = ["issue", "view", str(number), "--json", "number,title,state,labels,assignees,createdAt,updatedAt,url,body,comments"]
    if repo:
        args += ["--repo", repo]
    out = _run_gh(args)
    return Issue.from_json(json.loads(out))


def create_issue(
    title: str,
    body: str = "",
    repo: Optional[str] = None,
    labels: Optional[list[str]] = None,
    assignees: Optional[list[str]] = None,
) -> Issue:
    args = ["issue", "create", "--title", title]
    if body:
        args += ["--body", body]
    if repo:
        args += ["--repo", repo]
    if labels:
        for l in labels:
            args += ["--label", l]
    if assignees:
        for a in assignees:
            args += ["--assignee", a]
    out = _run_gh(args)
    number = int(out.strip().split("/")[-1])
    return view_issue(number, repo)


def close_issue(number: int, repo: Optional[str] = None, reason: str = "completed") -> None:
    args = ["issue", "close", str(number), "--reason", reason]
    if repo:
        args += ["--repo", repo]
    _run_gh(args)


def reopen_issue(number: int, repo: Optional[str] = None) -> None:
    args = ["issue", "reopen", str(number)]
    if repo:
        args += ["--repo", repo]
    _run_gh(args)


def add_comment(number: int, body: str, repo: Optional[str] = None) -> None:
    args = ["issue", "comment", str(number), "--body", body]
    if repo:
        args += ["--repo", repo]
    _run_gh(args)


def edit_issue(
    number: int,
    repo: Optional[str] = None,
    title: Optional[str] = None,
    body: Optional[str] = None,
    add_labels: Optional[list[str]] = None,
    remove_labels: Optional[list[str]] = None,
    add_assignees: Optional[list[str]] = None,
    remove_assignees: Optional[list[str]] = None,
) -> None:
    args = ["issue", "edit", str(number)]
    if repo:
        args += ["--repo", repo]
    if title:
        args += ["--title", title]
    if body:
        args += ["--body", body]
    if add_labels:
        for l in add_labels:
            args += ["--add-label", l]
    if remove_labels:
        for l in remove_labels:
            args += ["--remove-label", l]
    if add_assignees:
        for a in add_assignees:
            args += ["--add-assignee", a]
    if remove_assignees:
        for a in remove_assignees:
            args += ["--remove-assignee", a]
    _run_gh(args)


def search_issues(query: str, repo: Optional[str] = None, limit: int = 20) -> list[Issue]:
    full_query = f"repo:{repo} {query}" if repo else query
    args = ["search", "issues", full_query, "--limit", str(limit), "--json", "number,title,state,labels,assignees,createdAt,updatedAt,url,body,comments"]
    out = _run_gh(args)
    return [Issue.from_json(item) for item in json.loads(out)]


def print_issues(issues: list[Issue]) -> None:
    if not issues:
        print("No issues found.")
        return
    for i, issue in enumerate(issues, 1):
        labels = f" [{', '.join(issue.labels)}]" if issue.labels else ""
        assignees = f" assigned to {', '.join(issue.assignees)}" if issue.assignees else ""
        print(f"{i:>3}. #{issue.number:<6} [{issue.state:<6}] {issue.title}{labels}{assignees}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="GitHub Issues Manager")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List issues")
    p_list.add_argument("--repo")
    p_list.add_argument("--state", default="open", choices=["open", "closed", "all"])
    p_list.add_argument("--label")
    p_list.add_argument("--assignee")
    p_list.add_argument("--search")
    p_list.add_argument("--limit", type=int, default=20)

    p_view = sub.add_parser("view", help="View an issue")
    p_view.add_argument("number", type=int)
    p_view.add_argument("--repo")

    p_create = sub.add_parser("create", help="Create an issue")
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--body", default="")
    p_create.add_argument("--repo")
    p_create.add_argument("--label", action="append")
    p_create.add_argument("--assignee", action="append")

    p_close = sub.add_parser("close", help="Close an issue")
    p_close.add_argument("number", type=int)
    p_close.add_argument("--repo")
    p_close.add_argument("--reason", default="completed", choices=["completed", "not_planned"])

    p_reopen = sub.add_parser("reopen", help="Reopen an issue")
    p_reopen.add_argument("number", type=int)
    p_reopen.add_argument("--repo")

    p_comment = sub.add_parser("comment", help="Comment on an issue")
    p_comment.add_argument("number", type=int)
    p_comment.add_argument("--body", required=True)
    p_comment.add_argument("--repo")

    p_edit = sub.add_parser("edit", help="Edit an issue")
    p_edit.add_argument("number", type=int)
    p_edit.add_argument("--repo")
    p_edit.add_argument("--title")
    p_edit.add_argument("--body")
    p_edit.add_argument("--add-label", action="append")
    p_edit.add_argument("--remove-label", action="append")
    p_edit.add_argument("--add-assignee", action="append")
    p_edit.add_argument("--remove-assignee", action="append")

    p_search = sub.add_parser("search", help="Search issues")
    p_search.add_argument("query")
    p_search.add_argument("--repo")
    p_search.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()

    repo = args.repo if hasattr(args, "repo") and args.repo else None

    if args.command == "list":
        issues = list_issues(repo, args.state, args.label, args.assignee, args.search, args.limit)
        print_issues(issues)
    elif args.command == "view":
        issue = view_issue(args.number, repo)
        print(f"#{issue.number} [{issue.state}] {issue.title}")
        if issue.labels:
            print(f"Labels: {', '.join(issue.labels)}")
        if issue.assignees:
            print(f"Assignees: {', '.join(issue.assignees)}")
        print(f"URL: {issue.url}")
        print(f"\n{issue.body}")
    elif args.command == "create":
        issue = create_issue(args.title, args.body, repo, args.label, args.assignee)
        print(f"Created #{issue.number}: {issue.title}")
    elif args.command == "close":
        close_issue(args.number, repo, args.reason)
        print(f"Closed #{args.number}")
    elif args.command == "reopen":
        reopen_issue(args.number, repo)
        print(f"Reopened #{args.number}")
    elif args.command == "comment":
        add_comment(args.number, args.body, repo)
        print(f"Commented on #{args.number}")
    elif args.command == "edit":
        edit_issue(args.number, repo, args.title, args.body, args.add_label, args.remove_label, args.add_assignee, args.remove_assignee)
        print(f"Edited #{args.number}")
    elif args.command == "search":
        issues = search_issues(args.query, repo, args.limit)
        print_issues(issues)
