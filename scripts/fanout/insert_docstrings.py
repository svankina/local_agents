#!/usr/bin/env python3
"""Insert benchmark docstrings into a scratch copy of one Python file."""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import sys
from typing import Any

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from fanout_common import item_file, normalize_docstring_keys, parse_source, qualname_targets, read_json  # noqa: E402


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
    unknown = sorted(set(wanted) - set(targets))
    if unknown:
        raise ValueError(f"targets not found without docstrings: {', '.join(unknown)}")
    docstrings = normalize_docstring_keys(docstrings, wanted)

    lines = source.splitlines(keepends=True)
    operations: list[tuple[int, str, str]] = []
    named_nodes: dict[str, list[ast.AST]] = {}
    for qualname, node in ast_walk_named(parse_source(source, item["path"])):
        named_nodes.setdefault(qualname, []).append(node)
    for qualname in wanted:
        candidate_nodes = [
            node
            for node in named_nodes.get(qualname, [])
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and ast.get_docstring(node, clean=False) is None
        ]
        if not candidate_nodes:
            raise ValueError(f"target not found without docstring: {qualname}")
        for node in candidate_nodes:
            add_operation(operations, lines, node, qualname, docstrings[qualname])

    seen_replacements: set[int] = set()
    for line_index, op, text in sorted(operations, key=lambda row: row[0], reverse=True):
        if op == "replace":
            if line_index in seen_replacements:
                raise ValueError(f"multiple one-line suite replacements on line {line_index + 1}")
            seen_replacements.add(line_index)
            lines[line_index] = text
        else:
            lines.insert(line_index, text)
    return "".join(lines)


def add_operation(
    operations: list[tuple[int, str, str]],
    lines: list[str],
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
    qualname: str,
    docstring: str,
) -> None:
    if not node.body:
        raise ValueError(f"target has no body: {qualname}")
    first_stmt = node.body[0]
    literal = json.dumps(docstring, ensure_ascii=False)
    suite_line_index = first_stmt.lineno - 1 if first_stmt.lineno != node.lineno else node.lineno - 1
    suite_line = lines[suite_line_index]
    suite_text = suite_line[:-1] if suite_line.endswith("\n") else suite_line
    suite_colon_index = suite_text.rfind(":", 0, first_stmt.col_offset)
    suite_prefix = suite_text[: suite_colon_index + 1].strip() if suite_colon_index != -1 else ""
    looks_like_suite_header = suite_prefix.startswith(("def ", "async def ", "class ", ")"))
    if first_stmt.lineno == node.lineno or (suite_colon_index != -1 and looks_like_suite_header):
        line_index = suite_line_index
        original = lines[line_index]
        newline = "\n" if original.endswith("\n") else ""
        stripped_newline = original[:-1] if newline else original
        colon_index = suite_colon_index
        if colon_index == -1:
            raise ValueError(f"cannot locate one-line suite colon for {qualname}")
        block_indent = " " * (node.col_offset + 4)
        body_text = stripped_newline[colon_index + 1 :].strip()
        if not body_text:
            raise ValueError(f"empty one-line suite body for {qualname}")
        replacement = (
            stripped_newline[: colon_index + 1]
            + "\n"
            + f"{block_indent}{literal}\n"
            + f"{block_indent}{body_text}"
            + newline
        )
        operations.append((line_index, "replace", replacement))
        return

    if isinstance(node, ast.ClassDef) and isinstance(
        first_stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    ) and first_stmt.decorator_list:
        insertion_line = min(decorator.lineno for decorator in first_stmt.decorator_list) - 1
        indent = " " * first_stmt.col_offset
    else:
        insertion_line = first_stmt.lineno - 1
        indent = " " * first_stmt.col_offset
    operations.append((insertion_line, "insert", f"{indent}{literal}\n"))


def ast_walk_named(tree):
    def walk_body(body, stack):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                next_stack = [*stack, node.name]
                yield ".".join(next_stack), node
                yield from walk_body(node.body, next_stack)

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
