# 3× faster, 74% cheaper: Claude Code with local subagents on one RTX 3090 Ti

Same task, same quality bar — 32/32 machine-verified docstrings in both arms. Fable 5 working alone: 9.5 minutes, $9.22. Fable 5 supervising 8 local workers on one RTX 3090 Ti: 3 minutes, $2.40. Inside the work phase the gap is 23× — the locals wrote all 32 docstrings in 24.7 seconds. Every number ships with raw logs in the repo.

Last post built the engine: [1,184 decode tok/s from one RTX 3090 Ti](2026-06-800-toks-3090.md). This post is what the throughput buys.

The division of labor: Fable 5 keeps the senior chair — planning, review, merges — and the grunt work goes local on the 3090 Ti (24 GB). Two local configs earned seats: byteshape's Qwen3.6-35B-A3B IQ4_XS under llama.cpp for queue-serial agentic work (**100% toolcall, 5/5 agentic, 127–143 tok/s**), and Qwen3-30B-A3B GPTQ under vLLM for parallel fan-out. Baseline: Fable 5 doing everything itself.

## The fan-out showcase

Workload: backfill docstrings for 32 functions across scrapy@a8ffdcf8. Every item verified deterministically — py_compile, AST equivalence proving the code untouched, parameter coverage, verbatim parameter mentions, anti-placeholder checks. Same items, same verifier, two arms.

| | fleet (F-06) | solo (S-01) |
|---|---:|---:|
| verified | 32/32 | 32/32 |
| work phase | 24.7 s | 569 s |
| end-to-end | 176 s | 569 s |
| cloud cost | $2.40 | $9.22 |
| output throughput | 344 tok/s | 69.3 tok/s |

The fleet arm is Fable 5 making exactly two cloud calls — decompose (91 s), synthesize (57 s) — wrapped around 8 concurrent local streams of the vLLM pool. 39 requests, 78,130 local tokens, 7 feedback retries, all recovered. Aggregate 344 completion tok/s (3,157 counting fresh prefill), per-stream median 58, peak 101. The solo arm: Fable 5 alone, 85 turns, 39,454 output tokens.

The real finding is the runtime split: supervisor bookends 148 s (84%), local fleet 24.7 s (14%), harness 3.4 s (2%). The fleet did all the work in 14% of the window. The next thing to optimize is the cloud bookends, not the workers.

## The controlled worker swap

Solo-vs-fleet changes two things at once, so we ran the control: same supervisor, same 32 items, same gates — only the worker model swapped. The bookends cancel out. What's left is the workers.

| workers | verified | retries | work phase | worker cost | output tokens | avg tok/s | max tok/s (1 s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 8× local Qwen3-30B | 32/32 | 7 | **24.7 s** | ~$0 | 8,525 | 345 | 512 |
| 8× Fable 5 | 32/32 | 0 | 80.6 s | $6.28 | 21,222 | 263 | 356 |
| 8× Haiku 4.5 (thinking on) | 32/32 | 1 | 160.9 s | $1.42 | 154,003 | 957* | 1,282* |
| 8× Haiku 4.5 (thinking off) | 29/32 | 5 | 54.3 s | $0.66 | 20,493 | 378 | 508 |
| 1× Fable 5 solo (no dispatcher) | 32/32 | 0 | 569 s | $9.22 total | 39,454 | 69 | ~90† |

\* Haiku's rates count billed thinking tokens, not useful output — it emits fast and discards most of it.
† from a 5-minute arrival-timestamped probe run; per-turn emission estimate, not billed-usage based.

The solo row is the same model as the Fable workers doing the same work in series — 569 s alone, 80.6 s as a pool of 8, whose 32 requests sum to 564 s of work: the solo run re-laid in parallel. Local workers: 3.3× faster than Fable workers, and the $6.28 worker bill drops to electricity. Fable earns its price one way — zero retries. The locals needed 7; all recovered on feedback.

Haiku is the surprise, twice. With thinking on: slowest of the pools, billed for 154k output tokens to write what the locals wrote in 8.5k — you pay for every thought. Thinking off (`MAX_THINKING_TOKENS=0`): 3× faster, under half the cost, and it dropped 3 items the thinking version got right. The thinking tokens weren't all waste. Pick your tax: latency and tokens, or quality.

The harness took five runs to be fair to a real model: 1/32 (rejected a dotted-qualname dialect) → 12/32 (implicit parameter requirement) → 30/32 (undisclosed length threshold) → 31/32 (underscore-variant key crashed the inserter) → 32/32. Every fix deterministic, regression-tested against the real failed responses. The model was never incoherent. The harness was unfair.

## How the locals were picked

One GPU, one server at a time, three suites — throughput, 36 tool-call trials, 5 agentic repo-editing tasks — across llama.cpp Vulkan, llama.cpp CUDA (Docker and bare metal), and vLLM. The serving story — batching, quants, parsers — is in the last post. This table is the quality side it left out.

| Config | decode t/s | x4 agg | toolcall strict/lenient† | agentic | VRAM |
|---|---:|---:|---:|---:|---:|
| Gemma4 12B (Vulkan) | 68.9 | 30.5 | 0.806 / 1.000 | 3/5 | 8.5 GB |
| Gemma4 12B + MTP | 88.1 | 29.6 | 0.778 / 1.000 | 5/5 | 8.9 GB |
| Gemma4 26B A4B | 118.1 | 48.2 | 0.917 / 0.944 | 5/5 | 15.3 GB |
| 26B A4B `-cmoe` (CPU experts) | 14.6 | 9.5 | 0.917 / 0.972 | 4/5 | **3.0 GB** |
| Qwen3.6-27B Q3 | 43.5 | 48.0 | **1.000** | 5/5 | 15.3 GB |
| Nex-N2-mini Q3 | 136.6 | 127.2 | 0.778 / 0.833 | 5/5 | 16.3 GB |
| **byteshape 35B-A3B (Vulkan)** | **127.7** | 91.0 | **1.000** | **5/5** | 19.3 GB |
| Qwopus3.6-27B-v2 | 65.7 | 44.2 | **1.000** | 5/5 | 19.7 GB |
| same weights, CUDA Docker + MTP | **143.4** | 114.6 | **1.000** | — | 19.6 GB |
| same, CUDA, no spec-decode | 138.0 | **174.8** | — | — | 18.9 GB |
| same, CUDA **bare metal** | 135.7 | 107.4 | **1.000** | — | 19.6 GB |
| Qwen 35B AWQ, vLLM 0.22.1 | 130.6 | **360.3** | 0.167* | 0/5* | 21.8 GB |
| Qwen3-30B-A3B GPTQ, vLLM | 183.8 | **534.4** (808.7 @x8) | 0.972 | 3/5‡ | 22.2 GB |

† lenient forgives exactly one failure type — calling `list_dir` before the requested `read_file` (protocol-valid, fixable by prompting). Everything else still fails. Raw trials: `results/toolcall_lenient.json`.
‡ 3-run variance pass: 3/5, 1/5, 2/5 — the same two tasks failed every run (systematic). Throughput tier only.
\* not a model problem — that config generated gibberish for every prompt under vLLM (a temperature-0 "say hello" returned multi-script token salad). Same weights score 1.000 toolcall through llama.cpp; elimination log in the repo.

Two lessons the throughput suite can't teach. Read the failures, not the score: Gemma 12B's 0.806 strict toolcall is 1.000 lenient — every miss was the model calling `list_dir` before `read_file`, zero malformed calls. And cache-bust everything: cached prefill medians read 49.9 tok/s where the true number was 2305. That's 46× off.

One operational footgun: resolve GPUs by name, never enumeration index — Vulkan flipped device order mid-run and silently re-ran a config on the wrong card 😅.

## The fleet

- **Senior + default worker**: byteshape 35B-A3B via llama.cpp, queue-serial. 100% toolcall, 5/5 agentic, 127–143 tok/s. One model, both jobs.
- **Budget coexistence**: 26B `-cmoe` senior (3.0 GB) + 12B worker, 11.1 GB peak, measured under concurrent load.
- **Parallel pool (throughput tier)**: Qwen3-30B-A3B GPTQ under vLLM — 1,071 tok/s sustained at x16 (the sweep moved the knee past the original 808.7 @x8), toolcall 0.972. The agentic variance pass keeps it off multi-turn duty; its lane is single-shot fan-out — exactly what the showcase ran.

Next post: the same fleet on serial multi-turn work — a full CAD-kernel build replay. Numbers still cooking.

## Reproduction

Driver 580.159.03, llama.cpp b9592/b9596, vLLM 0.22.1. Harness, configs, raw logs, model SHAs, and failure diagnoses are all in the repo:

```bash
bench/run_config.sh C12-byteshape-35b            # best Vulkan config
bench/run_config_baremetal_cuda.sh C16-cuda-baremetal
bench/run_config_vllm.sh C15-vllm-35b            # vLLM parallel scaling
```

github.com/svankina/local_agents

Switching costs approaching zero.
