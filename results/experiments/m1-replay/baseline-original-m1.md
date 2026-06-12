# Original M1 Baseline - Forensic Reconstruction

Source: existing logs only. Evidence was read from the Claude Code transcript directory, `~/src/custom_cad` git history, and `~/.codex/agent-runs`; no evidence files were modified.

## Scope and Attribution Rule

I treat the historical baseline as the M1 implementation run, not the earlier CAD design/spec-writing work. The implementation window starts at the subagent-driven-development invocation in the main Claude transcript, `2026-06-11T17:07:36.895Z` (`2026-06-11 22:37:36.895 +05:30`), and ends at the M1-complete commit `4aaea71` at `2026-06-11 23:43:13 +05:30`.

The code-complete commit is `ff20f30` (`feat(app): scene sync + M1 box demo wired through the real kernel pipeline`) at `2026-06-11 23:34:53 +05:30`; `4aaea71` is included as post-acceptance M1 hygiene because it lands before M2 and the transcript completion note follows it. M2 begins afterward with `0592147` at `2026-06-12 00:15:22 +05:30`.

Token attribution rule: count Claude usage objects in the main M1 session and all `fff78efe.../subagents/agent-*.jsonl` sidechains whose timestamps fall in the implementation window. Streaming fragments repeat the same request usage, so I deduplicated by transcript path plus `requestId`/message id and kept the latest usage snapshot per request.

## Headline Results

| Metric | Value |
|---|---:|
| Calendar span | 3,937.0 s / 65.62 min |
| Active session time, 5 min gap cap | 3,935.028 s / 65.58 min |
| Idle/away by gap cap | 1.972 s |
| Assistant request groups | 319 |
| Tool-use content blocks | 348 |
| Cloud input tokens | 20,922 |
| Cloud output tokens | 162,420 |
| Cache creation tokens | 811,412 |
| Cache read tokens | 18,114,849 |
| Total tokens, all logged categories | 19,109,603 |
| Estimated API cost | $29.217689 |
| Effective pipeline, all tokens / wall | 4,853.341 tokens/s |
| Effective pipeline, output / active | 41.276 output tokens/s |
| Generation rate | Not derivable |

The official Anthropic pricing page fetched on 2026-06-12 lists Fable 5 at `$10/M` input, `$12.50/M` 5-minute cache write, `$20/M` 1-hour cache write, `$1/M` cache read, `$50/M` output; Sonnet 4.6 at `$3/M`, `$3.75/M`, `$6/M`, `$0.30/M`, `$15/M` respectively. Source: <https://platform.claude.com/docs/en/about-claude/pricing>.

## Token and Cost Breakdown

| Model / session kind | Input | Output | Cache create 5m | Cache create 1h | Cache read | USD |
|---|---:|---:|---:|---:|---:|---:|
| Main `claude-fable-5` | 997 | 38,082 | 0 | 220,230 | 10,691,857 | $17.010527 |
| Subagent `claude-fable-5` | 19,673 | 63,157 | 193,152 | 0 | 2,571,715 | $8.340695 |
| Subagent `claude-sonnet-4-6` | 252 | 61,181 | 398,030 | 0 | 4,851,277 | $3.866467 |
| Total | 20,922 | 162,420 | 591,182 | 220,230 | 18,114,849 | $29.217689 |

By model:

| Model | Input | Output | Cache create | Cache read | USD |
|---|---:|---:|---:|---:|---:|
| `claude-fable-5` | 20,670 | 101,239 | 413,382 | 13,263,572 | $25.351222 |
| `claude-sonnet-4-6` | 252 | 61,181 | 398,030 | 4,851,277 | $3.866467 |

No M1-related Codex subagent usage was found. The `~/.codex/agent-runs` entries around the M1 window were for `gemma`/`local_agents` or other projects, not `workdir=/home/svankina/src/custom_cad`.

## Wall-Clock by M1 Task

These durations use author timestamps in the M1 commit range. Where a task had a fix commit before acceptance, the fix is included in that task. Tasks 8 and 9 were reported by the transcript as parallel, so their per-task times overlap and should not be summed with the earlier serialized tasks.

| Task | Accepted commit(s) | Accepted at | Wall-clock from previous task boundary |
|---|---|---:|---:|
| 1 scaffold + import guard fix | `9dddb22`, `22dc443` | 2026-06-11 22:46:18 +05:30 | 521.105 s |
| 2 numeric tolerance | `2c41a6c` | 2026-06-11 22:47:59 +05:30 | 101 s |
| 3 vector/PlaneCS | `f2bc38d` | 2026-06-11 22:50:23 +05:30 | 144 s |
| 4 result/profile | `d0b8500`, `310a170` | 2026-06-11 22:53:35 +05:30 | 192 s |
| 5 B-rep/validateSolid + fix | `3114585`, `0d0167e` | 2026-06-11 23:03:49 +05:30 | 614 s |
| 6 extrude + fix | `b9e6bd9`, `1732d14` | 2026-06-11 23:15:12 +05:30 | 683 s |
| 7 tessellation + fix | `c38a4cb`, `937a128` | 2026-06-11 23:31:01 +05:30 | 949 s |
| 8 viewport shell | `36ef6e2` | 2026-06-11 23:34:50 +05:30 | 229 s, overlaps Task 9 |
| 9 scene sync + acceptance | `ff20f30` | 2026-06-11 23:34:53 +05:30 | 232 s, overlaps Task 8 |
| Post-M1 screenshot ignore | `4aaea71` | 2026-06-11 23:43:13 +05:30 | 500 s |

## Evidence Pointers

- Claude main transcript: `/home/svankina/.claude/projects/-home-svankina-src-custom-cad/fff78efe-6adb-40df-843a-c04bed886a50.jsonl`.
- Claude sidechains: `/home/svankina/.claude/projects/-home-svankina-src-custom-cad/fff78efe-6adb-40df-843a-c04bed886a50/subagents/*.jsonl`.
- First implementation marker: main transcript line with the `subagent-driven-development` skill at `2026-06-11T17:07:36.930Z`; the first Task 1 dispatch follows at `2026-06-11T17:08:42.921Z`.
- Completion marker: main transcript reports M1 merged/pushed/live and "M1 \"A box I can orbit\" is complete" at `2026-06-11T18:13:32.821Z`.
- Git evidence command: `git -C /home/svankina/src/custom_cad log --date=iso-strict --pretty=format:'%h %H %aI %s' --reverse 437a4a7..4aaea71`.

## Derivation Notes

Active time is computed from the global sorted transcript event timeline by summing each inter-event gap capped at 300 seconds. Because the main session and subagents were highly active throughout the run, this cap produces only 1.972 seconds of idle time. That is a transcript-activity metric, not a model-busy metric.

The request count is 319 deduplicated assistant request groups: 53 main-session Fable groups, 214 Sonnet sidechain groups, and 52 Fable sidechain groups. The tool-use count is 348 visible `tool_use` content blocks in the same window.

The broader design+plan+implementation span from the first "build a CAD engine" event at `2026-06-11T15:42:14Z` through M1 completion is 151 minutes and costs more tokens; I did not use it as the implementation baseline because it includes brainstorming, design-spec writing, and M1 plan authoring before execution.

## Limitations and Caveats

1. Generation rate is not derivable: Claude Code JSONL has timestamps and token usage but no server-side model-busy or decode timing, so `t_generating`, `t_prefill`, and true decode tokens/sec are null.
2. Thinking-token subtotals are not exposed in the usage objects I found. Billed thinking, if any, is included in `output_tokens`; visible versus reasoning output cannot be separated.
3. The active/idle split is sensitive to the 5-minute transcript-gap heuristic and parallel sidechains. It is useful for away-time detection, not for attributing time to model generation, tools, API wait, or human review.
