# Fable Fleet Bench — unsupervised session progress

Session start: 2026-06-12 ~19:20 UTC. Goal: fake-Fable supervisor experiments over
real local workers — zero real Fable spend. Each run capped 5–10 min. Infra reused:
one vLLM container (`fleetbench-vllm`, port 8091, C18) for all C18 experiments; one
server swap per additional model for E2.

## Experiment lineup

| id | question | status |
|---|---|---|
| E1 | plan terseness (terse/medium/detailed) vs first-pass rate, fix rounds, supervisor tokens/completed | DONE 4m15s |
| E3 | fix-message informativeness (quote-the-failure vs "wrong, try again") vs repair rate | running (retargeted: thinking-off, medium, 6 seeds) |
| E4 | temperature (0.0/0.2/0.6/1.0) vs single-shot error rate | DONE 3m — null effect |
| E5 | thinking on/off vs error rate + speed | DONE 1m12s — headline result |
| E2 | model speed vs error rate | DONE — table below |
| E6 | compression-dictionary opcode protocol | CANCELLED by user mid-run (code kept in runner) |
| E7 | diffusiongemma-26B-A4B-it: diffusion decoding speed vs error | DONE — verdict below |

## E7 finding: diffusiongemma-26B-A4B (Q4_K_M, llama.cpp PR#24423, 1 stream)

| metric | value |
|---|---|
| strict pass (format obeyed) | 0/30 — every reply fenced+prose despite explicit "no fences" |
| lenient pass (fences stripped) | 80% — logic is real, between gemma12-reasoning (73%) and C18-think (88%) |
| wall per episode | 7.14s single-stream (-n 1024 canvas, thought channel on) |
| tasks/min | ~8.4 vs C18-think 36, gemma12-nothink 83 |

As a supervised fleet worker TODAY: not viable. Instruction-following is the worst
measured (100% format violation rate -> a guaranteed fix round per task), no server
or batching exists (CLI only, PR not merged), and single-stream tasks/min is 4-10x
behind the autoregressive options. The diffusion decode itself is quick (~150ms/step,
14 steps/block) and the logic quality is promising — worth re-testing when (a) the
PR merges with llama-server support and (b) a chat template / system prompt reliably
suppresses the fence habit. Infra kept: ~/src/llama.cpp-diffusion build + Q4_K_M in
~/.cache/llama.cpp + wrapper bench/fleet_bench/run_diffusion_e7.py.

## E2 final table (single-shot, medium plan, temp 0.2)

| model | mode | pass | suite wall | agg tok/s |
|---|---|---|---|---|
| C18 30B vLLM x16 | thinking | 0.883 | 98.6s | 924 |
| C18 30B vLLM x16 | no-think | 0.40 | 5.0s | 737 |
| C12 35B llama x4 | thinking | 0.667 | 590s | 113 |
| C12 35B llama x4 | "no-think" (flag ignored) | 0.667 | 611s | 109 |
| C1 gemma12B llama x4 | reasoning | 0.733 | 295s | 170 |
| C1 gemma12B llama x4 | no-reasoning | 1.000 | 21.6s | 149 |

Unifying finding: nearly every failure across all models is reasoning-budget
overflow (finish=length at 3072), not capability. Gemma-12B with reasoning off is
a PERFECT 30/30 at 13.7x speed — best capability-per-wall-clock of the session.
C12 byteshape: 8/9 failures truncation; true logic capability ~96%, but llama.cpp
--reasoning-budget 0 does NOT disable its template's thinking (verified by probe;
reasoning_content still streams). C18 inverts: no-think drops it to 40% — the MoE
needs thinking here, dense gemma doesn't.


## E4 finding: temperature is a null knob

90–93% first-pass flat across temp 0.0/0.2/0.6/1.0. Every failure at every temp is
the SAME pathology: finish=length at 3072 — qwen3 overthinking camel-to-snake
(and one gcd). Temperature doesn't matter for this workload; thinking budget does.

## E5 finding (headline): thinking-off + fix loop = 14x throughput, everything still completes

| | first-pass | completed | sup tok/task | worker tok/ep | tasks/min |
|---|---|---|---|---|---|
| thinking-on | 0.90 | 30/30 | 69.6 | 1753 | 26.5 |
| thinking-off | 0.43 | 30/30 | 91.4 | 127 | 381.2 |

Thinking-off halves first-pass but the scripted fix loop recovers ALL of it; zero
format violations, zero truncations (failures are pure logic). Net: 14x tasks/min
and 14x fewer worker tokens for a 31% supervisor-token premium. If wall-clock is
the scarce resource, thinking-off + supervision wins big; if supervisor tokens are
scarce, thinking-on is still slightly cheaper per task.

## E1 finding (C18, temp 0.2, n=30/style)

Medium instructions dominate. Terse collapses on FORMAT (17/30 fenced replies —
never told "no markdown"); lenient rate 70% vs strict 30% shows failures are mostly
format, not logic. Detailed HURTS: 155 sup-tok/completed (2.3x medium) for a lower
first-pass rate — and 5/30 hit the 3072-token cap mid-think (overthinking induced
by constraint lists + examples; all finish=length on word-frequency/camel-to-snake).

| style | first-pass | completion | sup tok/completed | worker tok/ep |
|---|---|---|---|---|
| terse | 0.30 | 27/30 | 75.0 | 2538 |
| medium | 0.93 | 30/30 | 68.5 | 1625 |
| detailed | 0.80 | 29/30 | 155.1 | 2656 |

## State

- [x] Task bank: 10 pure_fn problems, property verifier proven sound (selftest green)
- [x] Harness: fake supervisor (plan styles, strict format verify, scripted fix loop,
      /tokenize-based supervisor-cost accounting) — `bench/fleet_bench/fake_supervisor.py`
- [x] Runner: `bench/fleet_bench/run_experiments.py` (e1/e3/e4/e2)
- [ ] C18 vLLM server healthy (loading; zsh word-split bug fixed — first launch passed
      flags as one arg, container exited; relaunched with eval)
- [ ] smoke episode
- [ ] E1 → E3 → E4 on C18, then E2 swaps: C12 (llama.cpp MTP), C1 (gemma 12B)

## Notes / decisions

- Supervisor cost = tokens of scripted plan+fix messages via vLLM /tokenize (cached).
- Format strictness: fenced/prose replies fail strict verify and cost a fix round;
  lenient verdict recorded separately so format vs logic failures separate cleanly.
- E2 needs a llama.cpp server path for C12/C1 — flags already in bench/configs.json.
- Results land in results/experiments/fable-fleet-bench/<date>-<exp>/ (episodes.json
  + summary.json per experiment).

## Queued: model sweep continuation (user list, 2026-06-13)

After the live gemma run, E2-suite + capability-matrix update for each of:
C5/C6 (gemma-26B cmoe/MTP variants; C4 base done: 80% nothink), C10 (dense 35B Q4),
C15 (35B AWQ vLLM — engine/quant isolate vs C12), C11 (phi-4-mini anchor),
C13 (Qwopus 27B MTP), C7/C9 (qwen 27B Q3 vs Q4), C8 (Nex-N2-mini), C17 (North-Mini-Code).
Run nothink + think arms where the template supports it. ~5 min each + swap.

## E7 infra notes

- Source: ~/src/llama.cpp-diffusion (PR #24423 branch `diffusiongemma`).
- No OpenAI server in PR: llama-diffusion-cli (end-to-end, -cnv interactive) and
  llama-diffusion-gemma-server (raw logits protocol for a Python driver).
  Plan: drive CLI via stdin wrapper, 1-stream, E2 suite, 30 episodes.
- Build runs INSIDE vllm/vllm-openai:v0.22.1 (has nvcc 13 + g++; cmake via pip);
  binaries must also RUN in that image (lib paths) — docker run -i --gpus all.
- Model: ~/.cache/llama.cpp/diffusiongemma-26B-A4B-it-Q4_K_M.gguf (16.8 GB).

## Resume notes (if session dies)

- Container stays up unless the box reboots: `docker ps | grep fleetbench-vllm`,
  health: `curl localhost:8091/health`.
- Re-run any experiment: `python3 bench/fleet_bench/run_experiments.py e1` (etc.)
  from the worktree root. Each is idempotent, overwrites its run dir.
- Kill the container only at session end: `docker stop fleetbench-vllm && docker rm fleetbench-vllm`.

---

# (prior session checkpoint, kept for reference)

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
