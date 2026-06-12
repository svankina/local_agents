# [N×] faster, [K%] fewer cloud tokens: running Claude Code with local subagents (byteshape Qwen3.6-35B-A3B on a $700 used GPU) instead of Fable 5 doing everything itself

*[N×] and [K%] are placeholders — they land when the CAD kernel part 1 build experiment at the bottom finishes. Every other number in this post is already measured and committed with raw logs.*

The bet: keep Claude Fable 5 as the senior — it plans, reviews, merges — and push the grunt work (search, edits, test loops) to a local model on a used RTX 3090 Ti (~$700, 24 GB). The winner of the benchmark campaign below is byteshape's Qwen3.6-35B-A3B IQ4_XS quant: **100% toolcall, 5/5 agentic, 127–143 tok/s decode**. The baseline it has to beat is Fable 5 doing everything itself.

We benchmarked Gemma 4 12B/26B, Qwen3.6-27B/35B, Nex-N2-mini, and Qwopus across llama.cpp Vulkan, llama.cpp CUDA (Docker and bare metal), and vLLM.

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

## Five lessons

1. **llama.cpp slot-parallelism barely scales**: 4 streams gives 1.25× (Vulkan) to 1.27× (CUDA) aggregate — one fast queue-serial server beats a slot pool.
2. **MTP speculative decoding helps solo, hurts batched**: +28% single-stream on Gemma 12B, −34% x4 aggregate on CUDA — turn it off past one stream.
3. **vLLM continuous batching is the real parallel path**: 2.76× at x4 (360 tok/s aggregate, ~90 per stream) on the same card where llama.cpp managed 1.27×.
4. **Read the failures, not the score**: Gemma 12B's 0.806 toolcall was entirely the model calling `list_dir` before `read_file` — zero malformed calls, a prompting fix.
5. **Cache-bust everything**: cached prefill medians read 49.9 tok/s where the true number was 2305 (46× off), and throughput suites can't see output corruption.

Two operational rules earned the hard way: resolve GPUs by name, never enumeration index — Vulkan flipped device order mid-campaign and silently re-ran one config on the wrong card — and `--max-num-seqs 4` is the flag that got vLLM to fit in 24 GB after the 32k-context startup OOMed.

## The one that got away

vLLM posted the best parallel scaling and scored zero on quality — because it generated gibberish for every prompt; a temperature-0 "say hello" returned multi-script token salad. We ruled out the tool parser (both candidates fail identically), the chat template (passed explicitly), and mrope config loss (re-injected via `--hf-overrides`). Remaining suspects: vLLM 0.22.1's quantized-MoE path for this VL-flavored architecture, or the community AWQ quant itself. The same weights score 1.000 toolcall through llama.cpp; the elimination log is in the repo.

## The fleet

- **Senior + default worker**: byteshape 35B-A3B via llama.cpp, queue-serial. 100% toolcall, 5/5 agentic, 127–143 tok/s. One model, both jobs.
- **Budget coexistence**: 26B `-cmoe` senior (3.0 GB) + 12B worker, 11.1 GB peak, measured under concurrent load.
- **Parallel pool**: vLLM architecture, parked until the serving bug is fixed or a vLLM-first model takes the slot.

## The experiment that fills in the headline

We replay the **CAD kernel part 1 build**: a small CAD engine from scratch — B-rep kernel → tessellation → three.js viewport — until a shaded box orbits at 60 fps behind a hard test gate. It's a real milestone we already shipped once, so the plan is pinned and the acceptance criteria are non-negotiable. Three arms, N≥3 runs each: Fable 5 solo, Fable 5 + cloud subagents, Fable 5 + local subagents. Measured: wall-clock, cloud tokens/$, local tokens, repair loops, GPU watt-hours per task.

| | wall-clock | cloud $ | repair loops |
|---|---:|---:|---:|
| Fable 5 solo | TBD | TBD | TBD |
| + cloud subagents | TBD | TBD | TBD |
| + local subagents | TBD | TBD | TBD |

If local workers save tokens but lose wall-clock to the serial queue, we publish that too.

## Reproduce it

RTX 3090 Ti (24 GB), driver 580.159.03, llama.cpp b9592/b9596, vLLM 0.22.1. Harness, configs, raw logs, model SHAs, and failure diagnoses are all in the repo:

```bash
bench/run_config.sh C12-byteshape-35b            # Vulkan champion
bench/run_config_baremetal_cuda.sh C16-cuda-baremetal
bench/run_config_vllm.sh C15-vllm-35b            # the scaling demo
```

github.com/svankina/local_agents
