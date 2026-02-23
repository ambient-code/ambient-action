# Ambient Action

A GitHub Action that creates sessions on the [Ambient Code Platform](https://github.com/ambient-code) from any workflow. Supports fire-and-forget and wait-for-completion modes.

## Usage

### Fire-and-forget

Create a session and continue immediately:

```yaml
- uses: ambient-code/ambient-action@v2
  with:
    api-url: ${{ secrets.AMBIENT_API_URL }}
    api-token: ${{ secrets.AMBIENT_BOT_TOKEN }}
    project: my-project
    prompt: "Refactor the auth module to use JWT tokens"
    repos: '[{"url": "https://github.com/org/app", "branch": "main", "autoPush": true}]'
```

### Wait for completion

Create a session and wait for results:

```yaml
- uses: ambient-code/ambient-action@v2
  id: session
  with:
    api-url: ${{ secrets.AMBIENT_API_URL }}
    api-token: ${{ secrets.AMBIENT_BOT_TOKEN }}
    project: my-project
    prompt: "Add unit tests for the payment service"
    repos: '[{"url": "https://github.com/org/app", "branch": "main"}]'
    wait: 'true'
    timeout: '60'

- run: |
    echo "Phase: ${{ steps.session.outputs.session-phase }}"
    echo "Result: ${{ steps.session.outputs.session-result }}"
```

### Triggered from an issue comment

```yaml
on:
  issue_comment:
    types: [created]

jobs:
  run:
    if: contains(github.event.comment.body, '/ambient')
    runs-on: ubuntu-latest
    steps:
      - uses: ambient-code/ambient-action@v2
        with:
          api-url: ${{ secrets.AMBIENT_API_URL }}
          api-token: ${{ secrets.AMBIENT_BOT_TOKEN }}
          project: my-project
          prompt: ${{ github.event.comment.body }}
          display-name: "Issue #${{ github.event.issue.number }}"
```

### As part of a feedback loop

Query Langfuse for corrections, then create improvement sessions:

```yaml
steps:
  - uses: actions/checkout@v4

  - uses: actions/setup-python@v5
    with:
      python-version: '3.11'

  - run: pip install -r scripts/feedback-loop/requirements.txt

  - name: Query corrections and create sessions
    run: |
      python scripts/feedback-loop/query_corrections.py \
        --langfuse-host "${{ secrets.LANGFUSE_HOST }}" \
        --langfuse-public-key "${{ secrets.LANGFUSE_PUBLIC_KEY }}" \
        --langfuse-secret-key "${{ secrets.LANGFUSE_SECRET_KEY }}" \
        --api-url "${{ secrets.AMBIENT_API_URL }}" \
        --api-token "${{ secrets.AMBIENT_BOT_TOKEN }}" \
        --project "${{ secrets.AMBIENT_PROJECT }}"
```

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `api-url` | Yes | - | Ambient Code Platform backend API URL |
| `api-token` | Yes | - | Bot user bearer token |
| `project` | Yes | - | Ambient project/namespace name |
| `prompt` | Yes | - | Initial prompt for the session |
| `display-name` | No | auto | Human-readable session name |
| `repos` | No | - | JSON array of repos |
| `labels` | No | - | JSON object of labels |
| `environment-variables` | No | - | JSON object of env vars for the runner |
| `timeout` | No | `30` | Session timeout in minutes |
| `model` | No | - | Model override |
| `wait` | No | `false` | Wait for session completion |
| `poll-interval` | No | `15` | Seconds between polls when waiting |
| `no-verify-ssl` | No | `false` | Disable SSL cert verification |

### `repos` format

```json
[
  {
    "url": "https://github.com/org/repo",
    "branch": "main",
    "autoPush": true
  }
]
```

## Outputs

| Output | Description |
|--------|-------------|
| `session-name` | Created session name (always set) |
| `session-uid` | Created session UID (always set) |
| `session-phase` | Final phase - only when `wait: true` |
| `session-result` | Result text - only when `wait: true` |

### Session phases

- `Completed` - session finished successfully
- `Error` - session encountered an error
- `Timeout` - session exceeded the timeout
- `Stopped` - session was manually stopped
- `CreateFailed` - API call to create the session failed

## How It Works

This is a [composite action](https://docs.github.com/en/actions/sharing-automations/creating-actions/creating-a-composite-action) that runs directly on the GitHub runner (no Docker container). It installs `requests` via pip, then runs `create_session.py` which calls the Ambient backend API.

## License

Apache 2.0 - see [LICENSE](LICENSE).
