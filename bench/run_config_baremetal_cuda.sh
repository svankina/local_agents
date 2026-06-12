#!/usr/bin/env bash
# Usage: bench/run_config_baremetal_cuda.sh <config-name> [suite ...]   (default: throughput toolcall agentic)
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

SRV=""
cleanup() {
  if [ -n "$SRV" ]; then
    kill "$SRV" 2>/dev/null || true
    wait "$SRV" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# ORCHESTRATOR-AUTHORIZED (do not remove): gracefully unload all Ollama-resident
# models via Ollama's own API before each timed run. This is a model unload, not a
# process kill - it does NOT violate the foreign-process constraint.
ollama ps 2>/dev/null | awk 'NR>1 {print $1}' | while read -r m; do ollama stop "$m" 2>/dev/null || true; done
sleep 3

for i in $(seq 1 60); do
  read -r UTIL MEM < <(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits | awk -F', ' 'NR==1{print $1, $2}')
  echo "gpu gate check $i: util=${UTIL}% mem=${MEM}MiB" | tee -a "$RAW/gpu_gate.log"
  if [ "$UTIL" -lt 10 ] && [ "$MEM" -lt 500 ]; then
    break
  fi
  sleep 30
done
if ! { [ "$UTIL" -lt 10 ] && [ "$MEM" -lt 500 ]; }; then
  echo "WARN: gpu_contended" | tee "$RAW/contended.flag"
  write_error_json "GPU gate timed out after 30 min"
  exit 0
fi

nvidia-smi --query-gpu=memory.used --format=csv,noheader | tee "$RAW/vram_before.txt"

COMMON=(--host 127.0.0.1 --port 8089 -ngl 99 --jinja -fa on)
readarray -t FLAGS < <(python3 - "$CFG" "$CACHE" <<'PY'
import json
import shlex
import sys

cfg, cache = sys.argv[1], sys.argv[2]
c = json.load(open("bench/configs.json"))
for arg in shlex.split(c[cfg].replace("<CACHE>", cache)):
    print(arg)
PY
)

llama-server-cuda "${COMMON[@]}" "${FLAGS[@]}" > "$RAW/server.log" 2>&1 &
SRV=$!
echo "$SRV" > results/.server.pid

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
  python3 "$script" "$CFG" | tee "$RAW/$s.json"
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

cleanup
SRV=""
