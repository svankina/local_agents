# Model Hot-Swap Latency Writeup

Date: 2026-06-13

This experiment measured the cost of swapping local models in and out of a single
GPU's VRAM. The motivating question is operational, not academic: if we want a
"route each request to the model that is best at it" fleet — a small model for
triage, a coder for code, a heavyweight for hard reasoning — and they cannot all
fit in VRAM at once, what penalty do we pay every time the resident set has to
change? The answer determines whether such routing is viable at all, and if so,
how the fleet should be partitioned.

The hardware is one RTX 3090 Ti (24 GB). The server is ollama 0.30.7, which is
convenient for this measurement because every `/api/generate` response reports a
`load_duration` field: the time from request receipt to model-ready, exclusive of
inference. That field *is* the swap cost. Weights live on NVMe; the host has 62 GB
of RAM, of which ~42 GB was page cache at run time, so a cycling working set of a
few models stays warm in RAM between swaps.

## Design

Seven models from the local fleet were chosen to span the size range, sorted
small to large: Qwen2.5 1.5B (0.99 GB), Granite3.2 2B (1.5 GB), Qwen2.5 3B
(1.9 GB), Phi4-mini 3.8B (2.5 GB), Gemma4 12B QAT (7.2 GB), Qwen3.6 27B Q4
(17 GB, dense), and Qwen3.6 35B-A3B Q4 (22 GB, MoE with ~3B active params — the
fleet champion from the C-series benchmarks).

Each swap was probed with a one-token generation (`num_predict=1`,
`temperature=0`) so that inference is negligible and `load_duration` dominates the
measured wall clock. Four regimes isolate the components of the penalty:

- **baseline** — the model is already resident (`keep_alive=5m`), and we re-query
  it. `load_duration` here is the no-swap floor: the cost ollama charges even when
  nothing is loaded.
- **warm** — the model is unloaded (`ollama stop` on every model first), then
  loaded. Its weights are warm in the OS page cache from a prior touch, so this
  isolates the runner-spawn + RAM→VRAM transfer cost. A discarded warm-up rep
  precedes the measured reps to guarantee the page cache is hot. This is the
  number a busy router actually sees.
- **cold** — the OS page cache is dropped (`sync; echo 3 > drop_caches`,
  requiring root) immediately before each load, forcing the weights to be read
  from NVMe. This is the worst case: a working set larger than RAM.
- **roundrobin** — the seven models are cycled small→large repeatedly with the
  default `keep_alive`, so each request's resident set is whatever ollama chose to
  keep. After each load the `/api/ps` resident set is recorded. This reproduces
  the realistic fleet behaviour: eviction is driven by VRAM pressure, not by an
  explicit stop.

Reps: warm and baseline ran 3 measured reps per model (plus the discarded warm-up
for warm); cold ran 2 reps over the four largest models; round-robin ran 2 full
cycles. Reported per-model figures are medians.

## Harness

The harness is `scripts/swap_latency_bench.py` (HTTP client against
`localhost:11434`, one regime per invocation, appends JSON-lines to
`results/experiments/model-swap-latency/measurements.jsonl`). The cold regime ran
as a single root script (`drop_caches` needs privilege) writing `cold.jsonl`.
Aggregation and the HTML report are `scripts/swap_latency_report.py`, producing
`metrics.json` and `report.html` in the same directory. The GPU was idle (4 MiB
resident) before the run.

## Results

Medians, in seconds, by regime:

| Model | Size | Resident floor | Warm swap-in | Cold swap-in | Swap penalty* |
|---|---|---|---|---|---|
| Qwen2.5 1.5B | 0.99 GB | 0.44 | 3.88 | 5.36 | +3.44 |
| Granite3.2 2B | 1.5 GB | 0.17 | 2.75 | — | +2.58 |
| Qwen2.5 3B | 1.9 GB | 0.44 | 3.62 | — | +3.18 |
| Phi4-mini 3.8B | 2.5 GB | 0.58 | 4.59 | — | +4.01 |
| Gemma4 12B QAT | 7.2 GB | 1.06 | 7.41 | 14.33 | +6.35 |
| Qwen3.6 27B Q4 | 17 GB | 0.83 | 18.94 (16.2–35.5) | 17.36 | +18.11 |
| Qwen3.6 35B-A3B Q4 | 22 GB | 0.71 | 8.54 | 27.21 | +7.83 |

\*penalty = warm swap-in − resident floor (the pure cost of bringing a model in,
above the floor ollama charges anyway).

The swap-in cost decomposes into a **fixed floor of ~2–3 s** (spawn the model
runner, initialise the CUDA context) **plus the weights**. Warm, the weight term
runs at roughly 2.5 GB/s of effective RAM→VRAM throughput; cold off NVMe it drops
to roughly 0.8 GB/s. So the fixed term dominates for small models — a 1 GB model
still costs ~3.9 s, almost all overhead — and the bandwidth term takes over above
~10 GB.

### Page cache is the largest single variable

The 35B MoE loads in ~8.5 s warm but ~27 s cold — better than 3×. (One uncontrolled
warm-sweep rep-0 touched 60 s under concurrent memory pressure; the controlled
drop-cache measurement is the trustworthy worst case at ~27 s.) With 62 GB of RAM
the hot models stay page-cached between swaps, so the warm column is what a busy
router lives on. The corollary is a cliff: if the routing working set ever exceeds
RAM, every swap falls onto the cold column and the penalty roughly triples.

### Small models co-reside; swaps among them are free

In the round-robin, ollama kept **three to four small models resident
simultaneously** — at one point Qwen2.5 1.5B + Granite3.2 2B + Qwen2.5 3B +
Phi4-mini 3.8B, together ~7 GB. Routing among models that already share VRAM
triggers no eviction at all, so the swap cost collapses to the resident floor
(sub-second to ~3 s). This is the regime where high-QPS routing belongs.

### Big models are jealous

Loading the 27B or 35B evicted the entire small pool down to just the big model.
Worse, the contention is asymmetric in time: while the 22 GB MoE stayed resident,
loading even a 3 B model had to fight for the remaining VRAM and ballooned from
~3 s to **17–27 s**, and a clean evict-and-reload of the 27 B hit **30 s**. The
penalty of a big model is not only its own load time — it is the tax it imposes on
the next several loads while it occupies the GPU.

### The 27B dense is the worst citizen; the MoE is well-behaved

The 27 B dense model loaded in 16–35 s even warm, with high run-to-run variance.
The 35 B MoE, despite being 5 GB larger on disk, loaded faster and more
consistently (~8.5 s warm). Fewer effective layers to wire up at load time
appears to matter more than raw byte count.

### Eviction is cheap; loading is the cost

Unloading the outgoing model is sub-second. The entire penalty is re-loading the
incoming model. Optimising swaps means minimising loads, not minimising unloads.

## What this means for a route-to-best-model fleet

- **Tier 1 — keep small specialists hot.** A 1.5B–4B triage/route/extract pool
  (~7 GB total) co-resides permanently in VRAM. Switching among them is free. This
  is where request-level routing lives.
- **Tier 2 — one heavyweight, swapped deliberately.** Reserve the remaining
  ~16 GB for a single 27B/35B loaded on demand. Budget ~8–10 s warm (the MoE) or
  up to ~27 s cold per swap-in, and accept that it evicts the small pool — so do
  not interleave big and small requests tightly.
- **Batch by model; do not ping-pong.** Fifty requests grouped by destination
  model pay the swap once; the same fifty interleaved pay it fifty times.
  Route-then-batch beats route-per-request whenever the swap exceeds the
  per-request budget.
- **Keep the working set under RAM.** Cold-disk roughly triples the penalty. A
  set of five or six models stays page-cached in 62 GB; staying under that keeps
  the fleet on the warm numbers.
- **Rule of thumb.** Swap penalty ≈ `2.5 s + model_GB / 2.5` warm. If that
  exceeds the request's latency budget, the model belongs in the always-resident
  tier, not the swap tier.

## Artifacts

- Harness: `scripts/swap_latency_bench.py`, `scripts/swap_latency_report.py`
- Raw data: `results/experiments/model-swap-latency/measurements.jsonl`,
  `cold.jsonl`
- Aggregates: `results/experiments/model-swap-latency/metrics.json`
- Report (polished HTML): `results/experiments/model-swap-latency/report.html`

## Threats to validity

- N is small (2–3 reps); the 27 B variance in particular is undersampled, so its
  warm figure should be read as "16–35 s, high variance" rather than a point
  estimate.
- Numbers are specific to ollama 0.30.7's loader, this GPU, and this NVMe.
  `load_duration` semantics are ollama's; a different server (llama.cpp direct,
  vLLM) would have a different floor.
- The round-robin resident set is ollama's scheduling policy, not a controlled
  variable; it documents observed behaviour rather than a guaranteed contract.
- Cold measurements drop the entire page cache, which is a stricter worst case
  than partial eviction; real cold-ish swaps under memory pressure will land
  between the warm and cold columns (as the observed 60 s outlier did).
