#!/usr/bin/env python3
"""Fake-supervisor experiment battery. Each experiment targets a 5-10 min run."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import fake_supervisor as fs  # noqa: E402
from families import pure_fn  # noqa: E402

ROOT = SCRIPT_DIR.parent.parent
OUT = ROOT / "results" / "experiments" / "fable-fleet-bench"
ITEMS = pure_fn.build_items()
SEEDS = (11, 22, 33)
CONCURRENCY = 16


def e1_terseness(run_dir: pathlib.Path) -> None:
    """Plan terseness vs outcome: does instruction detail buy first-pass rate,
    and is the extra supervisor spend worth it?"""
    eps = [
        {"item": it, "style": style, "temperature": 0.2, "seed": s}
        for style in ("terse", "medium", "detailed")
        for it in ITEMS
        for s in SEEDS
    ]
    results = fs.run_grid(eps, CONCURRENCY, run_dir / "episodes.json")
    summary = fs.summarize(results, by="style")
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


def e3_fix_informativeness(run_dir: pathlib.Path) -> None:
    """Fix-message quality vs repair rate: when the worker fails, does a fix that
    quotes the failing case repair better than a bare 'wrong, try again' - and is
    the extra fix verbosity worth its supervisor tokens?"""
    minimal_fix = lambda item, verdict: (  # noqa: E731
        f"Your {item['fn_name']} is wrong. Fix it. Output only the corrected "
        "function definition, no fences, no explanation."
    )
    fs.THINKING = False  # abundant clean logic failures, fast episodes
    eps = []
    for fix_name, fix_fn in (("informative", fs.fix_message), ("minimal", minimal_fix)):
        for it in ITEMS:
            for s in (*SEEDS, 44, 55, 66):  # 6 seeds: more r0 failures to repair
                eps.append({"item": it, "style": "medium", "temperature": 0.2,
                            "seed": s, "_fix": (fix_name, fix_fn)})
    # run with per-episode fix function
    orig = fs.fix_message
    results = []
    import concurrent.futures as cf
    import threading
    lock = threading.Lock()
    t0 = time.time()

    def one(ep):
        fix_name, fix_fn = ep.pop("_fix")
        # fix_message is module-global; pass through a thread-local wrapper instead
        rec = run_episode_with_fix(ep, fix_fn)
        rec["fix_style"] = fix_name
        return rec

    def run_episode_with_fix(ep, fix_fn):
        item, style, temperature, seed = ep["item"], ep["style"], ep["temperature"], ep["seed"]
        plan = fs.PLAN_STYLES[style](item)
        sup = fs.count_tokens(plan)
        messages = [{"role": "user", "content": plan}]
        rounds, passed, wtok = [], False, 0
        for rnd in range(fs.FIX_CAP + 1):
            w = fs.call_worker(messages, temperature, seed + rnd * 1000)
            wtok += w["usage"].get("completion_tokens", 0)
            strict, analysis = fs.verify(item, w["text"])
            rounds.append({"round": rnd, "strict": strict,
                           "violations": analysis["violations"],
                           "lenient_passed": analysis["lenient_verdict"]["passed"]})
            if strict["passed"]:
                passed = True
                break
            if rnd < fs.FIX_CAP:
                fixmsg = fix_fn(item, strict)
                sup += fs.count_tokens(fixmsg)
                messages.append({"role": "assistant", "content": w["text"]})
                messages.append({"role": "user", "content": fixmsg})
        return {"item": item["id"], "style": style, "temperature": temperature,
                "seed": seed, "passed": passed, "rounds_used": len(rounds),
                "first_pass": rounds[0]["strict"]["passed"],
                "first_lenient": rounds[0]["lenient_passed"],
                "violations_r0": rounds[0]["violations"],
                "supervisor_tokens": sup, "worker_completion_tokens": wtok,
                "rounds": rounds}

    done = 0
    with cf.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futs = [pool.submit(one, dict(ep)) for ep in eps]
        for f in cf.as_completed(futs):
            results.append(f.result())
            done += 1
            if done % 10 == 0:
                print(f"  {done}/{len(eps)}, {time.time()-t0:.0f}s", flush=True)
    assert fs.fix_message is orig
    (run_dir / "episodes.json").write_text(json.dumps(
        {"wall_s": round(time.time() - t0, 1), "results": results}, indent=1))
    # summarize repair rate among first-round failures
    summary = {}
    for k in ("informative", "minimal"):
        rs = [r for r in results if r["fix_style"] == k]
        failed_r0 = [r for r in rs if not r["first_pass"]]
        repaired = [r for r in failed_r0 if r["passed"]]
        summary[k] = {
            "n": len(rs),
            "first_pass_rate": round(sum(r["first_pass"] for r in rs) / len(rs), 3),
            "r0_failures": len(failed_r0),
            "repair_rate": round(len(repaired) / max(1, len(failed_r0)), 3),
            "sup_tokens_per_completed": round(
                sum(r["supervisor_tokens"] for r in rs) / max(1, sum(r["passed"] for r in rs)), 1),
        }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


def e4_temperature(run_dir: pathlib.Path) -> None:
    """Temperature vs error rate, single-shot (fix loop off isolates raw errors)."""
    eps = [
        {"item": it, "style": "medium", "temperature": t, "seed": s, "fix_cap": 0}
        for t in (0.0, 0.2, 0.6, 1.0)
        for it in ITEMS
        for s in SEEDS
    ]
    results = fs.run_grid(eps, CONCURRENCY, run_dir / "episodes.json")
    summary = fs.summarize(results, by="temperature")
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


def e2_model_suite(run_dir: pathlib.Path, label: str) -> None:
    """Speed-vs-error suite for the CURRENTLY SERVED model: single-shot over the
    bank, medium style, recording pass rates and measured aggregate tok/s.
    Run once per model (server swapped externally), results merged later."""
    eps = [
        {"item": it, "style": "medium", "temperature": 0.2, "seed": s, "fix_cap": 0}
        for it in ITEMS
        for s in SEEDS * 2  # 6 samples per item for tighter error bars
    ]
    t0 = time.time()
    results = fs.run_grid(eps, CONCURRENCY, run_dir / f"episodes-{label}.json")
    wall = time.time() - t0
    wtok = sum(r["worker_completion_tokens"] for r in results)
    n = len(results)
    summary = {
        "model": label,
        "n": n,
        "strict_pass_rate": round(sum(r["first_pass"] for r in results) / n, 3),
        "lenient_pass_rate": round(sum(r["first_lenient"] for r in results) / n, 3),
        "violations": fs._tally(v for r in results for v in r["violations_r0"]),
        "aggregate_tok_s": round(wtok / wall, 1),
        "wall_s": round(wall, 1),
    }
    (run_dir / f"summary-{label}.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


def e5_thinking(run_dir: pathlib.Path) -> None:
    """Thinking on vs off: the biggest single-model speed lever. Same suite,
    medium style, fix loop ON (supervision cost visible), measuring pass rates,
    tokens, and effective task throughput."""
    out = {}
    for label, thinking in (("thinking-on", True), ("thinking-off", False)):
        fs.THINKING = thinking
        eps = [
            {"item": it, "style": "medium", "temperature": 0.2, "seed": s}
            for it in ITEMS
            for s in SEEDS
        ]
        t0 = time.time()
        results = fs.run_grid(eps, CONCURRENCY, run_dir / f"episodes-{label}.json")
        wall = time.time() - t0
        n = len(results)
        comp = [r for r in results if r["passed"]]
        out[label] = {
            "n": n,
            "completed": len(comp),
            "first_pass_rate": round(sum(r["first_pass"] for r in results) / n, 3),
            "mean_rounds": round(sum(r["rounds_used"] for r in results) / n, 2),
            "sup_tokens_per_completed": round(
                sum(r["supervisor_tokens"] for r in results) / max(1, len(comp)), 1),
            "worker_tokens_mean": round(
                sum(r["worker_completion_tokens"] for r in results) / n, 1),
            "wall_s": round(wall, 1),
            "tasks_per_min": round(60 * n / wall, 1),
            "violations_r0": fs._tally(v for r in results for v in r["violations_r0"]),
        }
    fs.THINKING = True
    (run_dir / "summary.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


EXPERIMENTS = {
    "e1": e1_terseness,
    "e3": e3_fix_informativeness,
    "e4": e4_temperature,
    "e5": e5_thinking,
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("experiment", choices=[*EXPERIMENTS, "e2"])  # e2 swaps servers externally
    ap.add_argument("--label", default=None, help="model label for e2")
    ap.add_argument("--model", default=None, help="override served model name")
    ap.add_argument("--base", default=None, help="override base URL")
    ap.add_argument("--nothink", action="store_true")
    args = ap.parse_args()
    if args.nothink:
        fs.THINKING = False
    if args.model:
        fs.MODEL = args.model
    if args.base:
        fs.BASE = args.base
    stamp = time.strftime("%Y-%m-%d")
    run_dir = OUT / f"{stamp}-{args.experiment}"
    run_dir.mkdir(parents=True, exist_ok=True)
    if args.experiment == "e2":
        e2_model_suite(run_dir, args.label or fs.MODEL)
    else:
        EXPERIMENTS[args.experiment](run_dir)
