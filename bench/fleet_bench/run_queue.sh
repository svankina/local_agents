#!/usr/bin/env bash
# Sequential model sweep: swap llama-server per model, run the E2 suite per arm,
# rebuild the capability matrix after each model. One server at a time, reused
# across that model's arms.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
CACHE="$HOME/.cache/llama.cpp"
PIDFILE=/tmp/fleetbench-queue-server.pid

stop_server() {
  if [ -f "$PIDFILE" ]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null
    sleep 2
    rm -f "$PIDFILE"
  fi
}

start_server() { # args: extra flags after common
  stop_server
  nohup ~/.local/bin/llama-server-cuda \
    --host 127.0.0.1 --port 8089 -ngl 99 --jinja -fa on "$@" \
    > "/tmp/queue-server-current.log" 2>&1 &
  echo $! > "$PIDFILE"
  for i in $(seq 1 120); do
    curl -sf -o /dev/null http://127.0.0.1:8089/health && return 0
    kill -0 "$(cat "$PIDFILE")" 2>/dev/null || { echo "SERVER DIED:"; tail -5 /tmp/queue-server-current.log; return 1; }
    sleep 3
  done
  echo "SERVER TIMEOUT"; return 1
}

suite() { # args: label [--nothink]
  local label="$1"; shift
  echo "=== suite $label $(date +%H:%M:%S)"
  timeout 1500 python3 bench/fleet_bench/run_experiments.py e2 \
    --label "$label" --base http://127.0.0.1:8089/v1 --model queue \
    --concurrency 4 --seeds 3 "$@" 2>&1 | tail -3
}

# C13 Qwopus 27B MTP — think + nothink
if start_server -m "$CACHE/Qwopus3.6-27B-v2-MTP-Q4_K_M.gguf" \
    --spec-type draft-mtp --spec-draft-n-max 2 --no-spec-draft-backend-sampling \
    -c 32768 --parallel 4 --temp 0.2; then
  suite C13-qwopus27b --nothink
  suite C13-qwopus27b-think
fi

# C7 Qwen3.6-27B Q3 — think + nothink
if start_server -m "$CACHE/Qwen3.6-27B-Q3_K_M.gguf" -c 32768 --parallel 4 --temp 0.2; then
  suite C7-qwen27b-q3 --nothink
  suite C7-qwen27b-q3-think
fi

# C8 Nex-N2-mini Q3 — think + nothink
if start_server -m "$CACHE/nex-agi_Nex-N2-mini-Q3_K_M.gguf" -c 32768 --parallel 4 --temp 0.2; then
  suite C8-nex-mini --nothink
  suite C8-nex-mini-think
fi

# C6 gemma-26B cmoe + MTP draft — nothink only (gemma: reasoning harmful)
if start_server -m "$CACHE/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf" -cmoe \
    -md "$CACHE/mtp-gemma-4-26B-A4B-it.gguf" --spec-type draft-mtp --spec-draft-n-max 2 \
    --spec-draft-ngl 99 --no-spec-draft-backend-sampling \
    -c 65536 --cache-type-k q8_0 --cache-type-v q8_0 --parallel 4 --temp 0.2 --reasoning-budget 0; then
  suite C6-gemma26b-cmoe-mtp-nothink
fi

stop_server
python3 bench/fleet_bench/capability_matrix.py
echo "QUEUE_LLAMA_DONE $(date +%H:%M:%S)"
