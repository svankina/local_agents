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
- MTP speedup: C2 vs C1 improves p1k decode from 68.9 to 88.1 t/s, a 1.28x gain. C6 vs C5 improves p1k decode from 14.6 to 17.0 t/s, a 1.16x gain.
- C6 is a mixed-device result. Throughput/toolcall came from the RTX 3090 Ti, but the agentic re-run landed on RX 580+CPU after Vulkan enumeration flipped; `vram_loaded` is wrong at 58 MiB, and the phase-1 NVIDIA value was 3375 MiB. See `results/raw/C6-gemma26b-cmoe-mtp/DEVICE-CAVEAT.md`.
- The agentic 5-task suite has high run-to-run variance. C1 and C2 use the same weights but scored 3/5 vs 5/5, so treat agentic pass counts as coarse ranking signals.
- Vulkan multi-slot scaling is weak. C3 x4 aggregate is 74.0 t/s vs 59.2 single-stream decode, only 1.25x, below the 1.5x worker rubric. A fast queue-serial MTP worker such as C2 is likely better than a parallel pool.
- C8 temp sweep: toolcall was 0.778 at temp 0.2 vs 0.806 at temp 0.7; agentic was 5/5 at temp 0.2 vs 4/5 at temp 0.7.

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

`du -sh results/raw` reports 2.8M. The raw logs should stay in git for this benchmark pass: they are small, required to substantiate every number, and include the MTP acceptance and device-caveat evidence.
