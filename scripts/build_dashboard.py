#!/usr/bin/env python3
"""Generate dashboard.html at the repo root from committed result JSONs.

Static, self-contained, no JS dependencies. Rerun after new results land:
    python3 scripts/build_dashboard.py
"""
import html
import json
import pathlib
import subprocess
import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = ROOT / "results"

CONFIG_LABELS = {
    "C1-gemma12b-base": ("Gemma4 12B QAT", "llama.cpp Vulkan"),
    "C2-gemma12b-mtp": ("Gemma4 12B + MTP", "llama.cpp Vulkan"),
    "C3-gemma12b-par3": ("Gemma4 12B ×3 slots", "llama.cpp Vulkan"),
    "C4-gemma26b-gpu": ("Gemma4 26B A4B", "llama.cpp Vulkan"),
    "C5-gemma26b-cmoe": ("26B A4B -cmoe (CPU experts)", "llama.cpp Vulkan"),
    "C6-gemma26b-cmoe-mtp": ("26B A4B -cmoe + MTP", "llama.cpp Vulkan"),
    "C7-qwen27b-q3": ("Qwen3.6-27B Q3", "llama.cpp Vulkan"),
    "C8-nex-mini-q3": ("Nex-N2-mini Q3", "llama.cpp Vulkan"),
    "C12-byteshape-35b": ("byteshape Qwen3.6-35B-A3B ★", "llama.cpp Vulkan + MTP"),
    "C13-qwopus-27b": ("Qwopus3.6-27B-v2 + MTP", "llama.cpp Vulkan"),
    "C14-cuda-35b": ("byteshape 35B-A3B + MTP", "llama.cpp CUDA Docker"),
    "C14-cuda-35b-nospec": ("byteshape 35B-A3B (no spec)", "llama.cpp CUDA Docker"),
    "C16-cuda-baremetal": ("byteshape 35B-A3B + MTP", "llama.cpp CUDA bare metal"),
    "C15-vllm-35b": ("Qwen3.6-35B AWQ (output corrupted)", "vLLM 0.22.1"),
    "C17-north-mini-vllm": ("North Mini Code INT4 (load failed)", "vLLM 0.22.1"),
    "C18-qwen3-30b-vllm": ("Qwen3-30B-A3B GPTQ", "vLLM 0.22.1"),
}

ORDER = list(CONFIG_LABELS)


def fmt(v, nd=1):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{nd}f}".rstrip("0").rstrip(".") if nd else f"{v:.0f}"
    return str(v)


def load(p):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def config_rows():
    lenient = load(R / "toolcall_lenient.json") or {}
    rows = []
    for cfg in ORDER:
        d = load(R / f"{cfg}.json")
        if not d:
            continue
        name, backend = CONFIG_LABELS[cfg]
        err = d.get("error")
        t = (d.get("throughput") or {})
        single = ((t.get("single") or {}).get("p1k") or {}).get("decode_tps")
        conc = t.get("concurrent") or {}
        x4 = (conc.get("x4") or {}).get("aggregate_tps")
        x8 = (conc.get("x8") or {}).get("aggregate_tps")
        tc = sc = ag = None
        temps = (d.get("toolcall") or {}).get("temps") or {}
        if "0.2" in temps:
            tc = temps["0.2"].get("valid_rate")
        len_cfg = (lenient.get(cfg) or {}).get("0.2") or {}
        sc = len_cfg.get("lenient")
        atemps = (d.get("agentic") or {}).get("temps") or {}
        if "0.2" in atemps:
            ag = f'{atemps["0.2"].get("passed")}/{atemps["0.2"].get("of")}'
        vram = d.get("vram_loaded")
        rows.append((name, backend, single, x4, x8, tc, sc, ag, vram, err))
    return rows


def a01():
    rd = R / "experiments/m1-replay/2026-06-12-A-01"
    metrics = load(rd / "metrics.json") or {}
    stream = rd / "logs/claude-stream.jsonl"
    result = None
    if stream.exists():
        for line in stream.open():
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("type") == "result":
                result = e
    return metrics, result


def baseline():
    d = load(R / "experiments/m1-replay/baseline-original-m1.json") or {}
    cu = d.get("cloud_usage") or {}
    return {
        "calendar_span_seconds": d.get("calendar_span_seconds"),
        "estimated_cost_usd": cu.get("usd"),
        "output_tokens": cu.get("output_tokens") or 0,
    }


def build():
    rows_html = ""
    for name, backend, single, x4, x8, tc, sc, ag, vram, err in config_rows():
        if err:
            rows_html += (
                f"<tr class='err'><td>{html.escape(name)}</td><td>{html.escape(backend)}</td>"
                f"<td colspan='6'>did not run: {html.escape(str(err)[:90])}</td></tr>"
            )
            continue
        tc_s = f"{fmt(tc,3)}" + (f" / {fmt(sc,3)}" if sc is not None and sc != tc else "")
        x4_s = fmt(x4)
        if x8:
            x4_s += f" <span class='dim'>({fmt(x8)} @x8)</span>"
        rows_html += (
            f"<tr><td>{html.escape(name)}</td><td class='dim'>{html.escape(backend)}</td>"
            f"<td class='num'>{fmt(single)}</td><td class='num'>{x4_s}</td>"
            f"<td class='num'>{tc_s}</td><td class='num'>{ag or '—'}</td>"
            f"<td class='num'>{html.escape(str(vram or '—'))}</td></tr>"
        )

    metrics, result = a01()
    base = baseline()
    wall = metrics.get("wall_clock_seconds")
    cost = (result or {}).get("total_cost_usd")
    out_tok = ((result or {}).get("usage") or {}).get("output_tokens")
    base_min = base.get("calendar_span_seconds")
    base_cost = base.get("estimated_cost_usd")
    base_out = base.get("output_tokens")
    speedup = (base_min / wall) if (base_min and wall) else None

    gen = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    head_sha = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True).stdout.strip()

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>local_agents — results dashboard</title>
<style>
 :root {{ color-scheme: dark; }}
 body {{ background:#0e1116; color:#dbe2ea; font:15px/1.5 -apple-system,'Segoe UI',Roboto,sans-serif; margin:0; padding:32px 24px 64px; }}
 main {{ max-width:1060px; margin:0 auto; }}
 h1 {{ font-size:24px; margin:0 0 4px; }} h2 {{ font-size:18px; margin:36px 0 10px; color:#9fc2e8; }}
 .sub {{ color:#7d8896; font-size:13px; margin-bottom:24px; }}
 .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin:20px 0; }}
 .card {{ background:#161b23; border:1px solid #232b36; border-radius:10px; padding:14px 16px; }}
 .card .v {{ font-size:26px; font-weight:700; color:#7ee787; }} .card .v.blue {{ color:#79c0ff; }} .card .v.gold {{ color:#e3b341; }}
 .card .l {{ font-size:12px; color:#8b949e; margin-top:2px; }}
 table {{ border-collapse:collapse; width:100%; font-size:13.5px; }}
 th,td {{ padding:6px 10px; text-align:left; border-bottom:1px solid #1d242e; }}
 th {{ color:#8b949e; font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
 td.num {{ font-variant-numeric:tabular-nums; }}
 tr.err td {{ color:#f85149; }}
 .dim {{ color:#7d8896; }}
 a {{ color:#79c0ff; text-decoration:none; }} a:hover {{ text-decoration:underline; }}
 .note {{ font-size:12.5px; color:#7d8896; margin-top:8px; }}
 .badge {{ display:inline-block; padding:1px 8px; border-radius:10px; font-size:11.5px; background:#1f6feb33; color:#79c0ff; margin-left:6px; }}
 .badge.ok {{ background:#23863633; color:#7ee787; }} .badge.tbd {{ background:#9e6a0333; color:#e3b341; }}
</style></head><body><main>
<h1>local_agents — results dashboard</h1>
<div class="sub">RTX 3090 Ti 24 GB · generated {gen} · repo @ {head_sha} ·
 <a href="RESULTS.md">RESULTS.md</a> · <a href="docs/article/2026-06-local-subagent-fleet.md">article draft</a> ·
 <a href="docs/experiments/2026-06-12-m1-replay-local-subagents.md">experiment protocol</a> ·
 <a href="https://github.com/svankina/local_agents">github</a></div>

<div class="cards">
 <div class="card"><div class="v">808.7 t/s</div><div class="l">peak aggregate @x8 — C18 Qwen3-30B-A3B, vLLM (4.40× scaling)</div></div>
 <div class="card"><div class="v blue">143.4 t/s</div><div class="l">fastest single-stream w/ perfect toolcall — byteshape 35B, CUDA</div></div>
 <div class="card"><div class="v blue">1.000</div><div class="l">toolcall, 5/5 agentic — fleet champion C12 (19.3 GB)</div></div>
 <div class="card"><div class="v gold">{fmt(wall/60 if wall else None)} min</div><div class="l">Arm A solo replay (verified green) vs original {fmt(base_min/60 if base_min else None,0)} min — {fmt(speedup)}× faster</div></div>
 <div class="card"><div class="v gold">${fmt(cost,2)}</div><div class="l">Arm A cloud cost vs original ${fmt(base_cost,2)} · output {out_tok:,} vs {base_out:,} tok</div></div>
</div>

<h2>Benchmark scoreboard <span class="badge ok">complete</span></h2>
<table><tr><th>config</th><th>backend</th><th>decode t/s (p1k)</th><th>x4 aggregate t/s</th><th>toolcall strict / lenient</th><th>agentic</th><th>VRAM</th></tr>
{rows_html}</table>
<div class="note">★ fleet champion. Lenient toolcall forgives exactly one failure type (list_dir-before-read, protocol-valid). C18 agentic is the median of a 3-run variance pass (3/5, 1/5, 2/5 — csv-script &amp; add-flag failed every run → throughput tier only). C15 throughput numbers are mechanics-only: output was corrupted (see RESULTS.md). Full caveats in <a href="RESULTS.md">RESULTS.md</a>.</div>

<h2>CAD kernel part 1 build — replay experiment <span class="badge tbd">1 of 9+ runs</span></h2>
<table><tr><th>run</th><th>arm</th><th>wall-clock</th><th>cloud $</th><th>output tokens</th><th>quality</th></tr>
<tr><td class="dim">original build (forensic baseline)</td><td>cloud subagent workflow</td><td class="num">65.6 min</td><td class="num">${fmt(base_cost,2)}</td><td class="num">{base_out:,}</td><td>shipped</td></tr>
<tr><td>2026-06-12-A-01</td><td>A — Fable 5 solo</td><td class="num">{fmt(wall/60 if wall else None)} min</td><td class="num">${fmt(cost,2)}</td><td class="num">{out_tok:,}</td><td>verified: 67 unit + 5 integration green, 9/9 tasks</td></tr>
<tr class="dim"><td>arm B (cloud subagents)</td><td>B</td><td colspan="4">queued</td></tr>
<tr class="dim"><td>arm C (local subagents)</td><td>C</td><td colspan="4">queued — bare-metal serving, worker shim ready</td></tr>
</table>
<div class="note">Arm A split: 88.9% of run time waiting on cloud API (707 s of 795 s), 11.1% local tool execution. GPU stayed idle the whole run (clean cloud-only baseline). Per-run artifacts under <a href="results/experiments/m1-replay/">results/experiments/m1-replay/</a>.</div>

<h2>Showcase fan-out benchmark <span class="badge tbd">designed</span></h2>
<div class="note" style="font-size:13.5px;color:#dbe2ea">32-item docstring backfill on scrapy@a8ffdcf8 across C18's 8-stream vLLM pool — single-shot per item, AST-verified, supervisor limited to 2 cloud calls. Solo-Fable baseline vs fleet. Protocol: <a href="docs/experiments/2026-06-12-showcase-parallel-fanout.md">showcase-parallel-fanout.md</a></div>
</main></body></html>"""
    (ROOT / "dashboard.html").write_text(page)
    print("wrote", ROOT / "dashboard.html")


if __name__ == "__main__":
    build()
