#!/usr/bin/env bash
# Arm G: live supervised fan-out with gemma-12B-qat (reasoning off) on a running
# llama-server. Two real Fable supervisor calls + the local dispatcher.
# Differs from run_fleet_arm.sh: expects the worker server ALREADY RUNNING
# (llama.cpp, port 8089) instead of starting a vLLM container.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ARM="${ARM:-G}"
REP="${REP:-01}"
RUN_ID="${RUN_ID:-$(date +%F)-${ARM}-${REP}}"
RUN_DIR="${RUN_DIR:-$ROOT/results/experiments/showcase-fanout/$RUN_ID}"
CORPUS="${CORPUS:-$ROOT/.worktrees-corpus/$RUN_ID/scrapy}"
ITEMS_DIR="$RUN_DIR/items"
MODEL="${MODEL:-C1-gemma12b-nothink}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8089/v1}"
CONCURRENCY="${CONCURRENCY:-4}"
TELEMETRY_PID=""

cleanup() {
  if [ -n "${TELEMETRY_PID:-}" ] && kill -0 "$TELEMETRY_PID" 2>/dev/null; then
    kill "$TELEMETRY_PID" 2>/dev/null || true
    wait "$TELEMETRY_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

mkdir -p "$RUN_DIR"/{items,workers,logs,prompts}

curl -sf -o /dev/null "${BASE_URL%/v1}/health" || {
  echo "FATAL: no healthy worker server at $BASE_URL" >&2; exit 2; }

if [ ! -d "$CORPUS/.git" ]; then
  mkdir -p "$(dirname "$CORPUS")"
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

python3 - "$RUN_DIR" "$RUN_ID" "$MODEL" "$BASE_URL" "$CONCURRENCY" <<'PY'
import json, pathlib, sys
run_dir, run_id, model, base_url, conc = sys.argv[1:]
body = {
    "schema": "showcase-fanout.run.v1",
    "run_id": run_id,
    "arm": "G",
    "run_dir": run_dir,
    "corpus": "scrapy",
    "local_server": {
        "kind": "llama-server-cuda",
        "model_file": "gemma-4-12B-it-qat-UD-Q4_K_XL.gguf",
        "served_model": model,
        "flags": "-ngl 99 --jinja -fa on -c 32768 --parallel 4 --temp 0.2 --reasoning-budget 0",
        "base_url": base_url,
    },
    "fanout": {"items_total": 32, "concurrency": int(conc)},
    "selection_basis": "fleet-bench capability matrix: gemma-12B-nothink 100% first-pass, only model solving all 10 pure_fn items",
}
pathlib.Path(run_dir, "run.json").write_text(json.dumps(body, indent=2), encoding="utf-8")
PY

cat > "$RUN_DIR/prompts/supervisor-decomposition.txt" <<EOF
You are the Fable 5 supervisor for the pinned showcase fan-out benchmark, arm G
(gemma-12B-qat worker, reasoning disabled, chosen from the fleet-bench capability
matrix). Read $ITEMS_DIR/items.lock.json, confirm there are exactly 32 Scrapy
docstring backfill items at the pinned SHA, note any anomalies, and confirm the
local dispatcher command the runner will execute next. Do not inspect worker
transcripts or do per-item docstring work.
EOF

claude -p "$(cat "$RUN_DIR/prompts/supervisor-decomposition.txt")" \
  --output-format stream-json --verbose \
  --mcp-config '{"mcpServers":{}}' --strict-mcp-config > "$RUN_DIR/logs/supervisor-decomposition.jsonl" 2>&1

python3 scripts/fanout/dispatch.py \
  --run-dir "$RUN_DIR" \
  --items-dir "$ITEMS_DIR" \
  --corpus "$CORPUS" \
  --base-url "$BASE_URL" \
  --model "$MODEL" \
  --concurrency "$CONCURRENCY"

python3 scripts/compute_run_metrics.py "$RUN_DIR"

cat > "$RUN_DIR/prompts/supervisor-synthesis.txt" <<EOF
You are the Fable 5 supervisor for the pinned showcase fan-out benchmark, arm G.
Read $RUN_DIR/scorecard.json and $RUN_DIR/metrics.json only, then write
$RUN_DIR/summary.md with pass rate, retries, wall clock, token totals, and
notable instrumentation caveats. Do not inspect individual worker transcripts.
EOF

claude -p "$(cat "$RUN_DIR/prompts/supervisor-synthesis.txt")" \
  --output-format stream-json --verbose \
  --mcp-config '{"mcpServers":{}}' --strict-mcp-config > "$RUN_DIR/logs/supervisor-synthesis.jsonl" 2>&1

date -Is > "$RUN_DIR/ended_at.txt"
echo "$RUN_DIR"
