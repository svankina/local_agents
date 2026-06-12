#!/usr/bin/env python3
"""Capture the 24-stream measured replay for the 800-toks article assets."""

from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import json
import re
import signal
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "scripts" / "article_assets" / "data" / "x24"
IMAGE = "vllm/vllm-openai:latest"
CONTAINER = "article-800-toks-x24-capture"
PORT = 8091
MODEL = "C18-qwen3-30b-vllm"
COUNTER = "vllm:generation_tokens_total"
STREAMS = 24
MAX_TOKENS = 512
PROMPT_BASE = "\n".join(
    [
        "This is a synthetic long-context workload for a local coding-agent fanout benchmark.",
        "Each stream receives a distinct prompt so vLLM cannot turn the whole workload into a prefix-cache replay.",
        "Summarize the architecture, failure modes, measurements, and operator-facing tradeoffs.",
        *[
            f"Section {i:02d}: event ingestion, routing, retry accounting, telemetry alignment, "
            f"GPU saturation behavior, queue backpressure, structured outputs, and concise reporting."
            for i in range(1, 68)
        ],
    ]
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


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
    if CONTAINER in set(cp.stdout.splitlines()):
        raise SystemExit(f"container {CONTAINER} already exists; refusing to reuse or stop it")
    return snap


def extract_counter(scrape: str) -> float | None:
    for line in scrape.splitlines():
        if line.startswith(COUNTER):
            try:
                return float(line.rsplit(" ", 1)[1])
            except (IndexError, ValueError):
                return None
    return None


def start_container() -> tuple[str, subprocess.Popen[str]]:
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
        "32",
        "--quantization",
        "gptq_marlin",
        "--enable-auto-tool-choice",
        "--tool-call-parser",
        "hermes",
        "--reasoning-parser",
        "qwen3",
    ]
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
    with (OUT / "docker_run.err").open("w", encoding="utf-8") as err:
        cp = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=err, check=False)
    if cp.returncode != 0:
        raise SystemExit((OUT / "docker_run.err").read_text(errors="replace"))
    cid = cp.stdout.strip()
    (OUT / "container.id").write_text(cid + "\n", encoding="utf-8")
    log_f = (OUT / "server.log").open("w", encoding="utf-8")
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
    while time.monotonic() < deadline:
        for suffix in ("/health", "/v1/models"):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{suffix}", timeout=5) as r:
                    if r.status == 200:
                        return
            except Exception:
                pass
        time.sleep(2)
    raise TimeoutError("server never became healthy")


def scrape_metrics(stop: threading.Event, out: Path) -> None:
    url = f"http://127.0.0.1:{PORT}/metrics"
    next_tick = time.monotonic()
    with out.open("w", encoding="utf-8", buffering=1024 * 1024) as f:
        while not stop.is_set():
            ts = now_iso()
            mono = time.monotonic()
            body = ""
            err = None
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


def append_event(path: Path, event: str, **extra: Any) -> dict[str, Any]:
    row = {"ts": now_iso(), "event": event, **extra}
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


async def worker(worker_id: int, end_at: float) -> dict[str, Any]:
    requests = 0
    errors = 0
    completion_tokens = 0
    prompt_tokens = 0
    latencies: list[float] = []
    while time.monotonic() < end_at:
        nonce = f"Unique run nonce: stream={worker_id} request={requests} monotonic={time.monotonic():.6f}."
        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": nonce + "\n\n" + PROMPT_BASE}],
            "temperature": 0.2,
            "max_tokens": MAX_TOKENS,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            body = await asyncio.to_thread(post_chat, payload)
            usage = body.get("usage") or {}
            completion_tokens += int(usage.get("completion_tokens") or 0)
            prompt_tokens += int(usage.get("prompt_tokens") or 0)
            latencies.append(float(body.get("_client_wall_s") or 0.0))
        except Exception as exc:  # noqa: BLE001
            errors += 1
            latencies.append(0.0)
            if errors <= 3:
                print(f"worker {worker_id} request {requests} failed: {exc}", file=sys.stderr)
        requests += 1
    return {
        "worker": worker_id,
        "requests": requests,
        "errors": errors,
        "completion_tokens_usage": completion_tokens,
        "prompt_tokens_usage": prompt_tokens,
        "latency_s": latencies,
    }


async def run_workload(duration_s: float) -> dict[str, Any]:
    t0 = time.monotonic()
    end_at = t0 + duration_s
    workers = await asyncio.gather(*(worker(i, end_at) for i in range(STREAMS)))
    wall_s = time.monotonic() - t0
    return {
        "streams": STREAMS,
        "requested_duration_s": duration_s,
        "wall_s": wall_s,
        "max_tokens": MAX_TOKENS,
        "completion_tokens_usage": sum(w["completion_tokens_usage"] for w in workers),
        "prompt_tokens_usage": sum(w["prompt_tokens_usage"] for w in workers),
        "workers": workers,
    }


def read_metric_samples(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        counter = row.get("generation_counter")
        if counter is None:
            counter = extract_counter(row.get("scrape") or "")
        if counter is None:
            continue
        rows.append({"ts": parse_iso(row["ts"]), "monotonic_s": float(row["monotonic_s"]), "counter": float(counter)})
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


def fnum(row: dict[str, Any], key: str) -> float:
    raw = row.get(key)
    if raw in (None, ""):
        return 0.0
    return float(raw)


def nearest_telemetry(ts: dt.datetime, telemetry: list[dict[str, Any]]) -> dict[str, Any]:
    return min(telemetry, key=lambda r: abs((parse_iso(r["ts"]) - ts).total_seconds()))


def derive() -> dict[str, Any]:
    events = [json.loads(line) for line in (OUT / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    start = parse_iso(next(e["ts"] for e in events if e["event"] == "workload_start"))
    end = parse_iso(next(e["ts"] for e in events if e["event"] == "workload_end"))
    samples = [r for r in read_metric_samples(OUT / "vllm-metrics.jsonl") if start <= r["ts"] <= end]
    telemetry = read_telemetry(OUT / "telemetry.csv")
    if not samples:
        raise SystemExit("no metric samples inside workload window")
    rows: list[dict[str, Any]] = []
    for r in samples:
        t = nearest_telemetry(r["ts"], telemetry)
        rows.append(
            {
                "ts": r["ts"].isoformat(),
                "generation_tokens_total": f"{r['counter']:.3f}",
                "decode_tokens_delta": f"{r['delta']:.3f}",
                "decode_tok_s": f"{r['decode_tok_s']:.3f}",
                "gpu_util_pct": f"{fnum(t, 'gpu_util_pct'):.3f}",
                "vram_used_mib": f"{fnum(t, 'vram_used_mib'):.3f}",
                "power_w": f"{fnum(t, 'power_w'):.3f}",
                "temp_c": f"{fnum(t, 'temp_c'):.3f}",
                "sm_clock_mhz": f"{fnum(t, 'sm_clock_mhz'):.3f}",
                "cpu_util_pct": f"{fnum(t, 'cpu_util_pct'):.3f}",
                "ram_used_gib": f"{fnum(t, 'ram_used_gib'):.3f}",
            }
        )
    with (OUT / "replay-series.csv").open("w", newline="", encoding="utf-8") as f:
        fieldnames = list(rows[0])
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    active = [float(r["decode_tok_s"]) for r in rows if float(r["decode_tokens_delta"]) > 0]
    sustained = statistics.mean(active) if active else 0.0
    summary = {
        "schema": "local-agents.article-x24-capture.v1",
        "streams": STREAMS,
        "max_tokens": MAX_TOKENS,
        "counter_name": COUNTER,
        "metric_samples": len(rows),
        "active_seconds": len(active),
        "total_generation_tokens_delta": round(sum(float(r["decode_tokens_delta"]) for r in rows), 3),
        "sustained_decode_tok_s_active_mean": round(sustained, 3),
        "per_stream_decode_tok_s_active_mean": round(sustained / STREAMS, 3),
        "peak_decode_tok_s": round(max(float(r["decode_tok_s"]) for r in rows), 3),
        "peak_row_ts": max(rows, key=lambda r: float(r["decode_tok_s"]))["ts"],
    }
    (OUT / "capture-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def do_run(args: argparse.Namespace) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in [
        "telemetry.csv",
        "vllm-metrics.jsonl",
        "workload.json",
        "events.jsonl",
        "replay-series.csv",
        "capture-summary.json",
        "server.log",
        "container.id",
    ]:
        path = OUT / name
        if path.exists():
            path.unlink()
    run_json: dict[str, Any] = {
        "schema": "local-agents.article-x24-run.v1",
        "created_at": now_iso(),
        "image": IMAGE,
        "container": CONTAINER,
        "port": PORT,
        "model": MODEL,
        "streams": STREAMS,
        "duration_s": args.duration,
        "preflight": preflight(),
    }
    (OUT / "run.json").write_text(json.dumps(run_json, indent=2), encoding="utf-8")
    log_proc: subprocess.Popen[str] | None = None
    telemetry_proc: subprocess.Popen[str] | None = None
    metrics_stop = threading.Event()
    scraper: threading.Thread | None = None
    started = False
    try:
        _cid, log_proc = start_container()
        started = True
        wait_healthy()
        run_json["healthy_at"] = now_iso()
        run_json["vram_loaded"] = gpu_snapshot()
        (OUT / "run.json").write_text(json.dumps(run_json, indent=2), encoding="utf-8")
        telemetry_proc = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "telemetry_sampler.py"), "--out", str(OUT / "telemetry.csv")])
        scraper = threading.Thread(target=scrape_metrics, args=(metrics_stop, OUT / "vllm-metrics.jsonl"), daemon=True)
        scraper.start()
        append_event(OUT / "events.jsonl", "workload_start")
        workload = asyncio.run(run_workload(args.duration))
        workload["start_ts"] = next(json.loads(line)["ts"] for line in (OUT / "events.jsonl").read_text().splitlines() if "workload_start" in line)
        workload["end_ts"] = append_event(OUT / "events.jsonl", "workload_end")["ts"]
        (OUT / "workload.json").write_text(json.dumps(workload, indent=2), encoding="utf-8")
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
        run_json["post_stop_gpu"] = gpu_snapshot()
        run_json["ended_at"] = now_iso()
        (OUT / "run.json").write_text(json.dumps(run_json, indent=2), encoding="utf-8")
    print(json.dumps(derive(), indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run")
    run_p.add_argument("--duration", type=float, default=120.0)
    run_p.set_defaults(func=do_run)
    derive_p = sub.add_parser("derive")
    derive_p.set_defaults(func=lambda _args: print(json.dumps(derive(), indent=2)))
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
