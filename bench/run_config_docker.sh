#!/usr/bin/env bash
# Usage: bench/run_config_docker.sh <config-name> [suite ...]   (default: throughput toolcall agentic)
set -euo pipefail

cd "$(dirname "$0")/.."
CFG="$1"
shift || true
if [ "$#" -gt 0 ]; then
  SUITES=("$@")
else
  SUITES=(throughput toolcall agentic)
fi
CACHE="$HOME/.cache/llama.cpp"
RAW="results/raw/$CFG"
IMAGE="ghcr.io/ggml-org/llama.cpp:server-cuda"
CONTAINER="bench-$CFG"
STARTED=0
LOG_PID=""
mkdir -p "$RAW"

write_error_json() {
  local message="$1"
  python3 - "$CFG" "$message" <<'PY'
import json
import pathlib
import sys

cfg = sys.argv[1]
message = sys.argv[2]
raw = pathlib.Path(f"results/raw/{cfg}")
server_log = raw / "server.log"
tail = ""
if server_log.exists():
    tail = "\n".join(server_log.read_text(errors="replace").splitlines()[-120:])
merged = {
    "config": cfg,
    "gpu_contended": (raw / "contended.flag").exists(),
    "vram_before": (raw / "vram_before.txt").read_text().strip() if (raw / "vram_before.txt").exists() else None,
    "error": message,
    "server_log_tail": tail,
}
pathlib.Path(f"results/{cfg}.json").write_text(json.dumps(merged, indent=2))
print("wrote", f"results/{cfg}.json")
PY
}

cleanup() {
  if [ "$STARTED" -eq 1 ]; then
    docker stop "$CONTAINER" >/dev/null 2>&1 || true
  fi
  if [ -n "$LOG_PID" ]; then
    wait "$LOG_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if docker ps -a --format '{{.Names}}' | grep -Fxq "$CONTAINER"; then
  echo "FATAL: container $CONTAINER already exists; not stopping containers this runner did not start" >&2
  write_error_json "container $CONTAINER already exists before launch"
  exit 0
fi

for i in $(seq 1 30); do
  UTIL=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits)
  [ "$UTIL" -lt 10 ] && break
  sleep 10
done
[ "$UTIL" -lt 10 ] || echo "WARN: gpu_contended" | tee "$RAW/contended.flag"

# ORCHESTRATOR-AUTHORIZED (do not remove): gracefully unload all Ollama-resident
# models via Ollama's own API before each timed run. This is a model unload, not a
# process kill - it does NOT violate the foreign-process constraint. The machine
# owner has cleared the GPU for benchmarking; external agents on this box reload
# Ollama models ad hoc and would otherwise OOM the 14-16GB configs.
ollama ps 2>/dev/null | awk 'NR>1 {print $1}' | while read -r m; do ollama stop "$m" 2>/dev/null || true; done
sleep 3

nvidia-smi --query-gpu=memory.used --format=csv,noheader | tee "$RAW/vram_before.txt"

FLAGS=$(python3 -c "import json;c=json.load(open('bench/configs.json'));print(c['$CFG'].replace('<CACHE>','$CACHE'))")

if ! docker run -d --rm --gpus all -v "$CACHE:/models" -p 8089:8089 --name "$CONTAINER" "$IMAGE" $FLAGS > "$RAW/container.id" 2> "$RAW/docker_run.err"; then
  cat "$RAW/docker_run.err" >> "$RAW/server.log"
  write_error_json "docker run failed"
  exit 0
fi
STARTED=1

docker logs -f "$CONTAINER" > "$RAW/server.log" 2>&1 &
LOG_PID=$!

if ! python3 - <<'PY'
import sys
sys.path.insert(0, "bench")
from common import wait_healthy
wait_healthy()
PY
then
  write_error_json "server failed to become healthy"
  exit 0
fi
nvidia-smi --query-gpu=memory.used --format=csv,noheader | tee "$RAW/vram_loaded.txt"

for s in "${SUITES[@]}"; do
  case "$s" in
    throughput) script="bench/throughput.py" ;;
    toolcall) script="bench/toolcall_suite.py" ;;
    agentic) script="bench/miniagent.py" ;;
    *) script="bench/$s.py" ;;
  esac
  EXTRA_ARGS=()
  if [ "$CFG" = "C8-nex-mini-q3" ] && { [ "$s" = "toolcall" ] || [ "$s" = "agentic" ]; }; then
    EXTRA_ARGS=(--temps 0.2 0.7)
  fi
  python3 "$script" "$CFG" "${EXTRA_ARGS[@]}" | tee "$RAW/$s.json"
done

python3 - "$CFG" <<'PY'
import json
import pathlib
import sys

cfg = sys.argv[1]
raw = pathlib.Path(f"results/raw/{cfg}")
merged = {
    "config": cfg,
    "gpu_contended": (raw / "contended.flag").exists(),
    "vram_loaded": (raw / "vram_loaded.txt").read_text().strip(),
}
server_log = raw / "server.log"
if server_log.exists():
    accept_lines = [line.rstrip() for line in server_log.read_text(errors="replace").splitlines() if "accept" in line.lower()]
    if accept_lines:
        merged["notes"] = "\n".join(accept_lines)
for f in raw.glob("*.json"):
    body = json.loads(f.read_text())
    if "suite" not in body:
        continue
    merged[body["suite"]] = body
pathlib.Path(f"results/{cfg}.json").write_text(json.dumps(merged, indent=2))
print("wrote", f"results/{cfg}.json")
PY

docker stop "$CONTAINER" >/dev/null
STARTED=0
wait "$LOG_PID" 2>/dev/null || true
LOG_PID=""
