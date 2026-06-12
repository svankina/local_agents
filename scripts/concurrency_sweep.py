#!/usr/bin/env python3
"""Run and analyze the C18 vLLM concurrency sweep."""

from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "results" / "experiments" / "concurrency-sweep" / "2026-06-12-S1"
IMAGE = "vllm/vllm-openai:v0.22.1"
CONTAINER = "concurrency-sweep-2026-06-12-S1"
PORT = 8091
MODEL = "C18-qwen3-30b-vllm"
COUNTER = "vllm:generation_tokens_total"
LEVELS = [1, 2, 4, 8, 10, 12, 16, 24]
PROMPT_1K = (
    "You are summarizing a design document. "
    + "The system ingests events, deduplicates them, and routes them to workers. " * 60
)


def now_iso() -> str:
    return dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def parse_iso(raw: str) -> dt.datetime:
    return dt.datetime.fromisoformat(raw)


def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False, **kwargs)


def require_ok(cp: subprocess.CompletedProcess[str], what: str) -> None:
    if cp.returncode != 0:
        raise SystemExit(f"{what} failed\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")


def gpu_snapshot() -> dict[str, float]:
    cp = run(
        [
            "nvidia-smi",
            "--query-gpu=utilization.gpu,memory.used,power.draw,temperature.gpu",
            "--format=csv,noheader,nounits",
        ]
    )
    require_ok(cp, "nvidia-smi")
    util, mem, power, temp = [float(x.strip()) for x in cp.stdout.strip().split(",")[:4]]
    return {"gpu_util_pct": util, "vram_used_mib": mem, "power_w": power, "temp_c": temp}


def preflight() -> dict[str, Any]:
    snap = gpu_snapshot()
    if snap["gpu_util_pct"] >= 10 or snap["vram_used_mib"] >= 500:
        raise SystemExit(f"GPU preflight failed: {snap}")
    cp = run(["docker", "ps", "-a", "--format", "{{.Names}}"])
    require_ok(cp, "docker ps")
    names = set(cp.stdout.splitlines())
    if CONTAINER in names:
        raise SystemExit(f"container {CONTAINER} already exists; refusing to reuse or stop it")
    return snap


def start_container(max_num_seqs: int, server_log: Path) -> tuple[str, subprocess.Popen[str]]:
    flags = [
        "--model",
        "Qwen/Qwen3-30B-A3B-GPTQ-Int4",
        "--revision",
        "9b534e4318b7ebc3c961a839f13eb18b1833f441",
        "--served-model-name",
        MODEL,
        "--max-model-len",
        "16384",
        "--gpu-memory-utilization",
        "0.92",
        "--max-num-seqs",
        str(max_num_seqs),
        "--quantization",
        "gptq_marlin",
        "--enable-auto-tool-choice",
        "--tool-call-parser",
        "hermes",
        "--reasoning-parser",
        "qwen3",
    ]
    docker_run_err = RUN_DIR / f"docker_run_maxseq{max_num_seqs}.err"
    cid_path = RUN_DIR / "container.id"
    cmd = [
        "docker",
        "run",
        "-d",
        "--rm",
        "--gpus",
        "all",
        "--ipc=host",
        "-v",
        f"{Path.home() / '.cache' / 'huggingface'}:/root/.cache/huggingface",
        "-p",
        f"{PORT}:8000",
        "--name",
        CONTAINER,
        IMAGE,
        *flags,
    ]
    with docker_run_err.open("w") as err:
        cp = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=err, check=False)
    if cp.returncode != 0:
        return "", subprocess.Popen(["true"], text=True)
    cid = cp.stdout.strip()
    cid_path.write_text(cid + "\n", encoding="utf-8")
    log_f = server_log.open("a", encoding="utf-8")
    log_proc = subprocess.Popen(["docker", "logs", "-f", CONTAINER], stdout=log_f, stderr=subprocess.STDOUT, text=True)
    return cid, log_proc


def stop_container(log_proc: subprocess.Popen[str] | None) -> None:
    run(["docker", "stop", CONTAINER])
    if log_proc:
        try:
            log_proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            log_proc.terminate()


def wait_healthy(timeout_s: int = 900) -> None:
    deadline = time.monotonic() + timeout_s
    urls = [f"http://127.0.0.1:{PORT}/health", f"http://127.0.0.1:{PORT}/v1/models"]
    while time.monotonic() < deadline:
        for url in urls:
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    if r.status == 200:
                        return
            except Exception:
                pass
        time.sleep(2)
    raise TimeoutError("server never became healthy")


def startup_evidence(server_log: Path) -> dict[str, Any]:
    text = server_log.read_text(errors="replace", encoding="utf-8")
    kv_tokens = None
    for pat in (r"GPU KV cache size:\s*([0-9,]+)\s*tokens", r"([0-9,]+)\s+GPU KV-cache tokens"):
        m = re.search(pat, text)
        if m:
            kv_tokens = int(m.group(1).replace(",", ""))
            break
    health = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=10).status
    return {"health_status": health, "kv_cache_tokens": kv_tokens}


def scrape_metrics(stop: threading.Event, out: Path) -> None:
    url = f"http://127.0.0.1:{PORT}/metrics"
    next_tick = time.monotonic()
    with out.open("a", encoding="utf-8", buffering=1024 * 1024) as f:
        while not stop.is_set():
            ts = now_iso()
            mono = time.monotonic()
            err = None
            body = ""
            generation_counter = None
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    body = r.read().decode("utf-8", errors="replace")
                generation_counter = extract_counter(body)
            except Exception as exc:  # noqa: BLE001
                err = repr(exc)
            f.write(
                json.dumps(
                    {
                        "ts": ts,
                        "monotonic_s": mono,
                        "url": url,
                        "generation_counter": generation_counter,
                        "counter_name": COUNTER,
                        "error": err,
                        "scrape": body,
                    }
                )
                + "\n"
            )
            f.flush()
            next_tick += 1
            time.sleep(max(0.0, next_tick - time.monotonic()))


def extract_counter(scrape: str) -> float | None:
    for line in scrape.splitlines():
        if line.startswith(COUNTER):
            try:
                return float(line.rsplit(" ", 1)[1])
            except (IndexError, ValueError):
                return None
    return None


def append_event(path: Path, event: str, level: int | None = None, **extra: Any) -> dict[str, Any]:
    row = {"ts": now_iso(), "event": event}
    if level is not None:
        row["level"] = level
    row.update(extra)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row


def post_chat(payload: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=600) as r:
        body = json.loads(r.read())
    body["_client_wall_s"] = time.monotonic() - t0
    return body


async def worker(level: int, worker_id: int, end_at: float) -> dict[str, Any]:
    requests = 0
    errors = 0
    completion_tokens = 0
    prompt_tokens = 0
    latencies: list[float] = []
    while time.monotonic() < end_at:
        nonce = f"\nRun nonce: level {level}, stream {worker_id}, request {requests}, monotonic {time.monotonic():.6f}."
        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": PROMPT_1K + nonce + "\nSummarize in detail."}],
            "temperature": 0.2,
            "max_tokens": 512,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            body = await asyncio.to_thread(post_chat, payload)
            usage = body.get("usage") or {}
            completion_tokens += int(usage.get("completion_tokens") or 0)
            prompt_tokens += int(usage.get("prompt_tokens") or 0)
            latencies.append(float(body.get("_client_wall_s") or 0.0))
        except Exception:  # noqa: BLE001
            errors += 1
        requests += 1
    return {
        "worker": worker_id,
        "requests": requests,
        "errors": errors,
        "completion_tokens_usage": completion_tokens,
        "prompt_tokens_usage": prompt_tokens,
        "latency_s": latencies,
    }


async def run_level(level: int, duration_s: float) -> dict[str, Any]:
    t0 = time.monotonic()
    end_at = t0 + duration_s
    workers = await asyncio.gather(*(worker(level, i, end_at) for i in range(level)))
    wall_s = time.monotonic() - t0
    return {
        "level": level,
        "requested_duration_s": duration_s,
        "wall_s": wall_s,
        "max_tokens": 512,
        "completion_tokens_usage": sum(w["completion_tokens_usage"] for w in workers),
        "prompt_tokens_usage": sum(w["prompt_tokens_usage"] for w in workers),
        "workers": workers,
    }


def read_events(path: Path) -> dict[int, dict[str, dt.datetime]]:
    out: dict[int, dict[str, dt.datetime]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if "level" not in row:
            continue
        out.setdefault(int(row["level"]), {})[row["event"]] = parse_iso(row["ts"])
    return out


def read_metric_samples(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("generation_counter") is None:
            row["generation_counter"] = extract_counter(row.get("scrape") or "")
        if row.get("generation_counter") is None:
            continue
        rows.append({"ts": parse_iso(row["ts"]), "monotonic_s": float(row["monotonic_s"]), "counter": float(row["generation_counter"])})
    rows.sort(key=lambda r: r["monotonic_s"])
    for i, row in enumerate(rows):
        if i == 0:
            row["delta"] = 0.0
            row["decode_tok_s"] = 0.0
        else:
            prev = rows[i - 1]
            elapsed = max(1e-9, row["monotonic_s"] - prev["monotonic_s"])
            row["delta"] = max(0.0, row["counter"] - prev["counter"])
            row["decode_tok_s"] = row["delta"] / elapsed
    return rows


def read_telemetry(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fnum(row: dict[str, Any], key: str) -> float | None:
    raw = row.get(key)
    if raw in (None, ""):
        return None
    return float(raw)


def derive(run_dir: Path) -> list[dict[str, Any]]:
    events = read_events(run_dir / "events.jsonl")
    samples = read_metric_samples(run_dir / "vllm-metrics.jsonl")
    telemetry = read_telemetry(run_dir / "telemetry.csv")
    series_rows: list[dict[str, Any]] = []
    levels: list[dict[str, Any]] = []
    previous_sustained = None
    previous_level = None

    for level in LEVELS:
        start = events[level]["level_start"]
        end = events[level]["level_end"]
        active_start = start + dt.timedelta(seconds=10)
        selected = [r for r in samples if active_start <= r["ts"] <= end]
        t_selected = [r for r in telemetry if active_start <= parse_iso(r["ts"]) <= end]
        if not selected:
            raise SystemExit(f"no metric samples for level {level}")
        sustained = statistics.mean(float(r["decode_tok_s"]) for r in selected)
        peak = max(float(r["decode_tok_s"]) for r in selected)
        power_vals = [v for r in t_selected if (v := fnum(r, "power_w")) is not None]
        temp_vals = [v for r in t_selected if (v := fnum(r, "temp_c")) is not None]
        total_delta = sum(float(r["delta"]) for r in selected)
        seconds = sum(
            max(0.0, selected[i]["monotonic_s"] - selected[i - 1]["monotonic_s"])
            for i in range(1, len(selected))
        ) or len(selected)
        marginal_tok_s_per_stream = None
        marginal_pct_per_stream = None
        if previous_sustained is not None and previous_level is not None:
            added = level - previous_level
            marginal_tok_s_per_stream = (sustained - previous_sustained) / added
            marginal_pct_per_stream = ((sustained / previous_sustained) - 1.0) / added * 100.0
        row = {
            "level": level,
            "start_ts": start.isoformat(),
            "end_ts": end.isoformat(),
            "analysis_start_ts": active_start.isoformat(),
            "samples": len(selected),
            "generation_tokens_delta": round(total_delta, 3),
            "sustained_tok_s": round(sustained, 1),
            "per_stream_tok_s": round(sustained / level, 1),
            "peak_1s_tok_s": round(peak, 1),
            "mean_gpu_power_w": round(statistics.mean(power_vals), 1) if power_vals else None,
            "mean_gpu_temp_c": round(statistics.mean(temp_vals), 1) if temp_vals else None,
            "marginal_tok_s_per_added_stream": round(marginal_tok_s_per_stream, 1) if marginal_tok_s_per_stream is not None else None,
            "marginal_pct_per_added_stream": round(marginal_pct_per_stream, 2) if marginal_pct_per_stream is not None else None,
        }
        levels.append(row)
        for r in selected:
            series_rows.append(
                {
                    "ts": r["ts"].isoformat(),
                    "level": level,
                    "generation_tokens_total": r["counter"],
                    "decode_tokens_delta": r["delta"],
                    "decode_tok_s": round(float(r["decode_tok_s"]), 3),
                }
            )
        previous_sustained = sustained
        previous_level = level

    with (run_dir / "series.csv").open("w", newline="", encoding="utf-8") as f:
        fieldnames = ["ts", "level", "generation_tokens_total", "decode_tokens_delta", "decode_tok_s"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(series_rows)
    (run_dir / "levels.json").write_text(json.dumps({"levels": levels}, indent=2), encoding="utf-8")
    return levels


def write_run_json(run_dir: Path, data: dict[str, Any]) -> None:
    (run_dir / "run.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def do_run(args: argparse.Namespace) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    run_data: dict[str, Any] = {
        "schema": "local-agents.concurrency-sweep.v1",
        "created_at": now_iso(),
        "image": IMAGE,
        "container": CONTAINER,
        "port": PORT,
        "model": MODEL,
        "levels": LEVELS,
        "duration_s": args.duration,
        "drain_gap_s": args.drain_gap,
        "counter_name": COUNTER,
        "preflight": preflight(),
    }
    write_run_json(RUN_DIR, run_data)
    server_log = RUN_DIR / "server.log"
    log_proc: subprocess.Popen[str] | None = None
    telemetry_proc: subprocess.Popen[str] | None = None
    metrics_stop = threading.Event()
    scraper: threading.Thread | None = None
    started = False
    try:
        for max_num_seqs in [32, 24, 16]:
            run_data["attempted_max_num_seqs"] = max_num_seqs
            cid, log_proc = start_container(max_num_seqs, server_log)
            if not cid:
                continue
            started = True
            try:
                wait_healthy()
                run_data["selected_max_num_seqs"] = max_num_seqs
                run_data["startup"] = startup_evidence(server_log)
                run_data["vram_loaded"] = gpu_snapshot()
                write_run_json(RUN_DIR, run_data)
                break
            except Exception as exc:  # noqa: BLE001
                run_data.setdefault("startup_failures", []).append({"max_num_seqs": max_num_seqs, "error": repr(exc)})
                write_run_json(RUN_DIR, run_data)
                stop_container(log_proc)
                started = False
                log_proc = None
        if not started:
            raise SystemExit("no vLLM max-num-seqs attempt became healthy")

        telemetry_proc = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "telemetry_sampler.py"), "--out", str(RUN_DIR / "telemetry.csv")])
        scraper = threading.Thread(target=scrape_metrics, args=(metrics_stop, RUN_DIR / "vllm-metrics.jsonl"), daemon=True)
        scraper.start()
        append_event(RUN_DIR / "events.jsonl", "sweep_start")
        workloads = []
        for level in LEVELS:
            start_event = append_event(RUN_DIR / "events.jsonl", "level_start", level)
            result = asyncio.run(run_level(level, args.duration))
            result["start_ts"] = start_event["ts"]
            result["end_ts"] = append_event(RUN_DIR / "events.jsonl", "level_end", level)["ts"]
            workloads.append(result)
            (RUN_DIR / "workload.json").write_text(json.dumps({"levels": workloads}, indent=2), encoding="utf-8")
            time.sleep(args.drain_gap)
        append_event(RUN_DIR / "events.jsonl", "sweep_end")
        time.sleep(2)
    finally:
        metrics_stop.set()
        if scraper:
            scraper.join(timeout=10)
        if telemetry_proc:
            telemetry_proc.send_signal(signal.SIGTERM)
            try:
                telemetry_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                telemetry_proc.kill()
                telemetry_proc.wait()
        if started:
            stop_container(log_proc)
        run_data["post_stop_gpu"] = gpu_snapshot()
        run_data["ended_at"] = now_iso()
        write_run_json(RUN_DIR, run_data)
    levels = derive(RUN_DIR)
    print(json.dumps({"levels": levels}, indent=2))


def do_derive(_args: argparse.Namespace) -> None:
    print(json.dumps({"levels": derive(RUN_DIR)}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run")
    run_p.add_argument("--duration", type=float, default=75.0)
    run_p.add_argument("--drain-gap", type=float, default=10.0)
    run_p.set_defaults(func=do_run)
    derive_p = sub.add_parser("derive")
    derive_p.set_defaults(func=do_derive)
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
