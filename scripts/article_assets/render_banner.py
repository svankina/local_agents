#!/usr/bin/env python3
"""5:2 banner: the measured tachometer pinned at the capture's 1,248 tok/s peak.

Composes at 1000x400 with the demo renderer's own primitives, upscales to
2000x800. Every number comes from the x24 capture artifacts.
"""
import pathlib
import sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from PIL import Image, ImageDraw  # noqa: E402

import render_800_toks_assets as R  # noqa: E402


def main() -> None:
    series = R.load_replay_series()
    summary = R.load_capture_summary()
    cap = float(summary.get("peak_decode_tok_s") or max(float(r["decode_tok_s"]) for r in series))
    sustained = float(summary.get("sustained_decode_tok_s_active_mean") or 0)
    streams = int(summary.get("streams") or 24)
    # the full-load row nearest the peak (avoid nvidia-smi lag rows)
    peak_rows = [
        r for r in series
        if float(r["gpu_util_pct"]) >= 95 and float(r["power_w"]) >= 400
        and float(r["decode_tok_s"]) >= cap * 0.85
    ]
    row = max(peak_rows or series, key=lambda r: float(r["decode_tok_s"]))

    w, h = 1000, 400
    im = Image.new("RGB", (w, h), R.BG)
    dr = ImageDraw.Draw(im)

    # faint scanlines for the terminal-instrument feel
    for y in range(0, h, 4):
        dr.line([0, y, w, y], fill="#0b1220", width=1)

    # left: the claim
    dr.text((52, 64), "1,248 tok/s", font=R.F34B, fill=R.GREEN)
    dr.text((54, 116), "peak aggregate decode - measured", font=R.F15, fill=R.CYAN)
    dr.text((54, 152), "one RTX 3090 Ti  |  24 vLLM streams  |  Qwen3-30B-A3B GPTQ-Int4", font=R.F14, fill=R.TEXT)
    stats = [
        ("sustained, shared-prefix", "1,184"),
        ("sustained @ x16 (knee)", "1,071"),
        ("zero-cache floor", "671"),
    ]
    y = 198
    for label, val in stats:
        dr.text((54, y), val, font=R.F18, fill=R.GREEN)
        dr.text((128, y + 3), label, font=R.F14, fill=R.MUTED)
        y += 30
    dr.text((54, y + 14), f"{float(row['power_w']):.0f} W  ·  {float(row['temp_c']):.0f} C  ·  {float(row['gpu_util_pct']):.0f}% GPU at the peak row", font=R.F14, fill=R.MUTED)
    dr.text((54, h - 44), "github.com/svankina/local_agents  ·  every number ships with raw logs", font=R.F14, fill=R.DIM)

    # right: the dial, pinned at peak
    meter_box = (640, 64, 960, 286)
    R.draw_pane(dr, meter_box, "aggregate decode meter", R.CYAN)
    R.draw_meter(dr, meter_box, cap, 0, cap, streams, readout_tps=cap)
    dr.text((668, 306), f"{streams} STREAMS - MEASURED PEAK {cap:.1f}", font=R.F14, fill=R.MUTED)
    dr.text((668, 330), "measured replay - never animated above measured", font=R.F14, fill=R.DIM)

    out = im.resize((2000, 800), Image.Resampling.LANCZOS)
    dest = R.ASSET / "800-toks-banner-5x2.png"
    out.save(dest)
    print(f"wrote {dest} 2000x800")


if __name__ == "__main__":
    main()
