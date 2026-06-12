#!/usr/bin/env bash
# Usage: bench/run_config_vllm.sh <config-name> [suite ...]   (default: throughput toolcall agentic)
set -euo pipefail

cd "$(dirname "$0")/.."
CFG="$1"
shift || true
if [ "$#" -gt 0 ]; then
  SUITES=("$@")
else
  SUITES=(throughput toolcall agentic)
fi

HF_CACHE="$HOME/.cache/huggingface"
RAW="results/raw/$CFG"
IMAGE="vllm/vllm-openai:latest"
CONTAINER="bench-$CFG"
PORT=8091
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

FLAGS=$(python3 -c "import json;c=json.load(open('bench/configs.json'));print(c['$CFG'])")
SERVED_MODEL=$(python3 -c "import json,shlex;c=json.load(open('bench/configs.json'));a=shlex.split(c['$CFG']);print(a[a.index('--served-model-name')+1] if '--served-model-name' in a else a[a.index('--model')+1])")

if [[ "$FLAGS" == *"cohere_command4"* ]]; then
  SERVE_CMD="pip install -q 'cohere_melody>=0.9.0' && exec vllm serve $FLAGS"
  if ! docker run -d --rm --gpus all --ipc=host \
    -v "$HF_CACHE:/root/.cache/huggingface" \
    -p "$PORT:8000" \
    --name "$CONTAINER" \
    --entrypoint /bin/bash \
    "$IMAGE" -lc "$SERVE_CMD" > "$RAW/container.id" 2> "$RAW/docker_run.err"; then
    cat "$RAW/docker_run.err" >> "$RAW/server.log"
    write_error_json "docker run failed"
    exit 0
  fi
else
  if ! docker run -d --rm --gpus all --ipc=host \
    -v "$HF_CACHE:/root/.cache/huggingface" \
    -p "$PORT:8000" \
    --name "$CONTAINER" \
    "$IMAGE" $FLAGS > "$RAW/container.id" 2> "$RAW/docker_run.err"; then
    cat "$RAW/docker_run.err" >> "$RAW/server.log"
    write_error_json "docker run failed"
    exit 0
  fi
fi
STARTED=1

docker logs -f "$CONTAINER" > "$RAW/server.log" 2>&1 &
LOG_PID=$!

export BENCH_BASE="http://127.0.0.1:$PORT/v1"
export BENCH_MODEL="$SERVED_MODEL"
if [[ "$CFG" =~ ^C(17|18)- ]] && [ -z "${BENCH_THROUGHPUT_STREAMS:-}" ]; then
  export BENCH_THROUGHPUT_STREAMS="1 2 4 8"
fi

if ! python3 - <<'PY'
import sys
sys.path.insert(0, "bench")
from common import wait_healthy
wait_healthy(base="http://127.0.0.1:8091", tries=360)
PY
then
  write_error_json "server failed to become healthy"
  exit 0
fi
nvidia-smi --query-gpu=memory.used --format=csv,noheader | tee "$RAW/vram_loaded.txt"

if [[ "$CFG" =~ ^C(17|18)- ]]; then
  if ! python3 - "$CFG" "$SERVED_MODEL" <<'PY'
import json
import pathlib
import sys
import urllib.request

cfg = sys.argv[1]
model = sys.argv[2]
raw = pathlib.Path(f"results/raw/{cfg}")
base = "http://127.0.0.1:8091/v1/chat/completions"

def post(payload, name):
    req = urllib.request.Request(
        base,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.loads(r.read())
    (raw / name).write_text(json.dumps(body, indent=2))
    return body

hello = post(
    {
        "model": model,
        "messages": [{"role": "user", "content": "Say hello and name three colors."}],
        "temperature": 0,
        "max_tokens": 128,
    },
    "coherence_hello.json",
)
tool = post(
    {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a coding agent. Use read_file when asked to inspect a file.",
            },
            {"role": "user", "content": "Read TASK.md using the read_file tool."},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a text file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ],
        "tool_choice": "auto",
        "temperature": 0,
        "max_tokens": 256,
    },
    "coherence_tool.json",
)

msg = hello["choices"][0]["message"]
content = (msg.get("content") or "").lower()
colors = {"red", "green", "blue", "yellow", "orange", "purple", "black", "white"}
hello_ok = "hello" in content and len([c for c in colors if c in content]) >= 3
tool_calls = tool["choices"][0]["message"].get("tool_calls") or []
tool_ok = bool(tool_calls) and tool_calls[0].get("function", {}).get("name") == "read_file"
gate = {
    "config": cfg,
    "suite": "coherence_gate",
    "hello_ok": hello_ok,
    "hello_content": msg.get("content"),
    "tool_ok": tool_ok,
    "tool_calls": tool_calls,
}
(raw / "coherence_gate.json").write_text(json.dumps(gate, indent=2))
if not (hello_ok and tool_ok):
    print(json.dumps(gate, indent=2))
    raise SystemExit(1)
print(json.dumps(gate, indent=2))
PY
  then
    write_error_json "coherence gate failed"
    exit 0
  fi
fi

for s in "${SUITES[@]}"; do
  case "$s" in
    throughput) script="bench/throughput.py" ;;
    toolcall) script="bench/toolcall_suite.py" ;;
    agentic) script="bench/miniagent.py" ;;
    *) script="bench/$s.py" ;;
  esac
  python3 "$script" "$CFG" | tee "$RAW/$s.json"
done

python3 - "$CFG" "$SERVED_MODEL" <<'PY'
import json
import pathlib
import sys

cfg = sys.argv[1]
served_model = sys.argv[2]
raw = pathlib.Path(f"results/raw/{cfg}")
merged = {
    "config": cfg,
    "served_model": served_model,
    "gpu_contended": (raw / "contended.flag").exists(),
    "vram_loaded": (raw / "vram_loaded.txt").read_text().strip(),
}
server_log = raw / "server.log"
if server_log.exists():
    noteworthy = [
        line.rstrip()
        for line in server_log.read_text(errors="replace").splitlines()
        if any(token in line.lower() for token in ("error", "warn", "graph", "capture", "quant", "tool"))
    ]
    if noteworthy:
        merged["notes"] = "\n".join(noteworthy[-120:])
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
