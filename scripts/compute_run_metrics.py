#!/usr/bin/env python3
"""Compute m1-replay post-run metrics from run artifacts."""

from __future__ import annotations

import csv
import json
import math
import re
import sys
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path
from typing import Any


PROMPT_EVAL_RE = re.compile(r"prompt eval time =\s*([0-9.]+) ms /\s*([0-9]+) tokens.*?([0-9.]+) tokens per second")
DECODE_RE = re.compile(r"(?<!prompt )eval time =\s*([0-9.]+) ms /\s*([0-9]+) runs?.*?([0-9.]+) tokens per second")


def iso_to_ts(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def null_reason(reason: str) -> dict[str, Any]:
    return {"value": None, "reason": reason}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"parse_error": line})
    return rows


def read_telemetry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "gpu_wh": null_reason("telemetry.csv missing"),
            "wall_clock_seconds": null_reason("telemetry.csv missing"),
            "peak": {},
        }
    rows = list(csv.DictReader(path.open(newline="")))
    if len(rows) < 2:
        return {
            "gpu_wh": null_reason("telemetry.csv has fewer than two rows"),
            "wall_clock_seconds": null_reason("telemetry.csv has fewer than two rows"),
            "peak": {},
        }

    def f(row: dict[str, str], key: str) -> float | None:
        try:
            return float(row.get(key) or "")
        except ValueError:
            return None

    wh = 0.0
    valid_power = False
    for prev, cur in zip(rows, rows[1:]):
        t0 = f(prev, "monotonic_s")
        t1 = f(cur, "monotonic_s")
        p0 = f(prev, "power_w")
        p1 = f(cur, "power_w")
        if t0 is None or t1 is None or p0 is None or p1 is None or t1 < t0:
            continue
        valid_power = True
        wh += ((p0 + p1) / 2.0) * (t1 - t0) / 3600.0

    first_t = f(rows[0], "monotonic_s")
    last_t = f(rows[-1], "monotonic_s")
    wall = last_t - first_t if first_t is not None and last_t is not None and last_t >= first_t else None

    peak: dict[str, float | None] = {}
    for key in ("gpu_util_pct", "vram_used_mib", "power_w", "temp_c", "cpu_util_pct", "ram_used_gib"):
        vals = [f(r, key) for r in rows]
        nums = [v for v in vals if v is not None]
        peak[key] = max(nums) if nums else None

    return {
        "gpu_wh": wh if valid_power else null_reason("telemetry power_w unavailable"),
        "wall_clock_seconds": wall if wall is not None else null_reason("telemetry monotonic_s unavailable"),
        "peak": peak,
    }


def response_records(transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in transcript:
        body = row.get("body")
        if row.get("type") == "response" and isinstance(body, dict):
            end_ts = iso_to_ts(row.get("ts"))
            wall = body.get("_client_wall_s")
            start_ts = end_ts - wall if end_ts is not None and isinstance(wall, (int, float)) else None
            usage = body.get("usage") or {}
            timings = body.get("timings") or {}
            out.append(
                {
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                    "wall_s": wall,
                    "usage": usage,
                    "timings": timings,
                    "body": body,
                }
            )
    return out


def timing_seconds(timings: dict[str, Any], key: str) -> float | None:
    for candidate in (key, key.replace("_ms", "_time"), key.replace("_ms", "")):
        v = timings.get(candidate)
        if isinstance(v, (int, float)):
            return float(v) / 1000.0 if candidate.endswith("_ms") or key.endswith("_ms") else float(v)
    return None


def server_log_timings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"prefill_s": None, "decode_s": None, "requests": []}
    requests = []
    prefill_s = 0.0
    decode_s = 0.0
    for line in path.read_text(errors="replace").splitlines():
        pm = PROMPT_EVAL_RE.search(line)
        if pm:
            ms, tokens, tps = float(pm.group(1)), int(pm.group(2)), float(pm.group(3))
            prefill_s += ms / 1000.0
            requests.append({"kind": "prefill", "seconds": ms / 1000.0, "tokens": tokens, "tps": tps, "source": "llama-server.log"})
            continue
        dm = DECODE_RE.search(line)
        if dm:
            ms, tokens, tps = float(dm.group(1)), int(dm.group(2)), float(dm.group(3))
            decode_s += ms / 1000.0
            requests.append({"kind": "decode", "seconds": ms / 1000.0, "tokens": tokens, "tps": tps, "source": "llama-server.log"})
    return {"prefill_s": prefill_s or None, "decode_s": decode_s or None, "requests": requests}


def derive_request_metrics(responses: list[dict[str, Any]], log_metrics: dict[str, Any]) -> dict[str, Any]:
    per_request = []
    t_prefill = 0.0
    t_generating = 0.0
    t_api_wait = 0.0
    have_prefill = False
    have_decode = False

    for i, rec in enumerate(responses, 1):
        timings = rec["timings"] or {}
        usage = rec["usage"] or {}
        wall = rec.get("wall_s")
        prompt_n = timings.get("prompt_n") or usage.get("prompt_tokens") or usage.get("input_tokens")
        completion_n = timings.get("predicted_n") or usage.get("completion_tokens") or usage.get("output_tokens")
        prefill_s = timing_seconds(timings, "prompt_ms")
        decode_s = timing_seconds(timings, "predicted_ms")
        prefill_tps = timings.get("prompt_per_second")
        decode_tps = timings.get("predicted_per_second")
        if prefill_s is None and prompt_n and prefill_tps:
            prefill_s = float(prompt_n) / float(prefill_tps)
        if decode_s is None and completion_n and decode_tps:
            decode_s = float(completion_n) / float(decode_tps)
        if decode_tps is None and completion_n and wall:
            decode_tps = float(completion_n) / float(wall)
        if prefill_tps is None and prompt_n and wall:
            prefill_tps = float(prompt_n) / float(wall)

        if prefill_s is not None:
            t_prefill += prefill_s
            have_prefill = True
        if decode_s is not None:
            t_generating += decode_s
            have_decode = True
        if isinstance(wall, (int, float)):
            accounted = (prefill_s or 0.0) + (decode_s or 0.0)
            t_api_wait += max(0.0, float(wall) - accounted)
        per_request.append(
            {
                "request_index": i,
                "start_ts": rec.get("start_ts"),
                "end_ts": rec.get("end_ts"),
                "wall_s": wall,
                "prompt_tokens": prompt_n,
                "completion_tokens": completion_n,
                "prefill_tps": prefill_tps,
                "decode_tps": decode_tps,
                "timing_source": "transcript.timings" if timings else "usage_client_wall_fallback",
            }
        )

    if not have_prefill and log_metrics.get("prefill_s") is not None:
        t_prefill = float(log_metrics["prefill_s"])
        have_prefill = True
    if not have_decode and log_metrics.get("decode_s") is not None:
        t_generating = float(log_metrics["decode_s"])
        have_decode = True

    return {
        "per_request": per_request,
        "t_prefill": t_prefill if have_prefill else null_reason("no local prefill timings found"),
        "t_generating": t_generating if have_decode else null_reason("no generation timings found"),
        "t_api_wait": t_api_wait if responses else null_reason("no transcript response timings found"),
    }


def tool_exec_from_events(events: list[dict[str, Any]]) -> Any:
    stack: dict[str, float] = {}
    total = 0.0
    seen = False
    for row in events:
        name = row.get("event") or row.get("type")
        ts = iso_to_ts(row.get("ts")) or row.get("monotonic_s")
        if not isinstance(ts, (int, float)):
            continue
        ident = str(row.get("id") or row.get("tool_call_id") or row.get("command") or "default")
        if name in ("tool_start", "command_start", "task_gate_start"):
            stack[ident] = float(ts)
        elif name in ("tool_end", "command_end", "task_gate_end") and ident in stack:
            total += max(0.0, float(ts) - stack.pop(ident))
            seen = True
    return total if seen else null_reason("events.jsonl has no paired tool/command timing events")


def max_aggregate_tps_1s(per_request: list[dict[str, Any]]) -> Any:
    streams = []
    for r in per_request:
        start = r.get("start_ts")
        end = r.get("end_ts")
        tokens = r.get("completion_tokens")
        if not all(isinstance(v, (int, float)) for v in (start, end, tokens)) or end <= start or tokens <= 0:
            continue
        streams.append((float(start), float(end), float(tokens)))
    if not streams:
        return null_reason("no request start/end/completion token data")
    min_t = math.floor(min(s[0] for s in streams))
    max_t = math.ceil(max(s[1] for s in streams))
    best = {"value": 0.0, "window_start_ts": None, "source": "uniform_completion_token_derivation"}
    for sec in range(min_t, max_t):
        total = 0.0
        w0, w1 = float(sec), float(sec + 1)
        for start, end, tokens in streams:
            overlap = max(0.0, min(end, w1) - max(start, w0))
            if overlap:
                total += tokens * overlap / (end - start)
        if total > best["value"]:
            best = {"value": total, "window_start_ts": sec, "source": "uniform_completion_token_derivation"}
    return best


def peak_throughput(per_request: list[dict[str, Any]], log_metrics: dict[str, Any]) -> dict[str, Any]:
    decode_candidates = []
    prefill_candidates = []
    for r in per_request:
        if isinstance(r.get("decode_tps"), (int, float)):
            decode_candidates.append(
                {
                    "value": float(r["decode_tps"]),
                    "request_index": r["request_index"],
                    "prompt_tokens": r.get("prompt_tokens"),
                    "completion_tokens": r.get("completion_tokens"),
                    "source": r.get("timing_source"),
                }
            )
        if isinstance(r.get("prefill_tps"), (int, float)):
            prefill_candidates.append(
                {
                    "value": float(r["prefill_tps"]),
                    "request_index": r["request_index"],
                    "prompt_tokens": r.get("prompt_tokens"),
                    "completion_tokens": r.get("completion_tokens"),
                    "source": r.get("timing_source"),
                }
            )
    for item in log_metrics.get("requests", []):
        if item["kind"] == "decode":
            decode_candidates.append({"value": item["tps"], "source": item["source"], "tokens": item["tokens"]})
        elif item["kind"] == "prefill":
            prefill_candidates.append({"value": item["tps"], "source": item["source"], "tokens": item["tokens"]})
    return {
        "max_decode_tps_single": max(decode_candidates, key=lambda x: x["value"]) if decode_candidates else null_reason("no decode throughput data"),
        "max_aggregate_tps_1s": max_aggregate_tps_1s(per_request),
        "max_prefill_tps": max(prefill_candidates, key=lambda x: x["value"]) if prefill_candidates else null_reason("no prefill throughput data"),
    }


def scalar(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def compute(run_dir: Path) -> dict[str, Any]:
    telemetry = read_telemetry(run_dir / "telemetry.csv")
    transcript = read_jsonl(run_dir / "transcript.jsonl")
    if not transcript:
        for p in sorted((run_dir / "workers").glob("*/transcript.jsonl")) if (run_dir / "workers").exists() else []:
            transcript.extend(read_jsonl(p))
    events = read_jsonl(run_dir / "events.jsonl")
    log_metrics = server_log_timings(run_dir / "llama-server.log")
    responses = response_records(transcript)
    req_metrics = derive_request_metrics(responses, log_metrics)

    # Wall-clock priority (protocol: "first agent prompt -> accepted M1 exit"):
    # 1. the agent run's own boundaries (claude stream result event duration_ms);
    # 2. transcript request timestamps;
    # 3. telemetry span, flagged — the sampler deliberately brackets the run with
    #    setup/teardown, so this overstates the task window.
    wall = None
    wall_source = None
    for stream_path in sorted((run_dir / "logs").glob("claude-stream*.jsonl")) if (run_dir / "logs").exists() else []:
        for ev in read_jsonl(stream_path):
            if ev.get("type") == "result" and isinstance(ev.get("duration_ms"), (int, float)):
                wall = ev["duration_ms"] / 1000.0
                wall_source = f"claude stream result event ({stream_path.name})"
    if wall is None and isinstance(telemetry["wall_clock_seconds"], (int, float)):
        wall = telemetry["wall_clock_seconds"]
        wall_source = "telemetry span (FALLBACK — includes sampler setup/teardown padding)"
    if wall is None:
        times = [r.get("start_ts") for r in req_metrics["per_request"]] + [r.get("end_ts") for r in req_metrics["per_request"]]
        nums = [float(t) for t in times if isinstance(t, (int, float))]
        if len(nums) >= 2:
            wall = max(nums) - min(nums)
            wall_source = "transcript request timestamps (LAST RESORT — misses tool time between requests)"
    if wall is None:
        wall = null_reason("cannot derive wall-clock from stream, telemetry, or transcript")

    t_tool_exec = tool_exec_from_events(events)
    accounted = scalar(req_metrics["t_generating"]) + scalar(req_metrics["t_prefill"]) + scalar(req_metrics["t_api_wait"]) + scalar(t_tool_exec)
    if isinstance(wall, (int, float)):
        t_idle = max(0.0, wall - accounted)
        residual = wall - (accounted + t_idle)
        residual_pct = abs(residual) / wall * 100.0 if wall else 0.0
    else:
        t_idle = null_reason("wall-clock unavailable")
        residual = null_reason("wall-clock unavailable")
        residual_pct = null_reason("wall-clock unavailable")

    metrics = {
        "schema": "m1-replay.metrics.v1",
        "run_dir": str(run_dir),
        "wall_clock_seconds": wall,
        "wall_clock_source": wall_source,
        "time_accounting": {
            "t_generating": req_metrics["t_generating"],
            "t_thinking": null_reason("reasoning-channel timings are not present in OpenAI-compatible transcript"),
            "t_visible": req_metrics["t_generating"],
            "t_prefill": req_metrics["t_prefill"],
            "t_tool_exec": t_tool_exec,
            "t_api_wait": req_metrics["t_api_wait"],
            "t_idle": t_idle,
            "residual_seconds": residual,
            "residual_pct": residual_pct,
            "residual_rule": "buckets plus residual should sum to wall-clock within 2%",
            "sanity_ok": bool(isinstance(residual_pct, (int, float)) and residual_pct <= 2.0),
        },
        "peak_throughput": peak_throughput(req_metrics["per_request"], log_metrics),
        "energy": {"gpu_wh": telemetry["gpu_wh"]},
        "telemetry_summary": {"peak": telemetry["peak"]},
        "per_request": req_metrics["per_request"],
    }
    return metrics


def main() -> int:
    ap = ArgumentParser(description="Emit metrics.json for an m1-replay RUN_DIR.")
    ap.add_argument("run_dir")
    args = ap.parse_args()
    run_dir = Path(args.run_dir).resolve()
    metrics = compute(run_dir)
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(run_dir / "metrics.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
