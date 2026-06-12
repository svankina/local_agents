# Showcase Fan-Out Runbook

This runbook is for running the showcase fan-out benchmark on another machine or another corpus. The default task is Scrapy docstring backfill: 32 independent items, one worker response per item, one retry, deterministic verification.

## Prerequisites

- Python 3.
- Git.
- For local fleet arm F: a GPU that can serve your model plus a vLLM OpenAI-compatible container, or any already-running OpenAI-compatible server.
- For cloud arms S, H, and FW: Claude CLI installed and authenticated.
- The repository checked out at `/home/svankina/src/local_agents` or an equivalent path; run commands from repo root.

Do not benchmark before the server passes a small coherence probe. Send a trivial chat request and make sure the served model answers normally before dispatching 32 workers.

## Quickstart

Run one arm per fresh `RUN_ID`. The scripts create `RUN_DIR`, clone/check out the pinned Scrapy corpus, make items, run the arm, compute metrics, and write a scorecard.

Local 8-stream fleet, starting vLLM through Docker:

```bash
export ARM=F
export REP=01
export RUN_ID="$(date +%F)-${ARM}-${REP}"
export RUN_DIR="$PWD/results/experiments/showcase-fanout/$RUN_ID"
export CORPUS="$PWD/.worktrees/showcase/$RUN_ID/scrapy"

scripts/fanout/run_fleet_arm.sh
```

The fleet runner uses `MODEL=C18-qwen3-30b-vllm`, `BASE_URL=http://127.0.0.1:8091/v1`, `PORT=8091`, `VLLM_IMAGE=vllm/vllm-openai:v0.22.1`, and `VLLM_CONTAINER=fanout-$RUN_ID` unless overridden. If you already have an OpenAI-compatible server, keep the corpus/item setup but point `BASE_URL` and `MODEL` at your server, or invoke `scripts/fanout/dispatch.py` directly.

Solo Fable baseline:

```bash
export ARM=S
export REP=01
export RUN_ID="$(date +%F)-${ARM}-${REP}"
export RUN_DIR="$PWD/results/experiments/showcase-fanout/$RUN_ID"
export CORPUS="$PWD/.worktrees/showcase/$RUN_ID/scrapy"

scripts/fanout/run_solo_arm.sh
```

Haiku worker pool:

```bash
export ARM=H
export REP=01
export RUN_ID="$(date +%F)-${ARM}-${REP}"
export RUN_DIR="$PWD/results/experiments/showcase-fanout/$RUN_ID"
export CORPUS="$PWD/.worktrees/showcase/$RUN_ID/scrapy"

scripts/fanout/run_haiku_arm.sh
```

Fable worker-pool control:

```bash
export ARM=FW
export REP=01
export RUN_ID="$(date +%F)-${ARM}-${REP}"
export RUN_DIR="$PWD/results/experiments/showcase-fanout/$RUN_ID"
export CORPUS="$PWD/.worktrees/showcase/$RUN_ID/scrapy"

scripts/fanout/run_fable_workers_arm.sh
```

Cloud-worker model selection is controlled by `FANOUT_CLAUDE_MODEL`. `scripts/fanout/haiku-worker` defaults to `claude-haiku-4-5-20251001`; `run_fable_workers_arm.sh` sets `FANOUT_CLAUDE_MODEL=claude-fable-5`.

`haiku-worker` sets `MAX_THINKING_TOKENS=0` inside the worker subprocess. That disables extended thinking for Anthropic API models that honor it without changing your shell's global environment. The local OpenAI-compatible worker disables thinking through `chat_template_kwargs: {"enable_thinking": false}` when accepted, then falls back to `/no_think`.

## Different Corpus

Start with `scripts/fanout/make_items.py`. The default generator assumes:

- The corpus is a git checkout at the pinned Scrapy SHA.
- Candidate files live under `scrapy/**/*.py`.
- The task is missing Python docstrings on public functions/classes/methods.
- Each item can embed the full source file in one prompt.

For a new Python corpus, change the corpus URL/SHA constants in `fanout_common.py` and adjust the glob in `make_items.py`. Keep the item contract stable:

```json
{
  "id": "item-01",
  "path": "package/module.py",
  "file_sha256": "sha256 of pristine file",
  "targets": ["Class.method", "function_name"],
  "line_count": 123,
  "est_prompt_tokens": 2200
}
```

The worker receives one item, reads `path` from `--corpus`, verifies `file_sha256`, and emits:

```json
{"docstrings": {"Class.method": "Docstring text mentioning every required parameter."}}
```

For a different task family, keep the same dispatcher interface and replace the item builder, prompt, insertion step, and verifier. A new verifier must produce a JSON result with:

```json
{"passed": true, "failed_check": null, "reason": null}
```

or:

```json
{"passed": false, "failed_check": "contract_name", "reason": "human-readable retry feedback"}
```

The dispatcher relies on `passed`, `failed_check`, and `reason` for scorecards and retries.

## New Worker Backend

Add a worker executable that accepts this CLI:

```bash
your-worker \
  --item "$RUN_DIR/items/item-01.json" \
  --corpus "$CORPUS" \
  --out "$RUN_DIR/workers/item-01-attempt-1" \
  --feedback "optional verifier failure text"
```

If it is OpenAI-compatible, also accept:

```bash
--base-url http://127.0.0.1:8000/v1 --model served-model-name
```

Required artifacts under `--out`:

- `response.json`: parsed worker answer in the task contract.
- `transcript.jsonl`: request/response records. Include `_client_wall_s` on response bodies when possible.
- `tokens.json`: prompt/completion/cache/cost totals when available.

Exit semantics:

- Exit 0 only when `response.json` exists and matches the expected response shape.
- Exit nonzero on API failure, timeout, malformed JSON, hash mismatch, or missing response.
- Do not mutate the corpus checkout. Write only under `--out`.

Run it through the dispatcher:

```bash
python3 scripts/fanout/dispatch.py \
  --run-dir "$RUN_DIR" \
  --items-dir "$RUN_DIR/items" \
  --corpus "$CORPUS" \
  --worker-script path/to/your-worker \
  --concurrency 8
```

## Reading Results

`scorecard.json` is the primary result:

- `items_total`: denominator.
- `passed`, `failed`, `score`: quality outcome.
- `retries`: number of second attempts.
- `token_totals`: summed `tokens.json` fields.
- `items[]`: per-item status, attempts used, worker return code, timeout flag, wall time, failed check, and reason.

`metrics.json` is timing and throughput:

- `wall_clock_seconds`: measured request-span or stream wall time.
- `time_accounting`: generation/tool/API/idle buckets when available.
- `peak_throughput.max_aggregate_tps_1s`: derived 1-second aggregate completion-token rate.
- `peak_throughput.max_decode_tps_single`: best per-request completion tokens divided by client wall.

`throughput-summary.json` is the hand-curated aggregate used for the paper table. In this experiment it records S-01, F-06, FW-01, H-01, and worker-substitution ratios.

Useful-output accounting is intentionally simple:

```bash
python3 scripts/fanout/useful_output.py "$RUN_DIR"
```

It writes `useful-output-summary.json`, estimating useful output as compact `response.json` characters divided by 4. Use it for cross-arm sanity checks, not exact tokenizer accounting.

## Footguns

Run a coherence probe before benchmarking. A healthy server endpoint is not enough; verify the model can answer a basic chat request and, for local Qwen/vLLM configs, that thinking/tool-parser settings are coherent.

Use `--strict-mcp-config` for headless Claude sessions. The runners pass an empty MCP config so worker sessions do not inherit unrelated local tools.

Keep workers in the foreground in print/headless mode. Backgrounding or wrapping the main CLI process can hide failures and break token/timing capture.

Never pipe runners through `head` or `tee` during measured runs. Broken stdout consumers can produce SIGPIPE-style aborts and incomplete run directories.

Set thinking budgets deliberately for probe calls. H-01 showed that hidden/extended thinking can dominate billed output even when the useful JSON answer is small.

State every verifier requirement in the prompt. The F-02 to F-06 trail exists because the early prompt did not explicitly list every required key, parameter word, and non-placeholder rule. Mechanical gates are only fair when the worker sees the whole contract.

Do not edit the pinned corpus checkout. Workers write `response.json`; insertion and verification happen in scratch attempt directories.

Do not compare arms until they share `items.lock.json` semantics, retry policy, verifier, and scorecard schema.

