"""Suite A: minimal tool-loop agent. Usage: python3 miniagent.py <config> [--temps 0.2] [--max-turns 15]"""

import argparse
import json
import pathlib
import subprocess
import sys
import time

from common import chat, wait_healthy
from toolcall_suite import TOOLS

SYSTEM = (
    "You are a coding agent working in the current directory. Read TASK.md first, complete the task "
    "using the tools, verify your work, then reply with exactly DONE when finished."
)


def run_tool(name, args, cwd):
    try:
        if name == "read_file":
            return (cwd / args["path"]).read_text()[:8000]
        if name == "write_file":
            p = cwd / args["path"]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"])
            return f"wrote {args['path']}"
        if name == "list_dir":
            return "\n".join(
                sorted(x.name + ("/" if x.is_dir() else "") for x in (cwd / args.get("path", ".")).iterdir())
            )
        if name == "run_bash":
            r = subprocess.run(args["command"], shell=True, cwd=cwd, capture_output=True, text=True, timeout=60)
            return (r.stdout + r.stderr)[:8000] or f"(exit {r.returncode})"
    except Exception as e:
        return f"ERROR: {e}"
    return f"ERROR: unknown tool {name}"


def run_task(task, temp, max_turns):
    bench = pathlib.Path(__file__).parent
    cwd = pathlib.Path(
        subprocess.run(
            [sys.executable, bench / "make_sandbox.py", task["id"]],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    msgs = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "Begin. TASK.md has your task."},
    ]
    t0, turns = time.monotonic(), 0
    for turns in range(1, max_turns + 1):
        body = chat(msgs, tools=TOOLS, temperature=temp, max_tokens=2048)
        msg = body["choices"][0]["message"]
        msgs.append(msg)
        if not msg.get("tool_calls"):
            break
        for tc in msg["tool_calls"]:
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}
            msgs.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id", "0"),
                    "content": run_tool(tc["function"]["name"], args, cwd),
                }
            )
    check = subprocess.run(task["check"], shell=True, cwd=cwd, capture_output=True, text=True)
    return {
        "id": task["id"],
        "passed": check.returncode == 0,
        "turns": turns,
        "wall_s": round(time.monotonic() - t0, 1),
        "check_out": (check.stdout + check.stderr)[-500:],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--temps", type=float, nargs="+", default=[0.2])
    ap.add_argument("--max-turns", type=int, default=15)
    args = ap.parse_args()
    wait_healthy()
    tasks = json.loads((pathlib.Path(__file__).parent / "agentic_tasks.json").read_text())
    out = {"config": args.config, "suite": "agentic", "temps": {}}
    for temp in args.temps:
        rs = [run_task(t, temp, args.max_turns) for t in tasks]
        out["temps"][str(temp)] = {"passed": sum(r["passed"] for r in rs), "of": len(rs), "tasks": rs}
    json.dump(out, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
