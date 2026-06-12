#!/usr/bin/env python3
"""X-article table cards: phosphor-styled PNGs for content X can't render.

X Articles have no tables or code blocks; these cards carry them in the same
instrument aesthetic as the banner and demo gif. All numbers are the measured
values already committed in the markdown article.
"""
import pathlib
import sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from PIL import Image, ImageDraw  # noqa: E402

import render_800_toks_assets as R  # noqa: E402

SCALE = 2  # supersample for crisp text


def card(title: str, col_widths: list[int], rows: list[list[str]], accents: dict[tuple[int, int], str] | None = None,
         footnote: str | None = None) -> Image.Image:
    accents = accents or {}
    pad, rh, head_h, title_h = 28, 38, 44, 56
    w = sum(col_widths) + pad * 2
    body_end = title_h + 8 + (head_h - 10) + rh * (len(rows) - 1)
    h = body_end + pad + (34 if footnote else 0)
    im = Image.new("RGB", (w, h), R.BG)
    dr = ImageDraw.Draw(im)
    for y in range(0, h, 4):
        dr.line([0, y, w, y], fill="#0b1220", width=1)
    dr.rectangle([0, 0, w, 4], fill=R.GREEN)
    dr.text((pad, 18), title, font=R.F18, fill=R.CYAN)

    y = title_h + 8
    for ri, row in enumerate(rows):
        x = pad
        is_head = ri == 0
        if not is_head and ri % 2 == 0:
            dr.rectangle([pad // 2, y - 6, w - pad // 2, y + rh - 12], fill="#0d1520")
        for ci, cell in enumerate(row):
            color = accents.get((ri, ci), R.MUTED if is_head else R.TEXT)
            font = R.F14 if is_head else R.F15
            dr.text((x, y), cell, font=font, fill=color)
            x += col_widths[ci]
        y += head_h - 10 if is_head else rh
        if is_head:
            dr.line([pad, y - 8, w - pad, y - 8], fill="#22d3ee44", width=2)
    if footnote:
        dr.text((pad, h - 34), footnote, font=R.F14, fill=R.DIM)
    return im


def save(im: Image.Image, name: str) -> None:
    big = im.resize((im.width * SCALE, im.height * SCALE), Image.Resampling.LANCZOS)
    dest = R.ASSET / name
    big.save(dest)
    print("wrote", dest, f"{big.width}x{big.height}")


def main() -> None:
    G, Y = R.GREEN, R.YELLOW

    save(card(
        "what gave the wins",
        [340, 560, 540],
        [
            ["lever", "why it mattered", "measured"],
            ["vLLM continuous batching", "independent requests, one decode engine", "1.27x (llama.cpp) -> 4.40x @x8, 5.8x @x16"],
            ["Qwen3-30B-A3B GPTQ-Int4", "15.77 GiB weights, room for batched KV", "the only 30B-class quant that loaded"],
            ["gptq_marlin", "fast MoE int4 path on a 24 GB card", "183.8 tok/s single-stream"],
            ["--max-num-seqs 16", "exposes the real throughput tier", "x8: 808.7 -> x16: 1,071 tok/s"],
            ["--max-model-len 16384", "worker context without drowning KV", "32K OOMed; 16K loads, 56k KV tokens"],
            ["no speculative decoding", "leaves headroom for live streams", "spec cost -34% aggregate at x4"],
            ["--tool-call-parser hermes", "Qwen JSON -> OpenAI tool_calls", "0 -> 35/36 parsed tool calls"],
            ["--reasoning-parser qwen3", "thinking separated from content", "blank probes -> clean answers"],
        ],
        accents={(1, 2): G, (4, 2): G, (7, 2): G},
    ), "x-card-wins.png")

    save(card(
        "client-measured at the original --max-num-seqs 8 shape",
        [220, 320, 240, 320],
        [
            ["streams", "aggregate tok/s", "scaling", "per-stream tok/s"],
            ["1", "183.8", "-", "183.8"],
            ["2", "309.8", "1.69x", "155.4"],
            ["4", "534.4", "2.91x", "133.9"],
            ["8", "808.7", "4.40x", "101.3"],
        ],
        accents={(4, 1): G},
    ), "x-card-first-number.png")

    save(card(
        "the concurrency sweep - same server, counter-measured",
        [220, 340, 300, 420],
        [
            ["streams", "sustained tok/s", "per-stream", "marginal per stream"],
            ["8", "730.8", "91.3", "-"],
            ["10", "688.7", "68.9", "negative"],
            ["12", "796.7", "66.4", "+7.8%"],
            ["16", "1,071.3", "67.0", "+8.6%"],
            ["24", "1,184.0", "49.3", "+1.3%"],
        ],
        accents={(2, 3): Y, (4, 1): G, (5, 1): G},
        footnote="10 streams loses to 8: batches pad to captured CUDA-graph sizes [1,2,4,8,16,24,32] - ghost slots",
    ), "x-card-sweep.png")

    # the serve command as a terminal card
    lines = [
        "$ vllm serve Qwen/Qwen3-30B-A3B-GPTQ-Int4 \\",
        "    --revision 9b534e4318b7ebc3c961a839f13eb18b1833f441 \\",
        "    --max-model-len 16384 \\",
        "    --max-num-seqs 16 \\",
        "    --gpu-memory-utilization 0.92 \\",
        "    --quantization gptq_marlin \\",
        "    --enable-auto-tool-choice \\",
        "    --tool-call-parser hermes \\",
        "    --reasoning-parser qwen3",
    ]
    pad, lh = 28, 30
    w, h = 980, 56 + lh * len(lines) + pad
    im = Image.new("RGB", (w, h), "#04070c")
    dr = ImageDraw.Draw(im)
    for y in range(0, h, 4):
        dr.line([0, y, w, y], fill="#070d16", width=1)
    dr.rectangle([0, 0, w, 36], fill="#0b1220")
    for i, c in enumerate(("#f87171", "#fbbf24", "#34d399")):
        dr.ellipse([16 + i * 24, 12, 28 + i * 24, 24], fill=c)
    dr.text((92, 10), "reproduce it - vLLM 0.22.1", font=R.F14, fill=R.MUTED)
    y = 56
    for i, line in enumerate(lines):
        dr.text((pad, y), line, font=R.F15, fill=R.GREEN if i == 0 else R.TEXT)
        y += lh
    save(im, "x-card-serve.png")


if __name__ == "__main__":
    main()
