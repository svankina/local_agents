#!/usr/bin/env python3
"""Estimate useful output tokens from saved fan-out worker responses."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any


METHOD = "compact_response_json_chars_div_4"
NOTE = "No local Claude tokenizer is available; useful_output_tokens are estimated as compact response.json characters / 4."


def read_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: pathlib.Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / 4)) if text else 0


def compact_response_text(path: pathlib.Path) -> str:
    body = read_json(path)
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def attempt_sort_key(path: pathlib.Path) -> tuple[str, int, str]:
    name = path.parent.name
    item_id = name
    attempt = 0
    if "-attempt-" in name:
        item_id, raw_attempt = name.rsplit("-attempt-", 1)
        try:
            attempt = int(raw_attempt)
        except ValueError:
            attempt = 0
    return item_id, attempt, name


def scorecard_items(run_dir: pathlib.Path) -> dict[str, dict[str, Any]]:
    path = run_dir / "scorecard.json"
    if not path.exists():
        return {}
    scorecard = read_json(path)
    items = scorecard.get("items") or []
    return {item["id"]: item for item in items if isinstance(item, dict) and isinstance(item.get("id"), str)}


def summarize(run_dir: pathlib.Path) -> dict[str, Any]:
    score_items = scorecard_items(run_dir)
    per_item: dict[str, dict[str, Any]] = {}
    attempts: list[dict[str, Any]] = []

    for response_path in sorted((run_dir / "workers").glob("*/response.json"), key=attempt_sort_key):
        item_id, attempt, attempt_dir = attempt_sort_key(response_path)
        compact = compact_response_text(response_path)
        chars = len(compact)
        tokens = estimate_tokens(compact)
        attempts.append(
            {
                "item_id": item_id,
                "attempt": attempt,
                "attempt_dir": attempt_dir,
                "response_chars": chars,
                "useful_output_tokens": tokens,
            }
        )
        item = per_item.setdefault(
            item_id,
            {
                "item_id": item_id,
                "status": (score_items.get(item_id) or {}).get("status"),
                "attempts": 0,
                "response_chars": 0,
                "useful_output_tokens": 0,
            },
        )
        item["attempts"] += 1
        item["response_chars"] += chars
        item["useful_output_tokens"] += tokens

    total_chars = sum(int(item["response_chars"]) for item in per_item.values())
    total_tokens = sum(int(item["useful_output_tokens"]) for item in per_item.values())
    scorecard = read_json(run_dir / "scorecard.json") if (run_dir / "scorecard.json").exists() else {}
    billed_output = (scorecard.get("token_totals") or {}).get("completion_tokens")

    return {
        "schema": "showcase-fanout.useful-output-summary.v1",
        "run_id": run_dir.name,
        "method": METHOD,
        "estimate_note": NOTE,
        "billed_output_tokens": billed_output,
        "useful_output_tokens": total_tokens,
        "response_chars": total_chars,
        "items_with_response": len(per_item),
        "attempts_with_response": len(attempts),
        "items": [per_item[key] for key in sorted(per_item)],
        "attempts": attempts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Write useful-output-summary.json for a showcase fan-out run.")
    parser.add_argument("run_dir", type=pathlib.Path)
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    if not (run_dir / "workers").is_dir():
        raise SystemExit(f"workers directory not found: {run_dir / 'workers'}")

    summary = summarize(run_dir)
    out = run_dir / "useful-output-summary.json"
    write_json(out, summary)
    print(
        f"{out}: useful_output_tokens={summary['useful_output_tokens']} "
        f"method={summary['method']} ({summary['estimate_note']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
