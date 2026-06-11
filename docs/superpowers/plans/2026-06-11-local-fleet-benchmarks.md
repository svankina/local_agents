# Local Fleet Benchmarks Implementation Plan

> **For agentic workers:** This plan is executed by **GPT-5.5 Codex subagents** dispatched via `codex-agent start -m gpt-5.5 ...` and **actively monitored** by the orchestrator (Claude, main session) via `codex-agent watch <id>` polling. See "Orchestration Protocol". Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Benchmark every local-model candidate discussed for the subagent fleet (throughput, tool-calling reliability, agentic task completion, VRAM coexistence) on the RTX 3090 Ti and produce a decision matrix assigning each model a role (worker / senior / excluded).

**Architecture:** A uniform `llama-server` harness (OpenAI-compat API) serves each model config one at a time (GPU-serial — concurrent benchmarks invalidate numbers). Three Python suites hit the server: throughput (server `timings` field), tool-call reliability (scored synthetic cases), and agentic mini-tasks (minimal tool-loop agent against a generated sandbox repo). Results land as JSON in `results/`, aggregated into `results/RESULTS.md` and a role-assignment decision.

**Tech Stack:** llama.cpp (≥ the June-2026 build with `--spec-type draft-mtp`), Ollama (model blob source + eviction), Python 3 stdlib + `requests` + `pytest`, `codex-agent` CLI for subagent dispatch.

---

## Hard Constraints (read before any task)

1. **Never touch PID 2541 (`hermes-agent`)** or any process you didn't start. To free VRAM use `ollama stop <model>` (graceful eviction), and kill only llama-server PIDs recorded in `results/.server.pid` by our own scripts.
2. **GPU-serial:** exactly one benchmark config on the GPU at a time (exception: Task 12 coexistence test, which is the point). Pre-flight: GPU util must be <10% for 30s before a timing run; if hermes-agent is actively inferring, wait or record the contamination in the result JSON (`"gpu_contended": true`).
3. **No fabricated numbers.** Every figure in `results/` must come from a run whose raw log exists under `results/raw/`. A result JSON without a matching raw log is a task failure.
4. **No sudo.** Nothing here needs it. llama.cpp installs go to `~/.local/opt/` + `~/.local/bin/` symlinks, same as the existing b9128.
5. Repo is brand-new and dedicated to this work — commit directly to `master`, small commits per task. (`.worktrees/` isolation is skipped: there are no commits to branch from yet.)
6. Disk budget: ~60GB of GGUF downloads against 570GB free — fine, but put all downloads in `~/.cache/llama.cpp/` (llama-server `-hf` does this automatically) so they're shared and easy to clean.

## Orchestration Protocol (for the monitoring orchestrator)

- **Dispatch:** one Codex run per task group (Phases below), launched with
  `codex-agent start -m gpt-5.5 "<task brief: paste the full task text from this plan>"`.
  Record the run id. Do NOT use harness `run_in_background` for the codex process itself — `start` already detaches.
- **Monitor loop:** poll `codex-agent watch <id>` between other work; check progress at least every ~2–3 minutes during model downloads/long runs, every ~60s during scripted suite runs.
- **Steer/interrupt** (via `codex-agent` steering subcommands, or `stop` + `resume <id> "<correction>"`) immediately if the run: touches hermes-agent or any foreign process; reaches for sudo/apt; "estimates" a number instead of running the command; downloads something other than the listed artifacts; idles >10 min; or edits files outside this repo and `~/.local/{opt,bin}` / `~/.cache/llama.cpp`.
- **Verify between phases:** after each phase, the orchestrator reads the result JSONs, spot-checks 2 raw logs against the JSON numbers, and runs the relevant `pytest` before dispatching the next phase. Findings of mismatch → resume the same run with a correction, don't redo from scratch.
- **Phases:**
  - Phase 1 = Tasks 1–6 (scaffold, llama.cpp upgrade, downloads, harness code). One Codex run.
  - Phase 2 = Tasks 7–11 (benchmark configs C1–C8, GPU-serial). One Codex run, steered config-by-config.
  - Phase 3 = Tasks 12–13 (coexistence + aggregation/decision). One Codex run.
  - Stretch = Task 14 (C9–C11), only if Phase 2 finished clean and time permits.

## File Structure

```
local_agents/
├── docs/superpowers/plans/2026-06-11-local-fleet-benchmarks.md   (this file)
├── bench/
│   ├── common.py            # shared HTTP client + timing helpers
│   ├── throughput.py        # Suite T: prefill/decode tok/s, 1/2/4 concurrent streams
│   ├── toolcall_suite.py    # Suite TC: scored tool-call cases
│   ├── toolcall_cases.json  # the cases
│   ├── miniagent.py         # Suite A: minimal tool-loop agent
│   ├── agentic_tasks.json   # task definitions + check commands
│   ├── make_sandbox.py      # generates bench/sandbox fixture repos
│   ├── run_config.sh        # launches llama-server for a named config, runs suites, tears down
│   └── configs.json         # exact server flags per config C1–C11
├── tests/
│   └── test_scoring.py      # unit tests for the two scorers (no GPU needed)
├── results/
│   ├── raw/                 # full suite stdout + server logs, one dir per config
│   ├── <config>.json        # machine-readable results per config
│   └── RESULTS.md           # final aggregate table + role decision
└── .gitignore               # results/raw/, bench/sandbox/work-*, __pycache__
```

## Model / Config Matrix

| Config | Model | Serving | Why |
|---|---|---|---|
| C1 | Gemma 4 12B QAT Q4_0 | llama-server, full GPU, 1 slot | worker baseline |
| C2 | Gemma 4 12B QAT + MTP drafter | + `--spec-type draft-mtp` | worker speedup claim (1.5–2.2×) |
| C3 | Gemma 4 12B QAT, 3 slots | `--parallel 3`, KV q8_0 | worker fleet concurrency |
| C4 | Gemma 4 26B A4B QAT UD-Q4_K_XL | full GPU | senior candidate, best case |
| C5 | Gemma 4 26B A4B QAT | `-cmoe` (experts in RAM) | senior at 8GB VRAM (coexistence layout) |
| C6 | Gemma 4 26B A4B QAT | `-cmoe` + MTP | the tweet's 25+ tok/s claim |
| C7 | Qwen3.6-27B Q3_K_M (~13GB) | full GPU | senior candidate, quality leader |
| C8 | Nex-N2-mini Q3 (~16GB) | full GPU | senior candidate, agent post-train |
| C9* | Qwen3.6-27B Q4_K_M (17GB) | full GPU | Q3-vs-Q4 quality delta check |
| C10* | Qwen3.6-35B-A3B Q4_K_M (22GB) | full GPU | MoE senior comparison |
| C11* | phi4-mini 3.8B | full GPU | micro-worker floor |

\* = stretch (Task 14). **Excluded:** DiffusionGemma (no llama.cpp support yet, no tool-calling story, quality below Gemma 4 — revisit when llama.cpp lands), Nex-N2-Pro (397B, not local-feasible), GLM-4.7-Flash and Carnice/Claude-distill fine-tunes (weak or protocol-narrow per the r/hermesagent 3090 community benchmark).

**Addendum (community-benchmark imports, run as part of Phase 2 after C8):** per the r/hermesagent full-suite 3090 results (reddit 1twjvs8; CUDA, temp 0.6 — relative rankings only):

| Config | Model | Serving | Why |
|---|---|---|---|
| C12 | byteshape Qwen3.6-35B-A3B IQ4_XS (+MTP, no separate drafter needed) | full GPU | their overall winner: 73.5%, 115 TPS, 262K ctx, ~18GB |
| C13 | Qwopus3.6-27B-v2 (Q4-class GGUF) + MTP n=2 | full GPU | their CLI-40 leader (20/40, zero variance) — closest pack to our subagent workload |

Verify exact HF repos at download time (Task 3 Step 1 pattern; expect `byteshape/...Qwen3.6-35B-A3B...IQ4_XS` and a `Qwopus3.6-27B-v2` GGUF repo, else nearest bartowski/unsloth mirror). Qwen-family MTP uses built-in drafting (`--spec-type draft-mtp` without `-md`) — confirm flag shape against llama-server docs at run time. Add `"C12-byteshape-35b"` and `"C13-qwopus-27b"` entries to `bench/configs.json` following the existing pattern (`-c 32768 --temp 0.2`).

**C14 (stretch, alongside Task 14):** Gemma 4 31B QAT + MTP — weights already local via the Ollama pull (`ollama show gemma4:31b-it-qat --modelfile` → blob path), only the `mtp-` drafter GGUF needs downloading (~1–2GB from the 31B QAT repo). Unsloth measured 2.21× MTP speedup on this variant; ~18–21GB total, solo-tenant. Strongest dense-Gemma senior; mainly a reference point against C7/C12.

Exact HF repo names for downloads are *verified at runtime* (Task 3 step 1) because they're young releases; expected names with fallbacks are listed there.

## Decision Rubric (applied in Task 13)

- **Worker role:** tool-call valid rate ≥95% at temp 0.2, ≥3/5 agentic tasks, single-stream decode ≥30 tok/s, 3-slot aggregate ≥1.5× single-stream.
- **Senior role:** ≥4/5 agentic tasks, tool-call ≥95%, decode ≥15 tok/s, prefill ≥150 tok/s *with prompt-cache reuse measured* (the `-cmoe` killer question).
- **Coexistence:** chosen senior + worker layouts must fit ≤22GB VRAM together (Task 12 measures actual, not estimated).
- Ties broken by agentic wall-clock per completed task.

---

### Task 1: Repo scaffold + initial commit

**Files:** Create: `.gitignore`, `README.md`, `bench/`, `results/raw/.gitkeep`, `tests/`

- [ ] **Step 1: Scaffold**

```bash
cd /home/svankina/src/local_agents
mkdir -p bench tests results/raw docs/superpowers/plans
printf 'results/raw/\nbench/sandbox/work-*/\n__pycache__/\n*.pyc\n.worktrees/\n' > .gitignore
printf '# local_agents\n\nLocal-LLM subagent fleet for the 3090 Ti box. `bench/` measures candidate models; see docs/superpowers/plans/ for the plan and results/RESULTS.md for the verdict.\n' > README.md
touch results/raw/.gitkeep
```

- [ ] **Step 2: Initial commit**

```bash
git add -A && git commit -m "chore: scaffold benchmark repo"
```

### Task 2: Upgrade llama.cpp to an MTP-capable build

**Files:** Create: `~/.local/opt/llama.cpp-<new>/`, update symlinks in `~/.local/bin/`

The installed b9128 lacks `--spec-type draft-mtp` (MTP merged ~June 8, 2026) and ships no CUDA backend in the loaded list. Install the newest release with CUDA.

- [ ] **Step 1: Fetch latest release tag and the CUDA binary archive**

```bash
TAG=$(curl -s https://api.github.com/repos/ggml-org/llama.cpp/releases/latest | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')
echo "$TAG"
# pick the cuda x64 linux asset; name pattern as of 2026: llama-<tag>-bin-ubuntu-cuda-x64.zip (verify with:)
curl -s https://api.github.com/repos/ggml-org/llama.cpp/releases/latest | python3 -c 'import json,sys; [print(a["name"]) for a in json.load(sys.stdin)["assets"]]' | grep -i cuda
```

Expected: a tag ≥ b9300-ish and a `*cuda*x64*` asset. If no CUDA asset exists for linux, fall back to building: `cmake -B build -DGGML_CUDA=ON && cmake --build build -j 20 --target llama-server llama-bench llama-cli` from a `git clone --depth 1`.

- [ ] **Step 2: Install to ~/.local/opt and repoint symlinks**

```bash
cd ~/.local/opt
curl -LO https://github.com/ggml-org/llama.cpp/releases/download/$TAG/<cuda-asset-name>.zip
mkdir llama.cpp-$TAG && cd llama.cpp-$TAG && unzip ../<cuda-asset-name>.zip
ln -sf ~/.local/opt/llama.cpp-$TAG/<bindir>/llama-server ~/.local/bin/llama-server
ln -sf ~/.local/opt/llama.cpp-$TAG/<bindir>/llama-cli    ~/.local/bin/llama-cli
ln -sf ~/.local/opt/llama.cpp-$TAG/<bindir>/llama-bench  ~/.local/bin/llama-bench
```

(`<bindir>` is whatever the archive contains — typically `build/bin` or flat; list it first.)

- [ ] **Step 3: Verify CUDA + MTP support**

```bash
llama-server --version 2>&1 | grep -i cuda      # must show a CUDA backend loading
llama-server --help | grep -- --spec-type        # must list draft-mtp
llama-bench --help >/dev/null && echo llama-bench OK
```

Expected: all three checks pass. If `draft-mtp` is still absent in the latest release, build from master (Step 1 fallback) — it is merged there per llama.cpp PR history (early June 2026).

- [ ] **Step 4: Commit a note**

```bash
echo "llama.cpp: $TAG (CUDA, draft-mtp verified $(date +%F))" >> README.md
git add README.md && git commit -m "chore: record llama.cpp upgrade"
```

### Task 3: Download model artifacts

**Files:** populate `~/.cache/llama.cpp/` (no repo files except `bench/models.lock`)

- [ ] **Step 1: Verify HF repo names** (they're new releases; don't trust guesses)

```bash
for q in "gemma-4-12b-it-qat GGUF unsloth" "gemma-4-26B-A4B-it-qat GGUF unsloth" "Qwen3.6-27B GGUF" "Nex-N2-mini GGUF"; do
  curl -s "https://huggingface.co/api/models?search=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$q")&limit=5" | python3 -c 'import json,sys; [print(m["modelId"]) for m in json.load(sys.stdin)]'
done
```

Expected candidates (use these if confirmed, else nearest match from the search):
`unsloth/gemma-4-12b-it-qat-GGUF`, `unsloth/gemma-4-26B-A4B-it-qat-GGUF` (contains `mtp-gemma-4-26B-A4B-it.gguf` drafter at repo root), `unsloth/Qwen3.6-27B-GGUF`, `nex-agi/Nex-N2-mini-GGUF` (or `bartowski/...`). Also list repo files to get exact drafter filenames:

```bash
curl -s https://huggingface.co/api/models/<repo>/tree/main | python3 -c 'import json,sys; [print(f["path"], f.get("size",0)//2**20, "MiB") for f in json.load(sys.stdin)]'
```

- [ ] **Step 2: Download via llama-server -hf (caches to ~/.cache/llama.cpp, then exit)**

```bash
for spec in "<12b-repo>:Q4_0" "<26b-repo>:UD-Q4_K_XL" "<qwen-repo>:Q3_K_M" "<nex-repo>:Q3_K_M"; do
  timeout 1800 llama-cli -hf "$spec" -p "hi" -n 1 --no-display-prompt || true
done
# drafter ggufs (direct file download):
curl -L -o ~/.cache/llama.cpp/mtp-gemma-4-12b-it.gguf  "https://huggingface.co/<12b-repo>/resolve/main/<12b-mtp-file>"
curl -L -o ~/.cache/llama.cpp/mtp-gemma-4-26B-A4B-it.gguf "https://huggingface.co/<26b-repo>/resolve/main/<26b-mtp-file>"
```

- [ ] **Step 3: Record a lockfile and commit**

```bash
ls -l ~/.cache/llama.cpp/ | awk '{print $5, $9}' > bench/models.lock
git add bench/models.lock && git commit -m "chore: lock downloaded model artifacts"
```

Expected: 12B ≈7.2GB, 26B ≈13.2GB, Qwen Q3 ≈12–14GB, Nex Q3 ≈15–17GB, drafters ≈0.5–2GB each.

### Task 4: Harness — common client + scorer tests (TDD)

**Files:** Create: `bench/common.py`, `tests/test_scoring.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scoring.py
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "bench"))
from common import score_toolcall, parse_timings

def test_score_exact_match():
    case = {"expect_tool": "read_file", "expect_args": {"path": {"eq": "src/main.py"}}}
    call = {"name": "read_file", "arguments": json.dumps({"path": "src/main.py"})}
    assert score_toolcall(case, [call]) == (True, "ok")

def test_score_wrong_tool():
    case = {"expect_tool": "read_file", "expect_args": {}}
    call = {"name": "run_bash", "arguments": "{}"}
    ok, why = score_toolcall(case, [call])
    assert not ok and "tool" in why

def test_score_regex_arg():
    case = {"expect_tool": "run_bash", "expect_args": {"command": {"re": r"grep\s+-r"}}}
    call = {"name": "run_bash", "arguments": json.dumps({"command": "grep -r TODO ."})}
    assert score_toolcall(case, [call])[0]

def test_score_expect_no_tool():
    case = {"expect_tool": None}
    assert score_toolcall(case, [])[0]
    assert not score_toolcall(case, [{"name": "read_file", "arguments": "{}"}])[0]

def test_score_malformed_json_args():
    case = {"expect_tool": "read_file", "expect_args": {"path": {"eq": "x"}}}
    call = {"name": "read_file", "arguments": "{path: x"}  # invalid JSON
    ok, why = score_toolcall(case, [call])
    assert not ok and "json" in why.lower()

def test_parse_timings():
    body = {"timings": {"prompt_n": 1000, "prompt_per_second": 512.3,
                        "predicted_n": 256, "predicted_per_second": 41.7}}
    t = parse_timings(body)
    assert t == {"prefill_tps": 512.3, "decode_tps": 41.7, "prompt_n": 1000, "predicted_n": 256}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /home/svankina/src/local_agents && python3 -m pytest tests/ -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'common'`

- [ ] **Step 3: Implement bench/common.py**

```python
# bench/common.py
"""Shared helpers: OpenAI-compat chat client against llama-server, scorers."""
import json, re, time, urllib.request

BASE = "http://127.0.0.1:8089"

def chat(messages, tools=None, temperature=0.2, max_tokens=1024, base=BASE, timeout=600):
    payload = {"model": "local", "messages": messages, "temperature": temperature,
               "max_tokens": max_tokens, "timings_per_token": False}
    if tools:
        payload["tools"] = tools
    req = urllib.request.Request(base + "/v1/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read())
    body["_wall_s"] = round(time.monotonic() - t0, 3)
    return body

def tool_calls_of(body):
    msg = body["choices"][0]["message"]
    return [{"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]}
            for tc in (msg.get("tool_calls") or [])]

def parse_timings(body):
    t = body.get("timings") or {}
    return {"prefill_tps": t.get("prompt_per_second"),
            "decode_tps": t.get("predicted_per_second"),
            "prompt_n": t.get("prompt_n"), "predicted_n": t.get("predicted_n")}

def score_toolcall(case, calls):
    """case: {expect_tool: str|None, expect_args: {name: {eq|re|contains: val}}}"""
    if case.get("expect_tool") is None:
        return (not calls, "ok" if not calls else "unexpected tool call")
    if not calls:
        return (False, "no tool call made")
    call = calls[0]
    if call["name"] != case["expect_tool"]:
        return (False, f"wrong tool: {call['name']}")
    try:
        args = json.loads(call["arguments"]) if isinstance(call["arguments"], str) else call["arguments"]
    except (json.JSONDecodeError, TypeError):
        return (False, "arguments not valid JSON")
    for k, matcher in (case.get("expect_args") or {}).items():
        v = args.get(k)
        if "eq" in matcher and v != matcher["eq"]:
            return (False, f"arg {k}: {v!r} != {matcher['eq']!r}")
        if "re" in matcher and (not isinstance(v, str) or not re.search(matcher["re"], v)):
            return (False, f"arg {k}: {v!r} !~ /{matcher['re']}/")
        if "contains" in matcher and (not isinstance(v, str) or matcher["contains"] not in v):
            return (False, f"arg {k}: missing {matcher['contains']!r}")
    return (True, "ok")

def wait_healthy(base=BASE, tries=120):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(base + "/health", timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(2)
    raise SystemExit("server never became healthy")
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python3 -m pytest tests/ -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add bench/common.py tests/test_scoring.py && git commit -m "feat: bench client + scorers with tests"
```

### Task 5: Harness — the three suites

**Files:** Create: `bench/throughput.py`, `bench/toolcall_suite.py`, `bench/toolcall_cases.json`, `bench/miniagent.py`, `bench/make_sandbox.py`, `bench/agentic_tasks.json`

- [ ] **Step 1: bench/throughput.py**

```python
# bench/throughput.py
"""Suite T: single-stream prefill/decode + concurrent-stream scaling.
Usage: python3 throughput.py <config-name> [--streams 1 2 4] [--trials 3]"""
import argparse, concurrent.futures, json, statistics, sys, time
from common import chat, parse_timings, wait_healthy

PROMPT_1K = ("You are summarizing a design document. " +
             "The system ingests events, deduplicates them, and routes them to workers. " * 60)
PROMPT_8K = PROMPT_1K * 8  # ~8k tokens: exercises prefill properly

def one(prompt, max_tokens=256):
    body = chat([{"role": "user", "content": prompt + "\nSummarize in detail."}],
                max_tokens=max_tokens)
    t = parse_timings(body)
    t["wall_s"] = body["_wall_s"]
    return t

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config"); ap.add_argument("--streams", type=int, nargs="+", default=[1, 2, 4])
    ap.add_argument("--trials", type=int, default=3)
    args = ap.parse_args()
    wait_healthy()
    out = {"config": args.config, "suite": "throughput", "single": {}, "concurrent": {}}
    for label, prompt in [("p1k", PROMPT_1K), ("p8k", PROMPT_8K)]:
        trials = [one(prompt) for _ in range(args.trials)]
        out["single"][label] = {
            "prefill_tps": round(statistics.median(t["prefill_tps"] for t in trials), 1),
            "decode_tps": round(statistics.median(t["decode_tps"] for t in trials), 1),
            "trials": trials}
    for n in args.streams:
        if n == 1: continue
        t0 = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(n) as ex:
            rs = list(ex.map(lambda _: one(PROMPT_1K), range(n)))
        wall = time.monotonic() - t0
        total_tok = sum(r["predicted_n"] or 0 for r in rs)
        out["concurrent"][f"x{n}"] = {
            "per_stream_decode_tps": round(statistics.median(r["decode_tps"] for r in rs), 1),
            "aggregate_tps": round(total_tok / wall, 1), "wall_s": round(wall, 1), "trials": rs}
    json.dump(out, sys.stdout, indent=2); print()

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: bench/toolcall_cases.json** (12 cases; temp is swept by the runner)

```json
[
  {"id":"simple-read","prompt":"Read the file src/main.py and tell me what it does.","expect_tool":"read_file","expect_args":{"path":{"eq":"src/main.py"}}},
  {"id":"arg-fidelity","prompt":"Open the file named 'data/2026-06 report (final).csv' exactly as written.","expect_tool":"read_file","expect_args":{"path":{"eq":"data/2026-06 report (final).csv"}}},
  {"id":"pick-grep","prompt":"Find every occurrence of the string TODO anywhere in this project.","expect_tool":"run_bash","expect_args":{"command":{"re":"grep|rg"}}},
  {"id":"pick-list","prompt":"What files are in the tests directory?","expect_tool":"list_dir","expect_args":{"path":{"re":"tests/?$"}}},
  {"id":"no-tool","prompt":"What does the acronym YAML stand for?","expect_tool":null},
  {"id":"no-tool-2","prompt":"Briefly explain the difference between a thread and a process.","expect_tool":null},
  {"id":"write-exact","prompt":"Create a file called notes.txt containing exactly the text: hello fleet","expect_tool":"write_file","expect_args":{"path":{"eq":"notes.txt"},"content":{"contains":"hello fleet"}}},
  {"id":"nested-json","prompt":"Run the bash command to print the value of the HOME environment variable.","expect_tool":"run_bash","expect_args":{"command":{"re":"echo\\s+\"?\\$\\{?HOME"}}},
  {"id":"numeric-arg","prompt":"Show me the last 25 lines of build.log using a shell command.","expect_tool":"run_bash","expect_args":{"command":{"re":"tail\\s+(-n\\s*)?25\\s+build\\.log"}}},
  {"id":"quote-trap","prompt":"Write a file greeting.py whose content is: print(\"it's working\")","expect_tool":"write_file","expect_args":{"path":{"eq":"greeting.py"},"content":{"contains":"it's working"}}},
  {"id":"chain-first-step","prompt":"I need to know if config.yaml mentions 'redis'. Start by reading it.","expect_tool":"read_file","expect_args":{"path":{"eq":"config.yaml"}}},
  {"id":"long-path","prompt":"Read deeply/nested/path/to/the/module/handlers/event_router.py","expect_tool":"read_file","expect_args":{"path":{"eq":"deeply/nested/path/to/the/module/handlers/event_router.py"}}}
]
```

- [ ] **Step 3: bench/toolcall_suite.py**

```python
# bench/toolcall_suite.py
"""Suite TC. Usage: python3 toolcall_suite.py <config> [--temps 0.2 0.7] [--trials 3]"""
import argparse, json, pathlib, sys
from common import chat, tool_calls_of, score_toolcall, wait_healthy

TOOLS = [
  {"type":"function","function":{"name":"read_file","description":"Read a text file","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
  {"type":"function","function":{"name":"write_file","description":"Create or overwrite a text file","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}}},
  {"type":"function","function":{"name":"list_dir","description":"List directory entries","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
  {"type":"function","function":{"name":"run_bash","description":"Run a shell command and return stdout","parameters":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}}},
]
SYSTEM = "You are a coding agent. Use the provided tools when a task requires file or shell access. Answer directly when no tool is needed."

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config"); ap.add_argument("--temps", type=float, nargs="+", default=[0.2])
    ap.add_argument("--trials", type=int, default=3)
    args = ap.parse_args()
    wait_healthy()
    cases = json.loads((pathlib.Path(__file__).parent / "toolcall_cases.json").read_text())
    out = {"config": args.config, "suite": "toolcall", "temps": {}}
    for temp in args.temps:
        results, passed = [], 0
        for case in cases:
            for trial in range(args.trials):
                body = chat([{"role":"system","content":SYSTEM},{"role":"user","content":case["prompt"]}],
                            tools=TOOLS, temperature=temp, max_tokens=512)
                ok, why = score_toolcall(case, tool_calls_of(body))
                passed += ok
                results.append({"id": case["id"], "trial": trial, "ok": ok, "why": why})
        n = len(cases) * args.trials
        out["temps"][str(temp)] = {"valid_rate": round(passed / n, 3), "n": n, "results": results}
    json.dump(out, sys.stdout, indent=2); print()

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: bench/make_sandbox.py** (fixture generator; deterministic)

```python
# bench/make_sandbox.py
"""Create bench/sandbox/work-<task>/ fixture repos. Usage: python3 make_sandbox.py <task-id> -> prints workdir."""
import pathlib, shutil, sys

FIXTURES = {
  "fix-test": {
    "calc/__init__.py": "",
    "calc/ops.py": "def add(a, b):\n    return a - b  # bug\n\ndef mul(a, b):\n    return a * b\n",
    "test_ops.py": "from calc.ops import add, mul\n\ndef test_add():\n    assert add(2, 3) == 5\n\ndef test_mul():\n    assert mul(2, 3) == 6\n",
    "TASK.md": "The test suite fails. Find and fix the bug. Do not change the tests.",
  },
  "bulk-rename": {
    "app/db.py": "def fetch_record(rid):\n    return {'id': rid}\n",
    "app/api.py": "from app.db import fetch_record\n\ndef get(rid):\n    return fetch_record(rid)\n",
    "app/cli.py": "from app.db import fetch_record\n\nif __name__ == '__main__':\n    import sys; print(fetch_record(sys.argv[1]))\n",
    "app/__init__.py": "",
    "TASK.md": "Rename the function fetch_record to load_record everywhere in this repo, updating all callers.",
  },
  "csv-script": {
    "sales.csv": "region,amount\nwest,120\neast,80\nwest,200\nsouth,50\n",
    "TASK.md": "Write a script sum_by_region.py that reads sales.csv and prints each region with its total amount, one 'region,total' line per region, sorted by region name.",
  },
  "code-qa": {
    "pipeline.py": "import queue\n\nclass Router:\n    def __init__(self, workers):\n        self.q = queue.Queue(maxsize=64)\n        self.workers = workers\n\n    def dispatch(self, event):\n        if event.get('priority') == 'high':\n            self.workers[0].handle(event)\n        else:\n            self.q.put(event, timeout=5)\n",
    "TASK.md": "Answer in ANSWERS.md: 1) What happens to a high-priority event? 2) What is the queue's maxsize? 3) What exception risk exists in dispatch for normal events?",
  },
  "add-flag": {
    "tool.py": "import sys\n\ndef main(argv):\n    name = argv[1] if len(argv) > 1 else 'world'\n    print(f'hello {name}')\n\nif __name__ == '__main__':\n    main(sys.argv)\n",
    "TASK.md": "Add a --shout flag to tool.py: when passed anywhere in argv, output is uppercased. Flag must not be treated as the name.",
  },
}

def main():
    task = sys.argv[1]
    root = pathlib.Path(__file__).parent / "sandbox" / f"work-{task}"
    if root.exists():
        shutil.rmtree(root)
    for rel, content in FIXTURES[task].items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    print(root)

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: bench/agentic_tasks.json** (check commands run with cwd = the workdir)

```json
[
  {"id":"fix-test","check":"python3 -m pytest -q 2>&1 | grep -q '2 passed'"},
  {"id":"bulk-rename","check":"! grep -rn fetch_record . --include='*.py' && python3 -c 'from app.api import get; assert get(7)[\"id\"]==7' && grep -q load_record app/db.py"},
  {"id":"csv-script","check":"python3 sum_by_region.py | tr -d ' ' | grep -qx 'east,80' && python3 sum_by_region.py | tr -d ' ' | grep -qx 'west,320'"},
  {"id":"code-qa","check":"grep -qi 'workers\\[0\\]\\|first worker' ANSWERS.md && grep -q '64' ANSWERS.md && grep -qiE 'full|timeout|queue.Full|block' ANSWERS.md"},
  {"id":"add-flag","check":"python3 tool.py --shout bob | grep -qx 'HELLO BOB' && python3 tool.py alice | grep -qx 'hello alice'"}
]
```

- [ ] **Step 6: bench/miniagent.py**

```python
# bench/miniagent.py
"""Suite A: minimal tool-loop agent. Usage: python3 miniagent.py <config> [--temps 0.2] [--max-turns 15]"""
import argparse, json, pathlib, subprocess, sys, time
from common import chat, wait_healthy
from toolcall_suite import TOOLS

SYSTEM = ("You are a coding agent working in the current directory. Read TASK.md first, complete the task "
          "using the tools, verify your work, then reply with exactly DONE when finished.")

def run_tool(name, args, cwd):
    try:
        if name == "read_file":
            return (cwd / args["path"]).read_text()[:8000]
        if name == "write_file":
            p = cwd / args["path"]; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"]); return f"wrote {args['path']}"
        if name == "list_dir":
            return "\n".join(sorted(x.name + ("/" if x.is_dir() else "") for x in (cwd / args.get("path", ".")).iterdir()))
        if name == "run_bash":
            r = subprocess.run(args["command"], shell=True, cwd=cwd, capture_output=True, text=True, timeout=60)
            return (r.stdout + r.stderr)[:8000] or f"(exit {r.returncode})"
    except Exception as e:
        return f"ERROR: {e}"
    return f"ERROR: unknown tool {name}"

def run_task(task, temp, max_turns):
    bench = pathlib.Path(__file__).parent
    cwd = pathlib.Path(subprocess.run([sys.executable, bench / "make_sandbox.py", task["id"]],
                                      capture_output=True, text=True, check=True).stdout.strip())
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "Begin. TASK.md has your task."}]
    t0, turns = time.monotonic(), 0
    for turns in range(1, max_turns + 1):
        body = chat(msgs, tools=TOOLS, temperature=temp, max_tokens=2048)
        msg = body["choices"][0]["message"]
        msgs.append(msg)
        if not msg.get("tool_calls"):
            break
        for tc in msg["tool_calls"]:
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}
            msgs.append({"role": "tool", "tool_call_id": tc.get("id", "0"),
                         "content": run_tool(tc["function"]["name"], args, cwd)})
    check = subprocess.run(task["check"], shell=True, cwd=cwd, capture_output=True, text=True)
    return {"id": task["id"], "passed": check.returncode == 0, "turns": turns,
            "wall_s": round(time.monotonic() - t0, 1), "check_out": (check.stdout + check.stderr)[-500:]}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config"); ap.add_argument("--temps", type=float, nargs="+", default=[0.2])
    ap.add_argument("--max-turns", type=int, default=15)
    args = ap.parse_args()
    wait_healthy()
    tasks = json.loads((pathlib.Path(__file__).parent / "agentic_tasks.json").read_text())
    out = {"config": args.config, "suite": "agentic", "temps": {}}
    for temp in args.temps:
        rs = [run_task(t, temp, args.max_turns) for t in tasks]
        out["temps"][str(temp)] = {"passed": sum(r["passed"] for r in rs), "of": len(rs), "tasks": rs}
    json.dump(out, sys.stdout, indent=2); print()

if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Smoke-test the suites against the already-loaded Ollama model** (Ollama speaks OpenAI-compat on :11434 — this validates harness code before any server work)

```bash
cd bench
python3 - <<'EOF'
import common
common.BASE = "http://127.0.0.1:11434"
common.wait_healthy(common.BASE)  # ollama /health may 404; if so, hit /v1/models instead and patch wait_healthy to accept it
body = common.chat([{"role":"user","content":"say hi"}], base=common.BASE, max_tokens=10)
print(body["choices"][0]["message"]["content"])
EOF
```

Expected: a greeting prints. Fix any API-shape issues now (e.g. Ollama needs `"model": "gemma4:12b-it-qat"` — make the model name a `common.MODEL` global set via env `BENCH_MODEL`, default `"local"`). This step exists to de-risk; suites run against llama-server (:8089) for real benchmarks.

- [ ] **Step 8: Commit**

```bash
git add bench/ && git commit -m "feat: throughput, toolcall, and agentic suites"
```

### Task 6: Config definitions + runner

**Files:** Create: `bench/configs.json`, `bench/run_config.sh`

- [ ] **Step 1: bench/configs.json** — exact server flags (model paths use the Task 3 cache names; fix up to actual filenames from `bench/models.lock`)

```json
{
  "_common": "--host 127.0.0.1 --port 8089 -ngl 99 --jinja -fa on",
  "C1-gemma12b-base":  "-m <CACHE>/gemma-4-12b-it-qat-Q4_0.gguf -c 32768 --temp 0.2",
  "C2-gemma12b-mtp":   "-m <CACHE>/gemma-4-12b-it-qat-Q4_0.gguf -md <CACHE>/mtp-gemma-4-12b-it.gguf --spec-type draft-mtp --spec-draft-n-max 2 -c 32768 --temp 0.2",
  "C3-gemma12b-par3":  "-m <CACHE>/gemma-4-12b-it-qat-Q4_0.gguf -c 49152 --parallel 3 --cache-type-k q8_0 --cache-type-v q8_0 --temp 0.2",
  "C4-gemma26b-gpu":   "-m <CACHE>/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf -c 32768 --temp 0.2",
  "C5-gemma26b-cmoe":  "-m <CACHE>/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf -cmoe -c 65536 --cache-type-k q8_0 --cache-type-v q8_0 --temp 0.2",
  "C6-gemma26b-cmoe-mtp": "-m <CACHE>/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf -cmoe -md <CACHE>/mtp-gemma-4-26B-A4B-it.gguf --spec-type draft-mtp --spec-draft-n-max 2 -c 65536 --cache-type-k q8_0 --cache-type-v q8_0 --temp 0.2",
  "C7-qwen27b-q3":     "-m <CACHE>/Qwen3.6-27B-Q3_K_M.gguf -c 32768 --temp 0.2",
  "C8-nex-mini-q3":    "-m <CACHE>/Nex-N2-mini-Q3_K_M.gguf -c 32768 --temp 0.2",
  "C9-qwen27b-q4":     "-m <CACHE>/Qwen3.6-27B-Q4_K_M.gguf -c 32768 --temp 0.2",
  "C10-qwen35b-a3b":   "-m <CACHE>/Qwen3.6-35B-A3B-Q4_K_M.gguf -c 32768 --temp 0.2",
  "C11-phi4mini":      "-m <CACHE>/phi-4-mini-Q4_K_M.gguf -c 16384 --temp 0.2"
}
```

- [ ] **Step 2: bench/run_config.sh**

```bash
#!/usr/bin/env bash
# Usage: bench/run_config.sh <config-name> [suite ...]   (default: throughput toolcall agentic)
set -euo pipefail
cd "$(dirname "$0")/.."
CFG="$1"; shift; SUITES=("${@:-throughput toolcall agentic}")
CACHE="$HOME/.cache/llama.cpp"
RAW="results/raw/$CFG"; mkdir -p "$RAW"

# pre-flight: GPU must be quiet (hermes-agent may inferr periodically)
for i in $(seq 1 30); do
  UTIL=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits)
  [ "$UTIL" -lt 10 ] && break; sleep 10
done
[ "$UTIL" -lt 10 ] || echo "WARN: gpu_contended" | tee "$RAW/contended.flag"

ollama stop gemma4:12b-it-qat 2>/dev/null || true   # evict anything ollama has resident
sleep 3
nvidia-smi --query-gpu=memory.used --format=csv,noheader | tee "$RAW/vram_before.txt"

FLAGS=$(python3 -c "import json;c=json.load(open('bench/configs.json'));print(c['_common'],c['$CFG'].replace('<CACHE>','$CACHE'))")
llama-server $FLAGS > "$RAW/server.log" 2>&1 &
SRV=$!; echo $SRV > results/.server.pid
trap 'kill $SRV 2>/dev/null || true' EXIT

python3 - <<'EOF'
import sys; sys.path.insert(0, "bench"); from common import wait_healthy; wait_healthy()
EOF
nvidia-smi --query-gpu=memory.used --format=csv,noheader | tee "$RAW/vram_loaded.txt"

for s in ${SUITES[@]}; do
  python3 "bench/$s.py" "$CFG" | tee "$RAW/$s.json"
done
python3 - "$CFG" <<'EOF'
import json, sys, pathlib
cfg = sys.argv[1]; raw = pathlib.Path(f"results/raw/{cfg}")
merged = {"config": cfg, "gpu_contended": (raw/"contended.flag").exists(),
          "vram_loaded": (raw/"vram_loaded.txt").read_text().strip()}
for f in raw.glob("*.json"):
    merged[json.loads(f.read_text())["suite"]] = json.loads(f.read_text())
pathlib.Path(f"results/{cfg}.json").write_text(json.dumps(merged, indent=2))
print("wrote", f"results/{cfg}.json")
EOF
kill $SRV; wait $SRV 2>/dev/null || true
```

- [ ] **Step 3: Make executable, commit**

```bash
chmod +x bench/run_config.sh
git add bench/configs.json bench/run_config.sh && git commit -m "feat: config matrix + GPU-serial runner"
```

### Tasks 7–11: Run configs C1–C8 (Phase 2, GPU-serial, one task per group)

Each task is the same shape; run them strictly in order. **Task 7:** C1, C2 (12B baseline + MTP — directly answers "is MTP worth it on workers"). **Task 8:** C3 (concurrency; throughput suite + toolcall only — agentic on 3 slots tells us nothing extra). **Task 9:** C4, C5, C6 (26B ladder — full-GPU vs cmoe vs cmoe+MTP; this answers the 8GB-senior question; for C8-class runs add `--temps 0.2 0.7` to toolcall/agentic to test the hot-temp recommendation). **Task 10:** C7 (Qwen senior). **Task 11:** C8 (Nex senior, sweep both temps).

- [ ] **Step 1 (repeat per config):** `bench/run_config.sh <CFG>` — expected: three JSONs under `results/raw/<CFG>/`, merged `results/<CFG>.json`, server log shows the expected flags (verify MTP runs log drafter acceptance stats; verify `-cmoe` runs show <9GB in `vram_loaded.txt`).
- [ ] **Step 2 (repeat per config):** sanity-read the numbers: decode_tps within 2× of public reports (12B ≈ 40–70; 26B cmoe ≈ 15–30); toolcall valid_rate not 0 (a 0 usually means chat-template/`--jinja` issues, not a dumb model — check `server.log` before blaming the model and rerun once fixed).
- [ ] **Step 3 (after each task's configs):** `git add results/*.json && git commit -m "bench: results for <configs>"` (raw/ is gitignored).

**MTP comparison note (C2, C6):** decode_tps speedup = C2/C1 and C6/C5 single-stream `p1k`. Calibration reference (Unsloth, CUDA GPUs, June 2026): QAT+MTP speedups of 1.94× (12B), 1.83× (26B-A4B), 2.21× (31B). If our Vulkan numbers land far below ~1.5×, suspect harness/backend issues before concluding MTP doesn't help. Drafter GGUFs are the `mtp-` prefixed files inside the regular model repos. Record drafter acceptance rate from server.log into the result JSON's `"notes"` field by hand-extraction (grep `accept` in the log — exact line format varies by build; quote it verbatim).

### Task 12: Coexistence test (the actual fleet layout)

- [ ] **Step 1:** Launch BOTH servers: C5 flags on port 8089 AND C1 flags on port 8090 with `--parallel 2 -c 32768 --cache-type-k q8_0 --cache-type-v q8_0`. Expected: both healthy; `nvidia-smi` total <22.5GB (record actual to `results/coexist.json` along with per-process MiB).
- [ ] **Step 2:** Run `throughput.py` against both **simultaneously** (`BENCH BASE` env: add `--port` arg or `BENCH_BASE` env to common.py if not already) — measures interference: senior decode while 2 worker streams generate. Record both outputs in `results/coexist.json`.
- [ ] **Step 3:** Run `miniagent.py` against the senior while a worker stream loops `throughput.py`. Passed-task count must match C5's solo run (quality shouldn't change — only speed). Commit results.

### Task 13: Aggregate + decide

- [ ] **Step 1:** Write `results/RESULTS.md`: one table (config × prefill/decode/x4-aggregate/toolcall@0.2/agentic-passed/VRAM), one MTP-speedup line, one coexistence section, then apply the Decision Rubric verbatim and assign roles. Where a config fails the rubric, say which threshold failed with the number.
- [ ] **Step 2:** `pytest -q` one final time; `git add results/RESULTS.md && git commit -m "docs: benchmark results and fleet role decision"`.
- [ ] **Step 3 (orchestrator):** review RESULTS.md against 3 spot-checked raw logs; update the `local-agents-fleet-research` memory with the verdict.

### Task 14 (stretch): C9–C11

Only if Phase 2 was clean. C9 needs a Q4_K_M Qwen3.6-27B download (~17GB) — alternatively point `-m` at the existing Ollama blob: `ollama show qwen3.6:27b-q4_K_M --modelfile | grep FROM` gives the blob path under `/usr/share/ollama/.ollama/models/blobs/` (works; blobs are plain GGUF). Same trick for C10. C11: `ollama show phi4-mini:3.8b --modelfile`. Then `bench/run_config.sh C9-qwen27b-q4` etc., commit as in Tasks 7–11.

---

## Self-Review Notes

- Spec coverage: throughput ✓ (Suite T + MTP deltas), tool-calling ✓ (Suite TC, temp sweep for Nex), agentic ✓ (Suite A), memory/coexistence ✓ (Task 12), all discussed models covered or explicitly excluded with reasons (DiffusionGemma, N2-Pro) ✓, role decision ✓ (rubric + Task 13).
- Known runtime unknowns, handled in-plan: exact HF repo/file names (Task 3 Step 1 verifies), llama.cpp asset name (Task 2 Step 1 lists assets), drafter acceptance log format (quote verbatim), Ollama health endpoint shape (Task 5 Step 7 smoke test).
- Type consistency: `score_toolcall(case, calls) -> (bool, str)` used identically in tests and suite; `parse_timings` keys (`prefill_tps`, `decode_tps`) match throughput.py usage; `TOOLS` imported from toolcall_suite by miniagent ✓.
