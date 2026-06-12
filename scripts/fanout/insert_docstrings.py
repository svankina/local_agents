#!/usr/bin/env python3
"""Insert benchmark docstrings into a scratch copy of one Python file."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from fanout_common import item_file, parse_source, qualname_targets, read_json  # noqa: E402


def load_response(path: pathlib.Path) -> dict[str, str]:
    body = read_json(path)
    docstrings = body.get("docstrings") if isinstance(body, dict) else None
    if not isinstance(docstrings, dict):
        raise ValueError("response must contain object key docstrings")
    out: dict[str, str] = {}
    for key, value in docstrings.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("docstring map keys and values must be strings")
        out[key] = value
    return out


def insert_docstrings(source: str, item: dict[str, Any], docstrings: dict[str, str]) -> str:
    tree = parse_source(source, item["path"])
    targets = qualname_targets(tree)
    wanted = list(item["targets"])
    missing = sorted(set(wanted) - set(docstrings))
    extra = sorted(set(docstrings) - set(wanted))
    unknown = sorted(set(wanted) - set(targets))
    if missing:
        raise ValueError(f"missing docstrings for: {', '.join(missing)}")
    if extra:
        raise ValueError(f"extra docstrings for: {', '.join(extra)}")
    if unknown:
        raise ValueError(f"targets not found without docstrings: {', '.join(unknown)}")

    lines = source.splitlines(keepends=True)
    insertions: list[tuple[int, int, str]] = []
    for qualname in wanted:
        target = targets[qualname]
        node = next(n for n in ast_walk_named(parse_source(source, item["path"]), qualname))
        if not getattr(node, "body", None):
            raise ValueError(f"target has no body: {qualname}")
        first_stmt = node.body[0]
        lineno = first_stmt.lineno
        indent = " " * first_stmt.col_offset
        literal = json.dumps(docstrings[qualname], ensure_ascii=False)
        insertions.append((lineno - 1, first_stmt.col_offset, f"{indent}{literal}\n"))

    for line_index, _col, text in sorted(insertions, key=lambda row: row[0], reverse=True):
        lines.insert(line_index, text)
    return "".join(lines)


def ast_walk_named(tree, qualname: str):
    parts = qualname.split(".")

    def walk_body(body, stack):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                next_stack = [*stack, node.name]
                if next_stack == parts:
                    yield node
                yield from walk_body(node.body, next_stack)

    import ast

    yield from walk_body(tree.body, [])


def main() -> int:
    parser = argparse.ArgumentParser(description="Insert docstrings for one fan-out item.")
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--item", required=True)
    parser.add_argument("--response", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    item = read_json(pathlib.Path(args.item))
    source_path = item_file(pathlib.Path(args.corpus), item)
    source = source_path.read_text(encoding="utf-8")
    docstrings = load_response(pathlib.Path(args.response))
    modified = insert_docstrings(source, item, docstrings)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(modified, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
