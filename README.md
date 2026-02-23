# Ambient Feedback Loop Action

A GitHub Action that queries [Langfuse](https://langfuse.com) for agent corrections logged during [Ambient Code Platform](https://github.com/ambient-code) sessions and automatically creates improvement sessions to fix recurring issues.

## How It Works

1. **Queries Langfuse** for `session-correction` scores logged by the platform's corrections MCP tool
2. **Groups corrections** by target (workflow or repo) — repo corrections across different branches are merged into a single group
3. **Creates improvement sessions** on the Ambient Code Platform that analyze the corrections and propose targeted changes to workflow instructions, CLAUDE.md, and pattern files

Corrections can come from two sources:
- **Human** — a user redirected the agent during a session
- **Rubric** — a rubric evaluation flagged weak dimensions automatically

## Usage

### Basic (weekly schedule)

```yaml
name: Feedback Loop

on:
  schedule:
    - cron: '0 9 * * 1'  # Weekly on Monday at 9am UTC
  workflow_dispatch:

jobs:
  feedback-loop:
    runs-on: ubuntu-latest
    steps:
      - name: Run feedback loop
        uses: ambient-code/feedback-loop-action@v1
        with:
          langfuse-host: ${{ secrets.LANGFUSE_HOST }}
          langfuse-public-key: ${{ secrets.LANGFUSE_PUBLIC_KEY }}
          langfuse-secret-key: ${{ secrets.LANGFUSE_SECRET_KEY }}
          api-url: ${{ secrets.AMBIENT_API_URL }}
          api-token: ${{ secrets.AMBIENT_BOT_TOKEN }}
          project: ${{ secrets.AMBIENT_PROJECT }}
```

### With outputs

```yaml
- name: Run feedback loop
  id: feedback
  uses: ambient-code/feedback-loop-action@v1
  with:
    langfuse-host: ${{ secrets.LANGFUSE_HOST }}
    langfuse-public-key: ${{ secrets.LANGFUSE_PUBLIC_KEY }}
    langfuse-secret-key: ${{ secrets.LANGFUSE_SECRET_KEY }}
    api-url: ${{ secrets.AMBIENT_API_URL }}
    api-token: ${{ secrets.AMBIENT_BOT_TOKEN }}
    project: ${{ secrets.AMBIENT_PROJECT }}

- name: Report results
  run: |
    echo "Corrections found: ${{ steps.feedback.outputs.corrections-found }}"
    echo "Sessions created: ${{ steps.feedback.outputs.sessions-created }}"
```

### Dry run (no sessions created)

```yaml
- uses: ambient-code/feedback-loop-action@v1
  with:
    langfuse-host: ${{ secrets.LANGFUSE_HOST }}
    langfuse-public-key: ${{ secrets.LANGFUSE_PUBLIC_KEY }}
    langfuse-secret-key: ${{ secrets.LANGFUSE_SECRET_KEY }}
    api-url: ${{ secrets.AMBIENT_API_URL }}
    api-token: ${{ secrets.AMBIENT_BOT_TOKEN }}
    project: ${{ secrets.AMBIENT_PROJECT }}
    dry-run: 'true'
```

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `langfuse-host` | Yes | — | Langfuse instance URL |
| `langfuse-public-key` | Yes | — | Langfuse public key |
| `langfuse-secret-key` | Yes | — | Langfuse secret key |
| `api-url` | Yes | — | Ambient Code Platform backend API URL |
| `api-token` | Yes | — | Bot user bearer token for the Ambient API |
| `project` | Yes | — | Ambient project/namespace name |
| `since-days` | No | `7` | Number of days to look back for corrections |
| `min-corrections` | No | `2` | Minimum corrections per group to trigger a session |
| `dry-run` | No | `false` | Query and report without creating sessions |
| `no-verify-ssl` | No | `false` | Disable SSL certificate verification |

## Outputs

| Output | Description |
|--------|-------------|
| `corrections-found` | Total number of corrections fetched from Langfuse |
| `sessions-created` | Number of improvement sessions created |
| `groups-json` | JSON array of grouped correction summaries |

### `groups-json` format

```json
[
  {
    "target_type": "workflow",
    "target_repo_url": "https://github.com/org/workflows",
    "target_path": "workflows/bug-fix",
    "total_count": 5,
    "correction_type_counts": { "style": 3, "incomplete": 2 },
    "source_counts": { "human": 3, "rubric": 2 }
  }
]
```

## How Corrections Are Grouped

- **Workflow targets** are grouped by `(repo_url, branch, path)` — branch matters because different branches can have different workflow instructions
- **Repo targets** are grouped by `(repo_url)` only — branch is ignored because sessions work on ephemeral feature branches while corrections apply to the repo as a whole

## License

Apache 2.0 — see [LICENSE](LICENSE).
