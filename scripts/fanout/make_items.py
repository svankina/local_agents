#!/usr/bin/env python3
"""Generate the pinned Scrapy docstring backfill work-item lock."""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
from typing import Any

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from fanout_common import (  # noqa: E402
    CORPUS_URL,
    PINNED_SHA,
    generator_git_sha,
    parse_source,
    qualname_targets,
    sha256_text,
    verify_corpus_head,
    write_json,
)


def clone_corpus(dest: pathlib.Path) -> None:
    if dest.exists():
        if not (dest / ".git").exists():
            raise SystemExit(f"{dest} exists but is not a git checkout")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", CORPUS_URL, str(dest)], check=True)
    subprocess.run(["git", "-C", str(dest), "fetch", "origin", PINNED_SHA], check=True)
    subprocess.run(["git", "-C", str(dest), "checkout", "--detach", PINNED_SHA], check=True)


def candidate(path: pathlib.Path, corpus: pathlib.Path) -> dict[str, Any] | None:
    rel = path.relative_to(corpus).as_posix()
    source = path.read_text(encoding="utf-8")
    line_count = len(source.splitlines())
    if line_count < 50 or line_count > 400:
        return None
    tree = parse_source(source, rel)
    targets = qualname_targets(tree)
    if len(targets) < 3:
        return None
    est_prompt_tokens = int(len(source) / 3.5 + 600)
    if est_prompt_tokens > 4500:
        return None
    return {
        "path": rel,
        "file_sha256": sha256_text(source),
        "targets": sorted(targets),
        "line_count": line_count,
        "est_prompt_tokens": est_prompt_tokens,
        "_missing_count": len(targets),
    }


def build_items(corpus: pathlib.Path, count: int) -> list[dict[str, Any]]:
    candidates = []
    for path in sorted((corpus / "scrapy").glob("**/*.py")):
        item = candidate(path, corpus)
        if item is not None:
            candidates.append(item)
    candidates.sort(key=lambda row: (-int(row["_missing_count"]), row["path"]))
    if len(candidates) < count:
        raise SystemExit(f"only {len(candidates)} eligible items found, need {count}")
    items = []
    for index, item in enumerate(candidates[:count], 1):
        item = {k: v for k, v in item.items() if not k.startswith("_")}
        item["id"] = f"item-{index:02d}"
        items.append(item)
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Create showcase fan-out Scrapy work items.")
    parser.add_argument("--corpus", required=True, help="Scrapy checkout at the pinned SHA")
    parser.add_argument("--count", type=int, default=32)
    parser.add_argument("--out", required=True, help="Output items directory")
    parser.add_argument("--clone-if-missing", action="store_true")
    args = parser.parse_args()

    corpus = pathlib.Path(args.corpus).resolve()
    if args.clone_if_missing and not corpus.exists():
        clone_corpus(corpus)
    verify_corpus_head(corpus)
    out = pathlib.Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    repo_root = SCRIPT_DIR.parents[1]
    items = build_items(corpus, args.count)
    for item in items:
        write_json(out / f"{item['id']}.json", item)
    lock = {
        "schema": "showcase-fanout.items.v1",
        "corpus_url": CORPUS_URL,
        "pinned_sha": PINNED_SHA,
        "generator_git_sha": generator_git_sha(repo_root),
        "item_count": len(items),
        "items": items,
    }
    write_json(out / "items.lock.json", lock)
    print(f"wrote {len(items)} items to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
