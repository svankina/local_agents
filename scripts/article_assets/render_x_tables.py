#!/usr/bin/env python3
"""X-article cards: phosphor-styled PNGs for content X can't render.

X Articles have no tables or code blocks, and X re-encodes uploaded images down
to ~900 px wide, then shows them at ~600 px in the column. So these cards are
authored at a 900 px logical width with large type, rendered at 2x and
downscaled, so the text stays readable after X squeezes them. All numbers are
the measured values already committed in the markdown article.
"""
import pathlib
import sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import render_800_toks_assets as R  # noqa: E402

SCALE = 2          # supersample, then downscale to W for crisp text
W = 900            # logical width — matches X's stored-image cap

# larger type than the demo HUD: these get downscaled by X, so oversize them
FT = lambda px: ImageFont.truetype(R.FONT_REGULAR, px)   # noqa: E731
FB = lambda px: ImageFont.truetype(R.FONT_BOLD, px)      # noqa: E731
TITLE = FB(30)
HEAD = FT(22)
CELL = FT(26)
CELLB = FB(26)
LEVER = FB(26)
WHY = FT(20)
WIN = FB(24)
FOOT = FT(19)

G, Y, C, M, T, D, BG = R.GREEN, R.YELLOW, R.CYAN, R.MUTED, R.TEXT, R.DIM, R.BG


def scanlines(dr, w, h):
    for y in range(0, h, 5):
        dr.line([0, y, w, y], fill="#0b1220", width=1)


def wrap(dr, text, font, max_w):
    words, lines, cur = text.split(" "), [], ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if dr.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def save(im, name):
    big = im.resize((im.width * SCALE, im.height * SCALE), Image.Resampling.LANCZOS) \
        if False else im
    dest = R.ASSET / name
    big.save(dest)
    print("wrote", dest, f"{big.width}x{big.height}")


def render(draw_fn, height_fn):
    """Render at 2x then downscale to W for anti-aliased text."""
    # first pass to measure height at logical scale
    probe = Image.new("RGB", (W, 4000), BG)
    pd = ImageDraw.Draw(probe)
    h = height_fn(pd)
    im = Image.new("RGB", (W * SCALE, h * SCALE), BG)
    dr = ImageDraw.Draw(im)
    dr.SC = SCALE
    draw_fn(dr, h)
    return im.resize((W, h), Image.Resampling.LANCZOS)


def grid_card(title, col_x, aligns, rows, accents=None, footnote=None):
    accents = accents or {}
    pad, title_h, head_h, rh = 26, 56, 50, 50

    def height(_pd):
        return title_h + head_h + rh * (len(rows) - 1) + pad + (40 if footnote else 0)

    def draw(dr, h):
        s = SCALE
        scanlines(dr, W * s, h * s)
        dr.rectangle([0, 0, W * s, 5 * s], fill=G)
        dr.text((pad * s, 16 * s), title, font=TITLE, fill=C)
        y = title_h + 6
        for ri, row in enumerate(rows):
            head = ri == 0
            if not head and ri % 2 == 0:
                dr.rectangle([pad // 2 * s, (y - 6) * s, (W - pad // 2) * s, (y + rh - 12) * s], fill="#0d1520")
            for ci, cell in enumerate(row):
                color = accents.get((ri, ci), M if head else T)
                font = HEAD if head else (CELLB if accents.get((ri, ci)) else CELL)
                tw = dr.textlength(cell, font=font)
                xc = col_x[ci]
                x = xc if aligns[ci] == "l" else xc - tw
                dr.text((x * s, y * s), cell, font=font, fill=color)
            y += head_h - 6 if head else rh
            if head:
                dr.line([pad * s, (y - 10) * s, (W - pad) * s, (y - 10) * s], fill="#22d3ee55", width=2 * s)
        if footnote:
            dr.text((pad * s, (h - 32) * s), footnote, font=FOOT, fill=D)

    return render(draw, height)


def list_card(title, items, footnote=None):
    """Each item: lever (bold) / why (muted, wrapped) / -> measured (green, wrapped)."""
    pad, title_h = 26, 60
    inner = W - pad * 2

    def layout(pd):
        y = title_h
        spans = []
        for lever, why, win in items:
            top = y
            y += 34
            wl = wrap(pd, why, WHY, inner - 16)
            y += 26 * len(wl)
            ml = wrap(pd, "→ " + win, WIN, inner - 16)
            y += 30 * len(ml)
            y += 16  # gap
            spans.append((top, lever, wl, ml))
        return y, spans

    def height(pd):
        return layout(pd)[0] + (44 if footnote else 0)

    def draw(dr, h):
        s = SCALE
        scanlines(dr, W * s, h * s)
        dr.rectangle([0, 0, W * s, 5 * s], fill=G)
        dr.text((pad * s, 18 * s), title, font=TITLE, fill=C)
        # re-layout against a real measurer
        _, spans = layout(dr)
        for i, (top, lever, wl, ml) in enumerate(spans):
            if i:
                dr.line([pad * s, (top - 10) * s, (W - pad) * s, (top - 10) * s], fill="#1e293b", width=s)
            y = top
            dr.text((pad * s, y * s), lever, font=LEVER, fill=C)
            y += 34
            for ln in wl:
                dr.text(((pad + 8) * s, y * s), ln, font=WHY, fill=M)
                y += 26
            for j, ln in enumerate(ml):
                dr.text(((pad + 8) * s, y * s), ln, font=WIN, fill=G)
                y += 30
        if footnote:
            dr.text((pad * s, (h - 34) * s), footnote, font=FOOT, fill=D)

    return render(draw, height)


def main():
    # WINS — stacked list, all three columns kept, readable at 900 px
    save(list_card(
        "what gave the wins",
        [
            ("vLLM continuous batching", "independent requests become one saturated decode engine",
             "1.27x (llama.cpp slots) → 4.40x @x8, 5.8x @x16"),
            ("Qwen3-30B-A3B GPTQ-Int4", "15.77 GiB of weights, room left for batched KV cache",
             "the only 30B-class quant that loaded"),
            ("gptq_marlin", "keeps the MoE int4 path fast on a 24 GB card",
             "183.8 tok/s single-stream"),
            ("--max-num-seqs 16", "exposes the real throughput tier instead of queueing in the client",
             "x8: 808.7 → x16: 1,071 tok/s"),
            ("--max-model-len 16384", "enough worker context without drowning the card in KV",
             "32K OOMed; 16K loads with 56,080 KV tokens"),
            ("no speculative decoding", "leaves batching headroom for the live streams",
             "spec cost −34% aggregate at x4"),
            ("--tool-call-parser hermes", "turns Qwen's JSON tool calls into OpenAI tool_calls",
             "0 → 35/36 parsed tool calls"),
            ("--reasoning-parser qwen3", "separates thinking from visible content",
             "blank probes → clean answers"),
        ],
        footnote="Loaded VRAM 22,173 MiB · 55–56k GPU KV-cache tokens",
    ), "x-card-wins.png")

    # FIRST NUMBER — numeric grid
    save(grid_card(
        "client-measured at the original --max-num-seqs 8",
        col_x=[40, 470, 640, 860],
        aligns=["l", "r", "r", "r"],
        rows=[
            ["streams", "aggregate tok/s", "scaling", "per-stream"],
            ["1", "183.8", "—", "183.8"],
            ["2", "309.8", "1.69x", "155.4"],
            ["4", "534.4", "2.91x", "133.9"],
            ["8", "808.7", "4.40x", "101.3"],
        ],
        accents={(4, 1): G},
    ), "x-card-first-number.png")

    # SWEEP — numeric grid
    save(grid_card(
        "the concurrency sweep — counter-measured",
        col_x=[40, 430, 620, 860],
        aligns=["l", "r", "r", "r"],
        rows=[
            ["streams", "sustained tok/s", "per-stream", "marginal"],
            ["8", "730.8", "91.3", "—"],
            ["10", "688.7", "68.9", "negative"],
            ["12", "796.7", "66.4", "+7.8%"],
            ["16", "1,071.3", "67.0", "+8.6%"],
            ["24", "1,184.0", "49.3", "+1.3%"],
        ],
        accents={(2, 3): Y, (4, 1): G, (5, 1): G},
        footnote="10 < 8: batches pad to captured CUDA-graph sizes [1,2,4,8,16,24,32] — ghost slots",
    ), "x-card-sweep.png")

    # SERVE — terminal card, bigger type
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
    code = FT(20)
    pad, lh, top = 22, 30, 52
    h = top + lh * len(lines) + pad
    im = Image.new("RGB", (W * SCALE, h * SCALE), "#04070c")
    dr = ImageDraw.Draw(im)
    for y in range(0, h * SCALE, 5 * SCALE):
        dr.line([0, y, W * SCALE, y], fill="#070d16", width=1)
    dr.rectangle([0, 0, W * SCALE, 40 * SCALE], fill="#0b1220")
    for i, c in enumerate(("#f87171", "#fbbf24", "#34d399")):
        dr.ellipse([(16 + i * 26) * SCALE, 13 * SCALE, (30 + i * 26) * SCALE, 27 * SCALE], fill=c)
    dr.text((100 * SCALE, 11 * SCALE), "reproduce it — vLLM 0.22.1", font=HEAD, fill=M)
    y = top
    for i, line in enumerate(lines):
        dr.text((pad * SCALE, y * SCALE), line, font=code, fill=G if i == 0 else T)
        y += lh
    save(im.resize((W, h), Image.Resampling.LANCZOS), "x-card-serve.png")


if __name__ == "__main__":
    main()
