#!/usr/bin/env bash
# Insert and verify one showcase fan-out item attempt.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ITEM_ID="${1:?usage: run_item_check.sh item-NN [attempt]}"
ATTEMPT="${2:-}"

RUN_DIR="${RUN_DIR:?RUN_DIR must point at the fanout run directory}"
CORPUS="${CORPUS:?CORPUS must point at the pinned Scrapy checkout}"
ITEM="$RUN_DIR/items/$ITEM_ID.json"

if [ -z "$ATTEMPT" ]; then
  ATTEMPT_DIR="$(find "$RUN_DIR/workers" -maxdepth 1 -type d -name "$ITEM_ID-attempt-*" | sort | tail -n 1)"
else
  ATTEMPT_DIR="$RUN_DIR/workers/$ITEM_ID-attempt-$ATTEMPT"
fi

if [ -z "${ATTEMPT_DIR:-}" ] || [ ! -d "$ATTEMPT_DIR" ]; then
  echo "attempt directory not found for $ITEM_ID" >&2
  exit 2
fi

RESPONSE="$ATTEMPT_DIR/response.json"
MODIFIED="$ATTEMPT_DIR/modified.py"
VERIFY="$ATTEMPT_DIR/verify.json"

set +e
python3 "$ROOT/scripts/fanout/insert_docstrings.py" \
  --corpus "$CORPUS" \
  --item "$ITEM" \
  --response "$RESPONSE" \
  --out "$MODIFIED" >"$ATTEMPT_DIR/insert.stdout" 2>"$ATTEMPT_DIR/insert.stderr"
INSERT_RC=$?
set -e

python3 "$ROOT/scripts/fanout/verify_item.py" \
  --corpus "$CORPUS" \
  --item "$ITEM" \
  --modified "$MODIFIED" \
  --out "$VERIFY" \
  --insertion-rc "$INSERT_RC"
