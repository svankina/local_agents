"""Shared helpers: OpenAI-compat chat client against llama-server, scorers."""

import json
import os
import re
import time
import urllib.error
import urllib.request

BASE = os.environ.get("BENCH_BASE", "http://127.0.0.1:8089")
MODEL = os.environ.get("BENCH_MODEL", "local")


def v1_url(base, path):
    base = base.rstrip("/")
    if base.endswith("/v1"):
        return base + path
    return base + "/v1" + path


def chat(messages, tools=None, temperature=0.2, max_tokens=1024, base=None, timeout=600):
    base = base or BASE
    payload = {
        "model": os.environ.get("BENCH_MODEL", MODEL),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timings_per_token": False,
    }
    if tools:
        payload["tools"] = tools
    req = urllib.request.Request(
        v1_url(base, "/chat/completions"),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read())
    body["_wall_s"] = round(time.monotonic() - t0, 3)
    return body


def tool_calls_of(body):
    msg = body["choices"][0]["message"]
    return [
        {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]}
        for tc in (msg.get("tool_calls") or [])
    ]


def parse_timings(body):
    t = body.get("timings") or {}
    if t:
        return {
            "prefill_tps": t.get("prompt_per_second"),
            "decode_tps": t.get("predicted_per_second"),
            "prompt_n": t.get("prompt_n"),
            "predicted_n": t.get("predicted_n"),
            "timing_source": "server_timings",
        }
    usage = body.get("usage") or {}
    wall_s = body.get("_wall_s") or 0
    prompt_n = usage.get("prompt_tokens")
    predicted_n = usage.get("completion_tokens")
    prefill_tps = (prompt_n / wall_s) if prompt_n is not None and wall_s > 0 else None
    decode_tps = (predicted_n / wall_s) if predicted_n is not None and wall_s > 0 else None
    return {
        "prefill_tps": prefill_tps,
        "decode_tps": decode_tps,
        "prompt_n": prompt_n,
        "predicted_n": predicted_n,
        "timing_source": "client_wall_usage",
    }


def score_toolcall(case, calls):
    """Score one expected tool call.

    case shape: {expect_tool: str|None, expect_args: {name: {eq|re|contains: val}}}
    """
    if case.get("expect_tool") is None:
        return (not calls, "ok" if not calls else "unexpected tool call")
    if not calls:
        return (False, "no tool call made")
    call = calls[0]
    if call["name"] != case["expect_tool"]:
        return (False, f"wrong tool: {call['name']}")
    try:
        args = json.loads(call["arguments"]) if isinstance(call["arguments"], str) else call["arguments"]
    except (json.JSONDecodeError, TypeError):
        return (False, "arguments not valid JSON")
    for k, matcher in (case.get("expect_args") or {}).items():
        v = args.get(k)
        if "eq" in matcher and v != matcher["eq"]:
            return (False, f"arg {k}: {v!r} != {matcher['eq']!r}")
        if "re" in matcher and (not isinstance(v, str) or not re.search(matcher["re"], v)):
            return (False, f"arg {k}: {v!r} !~ /{matcher['re']}/")
        if "contains" in matcher and (not isinstance(v, str) or matcher["contains"] not in v):
            return (False, f"arg {k}: missing {matcher['contains']!r}")
    return (True, "ok")


def wait_healthy(base=None, tries=120):
    base = base or BASE
    for _ in range(tries):
        for url in (base.rstrip("/") + "/health", v1_url(base, "/models")):
            try:
                with urllib.request.urlopen(url, timeout=5) as r:
                    if r.status == 200:
                        return True
            except urllib.error.HTTPError:
                pass
            except Exception:
                pass
        time.sleep(2)
    raise SystemExit("server never became healthy")
