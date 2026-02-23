#!/bin/sh
set -e

OUTPUT_FILE="/tmp/feedback-loop-output.json"

CMD="python /app/query_corrections.py"
CMD="$CMD --langfuse-host \"$INPUT_LANGFUSE_HOST\""
CMD="$CMD --langfuse-public-key \"$INPUT_LANGFUSE_PUBLIC_KEY\""
CMD="$CMD --langfuse-secret-key \"$INPUT_LANGFUSE_SECRET_KEY\""
CMD="$CMD --api-url \"$INPUT_API_URL\""
CMD="$CMD --api-token \"$INPUT_API_TOKEN\""
CMD="$CMD --project \"$INPUT_PROJECT\""
CMD="$CMD --since-days \"${INPUT_SINCE_DAYS:-7}\""
CMD="$CMD --min-corrections \"${INPUT_MIN_CORRECTIONS:-2}\""
CMD="$CMD --output-file \"$OUTPUT_FILE\""

if [ "$INPUT_DRY_RUN" = "true" ]; then
  CMD="$CMD --dry-run"
fi

if [ "$INPUT_NO_VERIFY_SSL" = "true" ]; then
  CMD="$CMD --no-verify-ssl"
fi

eval $CMD

if [ -f "$OUTPUT_FILE" ]; then
  CORRECTIONS=$(python -c "import json; d=json.load(open('$OUTPUT_FILE')); print(d.get('corrections_found', 0))")
  SESSIONS=$(python -c "import json; d=json.load(open('$OUTPUT_FILE')); print(d.get('sessions_created', 0))")
  GROUPS=$(python -c "import json; d=json.load(open('$OUTPUT_FILE')); print(json.dumps(d.get('groups', [])))")

  echo "corrections-found=$CORRECTIONS" >> "$GITHUB_OUTPUT"
  echo "sessions-created=$SESSIONS" >> "$GITHUB_OUTPUT"

  {
    echo "groups-json<<GHEOF"
    echo "$GROUPS"
    echo "GHEOF"
  } >> "$GITHUB_OUTPUT"
else
  echo "corrections-found=0" >> "$GITHUB_OUTPUT"
  echo "sessions-created=0" >> "$GITHUB_OUTPUT"
  echo "groups-json=[]" >> "$GITHUB_OUTPUT"
fi
