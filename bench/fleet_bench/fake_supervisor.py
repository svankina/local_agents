#!/usr/bin/env python3
"""Fake-Fable supervisor harness: scripted plan/review/fix over a real local worker.

No real supervisor tokens are spent. The "supervisor" is a set of deterministic
templates; its cost is what a real supervisor WOULD have emitted, counted with the
serving engine's own /tokenize endpoint. The worker is a real local model.

Loop per item: plan -> exec -> verify -> (fix -> exec -> verify)*FIX_CAP.
Format adherence is strict: a submission wrapped in markdown fences or prose fails
strict verification and costs a fix round, exactly like a real supervisor having to
correct it. We also record whether a lenient parse would have passed, so format
violations and logic failures are separable.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import pathlib
import re
import sys
import threading
import time
import urllib.request
from typing import Any

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from families import pure_fn  # noqa: E402

BASE = "http://127.0.0.1:8091/v1"
MODEL = "C18-qwen3-30b-vllm"
FIX_CAP = 2

_tok_lock = threading.Lock()
_tok_cache: dict[str, int] = {}


def _post(path: str, payload: dict, timeout: int = 900) -> dict:
    req = urllib.request.Request(
        BASE.rstrip("/v1") + path if path.startswith("/tokenize") else BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def count_tokens(text: str) -> int:
    with _tok_lock:
        if text in _tok_cache:
            return _tok_cache[text]
    try:
        n = _post("/tokenize", {"model": MODEL, "prompt": text})["count"]
    except Exception:  # noqa: BLE001 - fall back to a chars/4 estimate
        n = max(1, len(text) // 4)
    with _tok_lock:
        _tok_cache[text] = n
    return n


# ---------------------------------------------------------------------------
# The fake supervisor: plan styles and fix templates
# ---------------------------------------------------------------------------

def plan_terse(item: dict) -> str:
    first = item["docstring"].splitlines()[0]
    return f"Implement {item['signature']} {first} Code only."


def plan_medium(item: dict) -> str:
    return (
        f"Implement this Python function.\n\n{item['signature']}\n"
        f'    """{item["docstring"]}"""\n\n'
        "Output only the function definition. No markdown fences, no explanation."
    )


def plan_detailed(item: dict) -> str:
    ex = "\n".join(
        f"  {item['fn_name']}({', '.join(repr(a) for a in e['args'])}) == {e['returns']!r}"
        for e in item["examples"]
    )
    return (
        f"Implement this Python function.\n\n{item['signature']}\n"
        f'    """{item["docstring"]}"""\n\n'
        f"Examples:\n{ex}\n\n"
        "Constraints:\n"
        f"- Define exactly one function named {item['fn_name']} with the signature above.\n"
        "- Use no imports; standard builtins only.\n"
        "- Handle edge cases (empty inputs, single elements).\n"
        "- Output ONLY the function definition: no markdown fences, no prose, no tests.\n"
    )


PLAN_STYLES = {"terse": plan_terse, "medium": plan_medium, "detailed": plan_detailed}


def fix_message(item: dict, verdict: dict) -> str:
    check = verdict.get("failed_check")
    if check == "format":
        return (
            "Your last reply was not bare code. Resend ONLY the function definition "
            f"for {item['fn_name']} - no markdown fences, no explanation, code only."
        )
    reason = (verdict.get("reason") or "")[:400]
    return (
        f"Your {item['fn_name']} failed verification: {check}: {reason}\n"
        "Fix the function. Output only the corrected function definition, "
        "no fences, no explanation."
    )


# ---------------------------------------------------------------------------
# Strict parsing: violations are data
# ---------------------------------------------------------------------------

FENCE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def analyze_reply(text: str, fn_name: str) -> dict[str, Any]:
    """Classify format violations and produce strict + lenient source."""
    out: dict[str, Any] = {"violations": [], "strict_source": text, "lenient_source": text}
    t = text.strip()
    if "<think>" in t or "</think>" in t:
        out["violations"].append("thinking-leak")
        t = re.sub(r"<think>.*?</think>", "", t, flags=re.DOTALL).strip()
    m = FENCE_RE.search(t)
    if "```" in t:
        out["violations"].append("fence")
        out["lenient_source"] = (m.group(1) if m else t.replace("```python", "").replace("```", "")).strip()
        pre = t[: t.index("```")].strip()
        if pre:
            out["violations"].append("prose")
    else:
        lines = t.splitlines()
        first_code = next((i for i, ln in enumerate(lines) if ln.startswith(("def ", "@"))), None)
        if first_code is None:
            out["violations"].append("no-def")
        elif first_code > 0:
            out["violations"].append("prose")
            out["lenient_source"] = "\n".join(lines[first_code:])
    out["strict_source"] = t
    return out


def verify(item: dict, reply: str) -> tuple[dict, dict]:
    """Returns (strict_verdict, analysis). Format violations fail strict."""
    a = analyze_reply(reply, item["fn_name"])
    if a["violations"]:
        strict = {"passed": False, "failed_check": "format",
                  "reason": ",".join(a["violations"])}
    else:
        strict = pure_fn.verify_submission(item, a["strict_source"])
    a["lenient_verdict"] = pure_fn.verify_submission(item, a["lenient_source"])
    return strict, a


# ---------------------------------------------------------------------------
# Worker call + supervised episode
# ---------------------------------------------------------------------------

THINKING = True  # qwen3 reasoning toggle (vLLM chat_template_kwargs)


def call_worker(messages: list[dict], temperature: float, seed: int,
                max_tokens: int = 3072) -> dict:
    t0 = time.time()
    payload = {
        "model": MODEL, "messages": messages, "temperature": temperature,
        "seed": seed, "max_tokens": max_tokens,
    }
    if not THINKING:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    r = _post("/chat/completions", payload)
    wall = time.time() - t0
    msg = r["choices"][0]["message"]
    return {
        "text": msg.get("content") or "",
        "usage": r.get("usage", {}),
        "wall_s": wall,
        "finish": r["choices"][0].get("finish_reason"),
    }


def run_episode(item: dict, style: str, temperature: float, seed: int,
                fix_cap: int = FIX_CAP) -> dict:
    """One supervised task: plan -> exec -> verify -> fix rounds. Returns full record."""
    plan = PLAN_STYLES[style](item)
    sup_tokens = count_tokens(plan)
    messages = [{"role": "user", "content": plan}]
    rounds, worker_out, worker_wall = [], 0, 0.0
    passed = False
    for rnd in range(fix_cap + 1):
        w = call_worker(messages, temperature, seed + rnd * 1000)
        worker_out += w["usage"].get("completion_tokens", 0)
        worker_wall += w["wall_s"]
        strict, analysis = verify(item, w["text"])
        rounds.append({
            "round": rnd,
            "strict": strict,
            "lenient_passed": analysis["lenient_verdict"]["passed"],
            "violations": analysis["violations"],
            "completion_tokens": w["usage"].get("completion_tokens", 0),
            "finish": w["finish"],
        })
        if strict["passed"]:
            passed = True
            break
        if rnd < fix_cap:
            fix = fix_message(item, strict)
            sup_tokens += count_tokens(fix)
            messages.append({"role": "assistant", "content": w["text"]})
            messages.append({"role": "user", "content": fix})
    return {
        "item": item["id"], "style": style, "temperature": temperature, "seed": seed,
        "passed": passed, "rounds_used": len(rounds),
        "first_pass": rounds[0]["strict"]["passed"],
        "first_lenient": rounds[0]["lenient_passed"],
        "violations_r0": rounds[0]["violations"],
        "supervisor_tokens": sup_tokens,
        "worker_completion_tokens": worker_out,
        "worker_wall_s": round(worker_wall, 2),
        "rounds": rounds,
    }


# ---------------------------------------------------------------------------
# Experiment driver: run a grid of episodes at fixed concurrency
# ---------------------------------------------------------------------------

def run_grid(episodes: list[dict], concurrency: int, out_path: pathlib.Path) -> list[dict]:
    results: list[dict] = []
    t0 = time.time()
    done = 0
    lock = threading.Lock()

    def one(ep: dict) -> dict:
        rec = run_episode(**ep)
        nonlocal done
        with lock:
            done += 1
            if done % 10 == 0:
                print(f"  {done}/{len(episodes)} episodes, {time.time()-t0:.0f}s", flush=True)
        return rec

    with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futs = [pool.submit(one, ep) for ep in episodes]
        for f in cf.as_completed(futs):
            results.append(f.result())
    wall = time.time() - t0
    payload = {"wall_s": round(wall, 1), "concurrency": concurrency,
               "n_episodes": len(episodes), "results": results}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=1))
    print(f"wrote {out_path} ({len(results)} episodes in {wall:.0f}s)")
    return results


def summarize(results: list[dict], by: str = "style") -> dict:
    groups: dict[str, list[dict]] = {}
    for r in results:
        groups.setdefault(str(r[by]), []).append(r)
    out = {}
    for k, rs in sorted(groups.items()):
        n = len(rs)
        comp = [r for r in rs if r["passed"]]
        out[k] = {
            "n": n,
            "completed": len(comp),
            "first_pass_rate": round(sum(r["first_pass"] for r in rs) / n, 3),
            "first_lenient_rate": round(sum(r["first_lenient"] for r in rs) / n, 3),
            "mean_rounds": round(sum(r["rounds_used"] for r in rs) / n, 2),
            "sup_tokens_per_completed": round(sum(r["supervisor_tokens"] for r in rs) / max(1, len(comp)), 1),
            "worker_tokens_mean": round(sum(r["worker_completion_tokens"] for r in rs) / n, 1),
            "violations_r0": _tally(v for r in rs for v in r["violations_r0"]),
        }
    return out


def _tally(it) -> dict[str, int]:
    d: dict[str, int] = {}
    for v in it:
        d[v] = d.get(v, 0) + 1
    return d


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="single episode sanity check")
    args = ap.parse_args()
    if args.smoke:
        item = pure_fn.build_items()[0]
        rec = run_episode(item, "medium", 0.2, 1)
        print(json.dumps(rec, indent=2))
