# H-01 token accounting audit (2026-06-12)

Verdict: underlying per-call records are correct; two scorecard labels mislead
for Claude-CLI workers.

1. `prompt_tokens: 442` maps the CLI's `input_tokens`, which counts only
   uncached input (~10/call). The real prompt volume is
   `cache_creation_input_tokens: 318,319` — each of the 33 fresh sessions
   re-writes its ~8k prompt to an ephemeral cache; no cross-item cache reuse.
2. `completion_tokens: 154,003` is genuine billed output: Haiku CLI sessions
   think before answering (sampled item-02: 9,511 output tokens for a ~600
   token docstring map). Local fleet produced the same 32/32 with 8,525
   completion tokens (thinking disabled server-side) — an 18x output-token
   difference for identical verified work.
3. Costs verified: per-item total_cost_usd sums to worker_cloud_cost_usd
   ($1.4186); supervisor $3.6283 (verbose this run).

Comparable worker-phase numbers (supervisor cancels per the control design):
- local fleet F-06: 24.7 s, ~$0 marginal, 8,525 completion tokens
- haiku fleet H-01: 160.9 s, $1.42, 154,003 completion tokens (incl. thinking)

Applies equally to FW-01 (same worker path; same label semantics).
