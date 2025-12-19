# CodeRabbit MCP Server

MCP (Model Context Protocol) server that enables Claude Code to interact with CodeRabbit reviews on GitHub PRs.

## Features

- **list_open_prs**: List all open pull requests
- **get_coderabbit_reviews**: Get CodeRabbit reviews for a specific PR
- **get_pending_fixes**: Extract actionable fix suggestions from CodeRabbit comments
- **apply_fix**: Apply a code fix to a file
- **run_linters**: Run code linters (ruff, black, prettier, eslint)
- **dismiss_review**: Dismiss a CodeRabbit review
- **get_pr_status**: Get PR status including mergeable state

## Setup

1. Set your GitHub token as an environment variable:
   ```bash
   export GITHUB_TOKEN=your-github-token-here
   ```

2. The server is configured in `.mcp.json` at the project root.

## Usage with Claude Code

Once configured, you can ask Claude Code things like:

- "List open PRs with CodeRabbit reviews"
- "Get pending fixes for PR #27"
- "Apply all CodeRabbit fixes for PR #28"
- "Run linters and fix issues"
- "Dismiss CodeRabbit reviews for PR #27"

## Example Workflow

```
You: "Check PR #28 for CodeRabbit suggestions and apply them"

Claude Code will:
1. Call get_coderabbit_reviews(28) to see review status
2. Call get_pending_fixes(28) to extract actionable fixes
3. Call apply_fix() for each fix
4. Call run_linters() to fix any remaining issues
5. Optionally call dismiss_review() if all fixes are applied
```

## Running Standalone

```bash
cd D:/AI
python -m mcp_servers.coderabbit.main
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| GITHUB_TOKEN | GitHub PAT with repo scope | Required |
| GITHUB_REPO | Repository (owner/repo) | blur702/AI |
| PROJECT_ROOT | Project root directory | D:/AI |
| LOG_LEVEL | Logging level | INFO |
