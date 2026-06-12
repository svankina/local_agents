# Local Fleet Benchmark Results

All figures below come from committed JSON plus raw logs under `results/raw/`. The normal throughput suite's `prefill_tps` medians are cache-polluted because later trials reused prompt cache (`prompt_n=4`); use `results/prefill_probe.json` for true cache-busted prefill where available.

## Scoreboard

| Config | Role Tested | True prefill t/s | Suite p8k prefill* | p1k decode t/s | x4 aggregate t/s | Toolcall @0.2 | Agentic @0.2 | VRAM loaded |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C1-gemma12b-base | worker | 2305.4 | 49.9 | 68.9 | 30.5 | 0.806 | 3/5 | 8541 MiB |
| C2-gemma12b-mtp | worker | n/a | 51.0 | 88.1 | 29.6 | 0.778 | 5/5 | 8861 MiB |
| C3-gemma12b-par3 | worker pool | n/a | 45.6 | 59.2 | 74.0 | 0.806 | n/a | 7744 MiB |
| C4-gemma26b-gpu | senior | 3840.8 | 74.3 | 118.1 | 48.2 | 0.917 | 5/5 | 15287 MiB |
| C5-gemma26b-cmoe | senior coexist | n/a | 13.4 | 14.6 | 9.5 | 0.917 | 4/5 | 3020 MiB |
| C6-gemma26b-cmoe-mtp | senior coexist | n/a | 12.3 | 17.0 | 8.7 | 0.944 | 5/5 | 58 MiB caveat |
| C7-qwen27b-q3 | senior | 1116.3 | 46.7 | 43.5 | 48.0 | 1.000 | 5/5 | 15309 MiB |
| C8-nex-mini-q3 | senior | 2990.5 | 106.7 | 136.6 | 127.2 | 0.778 | 5/5 | 16322 MiB |
| C12-byteshape-35b | senior | n/a | 97.2 | 127.7 | 91.0 | 1.000 | 5/5 | 19277 MiB |
| C13-qwopus-27b | senior | n/a | 41.9 | 65.7 | 44.2 | 1.000 | 5/5 | 19685 MiB |

*Cache-polluted suite median, retained for continuity with Phase 2. True cache-busted values for C1/C4/C7/C8 are in `results/prefill_probe.json` and used for decisions where available.

## Tool-Call Failures

| Config | Failures at temp 0.2 |
|---|---:|
| C1-gemma12b-base | 7x `wrong tool: list_dir` |
| C2-gemma12b-mtp | 8x `wrong tool: list_dir` |
| C3-gemma12b-par3 | 7x `wrong tool: list_dir` |
| C4-gemma26b-gpu | 1x `wrong tool: list_dir`, 1x `wrong tool: run_bash`, 1x wrong `run_bash` argument |
| C5-gemma26b-cmoe | 2x `wrong tool: list_dir`, 1x `wrong tool: run_bash` |
| C6-gemma26b-cmoe-mtp | 1x `wrong tool: list_dir`, 1x `wrong tool: run_bash` |
| C7-qwen27b-q3 | 0 |
| C8-nex-mini-q3 | 3x no tool call, 2x `wrong tool: list_dir`, 3x wrong path argument |
| C12-byteshape-35b | 0 |
| C13-qwopus-27b | 0 |

The Gemma 12B failures are not malformed tool calls; they are mostly the model choosing `list_dir` before `read_file`. That is a workflow caution, not a JSON/tool-schema failure.

## Notes

- C12 and C13 both accepted embedded MTP: their merged `notes` contain `draft acceptance` lines, and raw server logs show `creating MTP draft context` plus `draft-mtp`.
- C14 CUDA+MTP accepted embedded MTP on the Docker CUDA build: merged `notes` contain `draft acceptance` lines, and the raw server log shows `creating MTP draft context` plus `draft-mtp`.
- MTP speedup: C2 vs C1 improves p1k decode from 68.9 to 88.1 t/s, a 1.28x gain. C6 vs C5 improves p1k decode from 14.6 to 17.0 t/s, a 1.16x gain.
- C6 is a mixed-device result. Throughput/toolcall came from the RTX 3090 Ti, but the agentic re-run landed on RX 580+CPU after Vulkan enumeration flipped; `vram_loaded` is wrong at 58 MiB, and the phase-1 NVIDIA value was 3375 MiB. See `results/raw/C6-gemma26b-cmoe-mtp/DEVICE-CAVEAT.md`.
- The agentic 5-task suite has high run-to-run variance. C1 and C2 use the same weights but scored 3/5 vs 5/5, so treat agentic pass counts as coarse ranking signals.
- Vulkan multi-slot scaling is weak. C3 x4 aggregate is 74.0 t/s vs 59.2 single-stream decode, only 1.25x, below the 1.5x worker rubric. A fast queue-serial MTP worker such as C2 is likely better than a parallel pool.
- C8 temp sweep: toolcall was 0.778 at temp 0.2 vs 0.806 at temp 0.7; agentic was 5/5 at temp 0.2 vs 4/5 at temp 0.7.

## C14 CUDA Addendum

C14 uses the official Docker CUDA image `ghcr.io/ggml-org/llama.cpp:server-cuda@sha256:e502860c8aa147e74e7cf42568fa2a8407c578dd291c1b231f698a55dd83fef6`, llama.cpp `version: 9592 (ac4cddeb0)`, against the same byteshape Qwen3.6 35B IQ4_XS GGUF as C12. This is a version-skewed comparison: C12 Vulkan was run on local b9596, while C14 CUDA uses the current Docker image label b9592.

| Config | Backend | MTP | p1k decode t/s | p8k decode t/s | x2 aggregate t/s | x4 aggregate t/s | x4 scaling | x4 per-stream t/s | Toolcall @0.2 | VRAM loaded |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C12-byteshape-35b | Vulkan b9596 | yes | 127.7 | 127.9 | 9.6 | 91.0 | 0.71x | 31.0 | 1.000 | 19277 MiB |
| C14-cuda-35b | CUDA Docker b9592 | yes | 143.4 | 149.5 | 96.1 | 114.6 | 0.80x | 33.7 | 1.000 | 19583 MiB |
| C14-cuda-35b-nospec | CUDA Docker b9592 | no | 138.0 | 132.2 | 131.7 | 174.8 | 1.27x | 54.4 | n/a | 18897 MiB |

MTP ratio on CUDA is 143.4 / 138.0 = 1.04x for single-stream p1k decode. Verdict: CUDA improves single-stream speed over the C12 Vulkan run and the no-spec CUDA control has better x4 aggregate behavior, but neither CUDA result proves a real parallel worker pool by the >=1.5x x4 aggregate rubric. CUDA+MTP reaches only 114.6 aggregate t/s at x4 with 33.7 t/s per stream, while CUDA without MTP reaches 174.8 aggregate t/s at x4 with 54.4 t/s per stream; the control is the better parallel shape, but still short of the worker-pool threshold.

## C16 Bare-Metal CUDA Addendum

C16 uses native `llama-server-cuda`, built from the same llama.cpp commit as C14 (`version: 9592 (ac4cddeb0)`) with a user-local CUDA 13.0 pip-wheel toolkit. The run uses the same byteshape Qwen3.6 35B IQ4_XS GGUF and MTP flags as C12/C14.

| Config | Backend | MTP | p1k decode t/s | p8k decode t/s | x2 aggregate t/s | x4 aggregate t/s | x4 scaling | x4 per-stream t/s | Toolcall @0.2 | VRAM loaded |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C12-byteshape-35b | Vulkan b9596 | yes | 127.7 | 127.9 | 9.6 | 91.0 | 0.71x | 31.0 | 1.000 | 19277 MiB |
| C14-cuda-35b | CUDA Docker b9592 | yes | 143.4 | 149.5 | 96.1 | 114.6 | 0.80x | 33.7 | 1.000 | 19583 MiB |
| C16-cuda-baremetal | CUDA bare metal b9592 | yes | 135.7 | 136.7 | 92.0 | 107.4 | 0.79x | 31.6 | 1.000 | 19583 MiB |

Docker overhead was not visible in this run: C16 bare metal was 5.4% slower than C14 Docker on single-stream p1k decode, with the same loaded VRAM. Raw C16 logs contain `CUDA0`, `creating MTP draft context`, `draft-mtp`, and `draft acceptance` lines.

## C15 vLLM Addendum

C15 uses `vllm/vllm-openai:v0.22.1` (local image digest `sha256:953d3a06d5e64ab582985cd7401289d3abf2a2c14ef2158e9a84313daeec77d7`) with `mattbucci/Qwen3.6-35B-A3B-AWQ`. The original 32k startup OOMed during CUDA graph/KV profiling; the successful run used `--max-model-len 16384 --max-num-seqs 4 --gpu-memory-utilization 0.92`.

| Config | Backend | Timing source | p1k single decode t/s | x2 aggregate t/s | x2 scaling | x4 aggregate t/s | x4 scaling | x4 per-stream t/s | Toolcall @0.2 | Agentic @0.2 | VRAM loaded |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C14-cuda-35b-nospec | llama.cpp CUDA Docker b9592 | server timings | 138.0 | 131.7 | 0.95x | 174.8 | 1.27x | 54.4 | n/a | n/a | 18897 MiB |
| C15-vllm-35b | vLLM 0.22.1 AWQ Marlin | client wall usage | 130.6 | 180.6 | 1.38x | 360.3 | 2.76x | 90.3 | 0.167 (`qwen3_xml`) | 0/5 | 21811 MiB |

C15 throughput uses client-measured wall time from OpenAI-compatible usage counts because vLLM does not return llama.cpp's `timings` field. Therefore the C15 single-stream decode number is not directly comparable to C12/C14 server-side decode numbers. The apples-to-apples metric for the C15 question is the aggregate scaling ratio within the same client-measured run: x2 is 180.6 / 130.6 = 1.38x, and x4 is 360.3 / 130.6 = 2.76x.

Tool use did not recover with parser selection. `qwen3_coder` scored 0.167 because only the two no-tool cases passed; all required tool-call cases made no tool call. The required rerun with `qwen3_xml` produced the same 0.167 and agentic remained 0/5.

**Root cause (post-run manual diagnosis): the C15 server generates gibberish for every prompt** — a temperature-0 "say hello" probe returns multi-script token salad — so no output-reading suite could pass regardless of parser. Parser choice, chat template (passed explicitly via `--chat-template`), and mrope config loss (re-injected via `--hf-overrides`) were each tested and ruled out; remaining suspects are vLLM 0.22.1's `awq_marlin` MoE path for the `Qwen3_5MoeForConditionalGeneration` (VL) architecture, the `--language-model-only` path, or the community AWQ quant itself. Full evidence: `results/raw/C15-vllm-35b/GIBBERISH-DIAGNOSIS.md`. The toolcall/agentic zeros say nothing about the model — these weights score 1.000 toolcall via llama.cpp (C12) — and C15's throughput numbers measure token mechanics on corrupted output.

Verdict on the parallel-worker question: vLLM continuous batching demonstrates real parallel throughput scaling mechanics on this RTX 3090 Ti — C15 reached 360.3 aggregate t/s at x4, 2.76x over its 130.6 client-measured single-stream rate (90.3 t/s per stream), vs llama.cpp C14-nospec's 1.27x (174.8 aggregate, 54.4 per stream). But C15 is not a usable serving config: generation is corrupted (see above). The parallel-pool path needs either a vLLM build that serves this architecture correctly or a different vLLM-first model (e.g. Cohere north-mini-code 30B-A3B, which ships official vLLM tool-calling support).

## C17 North Mini vLLM Addendum

C17 attempted `cyankiwi/North-Mini-Code-1.0-AWQ-INT4` at revision `69f25e86d2b35d04837388514bec4eff729d1b30`, a compressed-tensors pack-quantized INT4 repo with 18,468,416,656 bytes of safetensor weights. The selected vLLM flags followed Cohere's North Mini recipe for parsing (`--tool-call-parser cohere_command4 --reasoning-parser cohere_command4 --enable-auto-tool-choice`) and used `--max-model-len 16384 --max-num-seqs 8 --gpu-memory-utilization 0.90 --quantization compressed-tensors`.

The server failed before health and before the mandatory coherence gate. vLLM 0.22.1 rejected the MoE quantization path with `AssertionError: Only symmetric quantization is supported for MoE` while constructing the compressed-tensors WNA16 Marlin MoE method. No throughput, toolcall, or agentic suites were run. Raw evidence is in `results/raw/C17-north-mini-vllm/server.log` and `results/raw/C17-north-mini-vllm/STARTUP-FAILURE.md`.

| Config | Backend | Quant | Coherence gate | x2 aggregate t/s | x2 scaling | x4 aggregate t/s | x4 scaling | x8 aggregate t/s | x8 scaling | per-stream t/s | Toolcall @0.2 | Agentic @0.2 | VRAM loaded |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C15-vllm-35b | vLLM 0.22.1 | AWQ Marlin | failed post-run diagnosis: gibberish | 180.6 | 1.38x | 360.3 | 2.76x | n/a | n/a | 90.3 at x4 | 0.167 (`qwen3_xml`) | 0/5 | 21811 MiB |
| C17-north-mini-vllm | vLLM 0.22.1 | compressed-tensors INT4 | not run: server failed before health | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a (`cohere_command4`) | n/a | n/a |

Verdict: C17 did not reach the 400 aggregate t/s bar because it never served successfully. It also does not qualify as the parallel worker pool: toolcall, agentic, and per-stream thresholds were not measurable. The next viable C17-style attempt needs either a symmetric AWQ/GPTQ INT4 North Mini quant compatible with vLLM's MoE Marlin path, a vLLM build/path that supports this asymmetric compressed-tensors MoE quant, or a larger-memory GPU for Cohere's official FP8/BF16 releases.

## Coexistence

Task 12 pair: C5-style 26B `-cmoe` senior on port 8089 plus C1-style 12B worker with `--parallel 2` on port 8090, both on the resolved RTX 3090 Ti device.

- Loaded VRAM: 10386 MiB total, with 2989 MiB senior and 7324 MiB worker.
- After concurrent load: 11138 MiB total, with 3556 MiB senior and 7509 MiB worker.
- Budget: pass, below the 22.5 GB ceiling.
- Decode under contention: senior 15.6 t/s; worker streams 63.8 and 63.8 t/s. End-to-end worker aggregate across both requests was 9.4 t/s because the two requests shared the load window and included prompt/wait time.

## Decision Rubric

Worker role requires toolcall >=95%, >=3/5 agentic, single decode >=30 t/s, and 3-slot aggregate >=1.5x single-stream. No candidate strictly clears it: C1/C2/C3 miss toolcall, C3 also misses scaling, and C3 lacks agentic data. Practical recommendation is C2 as a provisional queue-serial worker only if the `list_dir`-before-`read_file` behavior is acceptable or fixed by prompting/scaffolding.

Senior role requires >=4/5 agentic, toolcall >=95%, decode >=15 t/s, and prefill >=150 t/s. C7 is the clean strict senior among probed prefill configs. C12 is the best solo senior candidate by this suite: 127.7 t/s decode, 100% toolcall, 5/5 agentic, and 19277 MiB VRAM, but true cache-busted prefill was not separately probed. C13 is also viable but slower at 65.7 t/s decode and 19685 MiB. C8 fails the toolcall threshold despite excellent speed. C4/C5/C6 fail toolcall, with C6 just below at 0.944 and carrying the device caveat.

Coexistence decision: the measured C5+C1 layout fits easily in VRAM and gives acceptable senior decode under contention, but neither member strictly passes the quality thresholds. Use it only as a memory-feasibility fallback, not as the quality-first fleet.

## Raw Logs

`du -sh results/raw` reports 3.7M. The raw logs should stay in git for this benchmark pass: they are small, required to substantiate every number, and include the MTP acceptance, device-caveat, and startup-failure evidence.
