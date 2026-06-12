# 23× faster, 74% cheaper: running Claude Code with local subagents on an RTX 3090 Ti instead of Fable 5 doing everything itself

Scope up front: 23×/−74% is the work phase of an embarrassingly-parallel fan-out at quality parity (32/32 verified, both arms); end-to-end the same run is 3.2× faster. On serial multi-turn work the gap is smaller — a replayed CAD-kernel build (n=1 per arm) shows −33% cloud cost at +19% wall-clock. Every number is committed with raw logs.

Setup: Claude Fable 5 stays senior — planning, review, merges — and the grunt work goes local on an RTX 3090 Ti (24 GB). Two local configs earned roles in the benchmarks below: byteshape's Qwen3.6-35B-A3B IQ4_XS under llama.cpp for queue-serial agentic work (**100% toolcall, 5/5 agentic, 127–143 tok/s**), and Qwen3-30B-A3B GPTQ under vLLM for parallel fan-out. Baseline: Fable 5 doing everything itself.

## The fan-out showcase

Workload: backfill docstrings for 32 functions across scrapy@a8ffdcf8, each item verified deterministically — py_compile, AST equivalence proving code untouched, parameter coverage, verbatim parameter mentions, anti-placeholder checks. Same items, same verifier, two arms.

| | fleet (F-06) | solo (S-01) |
|---|---:|---:|
| verified | 32/32 | 32/32 |
| work phase | 24.7 s | 569 s |
| end-to-end | 176 s | 569 s |
| cloud cost | $2.40 | $9.22 |
| output throughput | 344 tok/s | 69.3 tok/s |

The fleet arm is Fable 5 making exactly two cloud calls — decompose (91 s), synthesize (57 s) — around 8 concurrent local streams of the vLLM pool: 39 requests, 78,130 local tokens, 7 feedback retries, all recovered; aggregate 344 completion tok/s (3,157 counting fresh prefill), per-stream median 58, peak 101. The solo arm: Fable 5 alone, 85 turns, 39,454 output tokens.

Work phase 23.0× faster, end-to-end 3.2×, cloud cost −74%, throughput 5.0× — at quality parity. The runtime split is the real finding: supervisor bookends 148 s (84%), local fleet 24.7 s (14%), harness 3 s (2%). The fleet did all the work in 14% of the window; the next optimization is the cloud bookends, not the workers.

The harness took five runs to be fair to a real model: 1/32 (rejected a dotted-qualname dialect) → 12/32 (implicit parameter requirement) → 30/32 (undisclosed length threshold) → 31/32 (underscore-variant key crashed the inserter) → 32/32. Every fix deterministic, regression-tested against the real failed responses. The model was never incoherent — the harness was unfair.

## Benchmark results

One GPU, one server at a time, three suites — throughput, 36 tool-call trials, 5 agentic repo-editing tasks — across llama.cpp Vulkan, llama.cpp CUDA (Docker and bare metal), and vLLM.

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
\* not a model problem — see "vLLM output corruption."

## Five lessons

1. **llama.cpp slot-parallelism barely scales**: 4 streams gives 1.25–1.27× aggregate — one fast queue-serial server beats a slot pool.
2. **MTP speculative decoding helps solo, hurts batched**: +28% single-stream on Gemma 12B, −34% x4 aggregate on CUDA — turn it off past one stream.
3. **vLLM continuous batching is the real parallel path**: 808.7 tok/s aggregate at x8 on Qwen3-30B-A3B GPTQ — 4.40× scaling, ~101 tok/s per stream, coherent output, real tool calls — where llama.cpp managed 1.27×.
4. **Read the failures, not the score**: Gemma 12B's 0.806 strict toolcall is 1.000 lenient — every miss was the model calling `list_dir` before `read_file`, zero malformed calls.
5. **Cache-bust everything**: cached prefill medians read 49.9 tok/s where the true number was 2305 (46× off), and throughput suites can't see output corruption.

Two operational rules: resolve GPUs by name, never enumeration index (Vulkan flipped device order mid-run and silently re-ran a config on the wrong card), and `--max-num-seqs 4` is what got vLLM into 24 GB after the 32k-context startup OOMed.

## vLLM output corruption

The first vLLM config posted the best parallel scaling and scored zero on quality: gibberish for every prompt — a temperature-0 "say hello" returned multi-script token salad. We ruled out the tool parser, chat template, and mrope config loss; the same weights score 1.000 toolcall through llama.cpp. The corruption is model-specific: a text-only architecture with an official quant (Qwen3-30B-A3B GPTQ-Int4) ran coherently under the same vLLM image, after two plumbing rounds (gen-3 Qwen needs `--tool-call-parser hermes`, not `qwen3_xml`; thinking models need probe budgets that survive the reasoning channel). Elimination log in the repo.

## The fleet

- **Senior + default worker**: byteshape 35B-A3B via llama.cpp, queue-serial. 100% toolcall, 5/5 agentic, 127–143 tok/s. One model, both jobs.
- **Budget coexistence**: 26B `-cmoe` senior (3.0 GB) + 12B worker, 11.1 GB peak, measured under concurrent load.
- **Parallel pool (throughput tier)**: Qwen3-30B-A3B GPTQ under vLLM — 808.7 tok/s aggregate at x8, toolcall 0.972. The agentic variance pass keeps it off autonomous multi-turn duty — but well-specified single-shot fan-out is exactly what the showcase ran on it.

## CAD kernel part 1 build (replay)

Replays a small CAD engine build — B-rep kernel → tessellation → three.js viewport — against a pinned plan and fixed gates (a shaded box orbiting at 60 fps behind a hard test gate). One completed rep per arm; N≥3 planned, so preliminary:

| | wall-clock | cloud $ | output tokens |
|---|---:|---:|---:|
| original build (cloud-subagent workflow, forensic baseline) | 65.6 min | $29.22 | 162k |
| A: Fable 5 solo (n=1) | 13.3 min | $13.44 | 51.5k |
| B: Fable 5 + cloud subagents (n=1) | 16.7 min | $13.30 | — |
| C: Fable 5 senior + local workers (n=1) | 15.8 min | $9.05 | 50.5k local |

All gates verified in all three arms. Arm B is slower than solo at the same cost: the six worker jobs are dependency-chained, so subagents added handoff overhead without parallelism. Arm C cuts cloud cost 33% vs solo at +19% wall-clock — its local workers generated 50,536 completion tokens against solo's 51,467 cloud output tokens, nearly token-for-token the same code volume moved off the cloud; the remaining cost is the senior's 53 supervision turns. One rep each of arms B and C was excluded for documented harness incidents (an inherited-MCP browser grab; a background dispatch that killed a print-mode session), not arm behavior.

## Reproduction

Driver 580.159.03, llama.cpp b9592/b9596, vLLM 0.22.1. Harness, configs, raw logs, model SHAs, and failure diagnoses are all in the repo:

```bash
bench/run_config.sh C12-byteshape-35b            # best Vulkan config
bench/run_config_baremetal_cuda.sh C16-cuda-baremetal
bench/run_config_vllm.sh C15-vllm-35b            # vLLM parallel scaling
```

github.com/svankina/local_agents
