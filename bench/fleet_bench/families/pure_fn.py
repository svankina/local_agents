#!/usr/bin/env python3
"""Tier-1 `pure_fn` family: implement a pure function from a spec.

Each problem ships a *reference* implementation and a seeded input generator.
- Visible examples shown to the worker are computed from the reference, so they
  can never drift from ground truth.
- Verification runs the worker's body against the reference on N seeded inputs
  (plus the visible examples). Equal on all -> pass. This gives unlimited
  airtight hidden cases without a model judge.

A worker is given: signature + docstring + 3 examples. It returns the function
source. Nothing else (no imports of the reference, no network) — the verifier
execs the submission in a restricted namespace and compares outputs.
"""
from __future__ import annotations

import ast
import json
import random
import sys
from dataclasses import dataclass
from typing import Any, Callable, Iterable


@dataclass
class Problem:
    id: str
    signature: str          # e.g. "def run_length_encode(s: str) -> list[tuple[str, int]]:"
    docstring: str
    reference: Callable[..., Any]
    inputs: Callable[[random.Random], tuple]   # one seeded test case -> args tuple
    example_seeds: tuple[int, ...] = (1, 2, 3)
    difficulty: str = "easy"


def fn_name(sig: str) -> str:
    return sig.split("def ", 1)[1].split("(", 1)[0].strip()


# ---------------------------------------------------------------------------
# Problem bank. Keep each reference small, total, and deterministic.
# ---------------------------------------------------------------------------

def _rle(s: str) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for ch in s:
        if out and out[-1][0] == ch:
            out[-1] = (ch, out[-1][1] + 1)
        else:
            out.append((ch, 1))
    return out


def _balanced(s: str) -> bool:
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for ch in s:
        if ch in "([{":
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack.pop() != pairs[ch]:
                return False
    return not stack


def _two_sum(nums: list[int], target: int) -> list[int]:
    seen: dict[int, int] = {}
    for i, n in enumerate(nums):
        if target - n in seen:
            return [seen[target - n], i]
        seen[n] = i
    return []


def _merge_intervals(intervals: list[list[int]]) -> list[list[int]]:
    out: list[list[int]] = []
    for lo, hi in sorted(intervals):
        if out and lo <= out[-1][1]:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return out


def _word_freq(text: str) -> dict[str, int]:
    freq: dict[str, int] = {}
    for w in text.lower().split():
        w = w.strip(".,!?;:")
        if w:
            freq[w] = freq.get(w, 0) + 1
    return freq


def _camel_to_snake(name: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _flatten(nested: list) -> list:
    out: list = []
    for el in nested:
        if isinstance(el, list):
            out.extend(_flatten(el))
        else:
            out.append(el)
    return out


def _roman(n: int) -> str:
    table = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
             (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
             (5, "V"), (4, "IV"), (1, "I")]
    out: list[str] = []
    for val, sym in table:
        while n >= val:
            out.append(sym)
            n -= val
    return "".join(out)


def _chunk(seq: list, size: int) -> list[list]:
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return abs(a)


def _rand_str(rng: random.Random, alphabet: str, lo: int, hi: int) -> str:
    return "".join(rng.choice(alphabet) for _ in range(rng.randint(lo, hi)))


PROBLEMS: list[Problem] = [
    Problem(
        "run-length-encode",
        "def run_length_encode(s: str) -> list[tuple[str, int]]:",
        "Run-length encode a string into (char, count) pairs, left to right.\n"
        "Consecutive equal characters collapse into one pair.",
        _rle,
        lambda r: (_rand_str(r, "aabbc", 0, 12),),
        difficulty="easy",
    ),
    Problem(
        "balanced-brackets",
        "def balanced_brackets(s: str) -> bool:",
        "Return True if every (), [], and {} in s is correctly matched and nested.\n"
        "Non-bracket characters are ignored.",
        _balanced,
        lambda r: (_rand_str(r, "()[]{}ab", 0, 10),),
        difficulty="easy",
    ),
    Problem(
        "two-sum-indices",
        "def two_sum(nums: list[int], target: int) -> list[int]:",
        "Return the indices [i, j] (i < j) of the first pair summing to target,\n"
        "scanning j left to right. Return [] if no pair exists.",
        _two_sum,
        lambda r: ([r.randint(-5, 9) for _ in range(r.randint(0, 7))], r.randint(0, 12)),
        difficulty="medium",
    ),
    Problem(
        "merge-intervals",
        "def merge_intervals(intervals: list[list[int]]) -> list[list[int]]:",
        "Merge overlapping closed intervals and return them sorted by start.\n"
        "Intervals touching at an endpoint (e.g. [1,3],[3,5]) merge.",
        _merge_intervals,
        lambda r: ([sorted((r.randint(0, 9), r.randint(0, 9))) for _ in range(r.randint(0, 5))],),
        difficulty="medium",
    ),
    Problem(
        "word-frequency",
        "def word_frequency(text: str) -> dict[str, int]:",
        "Count words case-insensitively. Split on whitespace, strip leading/trailing\n"
        ".,!?;: from each token, drop empties.",
        _word_freq,
        lambda r: (" ".join(_rand_str(r, "ab.,! ", 1, 5) for _ in range(r.randint(0, 6))),),
        difficulty="easy",
    ),
    Problem(
        "camel-to-snake",
        "def camel_to_snake(name: str) -> str:",
        "Convert a camelCase / PascalCase identifier to snake_case.\n"
        "An underscore goes before each interior uppercase letter; all lowercased.",
        _camel_to_snake,
        lambda r: (_rand_str(r, "abAB", 1, 10),),
        difficulty="easy",
    ),
    Problem(
        "flatten-nested",
        "def flatten(nested: list) -> list:",
        "Flatten an arbitrarily nested list of ints into a single flat list,\n"
        "preserving left-to-right order.",
        _flatten,
        lambda r: (_rand_nested(r, 2),),
        difficulty="medium",
    ),
    Problem(
        "int-to-roman",
        "def int_to_roman(n: int) -> str:",
        "Convert an integer 1..3999 to its Roman numeral.",
        _roman,
        lambda r: (r.randint(1, 3999),),
        difficulty="medium",
    ),
    Problem(
        "chunk-list",
        "def chunk(seq: list, size: int) -> list[list]:",
        "Split seq into consecutive chunks of length size (last may be shorter).\n"
        "size is always >= 1.",
        _chunk,
        lambda r: ([r.randint(0, 9) for _ in range(r.randint(0, 9))], r.randint(1, 4)),
        difficulty="easy",
    ),
    Problem(
        "gcd",
        "def gcd(a: int, b: int) -> int:",
        "Return the greatest common divisor of a and b (non-negative).\n"
        "gcd(0, 0) == 0.",
        _gcd,
        lambda r: (r.randint(0, 100), r.randint(0, 100)),
        difficulty="easy",
    ),
]


def _rand_nested(r: random.Random, depth: int) -> list:
    out: list = []
    for _ in range(r.randint(0, 4)):
        if depth > 0 and r.random() < 0.4:
            out.append(_rand_nested(r, depth - 1))
        else:
            out.append(r.randint(0, 9))
    return out


# ---------------------------------------------------------------------------
# Item generation
# ---------------------------------------------------------------------------

def _examples(p: Problem) -> list[dict[str, Any]]:
    out = []
    for seed in p.example_seeds:
        args = p.inputs(random.Random(seed))
        out.append({"args": list(args), "returns": p.reference(*args)})
    return out


def build_items(n_per_problem: int = 1) -> list[dict[str, Any]]:
    """One item per problem (v1). n_per_problem reserved for templated variants."""
    items = []
    for p in PROBLEMS:
        items.append({
            "id": f"pure_fn/{p.id}",
            "family": "pure_fn",
            "tier": 1,
            "difficulty": p.difficulty,
            "fn_name": fn_name(p.signature),
            "signature": p.signature,
            "docstring": p.docstring,
            "examples": _examples(p),
            "verify": {"problem_id": p.id, "n_cases": 200, "seed_base": 7919},
        })
    return items


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

_SAFE_BUILTINS = {
    "len", "range", "enumerate", "sorted", "reversed", "min", "max", "sum",
    "abs", "map", "filter", "zip", "list", "dict", "set", "tuple", "str",
    "int", "bool", "float", "isinstance", "all", "any", "ord", "chr", "round",
}


def _problem_by_id(pid: str) -> Problem:
    for p in PROBLEMS:
        if p.id == pid:
            return p
    raise KeyError(pid)


def verify_submission(item: dict[str, Any], source: str) -> dict[str, Any]:
    """Exec worker `source`, compare to reference on seeded inputs + examples."""
    p = _problem_by_id(item["verify"]["problem_id"])
    name = item["fn_name"]

    # 1. parses, defines exactly the target function, no imports / dunder access
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"passed": False, "failed_check": "parse", "reason": str(e)}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return {"passed": False, "failed_check": "no-import", "reason": "imports not allowed"}
    defines = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if name not in defines:
        return {"passed": False, "failed_check": "defines-fn", "reason": f"missing def {name}"}

    # 2. exec in a restricted namespace
    safe = {"__builtins__": {k: __builtins__[k] if isinstance(__builtins__, dict)
                             else getattr(__builtins__, k) for k in _SAFE_BUILTINS}}
    try:
        exec(compile(tree, item["id"], "exec"), safe)  # noqa: S102 - sandboxed builtins
    except Exception as e:  # noqa: BLE001
        return {"passed": False, "failed_check": "exec", "reason": repr(e)}
    fn = safe.get(name)
    if not callable(fn):
        return {"passed": False, "failed_check": "callable", "reason": f"{name} not callable"}

    # 3. visible examples + seeded hidden cases
    cases: list[tuple] = [tuple(ex["args"]) for ex in item["examples"]]
    base = item["verify"]["seed_base"]
    for k in range(item["verify"]["n_cases"]):
        cases.append(p.inputs(random.Random(base + k)))
    for args in cases:
        try:
            got = fn(*[_clone(a) for a in args])
        except Exception as e:  # noqa: BLE001
            return {"passed": False, "failed_check": "runtime", "reason": f"{args!r}: {e!r}"}
        want = p.reference(*[_clone(a) for a in args])
        if got != want:
            return {"passed": False, "failed_check": "mismatch",
                    "reason": f"{args!r} -> got {got!r}, want {want!r}"}
    return {"passed": True, "failed_check": None, "reason": None}


def _clone(x: Any) -> Any:
    return json.loads(json.dumps(x)) if isinstance(x, (list, dict)) else x


# ---------------------------------------------------------------------------
# CLI: emit items, or self-test the bank
# ---------------------------------------------------------------------------

def _selftest() -> int:
    items = build_items()
    bad = 0
    for it in items:
        p = _problem_by_id(it["verify"]["problem_id"])
        ref_src = _reference_source(p)
        r = verify_submission(it, ref_src)
        broken = verify_submission(it, _broken_source(p))
        tag = "ok " if (r["passed"] and not broken["passed"]) else "BAD"
        if tag == "BAD":
            bad += 1
        print(f"{tag} {it['id']:28} ref={r['passed']} broken_rejected={not broken['passed']}")
    print(f"\n{len(items)} problems, {bad} broken")
    return 1 if bad else 0


def _reference_source(p: Problem) -> str:
    import inspect
    import re
    src = inspect.getsource(p.reference)
    # rename the private ref (_rle) to the public name workers must define,
    # including recursive self-calls in the body
    return re.sub(rf"(?<![A-Za-z0-9_]){re.escape(p.reference.__name__)}(?![A-Za-z0-9_])",
                  fn_name(p.signature), src)


def _broken_source(p: Problem) -> str:
    name = fn_name(p.signature)
    return f"def {name}(*args, **kwargs):\n    return None\n"


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        raise SystemExit(_selftest())
    print(json.dumps(build_items(), indent=2, default=str))
