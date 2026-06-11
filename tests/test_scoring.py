import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "bench"))
from common import parse_timings, score_toolcall


def test_score_exact_match():
    case = {"expect_tool": "read_file", "expect_args": {"path": {"eq": "src/main.py"}}}
    call = {"name": "read_file", "arguments": json.dumps({"path": "src/main.py"})}
    assert score_toolcall(case, [call]) == (True, "ok")


def test_score_wrong_tool():
    case = {"expect_tool": "read_file", "expect_args": {}}
    call = {"name": "run_bash", "arguments": "{}"}
    ok, why = score_toolcall(case, [call])
    assert not ok and "tool" in why


def test_score_regex_arg():
    case = {"expect_tool": "run_bash", "expect_args": {"command": {"re": r"grep\s+-r"}}}
    call = {"name": "run_bash", "arguments": json.dumps({"command": "grep -r TODO ."})}
    assert score_toolcall(case, [call])[0]


def test_score_expect_no_tool():
    case = {"expect_tool": None}
    assert score_toolcall(case, [])[0]
    assert not score_toolcall(case, [{"name": "read_file", "arguments": "{}"}])[0]


def test_score_malformed_json_args():
    case = {"expect_tool": "read_file", "expect_args": {"path": {"eq": "x"}}}
    call = {"name": "read_file", "arguments": "{path: x"}
    ok, why = score_toolcall(case, [call])
    assert not ok and "json" in why.lower()


def test_parse_timings():
    body = {
        "timings": {
            "prompt_n": 1000,
            "prompt_per_second": 512.3,
            "predicted_n": 256,
            "predicted_per_second": 41.7,
        }
    }
    t = parse_timings(body)
    assert t == {
        "prefill_tps": 512.3,
        "decode_tps": 41.7,
        "prompt_n": 1000,
        "predicted_n": 256,
    }
