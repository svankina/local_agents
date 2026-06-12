# Building a Local Subagent Fleet on One RTX 3090 Ti

One 24 GB gaming GPU is now enough to serve an agent model that tool-calls at 100% and codes at 130+ tokens/sec. That changes the economics of Claude Code and Codex-style workflows.

We do not think it makes cloud agents obsolete. The useful shape is narrower: keep a strong cloud model in the senior seat, then push implementation drafts, file search, and test-fix loops into local workers when the work can tolerate a queue. The local workers spend local tokens instead of cloud output tokens. The question is whether the saved cloud money is worth the added serving complexity and possible wall-clock delay.

This post is the draft report for that experiment. The benchmark campaign is complete enough to pick a local serving shape. The M1 replay, the end-to-end coding experiment that measures wall-clock speedup and cloud-token savings, is designed but not yet run. Wherever the article needs those results, we leave explicit `[RESULTS TBD]` placeholders instead of guessing.

## The Bench Campaign

The hardware was a single NVIDIA GeForce RTX 3090 Ti with 24 GB of VRAM. The harness served one config at a time through an OpenAI-compatible endpoint, then ran three suites:

- Throughput: prefill/decode medians plus 2-way and 4-way concurrent requests.
- Tool calling: 36 synthetic tool-choice and argument-fidelity trials at temperature 0.2.
- Agentic tasks: five small repository-editing tasks through a minimal tool loop.

We tested Gemma 4 12B/26B, Qwen3.6-27B, Nex-N2-mini, byteshape Qwen3.6-35B-A3B, Qwopus3.6-27B-v2, a CUDA Docker control, and a vLLM AWQ serving path. The headline table below uses committed result JSONs and the aggregate notes in `RESULTS.md`.

| Config | Model/serving shape | p1k decode t/s | x4 aggregate t/s | Toolcall @0.2 | Agentic @0.2 | VRAM loaded |
|---|---|---:|---:|---:|---:|---:|
| C1 | Gemma 4 12B QAT, Vulkan | 68.9 | 30.5 | 0.806 | 3/5 | 8541 MiB |
| C2 | Gemma 4 12B QAT + MTP, Vulkan | 88.1 | 29.6 | 0.778 | 5/5 | 8861 MiB |
| C3 | Gemma 4 12B QAT, `--parallel 3`, Vulkan | 59.2 | 74.0 | 0.806 | n/a | 7744 MiB |
| C4 | Gemma 4 26B A4B QAT, Vulkan | 118.1 | 48.2 | 0.917 | 5/5 | 15287 MiB |
| C5 | Gemma 4 26B A4B QAT `-cmoe`, Vulkan | 14.6 | 9.5 | 0.917 | 4/5 | 3020 MiB |
| C6 | Gemma 4 26B A4B QAT `-cmoe` + MTP, Vulkan | 17.0 | 8.7 | 0.944 | 5/5 | 58 MiB caveat |
| C7 | Qwen3.6-27B Q3_K_M, Vulkan | 43.5 | 48.0 | 1.000 | 5/5 | 15309 MiB |
| C8 | Nex-N2-mini Q3_K_M, Vulkan | 136.6 | 127.2 | 0.778 | 5/5 | 16322 MiB |
| C12 | byteshape Qwen3.6-35B-A3B IQ4_XS, Vulkan + embedded MTP | 127.7 | 91.0 | 1.000 | 5/5 | 19277 MiB |
| C13 | Qwopus3.6-27B-v2 MTP Q4_K_M, Vulkan | 65.7 | 44.2 | 1.000 | 5/5 | 19685 MiB |
| C14 | byteshape Qwen3.6-35B-A3B IQ4_XS, CUDA Docker + MTP | 143.4 | 114.6 | 1.000 | n/a | 19583 MiB |
| C14 no-spec | same weights, CUDA Docker, no MTP | 138.0 | 174.8 | n/a | n/a | 18897 MiB |
| C15 | Qwen3.6-35B-A3B AWQ, vLLM 0.22.1 | 130.6 | 360.3 | 0.167 | 0/5 | 21811 MiB |

The champion for the llama.cpp path is C12: byteshape Qwen3.6-35B-A3B IQ4_XS. It hit 127.7 decode tokens/sec, 1.000 toolcall score, 5/5 agentic tasks, and loaded in 19277 MiB. The C14 CUDA Docker control was faster at 143.4 decode tokens/sec and also scored 1.000 on tool calls, but it was a version-skewed Docker run, not the preregistered bare-metal path for the end-to-end experiment. C16 bare-metal CUDA: `[C16 pending]`.

The most interesting result is C15. vLLM got real parallel throughput: 360.3 aggregate tokens/sec at x4, or 2.76x over its 130.6 single-stream client-measured decode rate. That is four workers at about 90 tokens/sec each. But the same serving path failed the harness's tool-use bar, so it is a throughput unlock, not yet a practical worker pool.

## What We Learned the Hard Way

Vulkan multi-slot scaling was weak. C3 reached 74.0 aggregate tokens/sec at x4 versus 59.2 single-stream decode, only 1.25x. That misses the 1.5x worker-pool rubric. For llama.cpp Vulkan, queue-serial workers are the conservative design.

MTP helped single-stream decode but fought batching. Gemma 12B improved from 68.9 to 88.1 tokens/sec with MTP, a 1.28x gain. Under CUDA on the 35B model, MTP was only 1.04x single-stream: 143.4 versus 138.0 tokens/sec. More importantly, the CUDA x4 aggregate dropped from 174.8 tokens/sec without speculation to 114.6 with MTP, a 34% drop.

CUDA beat Vulkan for the same byteshape weights. C12 Vulkan reached 127.7 p1k decode tokens/sec. C14 CUDA+MTP reached 143.4, roughly 12% faster. The experiment design records this as "about +10%" because C12 and C14 used different llama.cpp builds: local b9596 for Vulkan and Docker b9592 for CUDA.

vLLM continuous batching is the real parallel unlock. The llama.cpp CUDA no-spec control reached 174.8 aggregate tokens/sec at x4, only 1.27x over its 138.0 single-stream rate. vLLM reached 360.3 aggregate tokens/sec at x4, 2.76x over its 130.6 single-stream rate. Within that vLLM run, the scaling ratio is the useful apples-to-apples metric because vLLM reports client wall usage rather than llama.cpp server timings.

Toolcall "failures" need failure-type analysis. Gemma 12B's C1 failures were all `wrong tool: list_dir`. It did not emit broken JSON or ignore the tool schema. It cautiously listed the directory before reading the requested file. Strict score: 0.806. Lenient interpretation for "valid tool protocol, conservative workflow": 1.000.

True prefill needs cache-busted probes. The normal throughput suite's p8k prefill medians are cache-polluted because later trials reused prompt cache and reported `prompt_n=4`. For C1 the suite p8k prefill was 49.9 tokens/sec, while the cache-busted probe median was 2305.4 tokens/sec. For C4 it was 74.3 versus 3840.8. For C7 it was 46.7 versus 1116.3. For C8 it was 106.7 versus 2990.5. That is why the scoreboard labels suite p8k prefill as continuity data, not decision data.

Agentic small-N is high variance. C1 and C2 use the same Gemma 12B weights, but scored 3/5 and 5/5. Treat the five-task suite as a coarse ranking signal, not a precise capability measurement.

## War Stories

The most embarrassing bug was device selection. Vulkan device enumeration flipped mid-campaign and sent a 13 GB model to the 8 GB second GPU. The visible artifact was C6 reporting 58 MiB of loaded VRAM even though its phase-1 NVIDIA value had been 3375 MiB. The fix is boring and necessary: resolve the device by name, not by index.

The harness also had to handle worker failure as a normal benchmark event. One subagent died silently mid-run. The runner had to detect the missing output, salvage the completed logs, and mark the result so we did not accidentally promote a partial run.

vLLM took five startup-shaping attempts to fit the 24 GB card. The original 32k configuration OOMed during CUDA graph/KV profiling. The successful shape was `--max-model-len 16384 --max-num-seqs 4 --gpu-memory-utilization 0.92`; `--max-num-seqs` was the key knob.

## Open Issue: vLLM Serves This Model Wrong

Under llama.cpp, the byteshape Qwen3.6-35B-A3B weights tool-called at 1.000. Under vLLM, the AWQ serving path emitted zero required tool calls with both the `qwen3_coder` and `qwen3_xml` parser choices. The measured score was 0.167 only because the two no-tool cases passed.

Manual diagnosis found the real cause, and it is worse than parser plumbing: the vLLM server generates gibberish for every prompt — a temperature-0 "say hello" returns multi-script token salad. We ruled out the tool parser (both fail identically), the chat template (passing the repo's template explicitly via `--chat-template` changed nothing), and mrope config loss (re-injecting the rope block via `--hf-overrides` silenced vLLM's startup warning but not the garbage). What remains is vLLM 0.22.1's quantized-MoE path for this VL-flavored architecture, its `--language-model-only` extraction, or the community AWQ quant itself. The full elimination log lives in `results/raw/C15-vllm-35b/GIBBERISH-DIAGNOSIS.md`.

Two lessons we'd flag for anyone benchmarking serving stacks. First, throughput suites cannot see this failure: 360 tokens/sec of garbage measures exactly like 360 tokens/sec of code. Always probe output coherence before trusting a config's speed numbers. Second, this says nothing about the model — the same weights are flawless through llama.cpp. The parallel-pool architecture remains attractive on the scaling mechanics; it needs either a vLLM build that serves this architecture correctly or a model with first-class vLLM support.

## The Fleet Design

The design we would actually run has two tiers.

The senior tier stays quality-first. C12 is the current llama.cpp champion: fast enough at 127.7 decode tokens/sec, strict 1.000 tool calling, and 5/5 agentic. C7 is the clean strict senior among configs with cache-busted prefill: 43.5 decode tokens/sec, 1116.3 true prefill tokens/sec, 1.000 tool calling, and 5/5 agentic. C13 is viable but slower at 65.7 decode tokens/sec and uses 19685 MiB.

The worker tier has two modes. For quality-critical serial work, use queue-serial llama.cpp workers. That avoids the weak Vulkan multi-slot scaling and keeps the known-good tool-calling path. For parallel fan-out, keep a vLLM pool as the target architecture, but do not use it for autonomous coding until the tool-call plumbing is fixed.

Coexistence matters because the senior and worker may need to share the same card. The measured fallback layout was a C5-style 26B `-cmoe` senior plus a C1-style 12B worker with `--parallel 2`. Loaded VRAM was 10386 MiB total, then 11138 MiB after concurrent load. Under contention, the senior decoded at 15.6 tokens/sec, and the two worker streams decoded at 63.8 and 63.8 tokens/sec. The end-to-end worker aggregate across both requests was only 9.4 tokens/sec because the requests shared the load window and included prompt/wait time.

The direction for the article experiment is bare metal. The C14 Docker CUDA row is useful evidence, but measured Arm C should run a native host `llama-server` with backend, build, flags, model SHA, GPU name, and logs recorded per run.

## The Experiment We Still Need to Run

The end-to-end question is not "can the model pass a toy harness?" It is whether local subagents reduce wall-clock time or cloud-token spend on a realistic coding milestone.

The preregistered replay is custom_cad M1, "A Box I Can Orbit": `profile -> extrude -> half-edge B-rep -> validateSolid -> tessellate -> RenderData -> three.js viewport`. That task is a useful mix of kernel math, TypeScript API design, frontend rendering, integration tests, and visual acceptance.

We will run at least three successful repetitions per arm, preferably five:

| Arm | Name | Senior/orchestrator | Worker execution | What it measures |
|---|---|---|---|---|
| A | Claude solo | Claude Code cloud model | None | Baseline for doing all planning, edits, testing, and repairs in cloud tokens. |
| B | Claude + cloud subagents | Claude Code cloud model | Cloud subagents | The existing subagent-driven workflow: likely faster when parallelism works, but cloud-token heavy. |
| C | Claude + local subagents | Claude Code cloud model | Bare-metal local Qwen workers through a Bash shim | Whether local implementation work can displace cloud output tokens while the cloud senior reviews and gates changes. |

Primary metrics:

- Total wall-clock time from first prompt to accepted M1 exit.
- Wall-clock per task.
- Cloud input, output, cache-read, cache-write tokens, and USD.
- Local input/output tokens, decode tokens/sec, prompt tokens/sec, and active server time.
- Quality result, repair loops, senior patch rejections, TypeScript errors, vitest failures, and screenshot acceptance.

Pre-registered success criteria:

- Quality success: `npm run check` passes, `npx vitest run test/integration/m1.test.ts` passes, screenshot accepted, and no architecture violation is found.
- Cost win for Arm C: median cloud USD at least 40% lower than Arm B and at least 25% lower than Arm A among quality-successful runs.
- Wall-clock win for Arm C: median total wall-clock at least 10% lower than Arm A.
- Robustness: Arm C success rate at least 2/3 for `N=3` or at least 4/5 for `N=5`.

### Results Placeholders

| Arm | Quality-successful runs | Median wall-clock | Median cloud USD | Median cloud output tokens | Median repair loops |
|---|---:|---:|---:|---:|---:|
| A Claude solo | [RESULTS TBD] | [RESULTS TBD] | [RESULTS TBD] | [RESULTS TBD] | [RESULTS TBD] |
| B Claude + cloud subagents | [RESULTS TBD] | [RESULTS TBD] | [RESULTS TBD] | [RESULTS TBD] | [RESULTS TBD] |
| C Claude + local subagents | [RESULTS TBD] | [RESULTS TBD] | [RESULTS TBD] | [RESULTS TBD] | [RESULTS TBD] |

| Comparison | Wall-clock delta | Cloud USD delta | Cloud output-token delta | Interpretation |
|---|---:|---:|---:|---|
| C vs A | [RESULTS TBD] | [RESULTS TBD] | [RESULTS TBD] | [RESULTS TBD] |
| C vs B | [RESULTS TBD] | [RESULTS TBD] | [RESULTS TBD] | [RESULTS TBD] |
| B vs A | [RESULTS TBD] | [RESULTS TBD] | [RESULTS TBD] | [RESULTS TBD] |

We should not collapse this to one number. If Arm C saves money but loses wall-clock because workers queue serially, that is still a real result. If it looks cheap only because prompt-cache reads dominated one arm, that is not a local-worker win. If final success hides extra repair loops, the repair count belongs in the headline chart.

## Reproduce It

Hardware and driver evidence from `results/coexistence.json`:

- GPU: NVIDIA GeForce RTX 3090 Ti.
- VRAM: 24564 MiB reported by `nvidia-smi`.
- Driver: 580.159.03.
- CUDA runtime reported by `nvidia-smi`: 13.0.

Key repo commands:

```bash
# llama.cpp local configs
bench/run_config.sh C12-byteshape-35b
bench/run_config.sh C13-qwopus-27b

# CUDA Docker controls
bench/run_config_docker.sh C14-cuda-35b
bench/run_config_docker.sh C14-cuda-35b-nospec

# vLLM continuous batching probe
bench/run_config_vllm.sh C15-vllm-35b

# cache-busted prefill probes
python3 bench/prefill_probe.py

# coexistence probe
python3 bench/coexistence.py
```

Model lockfile entries from `bench/models.lock`:

| Artifact | Locked size or revision |
|---|---:|
| `Qwen3.6-27B-Q3_K_M.gguf` | 13586217184 bytes |
| `gemma-4-12B-it-qat-UD-Q4_K_XL.gguf` | 6716355328 bytes |
| `gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf` | 14249045120 bytes |
| `mtp-gemma-4-12b-it.gguf` | 253707328 bytes |
| `mtp-gemma-4-26B-A4B-it.gguf` | 251937728 bytes |
| `nex-agi_Nex-N2-mini-Q3_K_M.gguf` | 16226547712 bytes |
| `Qwen3.6-35B-A3B-IQ4_XS-4.19bpw.gguf` | 18605304512 bytes |
| `Qwopus3.6-27B-v2-MTP-Q4_K_M.gguf` | 16810713312 bytes |
| `ghcr.io/ggml-org/llama.cpp:server-cuda` | digest `sha256:e502860c8aa147e74e7cf42568fa2a8407c578dd291c1b231f698a55dd83fef6`, llama.cpp b9592 `ac4cddeb0` |
| `mattbucci/Qwen3.6-35B-A3B-AWQ` | revision `7525d0f423bd615da6cc3cf3ae6fdae42941ea05`, weights 20457664144 bytes |
| `vllm/vllm-openai:v0.22.1` | digest `sha256:953d3a06d5e64ab582985cd7401289d3abf2a2c14ef2158e9a84313daeec77d7`, revision `0decac0d96c42b49572498019f0a0e3600f50398` |

The main caution for reproduction is prefill. Do not trust normal suite p8k prefill numbers unless the probe busts prompt cache. For speed comparisons, record whether timings came from llama.cpp server fields or client wall usage. For agentic comparisons, keep failures and repair loops in the dataset.

