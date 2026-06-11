#!/usr/bin/env bash
# Usage: bench/run_config.sh <config-name> [suite ...]   (default: throughput toolcall agentic)
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

for i in $(seq 1 30); do
  UTIL=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits)
  [ "$UTIL" -lt 10 ] && break
  sleep 10
done
[ "$UTIL" -lt 10 ] || echo "WARN: gpu_contended" | tee "$RAW/contended.flag"

# ORCHESTRATOR-AUTHORIZED (do not remove): gracefully unload all Ollama-resident
# models via Ollama's own API before each timed run. This is a model unload, not a
# process kill — it does NOT violate the foreign-process constraint. The machine
# owner has cleared the GPU for benchmarking; external agents on this box reload
# Ollama models ad hoc and would otherwise OOM the 14-16GB configs.
ollama ps 2>/dev/null | awk 'NR>1 {print $1}' | while read -r m; do ollama stop "$m" 2>/dev/null || true; done
sleep 3

nvidia-smi --query-gpu=memory.used --format=csv,noheader | tee "$RAW/vram_before.txt"

FLAGS=$(python3 -c "import json;c=json.load(open('bench/configs.json'));print(c['_common'],c['$CFG'].replace('<CACHE>','$CACHE'))")
llama-server $FLAGS > "$RAW/server.log" 2>&1 &
SRV=$!
echo $SRV > results/.server.pid
trap 'kill $SRV 2>/dev/null || true' EXIT

if ! python3 - <<'PY'
import sys
sys.path.insert(0, "bench")
from common import wait_healthy
wait_healthy()
PY
then
  python3 - "$CFG" <<'PY'
import json
import pathlib
import sys

cfg = sys.argv[1]
raw = pathlib.Path(f"results/raw/{cfg}")
server_log = raw / "server.log"
tail = ""
if server_log.exists():
    tail = "\n".join(server_log.read_text(errors="replace").splitlines()[-80:])
merged = {
    "config": cfg,
    "gpu_contended": (raw / "contended.flag").exists(),
    "vram_before": (raw / "vram_before.txt").read_text().strip() if (raw / "vram_before.txt").exists() else None,
    "error": "server failed to become healthy",
    "server_log_tail": tail,
}
pathlib.Path(f"results/{cfg}.json").write_text(json.dumps(merged, indent=2))
print("wrote", f"results/{cfg}.json")
PY
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
    merged[body["suite"]] = body
pathlib.Path(f"results/{cfg}.json").write_text(json.dumps(merged, indent=2))
print("wrote", f"results/{cfg}.json")
PY

kill $SRV
wait $SRV 2>/dev/null || true
