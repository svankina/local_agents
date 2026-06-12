#!/usr/bin/env python3
"""Verify one scratch-modified fan-out item without model judgment."""

from __future__ import annotations

import argparse
import ast
import pathlib
import re
import subprocess
import sys
from typing import Any

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from fanout_common import (  # noqa: E402
    item_file,
    parse_source,
    qualname_targets,
    read_json,
    strip_docstrings,
    write_json,
)

PLACEHOLDER_RE = re.compile(r"\b(todo|tbd|fixme|placeholder)\b", re.IGNORECASE)


def fail(check: str, reason: str) -> dict[str, Any]:
    return {"passed": False, "failed_check": check, "reason": reason}


def ok() -> dict[str, Any]:
    return {"passed": True, "failed_check": None, "reason": None}


def compile_check(path: pathlib.Path) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def word_present(text: str, name: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", text) is not None


def verify(corpus: pathlib.Path, item: dict[str, Any], modified_path: pathlib.Path, insertion_rc: int = 0) -> dict[str, Any]:
    if insertion_rc != 0:
        return fail("insertion_clean", f"insert_docstrings.py exited {insertion_rc}")
    passed_compile, compile_output = compile_check(modified_path)
    if not passed_compile:
        return fail("compiles", compile_output or "py_compile failed")

    pristine_path = item_file(corpus, item)
    pristine_source = pristine_path.read_text(encoding="utf-8")
    modified_source = modified_path.read_text(encoding="utf-8")
    pristine_tree = parse_source(pristine_source, item["path"])
    modified_tree = parse_source(modified_source, str(modified_path))
    pristine_targets = qualname_targets(pristine_tree)

    coverage_missing = []
    all_nodes = collect_nodes(modified_tree)
    for qualname in item["targets"]:
        node = all_nodes.get(qualname)
        if node is None or ast.get_docstring(node, clean=False) is None:
            coverage_missing.append(qualname)
    if coverage_missing:
        return fail("coverage", "missing inserted docstrings: " + ", ".join(coverage_missing))

    stripped_pristine = ast.dump(strip_docstrings(pristine_tree), include_attributes=False)
    stripped_modified = ast.dump(strip_docstrings(modified_tree), include_attributes=False)
    if stripped_pristine != stripped_modified:
        return fail("ast_equivalence", "AST differs after stripping docstrings")

    for qualname in item["targets"]:
        node = all_nodes[qualname]
        docstring = ast.get_docstring(node, clean=False) or ""
        if len(docstring.strip()) < 20 or PLACEHOLDER_RE.search(docstring):
            return fail("non_placeholder", f"{qualname} docstring is too short or placeholder-like")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            target_meta = pristine_targets.get(qualname)
            params = target_meta.params if target_meta else ()
            missing = [name for name in params if not word_present(docstring, name)]
            if missing:
                return fail("parameter_mention", f"{qualname} missing parameter mention(s): {', '.join(missing)}")
    return ok()


def collect_nodes(tree: ast.AST) -> dict[str, ast.AST]:
    nodes: dict[str, ast.AST] = {}

    def walk_body(body: list[ast.stmt], stack: list[str]) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qualname = ".".join([*stack, node.name])
                nodes[qualname] = node
                walk_body(node.body, [*stack, node.name])

    if isinstance(tree, ast.Module):
        walk_body(tree.body, [])
    return nodes


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify one fan-out item scratch file.")
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--item", required=True)
    parser.add_argument("--modified", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--insertion-rc", type=int, default=0)
    args = parser.parse_args()

    item = read_json(pathlib.Path(args.item))
    result = verify(pathlib.Path(args.corpus), item, pathlib.Path(args.modified), args.insertion_rc)
    write_json(pathlib.Path(args.out), result)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
