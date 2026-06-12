#!/usr/bin/env python3
"""Per-model capability profiles from accumulated fleet-bench episodes.

Scans every episodes*.json in results/experiments/fable-fleet-bench/, aggregates
first-attempt pass rate per (model-label, item), and writes:
  capability-matrix.json  - machine-readable profile per model
  capability-matrix.md    - the human table + per-model strengths/weaknesses

Labels: e2/e7 files carry the model in the filename; e1/e3/e4/e5 ran on C18 and
are labeled by their condition so prompting/thinking effects stay visible.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BASE = ROOT / "results" / "experiments" / "fable-fleet-bench"


def label_for(path: pathlib.Path, rec: dict) -> str:
    name = path.name
    if name.startswith("episodes-"):
        return name[len("episodes-"):-len(".json")]
    exp = path.parent.name.split("-")[-1]
    if exp == "e1":
        return f"C18-think (plan={rec.get('style')})"
    if exp == "e4":
        return f"C18-think (temp={rec.get('temperature')})"
    if exp == "e3":
        return "C18-nothink (fixloop)"
    return f"C18-{exp}"


def first_pass(rec: dict) -> bool | None:
    if "first_pass" in rec:
        return bool(rec["first_pass"])
    if "passed" in rec and "rounds_used" in rec:
        return bool(rec["passed"]) and rec["rounds_used"] == 1
    if "passed" in rec:  # e7: single-shot; use lenient for capability (format tracked separately)
        return bool(rec.get("lenient_passed", rec["passed"]))
    return None


def main() -> int:
    cells: dict[str, dict[str, list[bool]]] = {}
    fmt_viol: dict[str, list[int]] = {}
    for f in sorted(BASE.glob("*/episodes*.json")):
        data = json.loads(f.read_text())
        for rec in data.get("results", []):
            if "error" in rec or "item" not in rec:
                continue
            lab = label_for(f, rec)
            fp = first_pass(rec)
            if fp is None:
                continue
            item = rec["item"].split("/")[-1]
            cells.setdefault(lab, {}).setdefault(item, []).append(fp)
            v = rec.get("violations_r0", rec.get("violations", []))
            fmt_viol.setdefault(lab, []).append(1 if v else 0)

    items = sorted({i for m in cells.values() for i in m})
    profiles = {}
    for lab, per_item in sorted(cells.items()):
        rates = {i: round(sum(v) / len(v), 2) for i, v in sorted(per_item.items())}
        n = sum(len(v) for v in per_item.values())
        overall = round(sum(sum(v) for v in per_item.values()) / n, 3)
        weak = [i for i, r in rates.items() if r < 0.5]
        strong = [i for i, r in rates.items() if r == 1.0]
        fv = fmt_viol.get(lab, [])
        profiles[lab] = {
            "n_episodes": n,
            "overall_first_pass": overall,
            "format_violation_rate": round(sum(fv) / max(1, len(fv)), 3),
            "per_item": rates,
            "always_solves": strong,
            "struggles_with": weak,
        }

    (BASE / "capability-matrix.json").write_text(json.dumps(
        {"items": items, "profiles": profiles}, indent=2))

    lines = ["# Capability matrix — first-attempt pass rate per item",
             "", "Built from every episodes*.json in this directory. 1.00 = always solves first try.", ""]
    short = {i: i[:14] for i in items}
    lines.append("| model / condition | n | overall | fmt-viol | " + " | ".join(short[i] for i in items) + " |")
    lines.append("|---|---:|---:|---:|" + "---:|" * len(items))
    for lab, p in sorted(profiles.items(), key=lambda kv: -kv[1]["overall_first_pass"]):
        row = [lab, str(p["n_episodes"]), f'{p["overall_first_pass"]:.2f}', f'{p["format_violation_rate"]:.2f}']
        row += [f'{p["per_item"].get(i, float("nan")):.2f}' if i in p["per_item"] else "—" for i in items]
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "## Per-model notes (auto-derived)", ""]
    for lab, p in sorted(profiles.items(), key=lambda kv: -kv[1]["overall_first_pass"]):
        good = ", ".join(p["always_solves"]) or "none"
        bad = ", ".join(p["struggles_with"]) or "none"
        lines.append(f"- **{lab}** ({p['overall_first_pass']:.0%} first-pass, "
                     f"{p['format_violation_rate']:.0%} format violations): "
                     f"always solves: {good}. struggles: {bad}.")
    (BASE / "capability-matrix.md").write_text("\n".join(lines) + "\n")
    print(f"wrote capability-matrix.{{json,md}}: {len(profiles)} profiles x {len(items)} items")
    for lab, p in sorted(profiles.items(), key=lambda kv: -kv[1]["overall_first_pass"]):
        print(f"  {p['overall_first_pass']:.2f} {lab}  (weak: {', '.join(p['struggles_with']) or '-'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
