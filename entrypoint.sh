#!/bin/sh
set -e

OUTPUT_FILE="/tmp/ambient-session-output.json"

CMD="python /app/create_session.py"
CMD="$CMD --api-url \"$INPUT_API_URL\""
CMD="$CMD --api-token \"$INPUT_API_TOKEN\""
CMD="$CMD --project \"$INPUT_PROJECT\""
CMD="$CMD --prompt \"$INPUT_PROMPT\""
CMD="$CMD --timeout \"${INPUT_TIMEOUT:-30}\""
CMD="$CMD --poll-interval \"${INPUT_POLL_INTERVAL:-15}\""
CMD="$CMD --output-file \"$OUTPUT_FILE\""

if [ -n "$INPUT_DISPLAY_NAME" ]; then
  CMD="$CMD --display-name \"$INPUT_DISPLAY_NAME\""
fi

if [ -n "$INPUT_REPOS" ]; then
  CMD="$CMD --repos '$INPUT_REPOS'"
fi

if [ -n "$INPUT_LABELS" ]; then
  CMD="$CMD --labels '$INPUT_LABELS'"
fi

if [ -n "$INPUT_ENVIRONMENT_VARIABLES" ]; then
  CMD="$CMD --env-vars '$INPUT_ENVIRONMENT_VARIABLES'"
fi

if [ -n "$INPUT_MODEL" ]; then
  CMD="$CMD --model \"$INPUT_MODEL\""
fi

if [ "$INPUT_WAIT" = "true" ]; then
  CMD="$CMD --wait"
fi

if [ "$INPUT_NO_VERIFY_SSL" = "true" ]; then
  CMD="$CMD --no-verify-ssl"
fi

eval $CMD
EXIT_CODE=$?

if [ -f "$OUTPUT_FILE" ]; then
  SESSION_NAME=$(python -c "import json; d=json.load(open('$OUTPUT_FILE')); print(d.get('session_name', ''))")
  SESSION_UID=$(python -c "import json; d=json.load(open('$OUTPUT_FILE')); print(d.get('session_uid', ''))")
  SESSION_PHASE=$(python -c "import json; d=json.load(open('$OUTPUT_FILE')); print(d.get('session_phase', ''))")
  SESSION_RESULT=$(python -c "import json; d=json.load(open('$OUTPUT_FILE')); print(d.get('session_result', ''))")

  echo "session-name=$SESSION_NAME" >> "$GITHUB_OUTPUT"
  echo "session-uid=$SESSION_UID" >> "$GITHUB_OUTPUT"
  echo "session-phase=$SESSION_PHASE" >> "$GITHUB_OUTPUT"

  {
    echo "session-result<<GHEOF"
    echo "$SESSION_RESULT"
    echo "GHEOF"
  } >> "$GITHUB_OUTPUT"
else
  echo "session-name=" >> "$GITHUB_OUTPUT"
  echo "session-uid=" >> "$GITHUB_OUTPUT"
  echo "session-phase=CreateFailed" >> "$GITHUB_OUTPUT"
  echo "session-result=" >> "$GITHUB_OUTPUT"
fi

exit $EXIT_CODE
