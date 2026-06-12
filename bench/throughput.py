"""Suite T: single-stream prefill/decode + concurrent-stream scaling.

Usage: python3 throughput.py <config-name> [--streams 1 2 4] [--trials 3]
"""

import argparse
import concurrent.futures
import json
import os
import statistics
import sys
import time

from common import chat, parse_timings, wait_healthy

PROMPT_1K = (
    "You are summarizing a design document. "
    + "The system ingests events, deduplicates them, and routes them to workers. " * 60
)
PROMPT_8K = PROMPT_1K * 8


def one(prompt, max_tokens=256):
    body = chat(
        [{"role": "user", "content": prompt + "\nSummarize in detail."}],
        max_tokens=max_tokens,
    )
    t = parse_timings(body)
    t["wall_s"] = body["_wall_s"]
    return t


def default_streams():
    raw = os.environ.get("BENCH_THROUGHPUT_STREAMS")
    if not raw:
        return [1, 2, 4]
    try:
        return [int(part) for part in raw.replace(",", " ").split()]
    except ValueError as exc:
        raise SystemExit(f"invalid BENCH_THROUGHPUT_STREAMS={raw!r}") from exc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--streams", "--levels", type=int, nargs="+", default=default_streams())
    ap.add_argument("--trials", type=int, default=3)
    args = ap.parse_args()
    wait_healthy()
    out = {"config": args.config, "suite": "throughput", "single": {}, "concurrent": {}}
    for label, prompt in [("p1k", PROMPT_1K), ("p8k", PROMPT_8K)]:
        trials = [one(prompt) for _ in range(args.trials)]
        out["single"][label] = {
            "prefill_tps": round(statistics.median(t["prefill_tps"] for t in trials), 1),
            "decode_tps": round(statistics.median(t["decode_tps"] for t in trials), 1),
            "trials": trials,
        }
    for n in args.streams:
        if n == 1:
            continue
        t0 = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(n) as ex:
            rs = list(ex.map(lambda _: one(PROMPT_1K), range(n)))
        wall = time.monotonic() - t0
        total_tok = sum(r["predicted_n"] or 0 for r in rs)
        out["concurrent"][f"x{n}"] = {
            "per_stream_decode_tps": round(statistics.median(r["decode_tps"] for r in rs), 1),
            "aggregate_tps": round(total_tok / wall, 1),
            "wall_s": round(wall, 1),
            "trials": rs,
        }
    json.dump(out, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
