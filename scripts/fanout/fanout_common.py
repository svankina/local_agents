#!/usr/bin/env python3
"""Shared helpers for the showcase fan-out docstring benchmark."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import pathlib
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


CORPUS_URL = "https://github.com/scrapy/scrapy.git"
PINNED_SHA = "a8ffdcf8517a8973391a14635234b6993b15a86a"
DEFAULT_MODEL = "Qwen/Qwen3-30B-A3B-GPTQ-Int4"
DEFAULT_BASE_URL = "http://127.0.0.1:8091/v1"


@dataclass(frozen=True)
class Target:
    qualname: str
    kind: str
    lineno: int
    col_offset: int
    params: tuple[str, ...]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def repo_head(corpus: pathlib.Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(corpus), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def verify_corpus_head(corpus: pathlib.Path) -> None:
    head = repo_head(corpus)
    if head != PINNED_SHA:
        raise SystemExit(f"corpus HEAD {head} != pinned {PINNED_SHA}")


def generator_git_sha(repo_root: pathlib.Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def public_name(name: str) -> bool:
    return not name.startswith("_")


def params_for(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    args = node.args
    names: list[str] = []
    names.extend(arg.arg for arg in args.posonlyargs)
    names.extend(arg.arg for arg in args.args)
    if args.vararg is not None:
        names.append(args.vararg.arg)
    names.extend(arg.arg for arg in args.kwonlyargs)
    if args.kwarg is not None:
        names.append(args.kwarg.arg)
    return tuple(name for name in names if name not in {"self", "cls"})


def qualname_targets(tree: ast.AST) -> dict[str, Target]:
    targets: dict[str, Target] = {}

    def visit_body(body: Iterable[ast.stmt], stack: list[str]) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qualname = ".".join([*stack, node.name])
                if public_name(node.name) and ast.get_docstring(node, clean=False) is None:
                    if isinstance(node, ast.ClassDef):
                        targets[qualname] = Target(qualname, "class", node.lineno, node.col_offset, ())
                    else:
                        targets[qualname] = Target(
                            qualname,
                            "function",
                            node.lineno,
                            node.col_offset,
                            params_for(node),
                        )
                visit_body(node.body, [*stack, node.name])

    if not isinstance(tree, ast.Module):
        return targets
    visit_body(tree.body, [])
    return targets


def parse_source(source: str, filename: str = "<source>") -> ast.Module:
    return ast.parse(source, filename=filename)


def item_file(corpus: pathlib.Path, item: dict[str, Any]) -> pathlib.Path:
    rel = pathlib.PurePosixPath(item["path"])
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"unsafe item path: {item['path']}")
    path = (corpus / pathlib.Path(*rel.parts)).resolve()
    corpus_resolved = corpus.resolve()
    if path != corpus_resolved and corpus_resolved not in path.parents:
        raise ValueError(f"item path escapes corpus: {item['path']}")
    return path


def strip_docstrings(tree: ast.AST) -> ast.AST:
    class Stripper(ast.NodeTransformer):
        def strip_body(self, node: ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            self.generic_visit(node)
            if node.body and isinstance(node.body[0], ast.Expr):
                value = node.body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    node.body = node.body[1:]
            return node

        def visit_Module(self, node: ast.Module):
            return self.strip_body(node)

        def visit_ClassDef(self, node: ast.ClassDef):
            return self.strip_body(node)

        def visit_FunctionDef(self, node: ast.FunctionDef):
            return self.strip_body(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            return self.strip_body(node)

    return ast.fix_missing_locations(Stripper().visit(copy.deepcopy(tree)))


def sorted_item_paths(items_dir: pathlib.Path) -> list[pathlib.Path]:
    return sorted(items_dir.glob("item-*.json"))


def v1_url(base: str, path: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/v1"):
        return base + path
    return base + "/v1" + path


def extract_json_object(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if not match:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end <= start:
                raise
            parsed = json.loads(text[start : end + 1])
        else:
            parsed = json.loads(match.group(1))
    if not isinstance(parsed, dict):
        raise ValueError("assistant response is not a JSON object")
    docstrings = parsed.get("docstrings")
    if not isinstance(docstrings, dict):
        raise ValueError("assistant response missing docstrings object")
    for key, value in docstrings.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("docstrings must map strings to strings")
    return {"docstrings": docstrings}


def write_tokens(out: pathlib.Path, responses: list[dict[str, Any]]) -> None:
    total_prompt = 0
    total_completion = 0
    requests = []
    for i, body in enumerate(responses, 1):
        usage = body.get("usage") or {}
        prompt = usage.get("prompt_tokens") or 0
        completion = usage.get("completion_tokens") or 0
        total_prompt += prompt
        total_completion += completion
        requests.append(
            {
                "request_index": i,
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "client_wall_s": body.get("_client_wall_s"),
                "timings": body.get("timings") or None,
            }
        )
    write_json(
        out / "tokens.json",
        {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "requests": requests,
        },
    )
