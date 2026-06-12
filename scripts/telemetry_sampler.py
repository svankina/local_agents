#!/usr/bin/env python3
"""1 Hz hardware telemetry CSV sampler for m1-replay experiments.

Uses system Python. If psutil is unavailable, falls back to Linux /proc parsing.
Per-core utilization is emitted as cpu0_pct..cpuN_pct columns in the CSV header.
GPU telemetry is read from one persistent nvidia-smi child:
  nvidia-smi --query-gpu=utilization.gpu,memory.used,power.draw,temperature.gpu,clocks.sm --format=csv,noheader,nounits -l 1
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - exercised only on hosts without psutil
    psutil = None


GPU_QUERY = "utilization.gpu,memory.used,power.draw,temperature.gpu,clocks.sm"
STOP = threading.Event()


def renice() -> None:
    try:
        os.nice(19)
    except OSError:
        pass


def start_nvidia_smi() -> tuple[subprocess.Popen[str] | None, queue.Queue[str]]:
    q: queue.Queue[str] = queue.Queue()
    cmd = [
        "nvidia-smi",
        f"--query-gpu={GPU_QUERY}",
        "--format=csv,noheader,nounits",
        "-l",
        "1",
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
    except OSError:
        return None, q

    def reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            if STOP.is_set():
                break
            q.put(line.strip())

    threading.Thread(target=reader, daemon=True).start()
    return proc, q


def parse_gpu(line: str | None) -> dict[str, float | None]:
    vals: list[float | None] = [None, None, None, None, None]
    if line:
        parts = [p.strip() for p in line.split(",")]
        for i, part in enumerate(parts[:5]):
            try:
                vals[i] = float(part)
            except ValueError:
                vals[i] = None
    return {
        "gpu_util_pct": vals[0],
        "vram_used_mib": vals[1],
        "power_w": vals[2],
        "temp_c": vals[3],
        "sm_clock_mhz": vals[4],
    }


def latest_gpu_line(q: queue.Queue[str], previous: str | None) -> str | None:
    line = previous
    while True:
        try:
            line = q.get_nowait()
        except queue.Empty:
            return line


def proc_cpu_snapshot() -> list[tuple[int, int]]:
    rows: list[tuple[int, int]] = []
    with open("/proc/stat", encoding="utf-8") as f:
        for line in f:
            if not line.startswith("cpu"):
                break
            parts = line.split()
            if parts[0] == "cpu" or parts[0][3:].isdigit():
                nums = [int(x) for x in parts[1:]]
                idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
                rows.append((sum(nums), idle))
    return rows


def proc_cpu_percent(prev: list[tuple[int, int]], cur: list[tuple[int, int]]) -> tuple[float, list[float]]:
    vals: list[float] = []
    for (ptotal, pidle), (ctotal, cidle) in zip(prev, cur):
        total = max(0, ctotal - ptotal)
        idle = max(0, cidle - pidle)
        vals.append(0.0 if total == 0 else 100.0 * (total - idle) / total)
    overall = vals[0] if vals else 0.0
    return overall, vals[1:]


def proc_mem() -> tuple[float, float, float]:
    vals: dict[str, int] = {}
    with open("/proc/meminfo", encoding="utf-8") as f:
        for line in f:
            k, v = line.split(":", 1)
            vals[k] = int(v.split()[0])
    used_kib = vals["MemTotal"] - vals.get("MemAvailable", vals.get("MemFree", 0))
    swap_used_kib = vals.get("SwapTotal", 0) - vals.get("SwapFree", 0)
    return used_kib / 1024 / 1024, vals.get("MemAvailable", 0) / 1024 / 1024, swap_used_kib / 1024 / 1024


def proc_disk_snapshot() -> tuple[int, int]:
    sectors_read = 0
    sectors_written = 0
    with open("/proc/diskstats", encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 14:
                continue
            name = parts[2]
            if name.startswith(("loop", "ram", "sr")):
                continue
            sectors_read += int(parts[5])
            sectors_written += int(parts[9])
    return sectors_read * 512, sectors_written * 512


def proc_net_snapshot() -> tuple[int, int]:
    rx = 0
    tx = 0
    with open("/proc/net/dev", encoding="utf-8") as f:
        for line in f.readlines()[2:]:
            iface, rest = line.split(":", 1)
            if iface.strip() == "lo":
                continue
            parts = rest.split()
            rx += int(parts[0])
            tx += int(parts[8])
    return rx, tx


class HostStats:
    def __init__(self) -> None:
        self.last_t = time.monotonic()
        if psutil:
            psutil.cpu_percent(interval=None)
            psutil.cpu_percent(interval=None, percpu=True)
            self.last_disk = psutil.disk_io_counters()
            self.last_net = psutil.net_io_counters()
            self.core_count = psutil.cpu_count(logical=True) or os.cpu_count() or 1
            self.last_proc_cpu = None
        else:
            self.last_proc_cpu = proc_cpu_snapshot()
            self.last_disk = proc_disk_snapshot()
            self.last_net = proc_net_snapshot()
            self.core_count = max(1, len(self.last_proc_cpu) - 1)

    def sample(self) -> dict[str, float | list[float]]:
        now = time.monotonic()
        elapsed = max(now - self.last_t, 1e-9)
        self.last_t = now
        if psutil:
            cpu = float(psutil.cpu_percent(interval=None))
            cores = [float(x) for x in psutil.cpu_percent(interval=None, percpu=True)]
            load1 = float(os.getloadavg()[0])
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            disk = psutil.disk_io_counters()
            net = psutil.net_io_counters()
            read_b = max(0, disk.read_bytes - self.last_disk.read_bytes)
            write_b = max(0, disk.write_bytes - self.last_disk.write_bytes)
            rx_b = max(0, net.bytes_recv - self.last_net.bytes_recv)
            tx_b = max(0, net.bytes_sent - self.last_net.bytes_sent)
            self.last_disk = disk
            self.last_net = net
            ram_used_gib = mem.used / 1024**3
            ram_available_gib = mem.available / 1024**3
            swap_used_gib = swap.used / 1024**3
        else:
            cur_cpu = proc_cpu_snapshot()
            cpu, cores = proc_cpu_percent(self.last_proc_cpu or cur_cpu, cur_cpu)
            self.last_proc_cpu = cur_cpu
            load1 = float(os.getloadavg()[0])
            ram_used_gib, ram_available_gib, swap_used_gib = proc_mem()
            disk = proc_disk_snapshot()
            net = proc_net_snapshot()
            read_b = max(0, disk[0] - self.last_disk[0])
            write_b = max(0, disk[1] - self.last_disk[1])
            rx_b = max(0, net[0] - self.last_net[0])
            tx_b = max(0, net[1] - self.last_net[1])
            self.last_disk = disk
            self.last_net = net

        return {
            "cpu_util_pct": cpu,
            "load1": load1,
            "per_core": cores,
            "ram_used_gib": ram_used_gib,
            "ram_available_gib": ram_available_gib,
            "swap_used_gib": swap_used_gib,
            "io_read_mb_s": read_b / 1024**2 / elapsed,
            "io_write_mb_s": write_b / 1024**2 / elapsed,
            "net_rx_kb_s": rx_b / 1024 / elapsed,
            "net_tx_kb_s": tx_b / 1024 / elapsed,
        }


def install_signal_handlers(csv_file) -> None:
    def stop(_signum, _frame) -> None:
        STOP.set()
        csv_file.flush()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)


def fmt(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample hardware telemetry to CSV at 1 Hz.")
    parser.add_argument("--out", required=True, help="CSV output path")
    args = parser.parse_args()

    renice()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    stats = HostStats()
    gpu_proc, gpu_q = start_nvidia_smi()
    last_gpu: str | None = None
    t0 = time.monotonic()
    next_tick = t0

    with out.open("a", newline="", buffering=1024 * 1024) as f:
        install_signal_handlers(f)
        fieldnames = [
            "ts",
            "monotonic_s",
            "gpu_util_pct",
            "vram_used_mib",
            "power_w",
            "temp_c",
            "sm_clock_mhz",
            "cpu_util_pct",
            "load1",
            *[f"cpu{i}_pct" for i in range(stats.core_count)],
            "ram_used_gib",
            "ram_available_gib",
            "swap_used_gib",
            "io_read_mb_s",
            "io_write_mb_s",
            "net_rx_kb_s",
            "net_tx_kb_s",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if out.stat().st_size == 0:
            writer.writeheader()

        while not STOP.is_set():
            now = time.monotonic()
            if now < next_tick:
                STOP.wait(next_tick - now)
                continue
            next_tick += 1.0
            last_gpu = latest_gpu_line(gpu_q, last_gpu)
            host = stats.sample()
            gpu = parse_gpu(last_gpu)
            cores = list(host.pop("per_core"))[: stats.core_count]
            row: dict[str, object] = {
                "ts": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds"),
                "monotonic_s": time.monotonic() - t0,
                **gpu,
                **host,
            }
            for i in range(stats.core_count):
                row[f"cpu{i}_pct"] = cores[i] if i < len(cores) else ""
            writer.writerow({k: fmt(row.get(k)) for k in fieldnames})

        f.flush()

    if gpu_proc is not None and gpu_proc.poll() is None:
        gpu_proc.terminate()
        try:
            gpu_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            gpu_proc.kill()
            gpu_proc.wait(timeout=3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
