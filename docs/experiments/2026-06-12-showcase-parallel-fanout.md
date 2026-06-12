# Experiment Design: Showcase Parallel Fan-Out — Docstring Backfill at 8-Stream Saturation

Internal id: `fanout`. Run dirs and result paths use the slug, e.g. `results/experiments/fanout/<run_id>/`.

Date: 2026-06-12

Status: design only. Do not run this protocol from this document review. Do not start model servers or touch GPU state while preparing this design.

## Purpose and Framing

This is the **showcase workload**: a task engineered to demonstrate the local fleet's design point — many independent single-shot jobs saturating 8 concurrent vLLM streams — in the most favorable honest light. The task was *selected to fit the measured strengths* of the serving config, and the article must say so explicitly.

It **complements, not replaces,** the preregistered CAD kernel experiment (`docs/experiments/2026-06-12-m1-replay-local-subagents.md`). The CAD replay measures the hard general case (multi-turn agentic implementation work); this experiment measures the favorable case (embarrassingly parallel single-shot work). The article must present both: the CAD replay bounds what the fleet *cannot* yet do, this benchmark shows what it *can*.

Two claims this experiment is built to measure:

1. **Speedup**: `speedup = wall_solo / wall_fleet` on identical work items with identical verification.
2. **Cloud-token savings**: `savings = (cloud_tokens_solo - cloud_tokens_fleet) / cloud_tokens_solo`, with the fleet arm's supervisor budgeted at two cloud calls by design.

## The Serving Config Being Showcased (C18)

From `RESULTS.md`, C18 Qwen3-30B-A3B GPTQ under vLLM:

- Model: `Qwen/Qwen3-30B-A3B-GPTQ-Int4` at revision `9b534e4318b7ebc3c961a839f13eb18b1833f441`.
- Server: vLLM 0.22.1 (`vllm/vllm-openai:v0.22.1`), flags `--max-model-len 16384 --max-num-seqs 8 --gpu-memory-utilization 0.92 --quantization gptq_marlin --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3`. 56,080 GPU KV-cache tokens; 22,173 MiB VRAM loaded.
- Measured strengths: 808.7 aggregate t/s at x8 (4.40x scaling, 101.3 t/s per stream), 534.4 at x4, 183.8 t/s single-stream p1k; toolcall 0.972 strict at temp 0.2.
- Measured weakness: multi-turn agentic loops. Three agentic runs scored 3/5, 1/5, 2/5 (median 2/5); `csv-script` and `add-flag` failed in all three runs — systematic, not variance.

Design constraints that follow directly from this data:

1. **Embarrassingly parallel**: ≥8 independent items, ideally 16-32, so the pool stays saturated through stragglers. Zero cross-item dependencies.
2. **Single-shot per item**: one prompt → one structured response. Never a multi-turn repair loop — that is the measured weakness.
3. **Mechanically verifiable per item without model judgment**: deterministic script checks only, so the quality score is a number nobody can dispute and the cloud supervisor is not needed for grading.
4. **Minimal supervisor by design**: exactly one decomposition call up front and one synthesis call at the end. Everything between is local.
5. **Per-item context budget**: 56,080 KV tokens / 8 streams ≈ 7k tokens per stream. Item prompts must be capped well under that.

## Candidate Tasks Considered

Scored 1-5 against: (1) parallel decomposition, (2) single-shot fit, (3) mechanical verifiability, (4) minimal-supervisor fit, (5) looks like real work.

| Candidate | (1) | (2) | (3) | (4) | (5) | Total | Disqualifying concern |
|---|---:|---:|---:|---:|---:|---:|---|
| A. Typed API clients from N OpenAPI specs, checked by `tsc` | 4 | 3 | 5 | 4 | 5 | 21 | Real specs are large: prompt + generated client can blow the ~7k/stream KV budget at x8, and a *compilable* client in one shot is a high-failure ask — the showcase would be fighting the context limit and its own pass rate. |
| B. Per-file docstring backfill on a real OSS repo, checked by AST-based scripts | 5 | 5 | 5 | 5 | 4 | 24 | Realism is a 4, not 5 — doc backfill is genuine maintenance work but less glamorous than codegen. Accepted. |
| C. Structured extraction over N long documents, checked by JSON Schema | 5 | 5 | 4 | 5 | 3 | 22 | Schema validation checks shape, not truth; grounding via verbatim-substring checks helps but the quality number stays softer, and the task reads as a toy. |

**Winner: B — per-file docstring backfill.** It is the only candidate where every constraint scores 5 where it matters: items are single source files (perfectly independent), the response is a small JSON object (single-shot, low completion tokens, far from the KV ceiling), and verification is airtight stdlib-Python AST work (parse + coverage + AST-equivalence + parameter-mention), requiring zero model judgment. Crucially, the worker never edits files or runs commands — it emits docstring text; deterministic scripts do the insertion and checking. This eliminates the exact failure modes C18 showed in `csv-script`/`add-flag` (multi-turn tool-loop repair).

## Task Specification

### Corpus (pinned, validated)

- Repo: `https://github.com/scrapy/scrapy.git`
- Pinned SHA: `a8ffdcf8517a8973391a14635234b6993b15a86a` (HEAD on 2026-06-12; nearest release tag `2.13.3` = `482feba192d63a56c1ef3401c0f060dfbe920dde`). Clone with `git clone <url> && git checkout a8ffdcf851...` or `git fetch origin a8ffdcf851... && git checkout FETCH_HEAD`.
- License: BSD-3-Clause (backfilling docstrings on it is plausible real maintenance work).
- **Design-time validation (performed for this document, no servers involved)**: an AST scan of `scrapy/` at the pinned SHA found **80 files** with ≥3 public symbols (functions/classes/methods whose names do not start with `_`) missing docstrings, within 50-400 lines. Top of the distribution: `scrapy/exporters.py` (26 missing), `scrapy/http/cookies.py` (26), `scrapy/statscollectors.py` (19). 32 work items are comfortably available.

### Work-item generator — `scripts/fanout/make_items.py` (spec; do not write yet)

Deterministic script, no model calls.

- Inputs: `--corpus <path>` (fresh clone at pinned SHA; script verifies `git rev-parse HEAD` matches), `--count 32`, `--out <run_dir>/items/`.
- Selection: walk `scrapy/**/*.py`; keep files with 50-400 lines, ≥3 missing public docstrings (module-level and nested `def`/`async def`/`class`, name not starting with `_`, `ast.get_docstring(...) is None`), and estimated prompt tokens ≤ 4,500 (estimate: `len(source)/3.5` + 600 template overhead). Rank by missing-docstring count descending, take top `--count`. Ties broken by path sort for determinism.
- Output per item: `items/item-NN.json`:

```json
{
  "id": "item-07",
  "path": "scrapy/statscollectors.py",
  "file_sha256": "<sha256 of file content at pinned SHA>",
  "targets": ["StatsCollector", "StatsCollector.get_value", "..."],
  "line_count": 135,
  "est_prompt_tokens": 2300
}
```

- Plus `items.lock.json`: corpus URL, pinned SHA, generator git SHA, item list with file hashes. This lock file is the single source of truth for both arms.

### Worker prompt template

One user message per item (system prompt fixed across items):

```text
SYSTEM:
You write Python docstrings. You will receive one Python source file and a list
of target symbols (functions, methods, classes) that lack docstrings. Respond
with a single JSON object and nothing else:
{"docstrings": {"<qualname>": "<docstring text>", ...}}
Rules: one entry per target, no extra keys. Docstrings must be plain text
(no surrounding quotes), accurate to the code, and for every function or
method must mention each named parameter (excluding self and cls). Do not
restate the code. Do not include reasoning.

USER:
File: {path}
Targets ({n}): {qualname_list}

<file>
{full file content}
</file>
```

Request parameters: `temperature 0.2`, `max_tokens 2048`, `response_format {"type": "json_object"}` if the server accepts it (record acceptance; fall back to fenced-JSON extraction otherwise), and thinking disabled via `chat_template_kwargs: {"enable_thinking": false}` (fallback: append `/no_think`; record which path was used). The C18 take-3 gate failure — reasoning tokens exhausting the budget — is exactly the trap the thinking-disable avoids.

### Worker shim — `scripts/fanout/fanout-worker` (spec; do not write yet)

A single-shot derivative of `scripts/m1-local-worker`, **reusing its conventions verbatim**: per-job out dir, `transcript.jsonl` with `request`/`response` records carrying `_client_wall_s`, `tokens.json` written by the same `write_tokens` logic (prompt/completion totals plus per-request records), nonzero exit on failure. Differences from the m1 shim:

- Exactly one chat request. No `tools` array, no tool loop, no `--max-turns`.
- No workspace mutation: the worker reads nothing and writes nothing outside its out dir. File content arrives embedded in the prompt; the response JSON is saved as `response.json`.
- Exit 0 iff the response parsed as the required JSON shape (insertion/verification happen downstream in the dispatcher).

CLI: `fanout-worker --base-url http://127.0.0.1:8000/v1 --model <served-name> --item items/item-NN.json --corpus <corpus> --out <run_dir>/workers/item-NN-attempt-1`.

### Insertion — `scripts/fanout/insert_docstrings.py` (spec)

Deterministic, stdlib-only. Takes the pristine file plus the worker's `{"docstrings": {...}}`, locates each target symbol's body start via `ast`, inserts a correctly indented string literal as the first statement, writes the modified file to a scratch copy (never the corpus clone). Fails loudly on: unknown qualname, non-string value, missing target. By construction it can only add docstrings — it cannot change code.

### Per-item verification — `scripts/fanout/verify_item.py` (spec)

Deterministic, stdlib-only, zero model judgment. For each item, against the scratch copy:

1. **Insertion clean**: `insert_docstrings.py` exited 0.
2. **Compiles**: `python3 -m py_compile <modified file>` exits 0.
3. **Coverage**: every qualname in the item's `targets` list now has `ast.get_docstring(...) is not None`. 100% required.
4. **AST equivalence**: strip all docstrings from both the modified and pristine file, compare `ast.dump(...)` — must be identical. (Guaranteed by the inserter's construction; kept as belt-and-braces against inserter bugs.)
5. **Parameter mention**: for each target function/method, the docstring must contain every named parameter (excluding `self`/`cls`; `*args`/`**kwargs` by bare name) as a word-boundary token. Classes exempt.
6. **Non-placeholder**: each docstring ≥ 20 characters, does not match `(?i)\b(todo|tbd|fixme|placeholder)\b`.

Output: `verify.json` per item attempt with pass/fail and the first failing check. The run-level `scorecard.json` aggregates: per-item status, attempts used, failure reasons. **Score = items passed / 32.** Nothing in the scorecard requires model judgment.

### Retry policy (both arms, identical)

At most **one retry per item**. A retry is a fresh single-shot request with the verifier's failure reason appended to the user message — not a conversation continuation, so the single-shot constraint holds. Items failing both attempts are scored failed. Retries are counted in the scorecard and reported; they are not hidden.

## Saturation Plan — `scripts/fanout/dispatch.py` (spec; do not write yet)

The shim is single-job, so a small dispatcher feeds the pool. Deterministic plumbing, no model calls.

- Reads `items.lock.json`; maintains a FIFO work queue of 32 items.
- Runs up to **8 concurrent** `fanout-worker` subprocesses — matching `--max-num-seqs 8`, the measured x8 shape. **Work-queue refill, not fixed batches**: the moment a worker exits, the next queued item launches, so stragglers never drain the pool below 8 while work remains. With 32 items (4 nominal waves) the pool stays saturated for most of the run; this is why the item count is 32 rather than 8.
- On worker exit: run insertion + verification synchronously (CPU-side, cheap); on verify-fail with attempts < 2, re-enqueue with feedback; else record final status.
- Per-item request timeout 300 s; a timed-out attempt counts as a failed attempt.
- Appends `events.jsonl` records: `job_start`, `job_end`, `verify_pass`, `verify_fail`, `retry_enqueued` — each with ISO + monotonic timestamps and item id. These are the timestamps `compute_run_metrics.py` joins against telemetry.
- Writes `scorecard.json` at the end and exits 0 (the supervisor's synthesis call judges; the dispatcher never does).

Client concurrency is capped at 8; vLLM would queue beyond that, but the cap keeps the run on the measured operating point.

## Arms

| Arm | Name | Who does the work | Cloud calls |
|---|---|---|---|
| S | Fable 5 solo | One Claude Code session processes all 32 items itself | Everything |
| F | Fleet fan-out | 8-stream C18 vLLM pool via dispatcher; Fable 5 supervises | Two by design |

Same `items.lock.json`, same prompt content requirements, same verifier, same one-retry budget, same scorecard format. No third arm: the cloud-subagent comparison lives in the CAD replay experiment.

### Arm F protocol (fleet)

Supervisor is Fable 5 (Claude Code). Exactly two supervisor involvements, pre-registered:

1. **Decomposition call**: the supervisor runs `make_items.py`, reads `items.lock.json`, confirms the item list (count, paths, no anomalies), and launches `dispatch.py`. One prompt, one response. No per-item cloud reasoning.
2. **Synthesis call**: after the dispatcher exits, the supervisor reads `scorecard.json` and `metrics.json` and writes `summary.md` (pass rate, retries, wall clock, token totals). One prompt, one response.

Everything between the two calls is local: the dispatcher and verifier run unattended. The supervisor must not inspect individual worker transcripts during the measured window (that would smuggle cloud tokens into the loop).

**Expected supervisor token budget: a few thousand cloud tokens total** (two prompts + two responses over small JSON artifacts; estimate 3,000-8,000 including system overhead — `[MEASURED]`). The solo arm's budget is *everything*: 32 files read into context plus 32 docstring sets generated plus verification round-trips.

### Arm S protocol (solo baseline)

One fresh Claude Code session (no project memory of this experiment), same fresh corpus clone, same `items.lock.json`. Prompt:

```text
Process items item-01 through item-32 from items.lock.json. For each item,
read the file, produce the docstrings JSON in the contract format, save it
as workers/item-NN-attempt-K/response.json, then run insert + verify via
scripts/fanout/run_item_check.sh item-NN. One retry per item on verify
failure, using the verifier's failure reason. Do not use subagents. Do not
call any local model server. Stop when scorecard.json is complete.
```

The solo agent may batch multiple items per assistant turn if it chooses — that is the honest solo behavior and wall-clock is wall-clock. Cloud usage is captured per the m1-replay instrumentation (OTEL preferred, `ccusage` export saved either way), with cache-creation and cache-read tokens reported separately so cache effects cannot silently flatter either arm.

## Environment and Run Protocol

Reuses the m1-replay run-dir conventions.

```bash
export ARM="F"            # F or S
export REP="01"
export RUN_ID="2026-06-XX-${ARM}-${REP}"
export RUN_DIR="/home/svankina/src/local_agents/results/experiments/fanout/$RUN_ID"
export CORPUS="/home/svankina/src/local_agents/.worktrees/fanout/$RUN_ID/scrapy"
mkdir -p "$RUN_DIR"/{items,workers,logs}

git clone https://github.com/scrapy/scrapy.git "$CORPUS"
git -C "$CORPUS" checkout a8ffdcf8517a8973391a14635234b6993b15a86a
git -C "$CORPUS" rev-parse HEAD > "$RUN_DIR/corpus_head.txt"

# Telemetry: same sampler, same rules (1 Hz, nice 19, passive) as m1-replay.
python3 scripts/telemetry_sampler.py --out "$RUN_DIR/telemetry.csv" &
echo $! > "$RUN_DIR/.telemetry.pid"
date -Is > "$RUN_DIR/started_at.txt"
```

Arm F additionally starts the C18 server with the exact flags recorded above, captures the vLLM container log to `$RUN_DIR/logs/vllm.log`, and records image digest, model revision, and flags in `run.json`. Arm S runs no local server; its telemetry establishes the GPU-idle baseline.

Repetitions: **N = 3 per arm**, interleaved (F, S, F, S, F, S) over similar time windows. Report medians plus min/max; never discard a run except under the m1-replay exclusion rules (infrastructure outage, unrecorded server flags, instrumentation total loss).

Warm-up: one untimed p1k probe request against the server before each F run (same policy every run), excluded from the measured window, recorded in `run.json`.

## Instrumentation and Metrics

Reused unchanged from m1-replay:

- `scripts/telemetry_sampler.py` at 1 Hz for the whole measured window of **both** arms; same overhead budget rules (no per-token hooks, sampler CPU < 1% of a core, pre-flight on/off validation < 2% wall-clock delta).
- `scripts/compute_run_metrics.py` for post-run aggregation. Note: there is no `llama-server.log` in this experiment — vLLM does not emit llama.cpp `timings`. The metrics script's existing fallback order applies: per-request client wall + `usage` from each worker's `transcript.jsonl` (the shim records `_client_wall_s` exactly for this), then telemetry-span wall clock (flagged). Run boundaries come from `events.jsonl`.
- Peak-throughput fields, same definitions: `max_decode_tps_single` (best per-request `completion_tokens / _client_wall_s`, with request id and sizes), `max_aggregate_tps_1s` (highest 1-second total completion-token throughput across concurrent streams, derived from per-request start/end with uniform-emission assumption, marked derived), `max_prefill_tps` where measurable. `max_aggregate_tps_1s` is the headline saturation number for arm F.
- Time accounting, same buckets where they apply: `t_generating`, `t_tool_exec` (insertion + verification time), `t_api_wait` (arm S / supervisor calls), `t_idle`, residual ≤ 2%. Arm F adds GPU-idle%: fraction of the dispatch window with GPU util < 10% while items remain queued — the saturation-quality signal; a well-fed pool should keep this near zero until the final wave drains.
- Energy: GPU Wh per run from telemetry, both arms (arm S's Wh is the desktop baseline).

`run.json` schema follows the m1-replay minimum schema with `arm` ∈ {`S`,`F`}, the `local_server` block replaced by the vLLM equivalent (image digest, model revision, flags, `max_num_seqs`), and a `fanout` block: items total, passed, failed, retries, per-item wall stats.

## Expected Numbers (formulas only — no invented results)

All result slots are `[MEASURED]`. The formulas are pre-registered so they cannot be chosen after seeing the data.

**Per-item shape (arm F)**: prompt ≈ 1,500-4,500 tokens (file + template, capped by the generator); completion ≈ 300-900 tokens (docstring JSON only — this is why the output contract is a docstring map, not a rewritten file). At the measured x8 operating point (101.3 t/s per stream), decode per item ≈ completion/101.3 ≈ 3-9 s, plus prefill and queueing.

- Fleet work wall: `wall_fleet_work = [MEASURED]` (dispatcher `job_start` first → `verify` last). Naive floor for context: `total_completion_tokens / 808.7` aggregate-decode seconds, plus prefill, insertion/verify, and final-wave drain — the floor is stated only to show how far the measured value is from the ceiling.
- Fleet total wall: `wall_fleet = wall_fleet_work + t_supervisor_decomposition + t_supervisor_synthesis = [MEASURED]`.
- Solo wall: `wall_solo = [MEASURED]` (first prompt → scorecard complete).
- **Speedup** `= wall_solo / wall_fleet = [MEASURED]`.
- Cloud tokens, fleet: `cloud_fleet = supervisor input + output + cache tokens = [MEASURED]` (expected order: 10^3-10^4).
- Cloud tokens, solo: `cloud_solo = [MEASURED]` (expected order: 10^5 — 32 files into context plus 32 outputs plus retries; expectation stated for sizing only, the measurement decides).
- **Savings** `= (cloud_solo - cloud_fleet) / cloud_solo = [MEASURED]`, reported both gross and with cache-read tokens excluded.
- Quality: `score_fleet = passed/32 = [MEASURED]`, `score_solo = passed/32 = [MEASURED]`, retries per arm `[MEASURED]`. Both arms graded by the identical script.
- Local tokens (arm F): prompt + completion totals from `tokens.json` files `= [MEASURED]`; GPU Wh `= [MEASURED]`.

Pre-registered presentability bar (if any of these fail, the article reports the failure rather than re-rolling): fleet pass rate ≥ 30/32 after retries; fleet pass rate ≥ solo pass rate − 2 items; speedup ≥ 3x; cloud savings ≥ 90%; GPU-idle% during the fed phase < 15%.

## Honest Caveats (must appear in the article)

1. **Selection bias is the point, and is disclosed**: this task was chosen *because* C18 is good at it. It demonstrates the design point of the 8-stream pool, not general coding ability. The CAD kernel replay is the general-case measurement and must be presented alongside.
2. The verifier checks structure (compiles, coverage, parameters mentioned, code untouched), not prose quality. A passing docstring can still be mediocre English. Both arms are graded by the same mechanical bar, so the *comparison* is fair even though the bar is not a full quality measure.
3. Solo wall-clock depends on how the cloud session batches items; that is allowed and reported, not controlled away.
4. Prompt-cache tokens can flatter the solo arm's marginal cost; gross and cache-separated numbers are both reported.
5. Per-stream local decode (101.3 t/s) is not the comparison; end-to-end wall clock is. The fleet wins, if it wins, on parallelism — not per-token speed.
6. N=3 per arm is small; medians plus min/max are reported and no run is discarded outside the preregistered exclusions.

## Deliverables Checklist (run time, not now)

- [ ] `scripts/fanout/make_items.py`, `fanout-worker`, `insert_docstrings.py`, `verify_item.py`, `dispatch.py`, `run_item_check.sh` written to the specs above.
- [ ] Pre-flight: telemetry overhead validation; server coherence gate (same hello + tool probe discipline as C18) before any measured F run.
- [ ] 3 F runs + 3 S runs, interleaved; `run.json`, `scorecard.json`, `telemetry.csv`, `events.jsonl`, worker `transcript.jsonl`/`tokens.json` per item, committed under `results/experiments/fanout/`.
- [ ] `summary.json` aggregate with medians by arm; article section drafted with both this benchmark and the CAD replay.
