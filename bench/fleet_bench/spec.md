# Fable Fleet Bench — v1 spec

**Question:** across local worker models, which one completes a suite of
instruction-bound tasks for the **fewest Fable (supervisor) output tokens** and the
least wasted wall-clock?

The scarce resource is the supervisor, not local compute. Local workers are cheap
and fast; every token Fable spends — planning, reviewing, writing fixes — is the
real cost. A worker that follows instructions well passes review on the first try
and needs almost no supervision. A worker that drifts forces re-review and fix
rounds, burning expensive supervisor tokens and stalling the pipeline. We rank
workers by **Fable output tokens per completed task**.

## Scope (v1)

Tiers 0–1 only. No SWE-bench yet (added once the pipeline is proven).

| Tier | Family | Each item is | Verifier (deterministic, no model judge) |
|---|---|---|---|
| 0 | `docstring` | a corpus function missing its docstring | existing `verify_item.py` (compiles + present + no TODO) |
| 0 | `typehint` | a corpus function with annotations stripped | restored sig parses + `mypy --strict` clean on the unit |
| 1 | `pure_fn` | a spec (sig + docstring + 3 examples) for a pure function | property test: `worker(x) == reference(x)` on N seeded inputs |
| 1 | `unit_test` | a function's source, asked for a pytest test | test collects, passes, and executes the target (coverage hit) |

`pure_fn` is the v1 workhorse: self-contained, infinite airtight hidden cases,
difficulty controlled by problem bank.

## Workers (first sweep)

| id | model | engine | why |
|---|---|---|---|
| C18 | Qwen3-30B-A3B GPTQ-Int4 | vLLM, 16-stream | published champion, baseline to beat |
| C12 | byteshape Qwen3.6-35B-A3B | llama.cpp, MTP | single-stream king, tested batched |
| C1 | gemma-4-12B-it-qat | llama.cpp | small-dense cheap/fast Pareto point |

Note: C12/C1 need a llama.cpp serving path; the existing fleet runner is vLLM-only.

## The supervised loop (per task)

```
plan   ── Fable writes the worker instruction (spec + explicit constraints)
exec   ── local worker produces a submission
verify ── deterministic check: correctness AND constraint adherence
review ── Fable inspects failed/won submissions, writes a fix instruction
           (loop exec→verify→review until pass or FIX_CAP rounds)
```

Fable output tokens are counted at every `plan` / `review` stage. A task that
exceeds `FIX_CAP` rounds is **abandoned** (counts its spent tokens, no completion).

## Pipelining (this is how "wasted time" is minimized)

Both tiers stay saturated and overlapping — the supervisor never blocks on a worker:

- Fable plans tasks ahead into a queue while workers grind the current batch.
- Worker pool runs at engine-native batch (C18 vLLM 16-stream; C12/C1 llama.cpp slots).
- Review/fix calls to Fable are **issued concurrently** (many in flight) so the
  supervisor's own aggregate output throughput is maximized, not serialized.
- We measure **supervisor idle %** and total wall-clock against a serial baseline.

## Metrics (per worker model)

- **Supervision cost (headline)** — Fable output tokens per completed task, split
  into plan / review / fix. Lower = better instruction-follower.
- **Instruction-following** — first-pass rate (passed with zero fixes), mean fix
  rounds to done, and a **violation taxonomy** (wrong format, out-of-scope edit,
  extra output, ignored constraint) tallied by the verifier + review.
- **Time wasted** — supervisor idle %, wall-clock vs serial baseline, completion rate.
- **Headline chart** — Fable-tokens-per-completed-task vs completion-rate, per model.
  Best bang/buck = the model that clears the suite for the least supervisor spend.

## Tasks carry explicit instructions

Every item adds constraints the worker must honor, so instruction-following is what
separates models — not just raw problem-solving. The verifier checks both:
correctness (does it work) and **adherence** (did it stay in scope, match the
required format/signature, add nothing it was told not to). `pure_fn` is the
correctness substrate; constraint wrappers turn it into an instruction-following test.

## Layout

```
bench/fleet_bench/
  spec.md            this file
  families/          one generator+verifier per family
    pure_fn.py
    ...
  generate.py        emit items.json manifest (all families)
  verify.py          dispatch item -> family verifier -> pass/fail
results/experiments/fable-fleet-bench/<date>-<arm>-<model>/
```
