"""Suite TC. Usage: python3 toolcall_suite.py <config> [--temps 0.2 0.7] [--trials 3]"""

import argparse
import json
import pathlib
import sys

from common import chat, lenient_toolcall_ok, score_toolcall, tool_calls_of, wait_healthy

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a text file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List directory entries",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Run a shell command and return stdout",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]
SYSTEM = "You are a coding agent. Use the provided tools when a task requires file or shell access. Answer directly when no tool is needed."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--temps", type=float, nargs="+", default=[0.2])
    ap.add_argument("--trials", type=int, default=3)
    args = ap.parse_args()
    wait_healthy()
    cases = json.loads((pathlib.Path(__file__).parent / "toolcall_cases.json").read_text())
    out = {"config": args.config, "suite": "toolcall", "temps": {}}
    for temp in args.temps:
        results, passed, lenient_passed = [], 0, 0
        for case in cases:
            for trial in range(args.trials):
                body = chat(
                    [{"role": "system", "content": SYSTEM}, {"role": "user", "content": case["prompt"]}],
                    tools=TOOLS,
                    temperature=temp,
                    max_tokens=512,
                )
                ok, why = score_toolcall(case, tool_calls_of(body))
                lenient_ok = lenient_toolcall_ok(ok, why)
                passed += ok
                lenient_passed += lenient_ok
                results.append(
                    {"id": case["id"], "trial": trial, "ok": ok, "lenient_ok": lenient_ok, "why": why}
                )
        n = len(cases) * args.trials
        out["temps"][str(temp)] = {
            "valid_rate": round(passed / n, 3),
            "lenient_valid_rate": round(lenient_passed / n, 3),
            "n": n,
            "results": results,
        }
    json.dump(out, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
