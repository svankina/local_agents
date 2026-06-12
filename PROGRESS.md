# Session checkpoint — 2026-06-12 (post credit-limit incident)

Limit incident: subscription five-hour window exhausted during H-02's synthesis
call. Worker data was complete; costs finalized from logs. No data loss.

## Done and pushed (through 45d404a)
- Benchmarks C1–C18 complete; champion byteshape Qwen3.6-35B-A3B (llama.cpp);
  parallel pool Qwen3-30B-A3B GPTQ under vLLM, 808.7 tok/s @x8. RESULTS.md is
  the source of truth.
- Showcase fan-out (scrapy@a8ffdcf8, 32 items, AST-verified):
  F-06 local 32/32 24.7s ~$0 · FW-01 fable-workers 32/32 80.6s $6.28 ·
  H-01 haiku 32/32 160.9s $1.42 (thinking-on) · H-02 haiku 29/32 54.6s $0.66
  (thinking-off, MAX_THINKING_TOKENS=0) · S-01 solo 32/32 569s $9.22 ·
  S-02 timing probe: solo per-turn max ~90 tok/s.
  Summary: results/experiments/showcase-fanout/throughput-summary.json.
- CAD kernel part 1 replay (n=1/arm, all gates verified): A 13.3min/$13.44 ·
  B 16.7min/$13.30 · C 15.8min/$9.05. B-01/C-01 excluded (documented).
  Forensic baseline: 65.6min/$29.22.
- Articles: docs/article/2026-06-800-toks-3090.md (publish FIRST; user added
  media/social assets offline) and 2026-06-local-subagent-fleet.md (fan-out
  scoped; CAD held for part 3). Editors: :8078 fleet, :8079 800-toks.
  Dashboard: dashboard.html via scripts/build_dashboard.py (stale vs newest runs).

## Open / next
1. H-02 row + thinking trade-off line into the fleet article's worker-swap table
   (29/32 finding: thinking tokens weren't all waste).
2. CAD replay reps to N>=3 per arm + arm D (plan→build→review→fix runner, designed
   not built). Polish CAD story for part 3.
3. Dashboard rebuild with showcase + replay tables.
4. Publication order: 800-toks article → fleet article → CAD part 3.

## Infra notes for a fresh session
- Local servers: ~/.local/bin/llama-server-cuda (b9592) and Vulkan b9596 via
  llama-server; vLLM via bench/run_config_vllm.sh (C18 config). GPU must be
  idle before timed runs; resolve GPU by name, never Vulkan index.
- Fan-out arms: scripts/fanout/run_{fleet,solo,haiku,fable_workers}_arm.sh.
  Haiku/Fable CLI workers: MAX_THINKING_TOKENS=0 set in haiku-worker.
- Headless arm sessions need --strict-mcp-config (browser-grab incident) and
  foreground-only worker execution (print-mode background trap).
- codex-agent runs die silently sometimes: watchdog pid + .running marker;
  kill via pkill -9 -f "agent-runs/<id>"; never pipe runners through head/tee.
