#!/usr/bin/env python3
"""Dispatch 32 fan-out docstring items over an 8-stream local worker pool."""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from fanout_common import DEFAULT_BASE_URL, DEFAULT_MODEL, now_iso, read_json, write_json  # noqa: E402


@dataclass
class Work:
    item: dict[str, Any]
    attempt: int
    feedback: str | None = None


class Dispatcher:
    def __init__(self, args: argparse.Namespace) -> None:
        self.run_dir = pathlib.Path(args.run_dir).resolve()
        self.corpus = pathlib.Path(args.corpus).resolve()
        self.items_dir = pathlib.Path(args.items_dir).resolve()
        self.base_url = args.base_url
        self.model = args.model
        self.concurrency = args.concurrency
        self.timeout_s = args.timeout_s
        self.worker = pathlib.Path(args.worker).resolve()
        self.events_path = self.run_dir / "events.jsonl"
        self.queue: deque[Work] = deque()
        self.results: dict[str, dict[str, Any]] = {}
        self.running: dict[asyncio.Task[dict[str, Any]], Work] = {}
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "workers").mkdir(parents=True, exist_ok=True)

    def event(self, name: str, **fields: Any) -> None:
        row = {"ts": now_iso(), "monotonic_s": time.monotonic(), "event": name, **fields}
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")

    def load_items(self) -> None:
        lock = read_json(self.items_dir / "items.lock.json")
        for item in lock["items"]:
            self.queue.append(Work(item=item, attempt=1))

    async def launch(self, work: Work) -> dict[str, Any]:
        item_id = work.item["id"]
        out = self.run_dir / "workers" / f"{item_id}-attempt-{work.attempt}"
        out.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            str(self.worker),
            "--base-url",
            self.base_url,
            "--model",
            self.model,
            "--item",
            str(self.items_dir / f"{item_id}.json"),
            "--corpus",
            str(self.corpus),
            "--out",
            str(out),
        ]
        if work.feedback:
            cmd.extend(["--feedback", work.feedback])
        self.event("job_start", item_id=item_id, attempt=work.attempt, out=str(out))
        started = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timed_out = False
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_s)
        except asyncio.TimeoutError:
            timed_out = True
            proc.kill()
            stdout, stderr = await proc.communicate()
        elapsed = time.monotonic() - started
        (out / "worker.stdout").write_bytes(stdout)
        (out / "worker.stderr").write_bytes(stderr)
        rc = -9 if timed_out else int(proc.returncode or 0)
        self.event("job_end", item_id=item_id, attempt=work.attempt, rc=rc, timed_out=timed_out, wall_s=elapsed)
        return {"rc": rc, "timed_out": timed_out, "out": out, "wall_s": elapsed}

    def run_check(self, work: Work, attempt_result: dict[str, Any]) -> dict[str, Any]:
        item_id = work.item["id"]
        out = pathlib.Path(attempt_result["out"])
        modified = out / "modified.py"
        verify_path = out / "verify.json"
        if attempt_result["rc"] != 0:
            result = {
                "passed": False,
                "failed_check": "worker",
                "reason": "worker timed out" if attempt_result["timed_out"] else f"worker exited {attempt_result['rc']}",
            }
            write_json(verify_path, result)
            return result

        self.event("command_start", id=f"{item_id}-attempt-{work.attempt}-insert", item_id=item_id, attempt=work.attempt, command="insert_docstrings")
        insert = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "insert_docstrings.py"),
                "--corpus",
                str(self.corpus),
                "--item",
                str(self.items_dir / f"{item_id}.json"),
                "--response",
                str(out / "response.json"),
                "--out",
                str(modified),
            ],
            capture_output=True,
            text=True,
        )
        (out / "insert.stdout").write_text(insert.stdout, encoding="utf-8")
        (out / "insert.stderr").write_text(insert.stderr, encoding="utf-8")
        self.event("command_end", id=f"{item_id}-attempt-{work.attempt}-insert", item_id=item_id, attempt=work.attempt, rc=insert.returncode, command="insert_docstrings")

        self.event("command_start", id=f"{item_id}-attempt-{work.attempt}-verify", item_id=item_id, attempt=work.attempt, command="verify_item")
        verify = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "verify_item.py"),
                "--corpus",
                str(self.corpus),
                "--item",
                str(self.items_dir / f"{item_id}.json"),
                "--modified",
                str(modified),
                "--out",
                str(verify_path),
                "--insertion-rc",
                str(insert.returncode),
            ],
            capture_output=True,
            text=True,
        )
        (out / "verify.stdout").write_text(verify.stdout, encoding="utf-8")
        (out / "verify.stderr").write_text(verify.stderr, encoding="utf-8")
        self.event("command_end", id=f"{item_id}-attempt-{work.attempt}-verify", item_id=item_id, attempt=work.attempt, rc=verify.returncode, command="verify_item")
        if verify_path.exists():
            return read_json(verify_path)
        return {"passed": False, "failed_check": "verify", "reason": f"verify exited {verify.returncode}"}

    def record_attempt(self, work: Work, attempt_result: dict[str, Any], verify: dict[str, Any]) -> None:
        item_id = work.item["id"]
        entry = self.results.setdefault(
            item_id,
            {
                "id": item_id,
                "path": work.item["path"],
                "status": "failed",
                "attempts_used": 0,
                "attempts": [],
            },
        )
        entry["attempts_used"] = max(int(entry["attempts_used"]), work.attempt)
        entry["attempts"].append(
            {
                "attempt": work.attempt,
                "worker_rc": attempt_result["rc"],
                "timed_out": attempt_result["timed_out"],
                "wall_s": attempt_result["wall_s"],
                "passed": bool(verify.get("passed")),
                "failed_check": verify.get("failed_check"),
                "reason": verify.get("reason"),
            }
        )
        if verify.get("passed"):
            entry["status"] = "passed"
            entry["failure_reason"] = None
            self.event("verify_pass", item_id=item_id, attempt=work.attempt)
        else:
            entry["failure_reason"] = verify.get("reason")
            self.event("verify_fail", item_id=item_id, attempt=work.attempt, failed_check=verify.get("failed_check"), reason=verify.get("reason"))

    def enqueue_retry_if_needed(self, work: Work, verify: dict[str, Any]) -> None:
        if verify.get("passed") or work.attempt >= 2:
            return
        reason = str(verify.get("reason") or verify.get("failed_check") or "verification failed")
        self.queue.append(Work(item=work.item, attempt=work.attempt + 1, feedback=reason))
        self.event("retry_enqueued", item_id=work.item["id"], attempt=work.attempt + 1, reason=reason)

    async def run(self) -> int:
        self.load_items()
        self.events_path.write_text("", encoding="utf-8")
        while self.queue or self.running:
            while self.queue and len(self.running) < self.concurrency:
                work = self.queue.popleft()
                task = asyncio.create_task(self.launch(work))
                self.running[task] = work
            if not self.running:
                continue
            done, _pending = await asyncio.wait(self.running.keys(), return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                work = self.running.pop(task)
                attempt_result = task.result()
                verify = self.run_check(work, attempt_result)
                self.record_attempt(work, attempt_result, verify)
                self.enqueue_retry_if_needed(work, verify)
        self.write_scorecard()
        return 0

    def write_scorecard(self) -> None:
        items = [self.results[key] for key in sorted(self.results)]
        passed = sum(1 for item in items if item["status"] == "passed")
        failed = len(items) - passed
        retries = sum(max(0, int(item["attempts_used"]) - 1) for item in items)
        token_totals = self.token_totals()
        scorecard = {
            "schema": "showcase-fanout.scorecard.v1",
            "items_total": len(items),
            "passed": passed,
            "failed": failed,
            "score": f"{passed}/{len(items)}" if items else "0/0",
            "retries": retries,
            "token_totals": token_totals,
            "items": items,
        }
        write_json(self.run_dir / "scorecard.json", scorecard)

    def token_totals(self) -> dict[str, Any]:
        prompt = 0
        completion = 0
        requests = 0
        for path in sorted((self.run_dir / "workers").glob("*/tokens.json")):
            body = read_json(path)
            prompt += int(body.get("prompt_tokens") or 0)
            completion += int(body.get("completion_tokens") or 0)
            requests += len(body.get("requests") or [])
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
            "requests": requests,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run showcase fan-out dispatcher.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--items-dir", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--timeout-s", type=int, default=300)
    parser.add_argument("--worker", default=str(SCRIPT_DIR / "fanout-worker"))
    args = parser.parse_args()
    return asyncio.run(Dispatcher(args).run())


if __name__ == "__main__":
    raise SystemExit(main())
