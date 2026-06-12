# A Local Subagent Fleet on One RTX 3090 Ti

**TL;DR**

- One 24 GB gaming GPU now serves a coding agent that tool-calls at **100%** and decodes at **127–143 tok/s**: byteshape's Qwen3.6-35B-A3B IQ4_XS quant.
- We benchmarked **16 configs** (Gemma 4 12B/26B, Qwen3.6-27B/35B, Nex-N2-mini, Qwopus) across llama.cpp Vulkan, llama.cpp CUDA (Docker + bare metal), and vLLM. Every number is committed with raw logs.
- llama.cpp does **not** scale across parallel slots (1.27× at 4 streams). vLLM does (**2.76×** — four workers at ~90 tok/s each), but its serving path corrupted this model's output. Details below.
- Next: replaying a real CAD-engine milestone with cloud-senior + local-worker arms to measure wall-clock and cloud-token savings. Results pending.

## The scoreboard

Single 3090 Ti, one server at a time, three suites: throughput, 36 tool-call trials, 5 agentic repo-editing tasks.

| Config | decode t/s | x4 agg | toolcall | agentic | VRAM |
|---|---:|---:|---:|---:|---:|
| Gemma4 12B (Vulkan) | 68.9 | 30.5 | 0.806 | 3/5 | 8.5 GB |
| Gemma4 12B + MTP | 88.1 | 29.6 | 0.778 | 5/5 | 8.9 GB |
| Gemma4 26B A4B | 118.1 | 48.2 | 0.917 | 5/5 | 15.3 GB |
| 26B A4B `-cmoe` (CPU experts) | 14.6 | 9.5 | 0.917 | 4/5 | **3.0 GB** |
| Qwen3.6-27B Q3 | 43.5 | 48.0 | **1.000** | 5/5 | 15.3 GB |
| Nex-N2-mini Q3 | 136.6 | 127.2 | 0.778 | 5/5 | 16.3 GB |
| **byteshape 35B-A3B (Vulkan)** | **127.7** | 91.0 | **1.000** | **5/5** | 19.3 GB |
| Qwopus3.6-27B-v2 | 65.7 | 44.2 | **1.000** | 5/5 | 19.7 GB |
| same weights, CUDA Docker + MTP | **143.4** | 114.6 | **1.000** | — | 19.6 GB |
| same, CUDA, no spec-decode | 138.0 | **174.8** | — | — | 18.9 GB |
| same, CUDA **bare metal** | 135.7 | 107.4 | **1.000** | — | 19.6 GB |
| Qwen 35B AWQ, vLLM 0.22.1 | 130.6 | **360.3** | 0.167* | 0/5* | 21.8 GB |

\* not a model problem — see "the one that got away."

## Five things we learned the hard way

1. **llama.cpp slot-parallelism barely scales.** 4 concurrent streams = 1.25× (Vulkan) to 1.27× (CUDA) aggregate. One fast queue-serial server beats a slot pool.
2. **MTP speculative decoding helps solo, hurts batched.** +28% single-stream on Gemma 12B, but on CUDA the x4 aggregate drops 34% with speculation on. Turn it off the moment you serve more than one stream.
3. **vLLM continuous batching is the real parallel unlock**: 360 tok/s aggregate at x4, 2.76× scaling, ~90 tok/s per worker — on the same card where llama.cpp managed 1.27×.
4. **Read the failures, not just the score.** Gemma 12B's "0.806 toolcall" was entirely the model cautiously calling `list_dir` before `read_file` — zero malformed calls. Lenient score: 1.000. One prompt line fixes it.
5. **Trust nothing you didn't cache-bust.** Our suite's prefill medians were up to **77× off** (49.9 vs 2305 tok/s) because prompt cache leaked into trials. And throughput suites can't see output corruption: 360 tok/s of garbage measures exactly like 360 tok/s of code.

## War stories, briefly

Vulkan device enumeration **flipped order mid-campaign** and pinned a 13 GB model to the 8 GB second GPU (0.8 tok/s). Resolve devices by name, never index. A subagent died silently mid-run and we salvaged partial raws. vLLM took five startup attempts to fit 24 GB — `--max-num-seqs 4` was the knob that mattered. Building CUDA llama.cpp with zero sudo via pip-wheel nvcc works, after four toolchain quirks.

## The one that got away

vLLM posted the best parallel scaling **and** scored zero on quality — because it generated gibberish for every prompt. Temperature-0 "say hello" → multi-script token salad. We eliminated the tool parser (both candidates fail identically), the chat template (passed explicitly, no change), and mrope config loss (re-injected via `--hf-overrides`, warning gone, garbage stayed). Remaining suspects: vLLM 0.22.1's quantized-MoE path for this VL-flavored architecture, or the community AWQ quant. Same weights are flawless through llama.cpp. Elimination log in the repo.

## The fleet we're actually running

- **Senior + default worker: byteshape 35B-A3B via llama.cpp, queue-serial.** 100% toolcall, 5/5 agentic, ~130 tok/s. One model, both jobs.
- **Budget coexistence**: 26B `-cmoe` senior (3 GB!) + 12B worker = 11.1 GB peak, measured working under concurrent load.
- **Parallel pool**: vLLM architecture, parked until the serving bug is resolved or a vLLM-first model takes the slot.

## What's next

We're replaying a real milestone — a CAD engine's "box I can orbit" (B-rep kernel → tessellation → three.js viewport, with a hard test gate) — three arms, N≥3 each: Claude solo, Claude + cloud subagents, Claude + **local** subagents (bare-metal serving, cloud senior reviewing). Measuring wall-clock, cloud tokens/$, local tokens, idle/thinking time split, and full hardware telemetry down to GPU watt-hours per task.

| | wall-clock | cloud $ | repair loops |
|---|---:|---:|---:|
| Claude solo | TBD | TBD | TBD |
| + cloud subagents | TBD | TBD | TBD |
| + local subagents | TBD | TBD | TBD |

If local workers save money but lose wall-clock to the serial queue, we'll publish that too.

## Reproduce it

RTX 3090 Ti (24 GB), driver 580.159.03, llama.cpp b9592/b9596, vLLM 0.22.1. Everything — harness, configs, raw logs, model SHAs, failure diagnoses — is in the repo:

```bash
bench/run_config.sh C12-byteshape-35b            # Vulkan champion
bench/run_config_baremetal_cuda.sh C16-cuda-baremetal
bench/run_config_vllm.sh C15-vllm-35b            # the scaling demo
```

github.com/svankina/local_agents
