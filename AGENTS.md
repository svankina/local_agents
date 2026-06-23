# local_agents Agent Notes

Benchmarking + showcase project for a **local-LLM subagent fleet** on a single RTX 3090 Ti box.
Measures candidate local models (throughput, tool-calling, agentic) to pick worker/senior
models, and compares local fan-out against cloud (Haiku, fable-workers, solo Claude). Remote
`github.com/svankina/local_agents` (branch `master`). llama.cpp pinned around **b9596** (CUDA,
draft-mtp verified 2026-06-11).

**Read first:** `RESULTS.md` (source-of-truth scoreboard/verdict) and `PROGRESS.md` (session
checkpoint: what's done/pushed, what's next, infra notes). The repo is large only because of
**gitignored** dirs — don't read them wholesale.

## Verdict (per RESULTS.md / PROGRESS.md)
- Champion worker model: **byteshape Qwen3.6-35B-A3B** (IQ4_XS, llama.cpp + draft-mtp).
- Parallel pool: **Qwen3-30B-A3B GPTQ under vLLM**, ~808.7 tok/s @ x8 (config C18).
- Fan-out showcase (32 items, AST-verified): local 24.7s ~$0 vs Haiku/solo cloud arms — see
  `results/experiments/showcase-fanout/`.

## Layout
- `bench/` — the benchmark harness.
  - `configs.json` — every `C1..C18` llama.cpp/vLLM server config (model, ctx, MTP/spec flags).
    Placeholders `<CACHE>`/`<GPU>` are substituted by the runners.
  - `run_config.sh`, `run_config_baremetal_cuda.sh`, `run_config_docker.sh`,
    `run_config_vllm.sh` — bring up a server for a config on Vulkan / bare-metal CUDA / Docker
    CUDA / vLLM.
  - `throughput.py`, `prefill_probe.py`, `toolcall_suite.py`, `coexistence.py`, `miniagent.py`,
    `make_sandbox.py` — the measurement suites. Cases: `toolcall_cases.json`,
    `agentic_tasks.json`. `models.lock` pins model files.
- `scripts/` — analysis + fan-out.
  - `scripts/fanout/run_{fleet,solo,haiku,fable_workers}_arm.sh` — the four fan-out arms;
    `dispatch.py`, `fanout-worker`, `haiku-worker`, `verify_item.py`, `make_items.py`.
  - `build_dashboard.py` → `dashboard.html`; `compute_run_metrics.py`,
    `concurrency_sweep.py`, `swap_latency_bench.py`, `telemetry_sampler.py`.
- `results/` — per-config JSON (`C1..C18-*.json`) + `results/raw/` logs + `results/experiments/`.
- `docs/` — `article/` (drafts: `2026-06-800-toks-3090.md`, `2026-06-local-subagent-fleet.md`),
  `experiments/` (writeups + RUNBOOKs), `superpowers/plans/` (the benchmark plan).
- `tests/` — `python3 -m pytest tests/` (fan-out harness, metrics, scoring).

## Gotchas (from PROGRESS.md infra notes)
- **GPU must be idle before timed runs.** Resolve the GPU by name, never by Vulkan index —
  Vulkan enumeration has flipped to RX 580+CPU mid-run (the C6 device caveat).
- Vulkan multi-slot scaling is weak; a fast queue-serial MTP worker often beats a parallel pool.
- Local servers: `~/.local/bin/llama-server-cuda` (b9592) and Vulkan `llama-server` (b9596);
  vLLM via `bench/run_config_vllm.sh` (C18). Haiku/Fable CLI workers set `MAX_THINKING_TOKENS=0`.
- Headless arm sessions need `--strict-mcp-config` and foreground-only worker execution.
- **`codex-agent` runs sometimes die silently** — guard with watchdog pid + `.running` marker;
  kill with `pkill -9 -f "agent-runs/<id>"`; never pipe runners through `head`/`tee`.
- Throughput numbers carry caveats: suite `prefill_tps` medians are cache-polluted (use
  `results/prefill_probe.json`); agentic 5-task suite has high run-to-run variance (coarse
  ranking only). RESULTS.md documents every excluded/caveated row.
- **Server/port map:** bench suites (and the local-worker shims) hit
  `http://127.0.0.1:8089` by default — `bench/common.py` `BENCH_BASE`; `configs.json`
  `_common` pins `--port 8089`. `BENCH_MODEL` (default `local`) overrides the served model
  name. `coexistence.py` runs a senior on `:8089` + a worker on `:8090 --parallel 2`
  simultaneously; keep combined VRAM under ~22.5 GB on the 24 GB 3090 Ti.
- **32k context (`-c 32768`) on every config:** prompts/plans over the window get an
  HTTP 400 from llama-server, not a truncation — slice oversized inputs to fit (the
  m1-replay run had to feed local workers one plan-task section at a time).
- **Pre-flight evicts resident *ollama* models** to reclaim VRAM but deliberately
  preserves other foreign GPU processes — don't widen the kill to all GPU users.

## Why the file count is huge (~34k) — mostly gitignored, don't crawl
`.worktrees/` (feature worktrees + full clones used as fan-out targets, e.g. scrapy),
`results/` + `results/raw/`, `data/`, `.playwright-mcp/`, `bench/sandbox/work-*/`, `__pycache__/`,
`*.log`, `*.jsonl` are all **gitignored** (`.gitignore`). The tracked surface is small:
`bench/`, `scripts/`, `tests/`, `docs/`, and the top-level `*.md`/`dashboard.html`.
