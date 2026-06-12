#!/usr/bin/env bash
# Run arm F: two Claude supervisor calls plus the local 8-stream fan-out dispatcher.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

ARM="${ARM:-F}"
REP="${REP:-01}"
RUN_ID="${RUN_ID:-$(date +%F)-${ARM}-${REP}}"
RUN_DIR="${RUN_DIR:-$ROOT/results/experiments/showcase-fanout/$RUN_ID}"
CORPUS="${CORPUS:-$ROOT/.worktrees/showcase/$RUN_ID/scrapy}"
ITEMS_DIR="$RUN_DIR/items"
MODEL="${MODEL:-C18-qwen3-30b-vllm}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8091/v1}"
PORT="${PORT:-8091}"
IMAGE="${VLLM_IMAGE:-vllm/vllm-openai:v0.22.1}"
CONTAINER="${VLLM_CONTAINER:-fanout-$RUN_ID}"
HF_CACHE="${HF_CACHE:-$HOME/.cache/huggingface}"
STARTED_CONTAINER=0
LOG_PID=""
TELEMETRY_PID=""

cleanup() {
  if [ -n "${TELEMETRY_PID:-}" ] && kill -0 "$TELEMETRY_PID" 2>/dev/null; then
    kill "$TELEMETRY_PID" 2>/dev/null || true
    wait "$TELEMETRY_PID" 2>/dev/null || true
  fi
  if [ "$STARTED_CONTAINER" -eq 1 ]; then
    docker stop "$CONTAINER" >/dev/null 2>&1 || true
  fi
  if [ -n "${LOG_PID:-}" ]; then
    wait "$LOG_PID" 2>/dev/null || true
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

if docker ps -a --format '{{.Names}}' | grep -Fxq "$CONTAINER"; then
  echo "FATAL: container $CONTAINER already exists; not stopping containers this runner did not start" >&2
  exit 2
fi

FLAGS="$(python3 - <<'PY'
import json
c=json.load(open("bench/configs.json"))
print(c["C18-qwen3-30b-vllm"])
PY
)"
SERVED_MODEL="$(python3 - <<'PY'
import json, shlex
c=json.load(open("bench/configs.json"))
a=shlex.split(c["C18-qwen3-30b-vllm"])
print(a[a.index("--served-model-name")+1])
PY
)"

docker run -d --rm --gpus all --ipc=host \
  -v "$HF_CACHE:/root/.cache/huggingface" \
  -p "$PORT:8000" \
  --name "$CONTAINER" \
  "$IMAGE" $FLAGS > "$RUN_DIR/logs/vllm.container.id"
STARTED_CONTAINER=1
docker logs -f "$CONTAINER" > "$RUN_DIR/logs/vllm.log" 2>&1 &
LOG_PID=$!

python3 - <<'PY'
import sys
sys.path.insert(0, "bench")
from common import wait_healthy
wait_healthy(base="http://127.0.0.1:8091", tries=360)
PY

python3 - "$BASE_URL" "$SERVED_MODEL" "$RUN_DIR" <<'PY'
import json, pathlib, sys, urllib.request
base, model, run_dir = sys.argv[1:]
payload = {"model": model, "messages": [{"role": "user", "content": "Say hello."}], "temperature": 0, "max_tokens": 128}
req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=120) as r:
    body = json.loads(r.read())
pathlib.Path(run_dir, "logs", "warmup.json").write_text(json.dumps(body, indent=2), encoding="utf-8")
PY

python3 scripts/telemetry_sampler.py --out "$RUN_DIR/telemetry.csv" &
TELEMETRY_PID=$!
echo "$TELEMETRY_PID" > "$RUN_DIR/.telemetry.pid"
date -Is > "$RUN_DIR/started_at.txt"

python3 - "$RUN_DIR" "$RUN_ID" "$IMAGE" "$SERVED_MODEL" "$FLAGS" <<'PY'
import json, pathlib, sys
run_dir, run_id, image, served_model, flags = sys.argv[1:]
body = {
    "schema": "showcase-fanout.run.v1",
    "run_id": run_id,
    "arm": "F",
    "run_dir": run_dir,
    "corpus": "scrapy",
    "local_server": {
        "kind": "vllm-openai",
        "image": image,
        "model_revision": "9b534e4318b7ebc3c961a839f13eb18b1833f441",
        "served_model": served_model,
        "flags": flags,
        "max_num_seqs": 8,
        "base_url": "http://127.0.0.1:8091/v1",
    },
    "fanout": {"items_total": 32, "concurrency": 8},
}
pathlib.Path(run_dir, "run.json").write_text(json.dumps(body, indent=2), encoding="utf-8")
PY

cat > "$RUN_DIR/prompts/supervisor-decomposition.txt" <<EOF
You are the Fable 5 supervisor for the pinned showcase fan-out benchmark.
Read $ITEMS_DIR/items.lock.json, confirm there are exactly 32 Scrapy docstring
backfill items at the pinned SHA, note any anomalies, and confirm the local
dispatcher command the runner will execute next. Do not inspect worker
transcripts or do per-item docstring work.
EOF

claude -p "$(cat "$RUN_DIR/prompts/supervisor-decomposition.txt")" \
  --output-format stream-json --verbose | tee "$RUN_DIR/logs/supervisor-decomposition.jsonl"

python3 scripts/fanout/dispatch.py \
  --run-dir "$RUN_DIR" \
  --items-dir "$ITEMS_DIR" \
  --corpus "$CORPUS" \
  --base-url "$BASE_URL" \
  --model "$SERVED_MODEL" \
  --concurrency 8

python3 scripts/compute_run_metrics.py "$RUN_DIR"

cat > "$RUN_DIR/prompts/supervisor-synthesis.txt" <<EOF
You are the Fable 5 supervisor for the pinned showcase fan-out benchmark.
Read $RUN_DIR/scorecard.json and $RUN_DIR/metrics.json only, then write
$RUN_DIR/summary.md with pass rate, retries, wall clock, token totals, and
notable instrumentation caveats. Do not inspect individual worker transcripts.
EOF

claude -p "$(cat "$RUN_DIR/prompts/supervisor-synthesis.txt")" \
  --output-format stream-json --verbose | tee "$RUN_DIR/logs/supervisor-synthesis.jsonl"

date -Is > "$RUN_DIR/ended_at.txt"
echo "$RUN_DIR"
