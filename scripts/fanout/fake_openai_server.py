#!/usr/bin/env python3
"""Tiny OpenAI-compatible fake server for fan-out dispatcher dry runs."""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from fanout_common import parse_source, qualname_targets  # noqa: E402


TARGETS_RE = re.compile(r"^Targets \((\d+)\): (.*)$", re.MULTILINE)
FILE_RE = re.compile(r"<file>\n(.*)\n</file>", re.DOTALL)


def make_docstrings(prompt: str) -> dict[str, str]:
    targets_match = TARGETS_RE.search(prompt)
    source_match = FILE_RE.search(prompt)
    if not targets_match or not source_match:
        return {}
    targets = [part.strip() for part in targets_match.group(2).split(",") if part.strip()]
    source = source_match.group(1)
    meta = qualname_targets(parse_source(source))
    docs: dict[str, str] = {}
    for qualname in targets:
        target = meta.get(qualname)
        if target and target.params:
            mentions = " ".join(f"The {name} parameter is documented for benchmark verification." for name in target.params)
            docs[qualname] = f"Describe the behavior of {qualname}. {mentions}"
        elif target and target.kind == "class":
            docs[qualname] = f"Describe the public behavior and lifecycle of the {qualname} class."
        else:
            docs[qualname] = f"Describe the public behavior of {qualname} for maintainers."
    return docs


class Handler(BaseHTTPRequestHandler):
    server_version = "fanout-fake-openai/1.0"

    def do_GET(self) -> None:
        if self.path.rstrip("/") in {"", "/v1", "/v1/models"}:
            self.write_json({"object": "list", "data": [{"id": "fake-fanout-model"}]})
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or "0")
        payload = json.loads(self.rfile.read(length) or b"{}")
        user = ""
        for message in payload.get("messages") or []:
            if message.get("role") == "user":
                user = message.get("content") or user
        docstrings = make_docstrings(user)
        content = json.dumps({"docstrings": docstrings}, sort_keys=True)
        prompt_tokens = max(1, sum(len((m.get("content") or "")) for m in payload.get("messages") or []) // 4)
        completion_tokens = max(1, len(content) // 4)
        body: dict[str, Any] = {
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "model": payload.get("model") or "fake-fanout-model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
        self.write_json(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def write_json(self, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fake OpenAI server for fan-out dry runs.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18091)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"fake OpenAI server listening on http://{args.host}:{args.port}/v1", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
