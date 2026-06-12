# Experiment Design: M1 Replay With Local Subagents

Date: 2026-06-12

Status: design only. Do not run this protocol from this document review. Do not start model servers, touch GPU state, or modify `~/src/custom_cad` while preparing this design.

## Purpose

Measure whether delegating implementation work to local model subagents reduces cloud-token cost and/or wall-clock time for a realistic coding milestone.

The test task is a replay of custom_cad M1, "A Box I Can Orbit", in a fresh workspace. M1 builds a TypeScript CAD kernel slice and viewport path:

`profile -> extrude -> half-edge B-rep -> validateSolid -> tessellate -> RenderData -> three.js viewport`

The pinned plan is:

`/home/svankina/src/custom_cad/docs/superpowers/plans/2026-06-11-m1-box-i-can-orbit.md`

Use `~/src/custom_cad` read-only as historical context only. The replay workspaces must be separate fresh git worktrees or clones.

## Prior Evidence

The local fleet benchmark in `/home/svankina/src/local_agents/RESULTS.md` found:

- Champion local model: `byteshape Qwen3.6-35B-A3B`.
- Best committed Vulkan result: 127.7 decode tokens/sec, tool-call score 1.000, agentic score 5/5.
- CUDA result around the C14 addendum: approximately 138-143 decode tokens/sec single-stream when available.
- llama.cpp multi-stream scaling was weak: x4 aggregate at or below about 1.27x single-stream for the relevant server shape.
- Therefore arm C should queue local workers serially against one native server instead of treating multiple concurrent local workers as independent throughput.

This experiment must record the serving configuration per run instead of baking a single backend into the conclusion. The hard requirement is bare metal: native host `llama-server`, no Docker.

## Hypotheses

H1: Local subagents reduce cloud output tokens and total cloud dollars versus cloud-only subagents because implementation drafts, test-fix loops, and file-search work move to local inference.

H2: Local subagents may not improve wall-clock time versus cloud subagents because local workers are queue-serial and slower per reasoning step than cloud workers.

H3: Claude solo has the most predictable quality but spends the most cloud tokens on implementation. Cloud subagents should be fastest when parallelism is effective, but also costly.

H4: Quality regressions will appear first as additional repair turns, failed `npm run check`, failed `test/integration/m1.test.ts`, or screenshot rejection. Counting only final pass/fail would hide this, so retries and repair time are first-class metrics.

## Arms

Run at least these three arms. Randomize arm order across repetitions.

| Arm | Name | Senior/orchestrator | Worker execution | Why included |
|---|---|---|---|---|
| A | Claude solo | Claude Code cloud model | None | Baseline for "just ask the senior model to implement the plan." |
| B | Claude + cloud subagents | Claude Code cloud model | Cloud subagents using the M1 plan's subagent-driven-development flow | Measures the already-used cloud delegation pattern. |
| C | Claude + local subagents | Claude Code cloud model | Bare-metal local Qwen3.6-35B workers through a Bash-shim subagent runner hitting native `llama-server` | Measures cloud-token savings from local delegation while keeping senior review/orchestration in cloud. |

Optional later arm, not part of the primary article chart: Claude Code with local subagents only for narrow repair tasks after a cloud implementation pass. This can test a hybrid that may be more practical than full local implementation delegation.

## Routing Mechanics

### Arm A: Claude Solo

The operator starts one Claude Code session in the fresh replay workspace and gives it the pinned M1 plan. The operator must instruct it not to use subagents and to implement task-by-task, running the specified gates.

All planning, file edits, test diagnosis, and repairs are cloud tokens.

### Arm B: Claude + Cloud Subagents

The operator starts one Claude Code senior session in the fresh replay workspace and uses the M1 plan's `superpowers:subagent-driven-development` flow. Workers are cloud subagents, not local processes.

Use the same task partition as arm C:

- Worker job 1: Task 1 scaffold.
- Worker job 2: Tasks 2-4 numeric/vector/profile/result.
- Worker job 3: Task 5 B-rep and `validateSolid`.
- Worker job 4: Task 6 `extrude`.
- Worker job 5: Task 7 tessellation.
- Worker job 6: Tasks 8-9 viewport, scene sync, M1 acceptance.

Allow cloud workers to run concurrently if the subagent framework supports it. Record actual overlap in the trace.

### Arm C: Claude + Local Subagents

The senior/orchestrator remains Claude Code. Local implementation workers run through a Bash-shim subagent command. The shim is the credible integration point because the local benchmark harness already speaks OpenAI-compatible chat to `llama-server`, while Claude Code subagent transport is not assumed to be replaceable with an Anthropic-compatible endpoint.

Do not use Docker. Do not use Ollama as the serving backend for measured runs. Ollama may be used only outside measured windows to inspect local blobs if needed.

Pre-registered local serving parameters, recorded per run:

```json
{
  "local_server": {
    "backend": "vulkan|cuda",
    "llama_cpp_build": "b9596 or exact git/tag/build id",
    "llama_server_path": "/absolute/path/to/llama-server",
    "model_repo_or_path": "byteshape/... or absolute GGUF path",
    "model_sha256": "sha256 of GGUF",
    "flags": ["-m", "...", "-c", "32768", "--temp", "0.2", "..."],
    "port": 8089,
    "parallel_slots": 1,
    "gpu_name": "RTX 3090 Ti",
    "driver_version": "recorded by operator",
    "server_log": "results/experiments/m1-replay/<run_id>/llama-server.log",
    "metrics_endpoint": "http://127.0.0.1:8089/metrics if enabled"
  }
}
```

Recommended initial server shape:

- Model: byteshape Qwen3.6-35B-A3B GGUF used for C12, or the exact successor if the run preregisters it.
- Context: 32768 tokens unless the pilot shows M1 worker prompts need more.
- Temperature: 0.2.
- Slots: `--parallel 1`, queue-serial.
- Backend priority: native CUDA if a verified build exists by experiment time; otherwise prebuilt Vulkan b9596.

Server setup template for the operator to run during the actual experiment:

```bash
export M1_LLAMACPP=/absolute/path/to/native/llama.cpp
export M1_MODEL=/absolute/path/to/model.gguf
export M1_PORT=8089

sha256sum "$M1_MODEL"
"$M1_LLAMACPP/llama-server" --version
"$M1_LLAMACPP/llama-server" \
  -m "$M1_MODEL" \
  -c 32768 \
  --parallel 1 \
  --temp 0.2 \
  --host 127.0.0.1 \
  --port "$M1_PORT" \
  --metrics \
  > "results/experiments/m1-replay/$RUN_ID/llama-server.log" 2>&1
```

The exact flags used in the measured run override this template and must be saved in `run.json`.

Local worker shim contract:

```bash
scripts/m1-local-worker \
  --base-url "http://127.0.0.1:8089/v1" \
  --model "local" \
  --workspace "$WORKSPACE" \
  --plan "$PINNED_PLAN_COPY" \
  --job "$JOB_JSON" \
  --out "$RUN_DIR/workers/job-03"
```

Expected shim behavior:

- Read only the assigned job, the pinned plan copy, and the current replay workspace.
- Send OpenAI-compatible chat completions to native `llama-server`.
- Use a minimal tool loop with `read_file`, `list_files`, `apply_patch`, and `run_bash` scoped to the replay workspace.
- Produce `worker.patch`, `worker.md`, `transcript.jsonl`, token counts, and command log.
- Never write outside the replay workspace or `results/experiments/m1-replay/<run_id>/workers/<job_id>`.
- Exit nonzero if it cannot produce a patch or if its assigned gate fails.

The Claude senior applies or rejects each worker patch, runs review and gates, and queues the next local worker. Because multi-stream scaling is weak, do not run two local workers at once against the same server for primary runs.

## Environment

Each run gets a fresh replay workspace outside `~/src/custom_cad`, for example:

```bash
export RUN_ID="2026-06-12-A-01"
export REPLAY_ROOT="/home/svankina/src/local_agents/.worktrees/m1-replay/$RUN_ID/custom_cad"
export RUN_DIR="/home/svankina/src/local_agents/results/experiments/m1-replay/$RUN_ID"
export CUSTOM_CAD_SOURCE="/home/svankina/src/custom_cad"
export PINNED_PLAN="$RUN_DIR/inputs/2026-06-11-m1-box-i-can-orbit.md"

mkdir -p "$RUN_DIR/inputs" "$(dirname "$REPLAY_ROOT")"
cp "$CUSTOM_CAD_SOURCE/docs/superpowers/plans/2026-06-11-m1-box-i-can-orbit.md" "$PINNED_PLAN"
git -C "$CUSTOM_CAD_SOURCE" rev-parse HEAD > "$RUN_DIR/inputs/custom_cad_source_head.txt"
git init "$REPLAY_ROOT"
```

The actual run must not modify `~/src/custom_cad`. If a git worktree is preferred, create it from a bare mirror or a separate clone, not by checking out changes in the owner's live tree.

Pinned inputs per run:

- Exact M1 plan file copied into `RUN_DIR/inputs/`.
- Exact senior prompt and worker prompts.
- Same skill set and allowed tools for all arms, except worker routing differs by arm.
- Same Node/npm versions if possible, recorded via `node --version` and `npm --version`.
- Same package manager behavior: run `npm install` when Task 1 requires it, do not reuse `node_modules`.

Memory hygiene:

- Start from a Claude Code session without project-specific memory from previous M1 runs.
- Disable or clear repo-local memories that mention the original M1 implementation.
- The senior may read the pinned plan, but should not inspect the old implementation commits during a measured run.
- Operator notes may include historical commit SHAs for analysis, but agents must not use them as implementation source.

## Metrics

### Primary Metrics

- Wall-clock total (time to completion): from first agent prompt after workspace creation to accepted M1 exit.
- Wall-clock per M1 task: Tasks 1 through 9 from the pinned plan.
- Total tokens used: cloud input/output/cache-read/cache-write tokens and USD cost; local prompt/completion tokens; and the combined per-run total.
- Average tokens/sec, reported at two levels that must not be conflated:
  - generation rate: completion tokens / model busy time (server-side timings) — measures the serving stack;
  - effective pipeline rate: total tokens / run wall-clock — measures the whole loop including tool execution and orchestration overhead.
- Time spent idling (see Time Accounting below).
- Time spent thinking: reasoning-channel time and tokens, per tier (see Time Accounting).
- Quality result: pass/fail plus number of repair loops.

### Time Accounting

Decompose each run's wall clock into non-overlapping buckets so "where did the time go" has a defensible answer. Derive the segmentation by joining per-request timestamps (server logs / OTEL events) with the telemetry timeline:

- `t_generating`: a model (cloud or local) is actively decoding. Split into `t_thinking` (reasoning-channel tokens: `reasoning_content` deltas locally; thinking blocks in cloud usage events) and `t_visible` (everything else). Where the API reports only token counts, estimate time as tokens / that request's measured decode rate and mark the estimate.
- `t_prefill`: prompt processing time on the local server (from `prompt eval` timings); fold cloud prefill into `t_api_wait` since it is not separable client-side.
- `t_tool_exec`: time between a tool call being issued and its result being returned (test runs, file edits, bash commands). Dominated by `npm run check` and vitest in this workload.
- `t_api_wait`: cloud round-trip latency not attributable to generation (queueing, network).
- `t_idle`: none of the above — the orchestrator is deciding, the queue is empty, or a worker waits on the serial slot. For arm C also report GPU-idle%: fraction of run wall-clock where GPU util < 10% while at least one worker task is pending (from telemetry join); this is the queue-serial contention signal.
- Sanity rule: buckets + residual must sum to wall-clock within 2%; report the residual.

### Throughput and Efficiency Metrics

- Per-request: time-to-first-token, decode t/s, prompt t/s, prompt size, completion size (local: server `timings`; cloud: OTEL event timing where available).
- Context growth: prompt tokens per successive request within a task (context-bloat indicator) and cache-hit fraction.
- Tokens per accepted task and per repair loop: rework cost in tokens, cloud vs local.
- Turns per task; tool calls per task; tool-call error rate during the real run (malformed call, nonexistent path, wrong-tool retries).
- Energy (article-friendly): integrate GPU power draw over the run (W → Wh) from telemetry; report Wh per run and Wh per accepted task for arm C, and estimated USD at the local electricity rate. Cloud arms get USD only.

### Hardware Telemetry

Run a sampler for the entire measured window of every run, all arms (baseline arms establish what "cloud-only" load looks like). Sampler: `scripts/telemetry_sampler.py` (to be written at setup; ~50 lines, psutil + nvidia-smi), 1 Hz, appending CSV rows to `results/experiments/m1-replay/<run_id>/telemetry.csv`:

- `ts` (ISO 8601, monotonic offset also recorded)
- GPU (RTX 3090 Ti via `nvidia-smi --query-gpu`): `gpu_util_pct`, `vram_used_mib`, `power_w`, `temp_c`, `sm_clock_mhz` (thermal-throttle detection)
- CPU: `cpu_util_pct` overall, `load1`, plus per-core utilization vector (worker tokenization and `npm run check` are CPU-side)
- Memory: `ram_used_gib`, `ram_available_gib`, `swap_used_gib`
- Disk: `io_read_mb_s`, `io_write_mb_s` (model load and npm install phases)
- Network: `net_rx_kb_s`, `net_tx_kb_s` (cloud-arm dependence; also catches registry stalls)

Derived per run (computed in analysis, stored in the run JSON): peak/mean VRAM, mean GPU util during `t_generating` vs overall, GPU-idle% as defined above, peak RAM, mean/peak CPU util, total GPU Wh, max temp and any throttle events, and the peak-throughput fields below. Telemetry alone must never be used to *infer* token counts — it contextualizes the primary metrics.

### Peak Throughput (max tokens/sec)

Log and report maximum tokens/sec per run, not just means/medians:

- `max_decode_tps_single`: highest per-request decode rate (server `timings.predicted_per_second`, or client usage/wall fallback), with the request id and prompt/completion sizes that produced it.
- `max_aggregate_tps_1s`: highest 1-second total completion-token throughput across all concurrent streams, derived in analysis from per-request start/end timestamps and completion token counts (assume uniform emission within a request; mark as derived). This is the burst ceiling number.
- `max_prefill_tps`: highest per-request prompt-processing rate, same sourcing rules.

All three go in `run.json` and the results tables alongside the medians.

### Telemetry Overhead Budget (do not slow the test down)

Instrumentation must be passive. Rules:

- One sampler process for the whole run, started before and killed after the measured window. Use streaming collectors, not per-sample forks: a single `nvidia-smi --query-gpu=... --format=csv,noheader -l 1` child plus psutil in-process — never spawn nvidia-smi per tick.
- Run the sampler at `nice 19` (and `ionice -c3` where available); buffered CSV appends, no fsync; flush on exit.
- 1 Hz fixed. No per-token or per-line hooks anywhere on the serving hot path; the local server runs at default log verbosity (no `-lv` debug levels), and `/metrics` is scraped only at job boundaries, never mid-generation.
- OTEL/event logging must use async/batched export; if only synchronous export is available, write to local file and ship after the run.
- Pre-flight validation (once, before arm runs start): run a short fixed workload (e.g. 3× p1k generation against the arm-C server) with telemetry on and off; require wall-clock delta < 2% and sampler CPU < 1% of one core (check via `pidstat`). Record the validation numbers in the experiment log. If the budget is exceeded, reduce to 0.5 Hz or trim columns before touching anything else.

### Instrumentation

Wall clock:

- Wrap every task/job in a timestamped trace entry.
- Use monotonic time when available and save ISO wall time for readability.
- Record `task_start`, `task_first_patch`, `task_gate_start`, `task_gate_end`, and `task_accepted`.

Cloud tokens and dollars:

- Prefer Claude Code OpenTelemetry if available, exported to the run directory.
- Also run `ccusage` or the provider/API usage export after each run and save raw output.
- Required fields: model, input tokens, output tokens, cache creation/read tokens if reported, billable cost in USD, and collection method.
- If the collection source gives only session-level totals, mark per-task token fields as null and keep session totals authoritative.

Local tokens:

- Save `llama-server.log` for the full run.
- If `--metrics` is enabled, scrape `/metrics` before and after each worker job and save snapshots.
- Save each worker's OpenAI-compatible response `usage` object when present.
- Reconcile three sources in analysis: response usage, server log timings, and metrics counters.

Quality gates:

```bash
npm run check
npx vitest run test/integration/m1.test.ts
```

Screenshot acceptance:

- Start the dev server only during the actual measured run's visual verification window.
- Capture at least one desktop screenshot named `m1-box-<run_id>.png`.
- Acceptance criteria: shaded 4x3x5 prism, crisp black edges, grid visible, z-up orientation, orbit interaction works, no hardcoded mesh bypassing the kernel pipeline.
- Store screenshots under `results/experiments/m1-replay/<run_id>/screenshots/`.

Additional quality signals:

- Count TypeScript errors encountered before final pass.
- Count vitest failures before final pass.
- Count import-boundary violations from `scripts/check-three-imports.sh`.
- Count senior rejections of worker patches.
- Record whether the final implementation contains the expected files, especially `test/integration/m1.test.ts`, `src/kernel/extrude.ts`, `src/kernel/tess.ts`, and `src/app/viewport/sceneSync.ts`.

## Repetitions and Success Criteria

Run `N >= 3` successful attempts per arm. Because the benchmark suite showed high run-to-run variance, prefer `N = 5` if operator time allows.

Pre-register these success criteria:

- Quality success: final `npm run check` passes, `npx vitest run test/integration/m1.test.ts` passes, screenshot accepted, and no architecture violation is found.
- Cost win for arm C: median cloud USD at least 40% lower than arm B and at least 25% lower than arm A, among quality-successful runs.
- Wall-clock win for arm C: median total wall-clock at least 10% lower than arm A. Arm C is not required to beat arm B to be article-worthy if cost savings are large.
- Robustness: arm C quality success rate at least 2/3 for `N=3` or at least 4/5 for `N=5`.

Report medians, min/max, and every failed run. Do not discard failures unless the preregistered exclusion rules apply.

Exclusion rules:

- Infrastructure outage unrelated to the arm, such as npm registry unavailable for all arms.
- Operator accidentally uses the wrong workspace or modifies `~/src/custom_cad`.
- Local server launched with unrecorded flags in arm C.
- Cloud usage instrumentation fails completely and cannot be reconstructed.

Do not exclude runs merely because the agent made poor implementation choices.

## Confounds and Mitigations

Prompt-cache effects:

- Randomize arm order.
- Record cache-read and cache-write tokens separately.
- Analyze both gross cloud cost and non-cache cloud cost if available.

Plan familiarity leakage:

- Use clean sessions.
- Do not expose original M1 implementation commits to agents.
- Keep the pinned plan identical across arms.
- Use the same senior prompt except for the routing instructions.

Nondeterminism:

- Use `N >= 3`, preferably `N = 5`.
- Keep local temperature fixed at 0.2.
- Record cloud model versions and dates.

Network variance:

- Cloud arms depend on network latency; arm C still depends on cloud senior calls.
- Run arms interleaved over similar time windows.
- Record start time, end time, and provider incidents if known.

GPU thermal and occupancy state:

- Arm C must use a bare-metal server with no unrelated GPU workload beyond normal desktop use.
- Record idle GPU temperature and power before server launch and after each worker job.
- Do not run concurrent local workers in primary runs.
- Include warm-up policy in `run.json`; if a warm-up request is used, use it for every arm C run and exclude its time from worker wall-clock only if preregistered.

Filesystem and dependency cache:

- Fresh workspace and fresh `node_modules` per run.
- npm download cache may exist globally; record whether the package lock was generated and npm install duration separately.

Human steering:

- Use a fixed intervention policy: the operator may only paste predefined correction prompts when an agent violates scope, stalls, or fails a gate twice.
- Record every human intervention in `events.jsonl`.

Quality hidden by retries:

- Preserve failed patches, test logs, and repair loops.
- Article charts should show both final pass rate and median repair count.

## Runbook

### 1. Prepare Run Metadata

```bash
export ARM="C"
export REP="01"
export RUN_ID="2026-06-12-${ARM}-${REP}"
export RUN_DIR="/home/svankina/src/local_agents/results/experiments/m1-replay/$RUN_ID"
export REPLAY_ROOT="/home/svankina/src/local_agents/.worktrees/m1-replay/$RUN_ID/custom_cad"
mkdir -p "$RUN_DIR"/{inputs,logs,workers,screenshots}
```

Create `run.json` before the agent starts:

```json
{
  "run_id": "2026-06-12-C-01",
  "arm": "C",
  "rep": 1,
  "status": "planned",
  "operator": "",
  "started_at": null,
  "ended_at": null,
  "workspace": "",
  "pinned_plan_sha256": "",
  "custom_cad_source_head": "",
  "senior_model": "",
  "worker_model": "",
  "local_server": null,
  "node_version": "",
  "npm_version": "",
  "success": null,
  "exclusion_reason": null
}
```

### 2. Create Fresh Workspace

```bash
cp /home/svankina/src/custom_cad/docs/superpowers/plans/2026-06-11-m1-box-i-can-orbit.md "$RUN_DIR/inputs/"
sha256sum "$RUN_DIR/inputs/2026-06-11-m1-box-i-can-orbit.md" > "$RUN_DIR/inputs/plan.sha256"
git -C /home/svankina/src/custom_cad rev-parse HEAD > "$RUN_DIR/inputs/custom_cad_source_head.txt"
git init "$REPLAY_ROOT"
node --version > "$RUN_DIR/inputs/node.version"
npm --version > "$RUN_DIR/inputs/npm.version"
```

### 3. Start Instrumentation

```bash
date -Is | tee "$RUN_DIR/started_at.txt"
# Enable Claude Code OTEL or the local equivalent here.
# Start a small event logger or append JSON lines manually to "$RUN_DIR/events.jsonl".

# Hardware telemetry sampler (all arms), 1 Hz for the whole measured window:
python3 scripts/telemetry_sampler.py --out "$RUN_DIR/telemetry.csv" &
echo $! > "$RUN_DIR/.telemetry.pid"
```

For arm C only, start the preregistered native `llama-server` manually and save its log path in `run.json`. Do not use Docker.

### 4. Execute the Arm

Arm A prompt template:

```text
Implement the pinned M1 plan in this fresh workspace. Work task-by-task.
Do not use subagents. Run the gates specified by the plan. Record task timing markers.
```

Arm B prompt template:

```text
Implement the pinned M1 plan in this fresh workspace using cloud subagents.
Use the six predefined worker jobs. The senior must review every worker patch,
run the specified gates, and record task timing markers.
```

Arm C prompt template:

```text
Implement the pinned M1 plan in this fresh workspace. Use local subagents only
through scripts/m1-local-worker for the six predefined worker jobs. Queue local
workers serially. The senior must review every worker patch, run the specified
gates, and record task timing markers. Do not inspect ~/src/custom_cad except
for the pinned plan copy already in the run directory.
```

### 5. Gate and Screenshot

```bash
cd "$REPLAY_ROOT"
npm run check 2>&1 | tee "$RUN_DIR/logs/npm-run-check-final.log"
npx vitest run test/integration/m1.test.ts 2>&1 | tee "$RUN_DIR/logs/m1-integration-final.log"
npm run dev 2>&1 | tee "$RUN_DIR/logs/npm-run-dev.log"
# Capture screenshot m1-box-$RUN_ID.png during the measured visual-verification window.
```

Stop the dev server after screenshot capture.

### 6. Collect Usage

```bash
# Cloud usage, depending on available tooling:
ccusage --json > "$RUN_DIR/cloud-usage.ccusage.json"
# Or export Claude Code OTEL/API usage to "$RUN_DIR/cloud-usage.otel.jsonl".

# Arm C:
curl -s "http://127.0.0.1:$M1_PORT/metrics" > "$RUN_DIR/local-metrics-final.prom"
```

### 7. Finalize

```bash
git -C "$REPLAY_ROOT" status --short > "$RUN_DIR/final-git-status.txt"
git -C "$REPLAY_ROOT" log --oneline --decorate --all > "$RUN_DIR/final-git-log.txt"
kill "$(cat "$RUN_DIR/.telemetry.pid")" 2>/dev/null || true
date -Is | tee "$RUN_DIR/ended_at.txt"
```

Update `run.json` with success/failure, exclusion reason if any, all usage totals, the time-accounting buckets (`t_generating` split into thinking/visible, `t_prefill`, `t_tool_exec`, `t_api_wait`, `t_idle`, residual), both tokens/sec levels (generation rate and effective pipeline rate), and the derived telemetry summary (peak/mean VRAM, mean GPU util during generation, GPU-idle%, peak RAM, mean/peak CPU, GPU Wh, max temp/throttle events).

## Results Schema

Store one JSON object per run at:

`results/experiments/m1-replay/<run_id>/run.json`

Minimum schema:

```json
{
  "run_id": "2026-06-12-C-01",
  "arm": "C",
  "rep": 1,
  "status": "completed",
  "success": true,
  "excluded": false,
  "exclusion_reason": null,
  "started_at": "2026-06-12T10:00:00+05:30",
  "ended_at": "2026-06-12T12:20:00+05:30",
  "wall_clock_seconds": 8400,
  "workspace": "/home/svankina/src/local_agents/.worktrees/m1-replay/2026-06-12-C-01/custom_cad",
  "tasks": [
    {
      "task": 1,
      "name": "Project scaffold",
      "started_at": "",
      "accepted_at": "",
      "wall_clock_seconds": null,
      "worker_kind": "none|cloud|local",
      "repair_loops": 0,
      "gate_passed": true
    }
  ],
  "cloud_usage": {
    "source": "otel|ccusage|api_export",
    "input_tokens": null,
    "output_tokens": null,
    "cache_creation_tokens": null,
    "cache_read_tokens": null,
    "usd": null
  },
  "local_usage": {
    "source": "llama_server_logs|metrics|response_usage",
    "input_tokens": null,
    "output_tokens": null,
    "decode_tokens_per_second_median": null,
    "active_seconds": null
  },
  "quality": {
    "npm_run_check": "pass",
    "m1_integration": "pass",
    "screenshot": "accepted",
    "screenshot_path": "screenshots/m1-box-2026-06-12-C-01.png",
    "typescript_error_count_before_final": 0,
    "vitest_failure_count_before_final": 0,
    "import_guard_failure_count_before_final": 0,
    "senior_patch_rejections": 0
  },
  "local_server": {
    "backend": "vulkan",
    "llama_cpp_build": "b9596",
    "model_sha256": "",
    "flags": [],
    "parallel_slots": 1
  }
}
```

Also maintain an aggregate file:

`results/experiments/m1-replay/summary.json`

with one row per run and derived medians by arm.

## Estimated Cost and Time

These are planning estimates, not conclusions.

| Arm | Estimated wall-clock | Estimated cloud cost | Notes |
|---|---:|---:|---|
| A Claude solo | 2-5 hours | High | No delegation overhead, but all exploration and repair is cloud. |
| B cloud subagents | 1-3 hours | Highest | Parallel workers may reduce time but duplicate context and generate more cloud tokens. |
| C local subagents | 2-6 hours | Low to medium | Senior remains cloud; local workers queue serially. Wall-clock may be worse while cloud spend falls. |

For arm C, local electricity cost can be estimated after the run from GPU power telemetry and active seconds, but the article's main cost metric should be cloud-token dollars because that is directly comparable across arms.

## Analysis Plan

Primary chart:

- X-axis: arm.
- Left Y-axis: median wall-clock time.
- Right Y-axis or adjacent bars: median cloud USD.
- Mark failed runs and repair loops visibly.

Secondary charts:

- Cloud input/output/cache tokens by arm.
- Local tokens and active server time for arm C.
- Task-level Gantt chart showing where queue-serial local work helped or hurt.
- Quality funnel: attempted runs -> final gate pass -> screenshot accepted.

Report:

- Median and range, not just best run.
- All excluded runs with reasons.
- Whether arm C's savings came from true token displacement or from cache effects.
- Whether wall-clock changed because of parallelism, model speed, or repair loops.

## Article Outline

1. Question: can a workstation GPU replace cloud subagents for real coding work?
2. Setup: M1 replay, why it is a representative CAD/kernel/frontend milestone.
3. Arms: Claude solo, Claude with cloud subagents, Claude orchestrating local Qwen workers.
4. Local serving: bare-metal `llama-server`, recorded backend/build/flags/model SHA; Vulkan b9596 as known baseline, CUDA if preregistered and verified.
5. Money chart: wall-clock versus cloud dollars, with pass/fail markers.
6. What got cheaper: cloud implementation tokens displaced by local worker tokens.
7. What did not get cheaper: senior review, prompt cache writes, failed repair loops, and visual acceptance.
8. Honest caveats:
   - Local workers may save money but lose wall-clock due to queue-serial serving.
   - Final success can hide quality regressions if retries are ignored.
   - Prompt-cache effects can make cloud arms look cheaper unless cache tokens are separated.
   - A single successful run is not enough because agentic variance is high.
   - CUDA versus Vulkan changes speed, so backend/build must be a recorded variable.
9. Practical recommendation: when local subagents are worth it, when cloud subagents are still better, and what workflow changes would improve the local arm.

