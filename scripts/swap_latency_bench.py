#!/usr/bin/env python3
"""Model hot-swap latency benchmark for an ollama fleet on a single GPU.

Measures the penalty of swapping models in/out of VRAM. The headline metric is
ollama's reported `load_duration` (ns) — time from request to model-ready —
plus wall-clock to first response.

Regimes:
  baseline   model already resident -> load_duration ~ 0 (the no-swap floor)
  warm       model unloaded, weights warm in OS page cache -> typical swap-in
  cold       page cache dropped (sudo) -> worst-case swap-in from NVMe
  roundrobin cycle A->B->C->...->A; each request evicts prev & loads next

Usage:
  swap_latency_bench.py warm     --reps 4
  swap_latency_bench.py baseline --reps 4
  swap_latency_bench.py roundrobin --cycles 3
  swap_latency_bench.py cold --models qwen2.5:1.5b,gemma4:12b-it-qat,qwen3_6_35b_a3b_q4km:latest --reps 2
"""
import argparse, json, subprocess, sys, time, urllib.request, os

OLLAMA = "http://localhost:11434"

# (ollama name, human label, disk size GB) sorted small -> large
MODELS = [
    ("qwen2.5:1.5b",                "Qwen2.5 1.5B",        0.99),
    ("granite3.2:2b",               "Granite3.2 2B",       1.5),
    ("qwen2.5:3b",                  "Qwen2.5 3B",          1.9),
    ("phi4-mini:3.8b",              "Phi4-mini 3.8B",      2.5),
    ("gemma4:12b-it-qat",           "Gemma4 12B (QAT)",    7.2),
    ("qwen3.6:27b-q4_K_M",          "Qwen3.6 27B Q4",      17.0),
    ("qwen3_6_35b_a3b_q4km:latest", "Qwen3.6 35B-A3B Q4",  22.0),
]
NAMES = [m[0] for m in MODELS]
LABEL = {m[0]: m[1] for m in MODELS}
SIZE  = {m[0]: m[2] for m in MODELS}


def generate(model, prompt="hi", num_predict=1, keep_alive=None):
    """One /api/generate call; returns parsed JSON + measured wall clock (s)."""
    body = {"model": model, "prompt": prompt, "stream": False,
            "options": {"num_predict": num_predict, "temperature": 0}}
    if keep_alive is not None:
        body["keep_alive"] = keep_alive
    data = json.dumps(body).encode()
    req = urllib.request.Request(OLLAMA + "/api/generate", data=data,
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as r:
        resp = json.loads(r.read())
    wall = time.perf_counter() - t0
    return resp, wall


def stop(model):
    subprocess.run(["ollama", "stop", model], capture_output=True)


def stop_all():
    for n in NAMES:
        stop(n)
    time.sleep(1.0)


def ps():
    try:
        with urllib.request.urlopen(OLLAMA + "/api/ps", timeout=10) as r:
            return json.loads(r.read()).get("models", [])
    except Exception:
        return []


def sample(model, wall, resp, regime, rep):
    return {
        "regime": regime, "rep": rep, "model": model, "label": LABEL.get(model, model),
        "size_gb": SIZE.get(model), "wall_s": round(wall, 4),
        "load_s":        round(resp.get("load_duration", 0) / 1e9, 4),
        "prompt_eval_s": round(resp.get("prompt_eval_duration", 0) / 1e9, 4),
        "eval_s":        round(resp.get("eval_duration", 0) / 1e9, 4),
        "total_s":       round(resp.get("total_duration", 0) / 1e9, 4),
    }


def run_warm(models, reps, out):
    # rep 0 is a discard warm-up that pulls weights into page cache.
    for rep in range(reps + 1):
        for m in models:
            stop_all()
            resp, wall = generate(m)
            s = sample(m, wall, resp, "warm", rep)
            s["warmup"] = (rep == 0)
            out.append(s)
            print(f"  warm   rep{rep} {LABEL[m]:<22} load={s['load_s']:.2f}s wall={s['wall_s']:.2f}s")


def run_baseline(models, reps, out):
    for m in models:
        # load and keep resident, then re-query: second+ calls have ~0 load.
        generate(m, keep_alive="5m")
        for rep in range(reps):
            resp, wall = generate(m, keep_alive="5m")
            out.append(sample(m, wall, resp, "baseline", rep))
            print(f"  base   rep{rep} {LABEL[m]:<22} load={out[-1]['load_s']:.3f}s wall={out[-1]['wall_s']:.3f}s")
        stop(m)


def run_roundrobin(models, cycles, out):
    stop_all()
    seq = models * cycles
    for i, m in enumerate(seq):
        resp, wall = generate(m)  # default keep_alive; next model forces evict+load
        s = sample(m, wall, resp, "roundrobin", i)
        resident = [x.get("name") or x.get("model") for x in ps()]
        s["resident_after"] = resident
        out.append(s)
        print(f"  rr     {i:>2} {LABEL[m]:<22} load={s['load_s']:.2f}s wall={s['wall_s']:.2f}s resident={resident}")


def run_cold(models, reps, out, drop_script):
    for rep in range(reps):
        for m in models:
            stop_all()
            # drop page cache so weights come from NVMe (worst case)
            subprocess.run(["bash", drop_script], capture_output=True)
            time.sleep(0.5)
            resp, wall = generate(m)
            out.append(sample(m, wall, resp, "cold", rep))
            print(f"  cold   rep{rep} {LABEL[m]:<22} load={out[-1]['load_s']:.2f}s wall={out[-1]['wall_s']:.2f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("regime", choices=["warm", "baseline", "roundrobin", "cold"])
    ap.add_argument("--reps", type=int, default=4)
    ap.add_argument("--cycles", type=int, default=3)
    ap.add_argument("--models", default="")
    ap.add_argument("--out", default="results/experiments/model-swap-latency/measurements.jsonl")
    ap.add_argument("--drop-script", default="/tmp/drop_caches.sh")
    args = ap.parse_args()

    models = [s.strip() for s in args.models.split(",") if s.strip()] or NAMES
    out = []
    print(f"== regime={args.regime} models={len(models)} ==")
    if args.regime == "warm":
        run_warm(models, args.reps, out)
    elif args.regime == "baseline":
        run_baseline(models, args.reps, out)
    elif args.regime == "roundrobin":
        run_roundrobin(models, args.cycles, out)
    elif args.regime == "cold":
        run_cold(models, args.reps, out, args.drop_script)

    with open(args.out, "a") as f:
        for s in out:
            f.write(json.dumps(s) + "\n")
    print(f"wrote {len(out)} samples -> {args.out}")


if __name__ == "__main__":
    main()
