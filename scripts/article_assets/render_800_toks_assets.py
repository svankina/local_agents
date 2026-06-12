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
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT / "docs" / "article" / "assets"
ASSET.mkdir(parents=True, exist_ok=True)

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
    x1, y1, x2, y2 = box
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


def draw_meter(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], tps: float, frame: int) -> None:
    x1, y1, x2, y2 = box
    y = y1 + 66
    draw.text((x1 + 34, y), f"{tps:05.1f}", font=F42B, fill=GREEN)
    draw.text((x1 + 260, y + 17), "tok/s", font=F22B, fill=CYAN)

    bar_x, bar_y = x1 + 34, y1 + 154
    bar_w, bar_h = x2 - x1 - 68, 28
    draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=12, fill="#020617", outline=BORDER)
    fill_w = int(bar_w * min(tps / 808.7, 1.0))
    col = GREEN if tps > 700 else YELLOW if tps > 350 else CYAN
    draw.rounded_rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], radius=12, fill=col)

    for frac, label in [(0, "0"), (0.25, "200"), (0.5, "400"), (0.75, "600"), (1, "808")]:
        tx = bar_x + int(bar_w * frac)
        draw.line([tx, bar_y + 34, tx, bar_y + 42], fill=DIM)
        draw.text((tx - 14, bar_y + 46), label, font=F14, fill=MUTED)

    per = tps / 8
    draw.text((x1 + 34, y1 + 126), f"8 streams  |  {per:04.1f} tok/s each", font=F15, fill=TEXT)
    if tps > 500:
        for i in range(12):
            sx = x1 + 30 + ((frame * 23 + i * 37) % (x2 - x1 - 60))
            sy = y1 + 40 + ((frame * 11 + i * 17) % 210)
            draw.point((sx, sy), fill=GREEN)
            draw.point((sx + 1, sy), fill=CYAN)


def ease(t: float) -> float:
    return 1 - (1 - t) ** 3


def render_demo(lines: list[str]) -> None:
    # 16:9, small enough for X/Twitter GIF upload while still readable in article.
    w, h = 960, 540
    left = (18, 36, 590, 486)
    rtop = (622, 36, 942, 258)
    rbot = (622, 276, 942, 486)

    base_log = [
        "$ bench/run_config_vllm.sh C18-qwen3-30b-vllm",
        "vLLM 0.22.1 | Qwen3-30B-A3B-GPTQ-Int4",
        "flags: --max-num-seqs 8 --max-model-len 16384",
        "health: ok | model loaded | VRAM 22,173 MiB",
        "coherence: hello ok | tool parser: hermes ok",
        "reasoning parser: qwen3 | quantization: gptq_marlin",
        "fanout: 8 streams | 32 docstring items",
    ]
    workers = [
        "s0 item-01 ok  286 tok  ast verified",
        "s1 item-02 ok  244 tok  ast verified",
        "s2 item-03 ok  312 tok  ast verified",
        "s3 item-04 retry -> ok  391 tok",
        "s4 item-05 ok  260 tok  ast verified",
        "s5 item-06 ok  228 tok  ast verified",
        "s6 item-07 ok  355 tok  ast verified",
        "s7 item-08 ok  274 tok  ast verified",
        "s0 item-09 ok  302 tok  ast verified",
        "s1 item-10 ok  219 tok  ast verified",
        "s2 item-11 retry -> ok  410 tok",
        "s3 item-12 ok  287 tok  ast verified",
        "s4 item-13 ok  248 tok  ast verified",
        "s5 item-14 ok  305 tok  ast verified",
        "s6 item-15 ok  352 tok  ast verified",
        "s7 item-16 ok  233 tok  ast verified",
        "...",
        "scorecard: 32/32 AST verified",
        "work phase: 24.7s | sustained 345 tok/s",
        "long decode ceiling: 808.7 tok/s",
    ]
    ff_lines = []
    for line in lines[:8]:
        line = line.replace("AMD Ryzen Threadripper 1920X (24) @ 3.50 GHz", "Threadripper 1920X (24)")
        line = line.replace("AMD Radeon RX 580 Series [Discrete]", "RX 580 8GB")
        line = line.replace("NVIDIA GeForce RTX 3090 Ti [Discrete]", "RTX 3090 Ti 24GB")
        ff_lines.append(line)

    frames: list[Image.Image] = []
    n = 72
    for f in range(n):
        phase = f / (n - 1)
        if phase < 0.16:
            tps = 45 + 20 * math.sin(f / 2)
        elif phase < 0.72:
            u = (phase - 0.16) / 0.56
            tps = 80 + 728.7 * ease(u)
            tps += 18 * math.sin(f * 0.7)
        else:
            # Hold at the measured ceiling. Do not animate above the published number.
            tps = 808.7
        tps = max(0, min(808.7, tps))

        im = Image.new("RGB", (w, h), BG)
        dr = ImageDraw.Draw(im)
        dr.rectangle([0, 0, w, 30], fill="#020617")
        dr.text((18, 8), "stylized replay  |  RTX 3090 Ti  |  vLLM x8", font=F15, fill=CYAN)
        dr.text((w - 268, 8), "Qwen3-30B-A3B GPTQ-Int4", font=F15, fill=MUTED)

        draw_pane(dr, left, "0: fanout run", GREEN)
        draw_pane(dr, rtop, "1: aggregate decode meter", CYAN)
        draw_pane(dr, rbot, "2: fastfetch", PURPLE)

        n_worker = int(max(0, (phase - 0.18)) / 0.70 * len(workers))
        n_worker = max(0, min(len(workers), n_worker))
        logs = base_log + workers[:n_worker]
        if 0.14 < phase < 0.95:
            spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"][f % 10]
            logs.append(f"{spinner} decoding batch: {tps:05.1f} tok/s aggregate")
        draw_text_lines(dr, left, logs, start_y=40, font=F14, max_lines=18)

        draw_meter(dr, rtop, tps, f)

        x1, y1, x2, y2 = rbot
        yy = y1 + 38
        for idx, line in enumerate(ff_lines):
            if idx == 0:
                dr.text((x1 + 14, yy), line, font=F15, fill=CYAN)
                yy += 21
                continue
            if line.startswith("-"):
                dr.text((x1 + 14, yy), line, font=F14, fill=DIM)
            elif ":" in line:
                k, v = line.split(":", 1)
                dr.text((x1 + 14, yy), k + ":", font=F14, fill=PURPLE)
                dr.text((x1 + 96, yy), v.strip()[:28], font=F14, fill=TEXT)
            else:
                dr.text((x1 + 14, yy), line, font=F14, fill=TEXT)
            yy += 20

        dr.rectangle([0, h - 24, w, h], fill="#16a34a")
        dr.text((18, h - 20), "[0] 808.7 decode tok/s from one RTX 3090 Ti", font=F14, fill="#03150a")
        dr.text((w - 142, h - 20), "24.7s  32/32", font=F14, fill="#03150a")
        frames.append(im)

    frames[-1].save(ASSET / "800-toks-tmux-demo-poster.png")

    # PIL's adaptive palette is enough here and keeps the GIF under Twitter's practical limits.
    gif_frames = [frames[0]] * 6 + frames + [frames[-1]] * 10
    gif_frames[0].save(
        ASSET / "800-toks-tmux-demo.gif",
        save_all=True,
        append_images=gif_frames[1:],
        duration=70,
        loop=0,
        optimize=True,
    )

    if shutil.which("ffmpeg"):
        tmp_dir = ASSET / ".800-toks-frames"
        tmp_dir.mkdir(exist_ok=True)
        for i, frame in enumerate(frames):
            frame.save(tmp_dir / f"frame-{i:04d}.png")
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                "14",
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
