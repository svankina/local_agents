# Showcase Fan-Out Experiment Writeup

Date: 2026-06-12

This experiment measured a deliberately favorable workload for a local 8-stream worker fleet: many independent, single-shot docstring backfill jobs on a pinned real codebase. The scientific question was not "is the local model better at coding than Claude?" It was narrower: if the same supervisor and the same verifier bookend the run, what changes when only the worker backend is substituted?

The controlled worker-swap design isolates that substitution. In the fleet and cloud-worker arms, the same Fable 5 supervisor performs the same two bookend roles: decomposition before dispatch and synthesis after dispatch. Those bookends are not free, but they cancel in the controlled comparison because they are held fixed while the worker pool changes. The measured variable is the middle phase: local vLLM workers, Fable CLI workers, or Haiku CLI workers.

## Design

The preregistered workload was per-file Python docstring backfill. The corpus was Scrapy pinned at `a8ffdcf8517a8973391a14635234b6993b15a86a` (`scrapy@a8ffdcf8` below). Pinning matters because every item contains a file hash, every worker prompt embeds source from that exact commit, and every verifier run compares against that same pristine source.

Items were selected mechanically by `scripts/fanout/make_items.py`: walk `scrapy/**/*.py`, keep files with 50-400 lines, at least three public functions/classes/methods missing docstrings, estimated prompt tokens no more than 4,500, rank by missing-docstring count descending, break ties by path, and take 32. Each item records `id`, relative `path`, `file_sha256`, `targets`, `line_count`, and `est_prompt_tokens`; `items.lock.json` records the corpus URL, pinned SHA, generator SHA, and item list.

The credibility core is the deterministic verification battery. A worker never edits the repository; it emits JSON docstrings. The harness inserts them into a scratch file and then checks:

- `python3 -m py_compile` succeeds.
- Every target now has an AST docstring.
- The pristine and modified files have identical AST dumps after stripping docstrings.
- Every function or method docstring mentions each named parameter except `self` and `cls`, including `*args` and `**kwargs` by bare name.
- No docstring is under 20 non-whitespace characters or matches `todo|tbd|fixme|placeholder`.

Those gates make the quality score mechanical: `passed / 32`, with no model grader. They do not prove the prose is excellent, but they do prove the code was not changed, all requested targets were covered, the file still compiles, and the docstrings met the explicit contract.

## Executed Protocol And Deviations

The preregistration is `docs/experiments/2026-06-12-showcase-parallel-fanout.md`. The executed experiment kept the core design: pinned Scrapy corpus, 32 locked items, one retry per item, identical deterministic verifier, and an 8-slot dispatcher for worker-pool arms.

Deviations from preregistration:

- Paths used `results/experiments/showcase-fanout/` rather than the preregistered `results/experiments/fanout/` slug.
- The preregistration called for N=3 per arm interleaved F/S/F/S/F/S. The executed evidence is N=1 for each final comparison arm, plus harness-fairness iterations and probes.
- The executed arms expanded beyond S and F: `FW-01` added Fable CLI workers under the same dispatcher, `H-01` added Haiku CLI workers with thinking enabled by the observed CLI behavior, and `H-02` probed Haiku with thinking disabled.
- `F-01` was aborted and excluded before scorecard production; its run directory has `run.json` and `started_at.txt` only. The excluded-run note is SIGPIPE, and there is no scorecard to analyze.
- `S-02-timing-probe` was explicitly a 300 s timing probe, not a scoreboard repetition.
- The fleet was iterated for harness fairness before the final local result. The iteration was not rerolling a bad model result behind the same harness; each failed run exposed a deterministic harness or prompt-contract defect, which was fixed before the next run.
- Supervisor cost varied substantially across runs instead of staying at the original "few thousand tokens" expectation. The direct `supervisor-*.jsonl` result records show summed bookend costs from `$1.624351` in H-02 to `$3.628339` in H-01. The `.21-.63` supervisor-cost-variance figure requested for the threat model was not present as a named field in `scorecard.json`, `throughput-summary.json`, `H-01-token-audit.md`, or the supervisor result logs, so this writeup uses the artifact-backed dollar ranges instead.

## Runs

| Run | Role | Score | Retries | Diagnosed defect / finding | Deterministic fix or disposition |
|---|---:|---:|---:|---|---|
| F-01 | aborted local fleet | none | none | Aborted before scorecard; excluded as SIGPIPE/incomplete infrastructure run. | One honest excluded line; no result used. |
| F-02 | local fleet iteration | 1/32 | 31 | 28 failed insertion-clean attempts, 29 parameter-mention failures, 5 worker-shape failures (`assistant response missing docstrings object`). | Tighten JSON extraction/normalization and make verifier requirements explicit in the prompt. |
| F-03 | local fleet iteration | 12/32 | 22 | 40 parameter-mention failures and 2 non-placeholder failures; the prompt still left required parameter words too implicit. | Prompt enumerates exact required keys and, per target, exact parameter words. |
| F-04 | local fleet iteration | 30/32 | 10 | Remaining failures were 10 non-placeholder and 2 parameter-mention attempts; final score failed on two too-short/placeholder-like docstrings. | Retry feedback was made check-specific, especially for `non_placeholder`. |
| F-05 | local fleet iteration | 31/32 | 5 | One final insertion-clean failure; comments in `fanout_common.py` identify the case as underscore-sensitive key matching (`DummyLock.acquire` vs `_DummyLock.acquire`). | Accept unambiguous underscore-insensitive qualname matches while still enforcing coverage. |
| F-06 | final local fleet | 32/32 | 7 | Passed all 32; first-attempt misses were 5 parameter mentions and 2 non-placeholder checks, all fixed by one retry. | Final arm F result. |
| S-01 | solo Fable baseline | 32/32 | 0 | One Claude session completed all 32 items without local server or subagents. | Final solo baseline. |
| S-02 timing probe | solo probe | not scored | not scored | Five-minute instrumented timing probe only; `run.json` says "NOT a scoreboard rep". | Used only for per-turn timing estimate in throughput summary. |
| FW-01 | Fable worker pool | 32/32 | 0 | Same dispatcher shape as F/H, but workers were Fable CLI sessions. | Controlled worker-swap cloud-worker arm. |
| H-01 | Haiku worker pool, thinking observed | 32/32 | 1 | Passed, but billed output was 154,003 tokens for about 9,213 useful-output tokens. | Token audit concludes CLI thinking dominated output. |
| H-02 | Haiku worker pool, thinking off | 29/32 | 5 | Thinking-off cut billed output to 20,493 tokens and worker cost to `$0.6564423`, but quality fell to 29/32. | Treated as the quality/cost trade-off probe, not the best Haiku quality result. |

## Results

The final local fleet (`F-06`) and solo baseline (`S-01`) both scored 32/32. The solo baseline took 569.077 s. The local fleet worker dispatch took 24.7 s in the aggregate throughput summary; including supervisor bookends and harness overhead, the `F-06` window was 176.0 s (`147.9 s` supervisor, `24.7 s` local fleet, `3.4 s` harness overhead). End-to-end speedup against solo was therefore `569.0 / 176.0 = 3.2x`; worker-phase-only speedup was `569.0 / 24.7 = 23.0x`.

Worker-swap table:

| Arm | Worker backend | Score | Worker dispatch/window used for rate | Avg billed completion tok/s | Max aggregate tok/s | Useful-output tokens | Useful-output tok/s | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---|
| S-01 | one Fable solo session | 32/32 | 569.0 s | 69.3 pipeline, 71.6 API-time | 90 per-turn probe max | 11,607 | 20.4 | Single cloud stream; prompt side dominated by cache reads. |
| F-06 | local vLLM Qwen3 30B, 8 streams | 32/32 | 24.7 s | 344 | 511.3 from `metrics.json` | 8,919 | 366.7 using `metrics.json` dispatch wall | Supervisor cost recorded separately; worker marginal cloud cost eliminated. |
| FW-01 | Fable CLI workers, 8 slots | 32/32 | 80.6 s | 263.3 | 355.6 | 14,745 | 184.0 | Worker cloud cost `$6.284875`; supervisor `$3.387782`. |
| H-01 | Haiku CLI workers, thinking observed | 32/32 | 160.9 s | 957.1 billed, misleading | 1281.9 billed, misleading | 9,213 | 57.4 | Output includes CLI thinking; worker cloud cost `$1.418612`. |
| H-02 | Haiku CLI workers, thinking off | 29/32 | 54.263 s | 377.7 | 508.2 | 11,150 | 205.5 | Quality fell to 29/32; worker cloud cost `$0.6564423`. |

`results/experiments/showcase-fanout/throughput-summary.json` reports the controlled worker-substitution ratios with supervisor bookends cancelled: local vs Fable workers were `3.3x` faster (`24.7 s` vs `80.6 s` dispatch), local eliminated worker cloud cost, and quality was parity at 32/32 for S-01, F-06, FW-01, and H-01. H-02 shows a separate thinking trade-off: lower cost and lower billed output, but 29/32 quality rather than 32/32.

Useful-output accounting uses compact `response.json` characters divided by 4, matching `scripts/fanout/useful_output.py`. The tracked useful-output summaries report F-06 `8,919`, FW-01 `14,745`, H-01 `9,213`, and H-02 `11,150` useful-output tokens. S-01 was derived by the same method from 32 response files: 46,429 compact response characters, estimated as 11,607 useful-output tokens. This is an estimate, not tokenizer truth.

Token accounting confirms the thinking finding. `H-01-token-audit.md` says H-01's `prompt_tokens: 442` is only uncached input, while real prompt volume was `318,319` cache-creation tokens and `115,170` cache-read tokens. It also verifies H-01's `154,003` completion tokens as genuine billed output and compares it to local F-06's `8,525` completion tokens for the same 32/32 verified work: an 18x billed-output difference driven by CLI thinking. H-02 reduced completion tokens to `20,493`, but quality dropped to 29/32.

## Threats To Validity

The main threat is sample size: the final comparison is n=1 per arm. The preregistered N=3 was not executed, so the result is a disciplined case study, not a distributional estimate.

The task family is narrow: docstring JSON over Python files. It was chosen because it fits the 8-stream local-serving design point: independent, single-shot, low-output, mechanically verifiable work. It should not be generalized to multi-turn agentic implementation work.

CLI session boot overhead is structural to the cloud-worker arms. Fable and Haiku workers launch many headless CLI sessions; that is part of the backend substitution being measured, but it means the comparison includes process/session startup behavior, not pure model decode speed.

Timing is client-measured. Fleet and worker-arm rates come from transcript request timestamps and uniform-emission aggregate derivations; solo rates use stream/probe timing. The numbers are fit for end-to-end harness comparison, not server-internal profiling.

Useful output is estimated as compact response JSON characters divided by 4. That is stable across arms but approximate.

Supervisor cost varied across runs. Because the controlled worker-swap comparison cancels identical supervisor bookends, this does not change the worker substitution result, but it does limit claims about absolute end-to-end cloud cost. Direct supervisor logs show summed bookend costs of `$2.933622` (F-02), `$2.295385` (F-03), `$2.207710` (F-04), `$3.165966` (F-05), `$2.394614` (F-06), `$3.387782` (FW-01), `$3.628339` (H-01), and `$1.624351` (H-02). I did not find an artifact field that verifies the `.21-.63` range, so it is not used as a numeric claim here.
