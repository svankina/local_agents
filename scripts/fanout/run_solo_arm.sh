#!/usr/bin/env bash
# Run arm S: one Claude Code solo session processes all 32 items.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ARM="${ARM:-S}"
REP="${REP:-01}"
RUN_ID="${RUN_ID:-$(date +%F)-${ARM}-${REP}}"
RUN_DIR="${RUN_DIR:-$ROOT/results/experiments/showcase-fanout/$RUN_ID}"
CORPUS="${CORPUS:-$ROOT/.worktrees/showcase/$RUN_ID/scrapy}"
ITEMS_DIR="$RUN_DIR/items"
TELEMETRY_PID=""

cleanup() {
  if [ -n "${TELEMETRY_PID:-}" ] && kill -0 "$TELEMETRY_PID" 2>/dev/null; then
    kill "$TELEMETRY_PID" 2>/dev/null || true
    wait "$TELEMETRY_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

mkdir -p "$RUN_DIR"/{items,workers,logs,prompts}
mkdir -p "$(dirname "$CORPUS")"

if [ ! -d "$CORPUS/.git" ]; then
  git clone https://github.com/scrapy/scrapy.git "$CORPUS"
fi
git -C "$CORPUS" fetch origin a8ffdcf8517a8973391a14635234b6993b15a86a
git -C "$CORPUS" checkout --detach a8ffdcf8517a8973391a14635234b6993b15a86a
git -C "$CORPUS" rev-parse HEAD > "$RUN_DIR/corpus_head.txt"

python3 scripts/fanout/make_items.py --corpus "$CORPUS" --count 32 --out "$ITEMS_DIR"

python3 scripts/telemetry_sampler.py --out "$RUN_DIR/telemetry.csv" &
TELEMETRY_PID=$!
echo "$TELEMETRY_PID" > "$RUN_DIR/.telemetry.pid"
date -Is > "$RUN_DIR/started_at.txt"

python3 - "$RUN_DIR" "$RUN_ID" <<'PY'
import json, pathlib, sys
run_dir, run_id = sys.argv[1:]
body = {
    "schema": "showcase-fanout.run.v1",
    "run_id": run_id,
    "arm": "S",
    "run_dir": run_dir,
    "local_server": None,
    "fanout": {"items_total": 32, "concurrency": None},
}
pathlib.Path(run_dir, "run.json").write_text(json.dumps(body, indent=2), encoding="utf-8")
PY

cat > "$RUN_DIR/prompts/solo.txt" <<EOF
Process items item-01 through item-32 from $ITEMS_DIR/items.lock.json. For each item,
read the file from $CORPUS, produce the docstrings JSON in the contract format, save it
as $RUN_DIR/workers/item-NN-attempt-K/response.json, then run insert + verify via
RUN_DIR=$RUN_DIR CORPUS=$CORPUS scripts/fanout/run_item_check.sh item-NN K. One retry per
item on verify failure, using the verifier's failure reason. Do not use subagents. Do not
call any local model server. Stop when $RUN_DIR/scorecard.json is complete.

The scorecard must use schema showcase-fanout.scorecard.v1 and include items_total,
passed, failed, score, retries, token_totals if available, and per-item status,
attempts_used, attempts, and failure_reason fields matching the dispatcher scorecard
shape. Do not edit the pinned corpus checkout; only write under $RUN_DIR.
EOF

export RUN_DIR
export CORPUS
claude -p "$(cat "$RUN_DIR/prompts/solo.txt")" \
  --output-format stream-json --verbose | tee "$RUN_DIR/logs/claude-stream.jsonl"

python3 scripts/compute_run_metrics.py "$RUN_DIR"
date -Is > "$RUN_DIR/ended_at.txt"
echo "$RUN_DIR"
