#!/usr/bin/env bash
# Run arm H: Claude supervisor calls plus an 8-slot Haiku CLI fan-out dispatcher.
# Fable-workers control arm: identical harness to arm H, model overridden.
export FANOUT_CLAUDE_MODEL="claude-fable-5"
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ARM="${ARM:-H}"
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
    "arm": "H",
    "run_dir": run_dir,
    "corpus": "scrapy",
    "local_server": None,
    "fanout": {
        "items_total": 32,
        "concurrency": 8,
        "worker": "claude-cli",
        "worker_model": "claude-haiku-4-5-20251001",
    },
}
pathlib.Path(run_dir, "run.json").write_text(json.dumps(body, indent=2), encoding="utf-8")
PY

cat > "$RUN_DIR/prompts/supervisor-decomposition.txt" <<EOF
You are the Fable 5 supervisor for arm H of the pinned showcase fan-out benchmark.
Read $ITEMS_DIR/items.lock.json, confirm there are exactly 32 Scrapy docstring
backfill items at the pinned SHA, note any anomalies, and confirm the Haiku
dispatcher command the runner will execute next. Do not inspect worker
transcripts or do per-item docstring work.
EOF

claude -p "$(cat "$RUN_DIR/prompts/supervisor-decomposition.txt")" \
  --output-format stream-json --verbose \
  --mcp-config '{"mcpServers":{}}' --strict-mcp-config > "$RUN_DIR/logs/supervisor-decomposition.jsonl" 2>&1

python3 scripts/fanout/dispatch.py \
  --run-dir "$RUN_DIR" \
  --items-dir "$ITEMS_DIR" \
  --corpus "$CORPUS" \
  --worker-script scripts/fanout/haiku-worker \
  --concurrency 8

python3 scripts/compute_run_metrics.py "$RUN_DIR"

cat > "$RUN_DIR/prompts/supervisor-synthesis.txt" <<EOF
You are the Fable 5 supervisor for arm H of the pinned showcase fan-out benchmark.
Read $RUN_DIR/scorecard.json and $RUN_DIR/metrics.json only, then write
$RUN_DIR/summary.md with pass rate, retries, wall clock, token totals including
worker cloud cost and supervisor cloud cost, and notable instrumentation caveats.
Do not inspect individual worker transcripts.
EOF

claude -p "$(cat "$RUN_DIR/prompts/supervisor-synthesis.txt")" \
  --output-format stream-json --verbose \
  --mcp-config '{"mcpServers":{}}' --strict-mcp-config > "$RUN_DIR/logs/supervisor-synthesis.jsonl" 2>&1

python3 - "$RUN_DIR" <<'PY'
import json, pathlib, sys
run_dir = pathlib.Path(sys.argv[1])
scorecard_path = run_dir / "scorecard.json"
scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
total = 0.0
seen = False
for path in sorted((run_dir / "logs").glob("supervisor-*.jsonl")):
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        cost = row.get("total_cost_usd")
        if row.get("type") == "result" and isinstance(cost, (int, float)):
            total += float(cost)
            seen = True
tokens = scorecard.setdefault("token_totals", {})
if seen:
    tokens["supervisor_cloud_cost_usd"] = total
    tokens["cloud_cost_usd"] = float(tokens.get("worker_cloud_cost_usd") or 0.0) + total
scorecard_path.write_text(json.dumps(scorecard, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

date -Is > "$RUN_DIR/ended_at.txt"
echo "$RUN_DIR"
