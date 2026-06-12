# Showcase Fan-out — Arm G — Run 2026-06-13-G-01

Sources: `scorecard.json` (showcase-fanout.scorecard.v1), `metrics.json` (m1-replay.metrics.v1). Individual worker transcripts were not inspected.

## Pass rate

**30/32 passed (93.75%)**, 2 failed.

| Failed item | Path | Failure |
|---|---|---|
| item-12 | `scrapy/core/downloader/__init__.py` | Worker exited 1 on both attempts (112.7 s, then 32.3 s) |
| item-21 | `scrapy/extensions/corestats.py` | `parameter_mention` check failed on both attempts — attempt 1: `CoreStats.item_dropped` missing mention of `item`; attempt 2: `CoreStats.item_scraped` missing mention of `item` |

## Retries

**4 retries total.** Two items recovered on their second attempt — item-03 (`scrapy/contracts/__init__.py`) and item-08 (`scrapy/http/headers.py`), both after first-attempt `parameter_mention` failures. The other two retries (item-12, item-21) failed both attempts. All first-attempt soft failures were `parameter_mention` checks; item-12's was the only worker-process failure.

## Wall clock

**184.4 s** end to end. Per-item worker wall times were mostly 8–23 s; the outlier was item-12 attempt 1 at 112.7 s. The corresponding request (index 14) emitted exactly 2048 completion tokens — as did its follow-up request 15 — consistent with hitting a completion-token cap before the worker exited 1.

Peak throughput: 74.1 tok/s single-request decode, 86.4 tok/s aggregate (1 s window), 1743.9 tok/s prefill.

## Token totals

| Metric | Value |
|---|---|
| Prompt tokens | 75,293 |
| Completion tokens | 10,807 |
| Total tokens | 86,100 |
| Requests | 36 |
| Cache creation / read | 0 / 0 |
| Cloud cost (supervisor) | $1.5953 |
| Cloud cost (workers) | not recorded (`null`) |

## Instrumentation caveats

- **Wall-clock source is the last-resort fallback**: derived from transcript request timestamps, which miss tool-execution time between requests, so 184.4 s is a lower bound on true wall time.
- **Time accounting failed its sanity check** (`sanity_ok: false`): buckets sum to far more than wall clock (residual −424.3 s, 230%). `t_generating` is 452.6 s against a 184.4 s wall clock — generation time across concurrent workers was summed without de-overlapping, so the buckets are not a wall-clock breakdown.
- **Thinking time unavailable**: reasoning-channel timings are absent from the OpenAI-compatible transcript, so `t_thinking` is null and folded into visible generation time.
- **No GPU energy figure**: `telemetry.csv` had fewer than two rows, so `gpu_wh` is null and the telemetry peak summary is empty.
- **Worker cloud cost is null** — the $1.60 total reflects supervisor cost only.
- **Possible completion-token cap**: requests 14 and 15 both emitted exactly 2048 completion tokens, both associated with failed item-12; truncation at a 2048-token cap is the likely proximate cause of that worker's exit-1 failures.