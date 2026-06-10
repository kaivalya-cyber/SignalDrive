# GitHub Issues Manager

An AI agent that manages GitHub issues using any LLM provider — OpenAI, Anthropic Claude, NVIDIA NIM, OpenRouter, Together, Groq, DeepSeek, and more.

## Quick Start

```bash
# 1. Install
pip install -e .

# 2. Set your API key and provider
cp .env.example .env
# Edit .env — set PROVIDER and your API key

# 3. Authenticate GitHub CLI
gh auth login

# 4. Run
issues-manager "Show all open issues labeled bug"
```

## Usage

### AI mode — natural language

```bash
issues-manager "List my open issues"
issues-manager "Create an issue titled 'Fix login bug' with label 'bug'"
issues-manager "Close issue #42 as completed"
issues-manager "Search for issues about performance"
```

### Interactive mode

```bash
issues-manager
>> List open issues assigned to me
>> Create a new issue titled "Add dark mode" with labels "enhancement"
>> exit
```

## Providers

| Provider      | Env variable        | Default model                                      |
| ------------- | ------------------- | -------------------------------------------------- |
| openai        | `OPENAI_API_KEY`    | `gpt-4o`                                           |
| anthropic     | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514`                         |
| nvidia        | `NVIDIA_API_KEY`    | `nvidia/llama-3.1-nemotron-70b-instruct`           |
| openrouter    | `OPENROUTER_API_KEY`| `anthropic/claude-sonnet-4-6`                      |
| together      | `TOGETHER_API_KEY`  | `meta-llama/Llama-3.3-70B-Instruct-Turbo`         |
| groq          | `GROQ_API_KEY`      | `llama-3.3-70b-versatile`                          |
| deepseek      | `DEEPSEEK_API_KEY`  | `deepseek-chat`                                    |

Override the model: `GH_MANAGER_MODEL=gpt-4o-mini`

## How it works

1. You give a natural language instruction
2. The LLM decides which tools to call (list, create, close, etc.)
3. Tools execute via the `gh` CLI
4. Results go back to the LLM for a final response

## Tools

| Category     | Tools |
|-------------|-------|
| Issues      | `list_issues`, `view_issue`, `create_issue`, `close_issue`, `reopen_issue`, `comment_on_issue`, `edit_issue`, `search_issues`, `add_issue_assignees`, `lock_issue`, `unlock_issue` |
| Pull Requests | `list_pull_requests`, `view_pull_request`, `create_pull_request`, `merge_pull_request`, `add_pr_review` |
| Labels      | `list_labels`, `create_label` |
| Milestones  | `list_milestones` |
| Releases    | `list_releases`, `create_release` |
| Workflows   | `list_workflows`, `list_workflow_runs`, `trigger_workflow` |
| Notifications | `list_notifications`, `mark_notifications_read` |
| PR Checks   | `list_pr_checks`, `request_pr_reviewers` |
| Comments    | `list_issue_comments`, `get_comment`, `update_comment`, `delete_comment` |
| Search      | `search_repos`, `search_code`, `search_users` |
| Gists       | `list_gists`, `create_gist` |
| Repository  | `get_repo_info`, `list_branches`, `delete_branch`, `whoami`, `list_contributors`, `rate_limit`, `fork_repo`, `star_repo`, `unstar_repo`, `create_repo`, `compare_refs` |
| Milestones  | `list_milestones`, `create_milestone`, `set_issue_milestone` |
| Security      | `list_dependabot_alerts` |
| Deployments   | `list_deployments` |
| Topics        | `list_repo_topics`, `add_repo_topic` |
| Labels        | `list_labels`, `create_label`, `update_label`, `delete_label` |
| Collaborators | `list_collaborators`, `add_collaborator` |
| Workflow Mgmt | `cancel_workflow_run`, `rerun_workflow` |
| Repo Mgmt     | `archive_repo`, `unarchive_repo`, `change_repo_visibility`, `list_repo_languages`, `get_repo_license` |
| Reactions     | `add_reaction` |
| Pins            | `pin_issue`, `unpin_issue` |
| PR Review       | `list_pr_review_comments`, `get_pr_diff` |
| Git History     | `list_commits`, `list_tags` |
| Auto-merge      | `enable_auto_merge`, `disable_auto_merge` |
| Commit Status   | `create_commit_status` |
| Issue Events    | `list_issue_events` |
| Environments    | `list_environments` |
| Repo Transfer   | `transfer_repo` |
| Other           | `transfer_issue`, `set_issue_priority`, `set_issue_milestone`, `remove_issue_labels`, `update_pr_branch`, `remove_collaborator` |

## Architecture

```
issues-manager
├── issues_manager/
│   ├── cli.py           # CLI entry point
│   ├── agent.py         # Agent loop: LLM ↔ tools
│   ├── providers/       # LLM providers (OpenAI, Anthropic, etc.)
│   │   ├── base.py
│   │   ├── openai_compat.py
│   │   └── anthropic_provider.py
│   └── tools/           # GitHub issue/PR tools
│       ├── github.py    # All operations via gh CLI
│       └── __init__.py  # Tool registry
└── pyproject.toml        # Package config
```

## Requirements

- Python ≥ 3.11
- [GitHub CLI (`gh`)](https://cli.github.com/) authenticated with repo scope
