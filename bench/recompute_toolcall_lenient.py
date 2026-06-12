"""Recompute strict and lenient toolcall rates from saved trial records."""

import argparse
import json
import pathlib

from common import lenient_toolcall_ok


def recompute(raw_root):
    out = {}
    for path in sorted(raw_root.glob("*/toolcall*.json")):
        suite = json.loads(path.read_text())
        config = suite["config"]
        out.setdefault(config, {})
        for temp, temp_data in sorted(suite.get("temps", {}).items(), key=lambda item: float(item[0])):
            results = temp_data["results"]
            n = len(results)
            strict_passes = sum(1 for row in results if row["ok"])
            forgiven = sum(
                1 for row in results if not row["ok"] and lenient_toolcall_ok(row["ok"], row["why"])
            )
            residual_failures = [
                row["why"]
                for row in results
                if not row["ok"] and not lenient_toolcall_ok(row["ok"], row["why"])
            ]
            out[config][temp] = {
                "strict": round(strict_passes / n, 3),
                "lenient": round((strict_passes + forgiven) / n, 3),
                "n": n,
                "forgiven_count": forgiven,
                "residual_failures": residual_failures,
            }
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=pathlib.Path, default=pathlib.Path("results/raw"))
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("results/toolcall_lenient.json"))
    args = parser.parse_args()

    args.output.write_text(json.dumps(recompute(args.raw_root), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
