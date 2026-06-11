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

ollama stop gemma4:12b-it-qat 2>/dev/null || true
sleep 3
nvidia-smi --query-gpu=memory.used --format=csv,noheader | tee "$RAW/vram_before.txt"

FLAGS=$(python3 -c "import json;c=json.load(open('bench/configs.json'));print(c['_common'],c['$CFG'].replace('<CACHE>','$CACHE'))")
llama-server $FLAGS > "$RAW/server.log" 2>&1 &
SRV=$!
echo $SRV > results/.server.pid
trap 'kill $SRV 2>/dev/null || true' EXIT

python3 - <<'PY'
import sys
sys.path.insert(0, "bench")
from common import wait_healthy
wait_healthy()
PY
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
for f in raw.glob("*.json"):
    body = json.loads(f.read_text())
    merged[body["suite"]] = body
pathlib.Path(f"results/{cfg}.json").write_text(json.dumps(merged, indent=2))
print("wrote", f"results/{cfg}.json")
PY

kill $SRV
wait $SRV 2>/dev/null || true
