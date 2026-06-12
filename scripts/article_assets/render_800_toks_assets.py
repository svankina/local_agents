#!/usr/bin/env python3
"""Render stylized social assets for docs/article/2026-06-800-toks-3090.md.

Creates:
- docs/article/assets/fastfetch-3090ti.png
- docs/article/assets/800-toks-tmux-demo.gif
- docs/article/assets/800-toks-tmux-demo.mp4
- docs/article/assets/800-toks-tmux-demo-poster.png
"""

from __future__ import annotations

import math
import re
import csv
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / "docs" / "article" / "assets"
ASSET.mkdir(parents=True, exist_ok=True)
DATA = ROOT / "scripts" / "article_assets" / "data" / "x24"

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
F14 = ImageFont.truetype(FONT_REGULAR, 14)
F15 = ImageFont.truetype(FONT_REGULAR, 15)
F16 = ImageFont.truetype(FONT_REGULAR, 16)
F17 = ImageFont.truetype(FONT_REGULAR, 17)
F18 = ImageFont.truetype(FONT_REGULAR, 18)
F22B = ImageFont.truetype(FONT_BOLD, 22)
F34B = ImageFont.truetype(FONT_BOLD, 34)
F42B = ImageFont.truetype(FONT_BOLD, 42)

BG = "#0b1020"
PANE = "#111827"
PANE2 = "#0f172a"
BORDER = "#334155"
CYAN = "#22d3ee"
GREEN = "#22c55e"
YELLOW = "#facc15"
RED = "#ef4444"
MUTED = "#94a3b8"
TEXT = "#e5e7eb"
DIM = "#64748b"
PURPLE = "#a78bfa"


def fastfetch_lines() -> list[str]:
    cmd = [
        "fastfetch",
        "--logo",
        "none",
        "--pipe",
        "true",
        "--structure",
        "Title:Separator:OS:Host:Kernel:CPU:GPU:Memory:Disk",
        "--key-type",
        "string",
    ]
    raw = subprocess.check_output(cmd, text=True)
    raw = re.sub(r"\x1b\[[0-9;]*m", "", raw).strip("\n")
    lines = raw.splitlines()
    stable: list[str] = []
    for line in lines:
        line = re.sub(r"Memory: .* / 62\.68 GiB.*", "Memory: 62.68 GiB usable", line)
        stable.append(line)
    return stable


def render_fastfetch_png(lines: list[str]) -> None:
    pad = 26
    line_h = 27
    w = 860
    h = pad * 2 + line_h * len(lines) + 16
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, w - 8, h - 8], radius=16, fill=PANE2, outline=BORDER, width=2)
    d.text((pad, pad), lines[0], font=F22B, fill=CYAN)
    y = pad + line_h
    for line in lines[1:]:
        if line.startswith("-"):
            d.text((pad, y), line, font=F18, fill=DIM)
        elif ":" in line:
            k, v = line.split(":", 1)
            d.text((pad, y), k + ":", font=F18, fill=CYAN)
            d.text((pad + 170, y), v.strip(), font=F18, fill=TEXT)
        else:
            d.text((pad, y), line, font=F18, fill=TEXT)
        y += line_h
    img.save(ASSET / "fastfetch-3090ti.png")


def draw_pane(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str, accent: str = CYAN) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle([x1, y1, x2, y2], radius=10, fill=PANE, outline=BORDER, width=2)
    draw.rectangle([x1 + 2, y1 + 2, x2 - 2, y1 + 30], fill="#020617")
    draw.text((x1 + 12, y1 + 7), title, font=F15, fill=accent)
    draw.text((x2 - 54, y1 + 7), "tmux", font=F14, fill=DIM)


def draw_text_lines(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    lines: list[str],
    start_y: int = 40,
    font: ImageFont.FreeTypeFont = F16,
    max_lines: int | None = None,
) -> None:
    x1, y1, _x2, y2 = box
    line_h = 23
    max_fit = int((y2 - y1 - start_y - 12) / line_h)
    visible = lines[-(max_lines or max_fit) :]
    y = y1 + start_y
    for line in visible:
        fill = TEXT
        if line.startswith("$"):
            fill = GREEN
        elif "ok" in line or "verified" in line:
            fill = "#bbf7d0"
        elif "retry" in line:
            fill = YELLOW
        elif "ceiling" in line or "scorecard" in line:
            fill = CYAN
        draw.text((x1 + 14, y), line, font=font, fill=fill)
        y += line_h


def draw_meter(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    tps: float,
    frame: int,
    cap: float,
    streams: int,
    readout_tps: float | None = None,
) -> None:
    # tps drives the needle (eased display value); readout_tps is the measured
    # sample printed in the digital readout, so printed numbers are never eased.
    x1, y1, x2, y2 = box
    cap = max(cap, 1.0)
    tps = min(tps, cap)
    readout_val = min(cap, tps if readout_tps is None else readout_tps)

    cx, cy = (x1 + x2) // 2, y1 + 126
    r = min((x2 - x1) // 3, 78)
    start, end = -215, 35
    ratio = max(0, min(tps / cap, 1.0))
    needle_angle = math.radians(start + (end - start) * ratio)
    arc_box = [cx - r, cy - r, cx + r, cy + r]

    draw.text((x1 + 18, y1 + 38), "measured replay", font=F14, fill=MUTED)

    draw.arc(arc_box, start, end, fill=BORDER, width=14)
    draw.arc(arc_box, start, start + int((end - start) * 0.78), fill=GREEN, width=14)
    draw.arc(arc_box, start + int((end - start) * 0.78), end, fill=RED, width=14)
    draw.arc([cx - r + 15, cy - r + 15, cx + r - 15, cy + r - 15], start, start + int((end - start) * ratio), fill=CYAN, width=4)

    for i in range(17):
        frac = i / 16
        angle = math.radians(start + (end - start) * frac)
        major = i % 4 == 0
        tick_outer = r + 1
        tick_inner = r - (24 if major else 14)
        ox = cx + math.cos(angle) * tick_outer
        oy = cy + math.sin(angle) * tick_outer
        ix = cx + math.cos(angle) * tick_inner
        iy = cy + math.sin(angle) * tick_inner
        draw.line([ix, iy, ox, oy], fill=TEXT if major else DIM, width=3 if major else 2)
        if major:
            label = f"{cap * frac:.0f}"
            lx = cx + math.cos(angle) * (r - 43)
            ly = cy + math.sin(angle) * (r - 43)
            draw.text((lx - 18, ly - 8), label, font=F14, fill=MUTED)

    nx = cx + math.cos(needle_angle) * (r - 24)
    ny = cy + math.sin(needle_angle) * (r - 24)
    tail_x = cx - math.cos(needle_angle) * 18
    tail_y = cy - math.sin(needle_angle) * 18
    draw.line([tail_x, tail_y, nx, ny], fill="#f43f5e", width=7)
    draw.line([tail_x, tail_y, nx, ny], fill="#fb7185", width=3)
    draw.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill="#020617", outline=CYAN, width=3)

    readout = f"{readout_val:05.1f}"
    read_box = [x1 + 18, y1 + 168, x2 - 18, y1 + 221]
    draw.rounded_rectangle(read_box, radius=12, fill="#020617", outline="#22d3ee66", width=1)
    draw.text((x1 + 58, y1 + 174), readout, font=F34B, fill=GREEN)
    draw.text((x1 + 190, y1 + 185), "tok/s", font=F18, fill=CYAN)
    draw.text((x1 + 103, y1 + 207), f"{streams}x - {readout_val / streams:04.1f} tok/s each", font=F14, fill=MUTED)


def draw_max_pane(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], run_max: float, is_new: bool) -> None:
    # Running maximum of the measured per-second samples seen so far in the replay.
    x1, y1, x2, y2 = box
    draw.text((x1 + 16, y1 + 12), "max tok/s (this replay)", font=F14, fill=MUTED)
    color = YELLOW if is_new else GREEN
    draw.text((x2 - 196, y1 + 4), f"{run_max:06.1f}", font=F34B, fill=color)
    if is_new:
        draw.text((x2 - 40, y1 + 12), "NEW", font=F14, fill=YELLOW)


def ease(t: float) -> float:
    return 1 - (1 - t) ** 3


def load_replay_series() -> list[dict[str, float | str]]:
    path = DATA / "replay-series.csv"
    if not path.exists():
        raise SystemExit(f"missing measured replay data: {path.relative_to(ROOT)}")
    rows: list[dict[str, float | str]] = []
    numeric = {
        "generation_tokens_total",
        "decode_tokens_delta",
        "decode_tok_s",
        "gpu_util_pct",
        "vram_used_mib",
        "power_w",
        "temp_c",
        "cpu_util_pct",
        "ram_used_gib",
    }
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            parsed: dict[str, float | str] = dict(row)
            for key in numeric:
                parsed[key] = float(row[key] or 0)
            rows.append(parsed)
    if not rows:
        raise SystemExit(f"empty measured replay data: {path.relative_to(ROOT)}")
    return rows


def load_capture_summary() -> dict[str, float | int | str]:
    path = DATA / "capture-summary.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def load_workload() -> dict[str, object]:
    path = DATA / "capture-workload.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def draw_metric_bar(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    label: str,
    value: str,
    frac: float,
    color: str,
) -> None:
    draw.text((x, y), label, font=F14, fill=MUTED)
    draw.text((x + 88, y), value, font=F14, fill=TEXT)
    bx, by, bw, bh = x, y + 19, 268, 9
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=4, fill="#020617", outline="#1e293b")
    draw.rounded_rectangle([bx, by, bx + int(bw * max(0, min(frac, 1))), by + bh], radius=4, fill=color)


def draw_telemetry(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    row: dict[str, float | str],
    eased: dict[str, float] | None = None,
) -> None:
    # Text always shows the measured sample; the bar widths glide on the eased
    # display values so motion is smooth without ever printing an unmeasured number.
    x1, y1, _x2, _y2 = box
    gpu = float(row["gpu_util_pct"])
    vram_mib = float(row["vram_used_mib"])
    power = float(row["power_w"])
    temp = float(row["temp_c"])
    cpu = float(row["cpu_util_pct"])
    ram = float(row["ram_used_gib"])
    e = eased or {"gpu": gpu, "vram": vram_mib, "power": power, "temp": temp, "cpu": cpu, "ram": ram}
    metrics = [
        ("GPU", f"{gpu:05.1f}%", e["gpu"] / 100, GREEN),
        ("VRAM", f"{vram_mib / 1024:05.2f}G", e["vram"] / 24564, PURPLE),
        ("CPU", f"{cpu:05.1f}%", e["cpu"] / 100, CYAN),
        ("RAM", f"{ram:05.2f}G", e["ram"] / 62.68, CYAN),
        ("POWER", f"{power:05.1f}W", e["power"] / 450, YELLOW),
        ("TEMP", f"{temp:05.1f}C", e["temp"] / 90, GREEN if temp < 75 else YELLOW),
    ]
    y = y1 + 40
    for label, value, frac, color in metrics:
        draw_metric_bar(draw, x1 + 16, y, label, value, frac, color)
        y += 28


def render_demo(lines: list[str]) -> None:
    # 16:9, small enough for X/Twitter GIF upload while still readable in article.
    w, h = 960, 540
    left = (18, 36, 590, 440)
    maxbox = (18, 452, 590, 510)
    rtop = (622, 36, 942, 258)
    rbot = (622, 276, 942, 510)

    series = load_replay_series()
    summary = load_capture_summary()
    workload = load_workload()
    active_indices = [i for i, row in enumerate(series) if float(row["decode_tokens_delta"]) > 0]
    if active_indices:
        series = series[active_indices[0] : active_indices[-1] + 1]
    cap = float(summary.get("peak_decode_tok_s") or max(float(r["decode_tok_s"]) for r in series))
    sustained = float(summary.get("sustained_decode_tok_s_active_mean") or 0)
    streams = int(summary.get("streams") or 24)
    total_tokens = int(float(summary.get("total_generation_tokens_delta") or series[-1]["generation_tokens_total"]))
    active_seconds = int(summary.get("active_seconds") or sum(1 for r in series if float(r["decode_tokens_delta"]) > 0))
    metric_samples = int(summary.get("metric_samples") or len(series))
    max_vram = max(float(r["vram_used_mib"]) for r in series)
    max_power = max(float(r["power_w"]) for r in series)
    max_temp = max(float(r["temp_c"]) for r in series)

    base_log = [
        "$ scripts/article_assets/capture_x24_replay.py run --duration 120",
        "vLLM 0.22.1 | Qwen3-30B-A3B-GPTQ-Int4",
        "flags: --max-num-seqs 32 --max-model-len 16384",
        f"health: ok | model loaded | VRAM {max_vram:,.0f} MiB",
        f"counter: vllm:generation_tokens_total",
        "reasoning parser: qwen3 | quantization: gptq_marlin",
        f"fanout: {streams} streams | {active_seconds}s measured decode",
    ]
    workers = []
    for worker in workload.get("workers", []):
        if not isinstance(worker, dict):
            continue
        wid = int(worker.get("worker", len(workers)))
        reqs = int(worker.get("requests", 0))
        generated = int(worker.get("completion_tokens_usage", 0))
        errors = int(worker.get("errors", 0))
        status = "ok" if errors == 0 else f"{errors} errors"
        workers.append(f"s{wid} {reqs} requests {status}  {generated:,} generated")
    workers.extend(
        [
            "...",
            f"metric samples: {metric_samples} | generated {total_tokens:,}",
            f"sustained measured: {sustained:.1f} tok/s",
            f"measured ceiling: {cap:.1f} tok/s",
            f"thermal: {max_temp:.0f}C max | power {max_power:.1f}W max",
        ]
    )

    frames: list[Image.Image] = []
    n = len(series)
    # Motion: SUB eased sub-frames per measured second. The needle and telemetry
    # bars follow each new sample with a critically-damped chase (convex blend of
    # measured values - they can never exceed the running measured range). All
    # printed numbers step on the raw samples only.
    SUB = 4
    EASE_NEEDLE = 0.30
    EASE_BARS = 0.22
    display_tps = max(0.0, min(cap, float(series[0]["decode_tok_s"])))
    eased_tel = {
        "gpu": float(series[0]["gpu_util_pct"]),
        "vram": float(series[0]["vram_used_mib"]),
        "power": float(series[0]["power_w"]),
        "temp": float(series[0]["temp_c"]),
        "cpu": float(series[0]["cpu_util_pct"]),
        "ram": float(series[0]["ram_used_gib"]),
    }
    run_max = 0.0
    poster_master_index = {}
    for f in range(n):
        phase = f / (n - 1)
        row = series[f]
        sample_tps = max(0, min(cap, float(row["decode_tok_s"])))
        new_max = sample_tps > run_max
        run_max = max(run_max, sample_tps)
        targets = {
            "gpu": float(row["gpu_util_pct"]),
            "vram": float(row["vram_used_mib"]),
            "power": float(row["power_w"]),
            "temp": float(row["temp_c"]),
            "cpu": float(row["cpu_util_pct"]),
            "ram": float(row["ram_used_gib"]),
        }

        n_worker = int(max(0, (phase - 0.18)) / 0.70 * len(workers))
        n_worker = max(0, min(len(workers), n_worker))
        logs = base_log + workers[:n_worker]
        if 0.14 < phase < 0.95:
            logs.append(f"$ decode sample {f + 1:03d}: {sample_tps:05.1f} tok/s aggregate")

        for sub in range(SUB):
            display_tps += (sample_tps - display_tps) * EASE_NEEDLE
            for k in eased_tel:
                eased_tel[k] += (targets[k] - eased_tel[k]) * EASE_BARS

            im = Image.new("RGB", (w, h), BG)
            dr = ImageDraw.Draw(im)
            dr.rectangle([0, 0, w, 30], fill="#020617")
            dr.text((18, 8), "measured replay  |  RTX 3090 Ti  |  vLLM x24", font=F15, fill=CYAN)
            dr.text((w - 268, 8), "Qwen3-30B-A3B GPTQ-Int4", font=F15, fill=MUTED)

            draw_pane(dr, left, "0: fanout run", GREEN)
            draw_pane(dr, maxbox, "3: peak", YELLOW)
            draw_pane(dr, rtop, "1: aggregate decode meter", CYAN)
            draw_pane(dr, rbot, "2: measured telemetry", PURPLE)

            draw_text_lines(dr, left, logs, start_y=40, font=F14, max_lines=16)
            draw_meter(dr, rtop, display_tps, f, cap, streams, readout_tps=sample_tps)
            draw_max_pane(dr, maxbox, run_max, new_max and sub < SUB // 2)
            draw_telemetry(dr, rbot, row, eased=eased_tel)
            frames.append(im)
        poster_master_index[f] = len(frames) - 1

    out_frames = [frame.resize((1920, 1080), Image.Resampling.LANCZOS) for frame in frames]
    poster_candidates = [
        i
        for i, row in enumerate(series)
        if i > len(series) // 2
        and float(row["gpu_util_pct"]) >= 95
        and float(row["power_w"]) >= 400
        and float(row["decode_tok_s"]) >= cap * 0.85
    ]
    peak_row = max(poster_candidates or range(len(series)), key=lambda i: float(series[i]["decode_tok_s"]))
    out_frames[poster_master_index[peak_row]].save(ASSET / "800-toks-tmux-demo-poster.png")

    # GIF: every other sub-frame at 30ms -> ~16.5 fps with eased deltas (smooth),
    # holds on first/last frame. MP4 below carries the full 30 fps version.
    gif_seq = [out_frames[0]] * 8 + out_frames[::2] + [out_frames[-1]] * 14
    gif_seq[0].save(
        ASSET / "800-toks-tmux-demo.gif",
        save_all=True,
        append_images=gif_seq[1:],
        duration=60,
        loop=0,
        optimize=True,
    )

    if shutil.which("ffmpeg"):
        tmp_dir = ASSET / ".800-toks-frames"
        tmp_dir.mkdir(exist_ok=True)
        for i, frame in enumerate(out_frames):
            frame.save(tmp_dir / f"frame-{i:04d}.png")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                "30",
                "-i",
                str(tmp_dir / "frame-%04d.png"),
                "-vf",
                "format=yuv420p",
                "-movflags",
                "+faststart",
                "-pix_fmt",
                "yuv420p",
                str(ASSET / "800-toks-tmux-demo.mp4"),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for p in tmp_dir.glob("frame-*.png"):
            p.unlink()
        tmp_dir.rmdir()


def main() -> None:
    lines = fastfetch_lines()
    render_fastfetch_png(lines)
    render_demo(lines)
    for name in [
        "fastfetch-3090ti.png",
        "800-toks-tmux-demo.gif",
        "800-toks-tmux-demo.mp4",
        "800-toks-tmux-demo-poster.png",
    ]:
        path = ASSET / name
        if path.exists():
            print(f"{path.relative_to(ROOT)} {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
