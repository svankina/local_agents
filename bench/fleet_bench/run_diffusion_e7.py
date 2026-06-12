#!/usr/bin/env python3
"""E7: diffusiongemma-26B-A4B-it through llama-diffusion-cli (PR #24423).

No OpenAI server exists for this model, so we drive the CLI's conversation mode
over a pipe: wait for the "> " prompt, write one flattened plan line, read the
denoised reply, verify, /clear, repeat. Single stream (the CLI has one canvas).
E2-comparable: medium plan, single-shot, 10 problems x 3 samples.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import select
import subprocess
import sys
import time

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import fake_supervisor as fs  # noqa: E402
from families import pure_fn  # noqa: E402

ROOT = SCRIPT_DIR.parent.parent
OUT = ROOT / "results" / "experiments" / "fable-fleet-bench" / f"{time.strftime('%Y-%m-%d')}-e7"
HOME = pathlib.Path.home()

CMD = [
    "docker", "run", "--rm", "-i", "--gpus", "all",
    "-v", f"{HOME}/src/llama.cpp-diffusion:/src",
    "-v", f"{HOME}/.cache/llama.cpp:/models",
    "-e", "LD_LIBRARY_PATH=/src/build-docker/bin",
    "--entrypoint", "/src/build-docker/bin/llama-diffusion-cli",
    "vllm/vllm-openai:v0.22.1",
    "-m", "/models/diffusiongemma-26B-A4B-it-Q4_K_M.gguf",
    "-ngl", "99", "-n", "1024", "--temp", "0.2", "-cnv",
]

# the model emits an in-canvas thought channel; the answer follows the last marker
CHANNEL_RE = re.compile(r"<\|channel\|?>\s*(\w+)")


def split_channels(text: str) -> str:
    """Return the final (non-thought) content of a reply."""
    parts = CHANNEL_RE.split(text)
    if len(parts) == 1:
        return text.strip()
    # parts: [pre, name1, body1, name2, body2, ...] - take the last non-thought body
    out = ""
    for name, body in zip(parts[1::2], parts[2::2]):
        if name.lower() not in ("thought", "analysis", "think"):
            out = body
    if not out:  # nothing but thought: treat whole reply as-is (will fail verify)
        out = parts[-1]
    return out.strip()


class DiffusionCLI:
    def __init__(self):
        # binary pipes + os.read: select() on a text wrapper deadlocks on buffered data
        self.proc = subprocess.Popen(CMD, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.set_blocking(self.proc.stdout.fileno(), False)
        os.set_blocking(self.proc.stderr.fileno(), False)
        self.err_tail: list[str] = []
        self._errbuf = b""

    def _drain_err(self):
        try:
            chunk = os.read(self.proc.stderr.fileno(), 65536)
        except BlockingIOError:
            return
        if chunk:
            self._errbuf += chunk
            *lines, self._errbuf = self._errbuf.split(b"\n")
            self.err_tail.extend(ln.decode(errors="replace") for ln in lines)
            if len(self.err_tail) > 300:
                del self.err_tail[:150]

    def read_until_prompt(self, timeout: float = 600) -> str:
        """Collect stdout until the '> ' prompt appears at the end."""
        buf, t0 = b"", time.time()
        while time.time() - t0 < timeout:
            self._drain_err()
            r = select.select([self.proc.stdout], [], [], 0.25)[0]
            if r:
                try:
                    chunk = os.read(self.proc.stdout.fileno(), 65536)
                except BlockingIOError:
                    chunk = b""
                if chunk == b"" and self.proc.poll() is not None:
                    raise RuntimeError("CLI exited\n" + "\n".join(self.err_tail[-15:]))
                buf += chunk
                if buf.endswith(b"\n> ") or buf == b"> ":
                    return buf[:-2].decode(errors="replace")
            elif self.proc.poll() is not None:
                raise RuntimeError("CLI exited\n" + "\n".join(self.err_tail[-15:]))
        raise TimeoutError(f"no prompt after {timeout}s; tail: {buf[-200:]!r}")

    def turn(self, line: str, timeout: float = 600) -> str:
        self.proc.stdin.write((line.replace("\n", " ") + "\n").encode())
        self.proc.stdin.flush()
        return self.read_until_prompt(timeout)

    def clear(self):
        self.turn("/clear", timeout=30)

    def last_turn_stats(self) -> dict:
        stats = {}
        for ln in reversed(self.err_tail):
            m = re.search(r"total time: ([\d.]+)ms.*?(\d+) steps", ln)
            if m and "decode_ms" not in stats:
                stats["decode_ms"] = float(m.group(1))
                stats["steps"] = int(m.group(2))
            m = re.search(r"throughput: ([\d.]+) tok/s \((\d+) tok", ln)
            if m and "tok_s" not in stats:
                stats["tok_s"] = float(m.group(1))
                stats["n_tok"] = int(m.group(2))
            if len(stats) >= 4:
                break
        return stats


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    items = pure_fn.build_items()
    cli = DiffusionCLI()
    print("loading model (cold load can take ~2 min)...", flush=True)
    banner = cli.read_until_prompt(timeout=600)
    print(f"ready ({len(banner)} banner chars)", flush=True)

    results = []
    t0 = time.time()
    for rep in range(3):
        for it in items:
            plan = fs.plan_medium(it)
            t1 = time.time()
            try:
                raw = cli.turn(plan)
            except (RuntimeError, TimeoutError) as e:
                results.append({"item": it["id"], "rep": rep, "error": str(e)[:300]})
                print(f"  ERROR {it['id']} rep{rep}: {e}", flush=True)
                break
            wall = time.time() - t1
            reply = split_channels(raw)
            strict, analysis = fs.verify(it, reply)
            rec = {
                "item": it["id"], "rep": rep, "wall_s": round(wall, 2),
                "passed": strict["passed"],
                "lenient_passed": analysis["lenient_verdict"]["passed"],
                "failed_check": strict.get("failed_check"),
                "violations": analysis["violations"],
                "raw_len": len(raw), "stats": cli.last_turn_stats(),
            }
            results.append(rec)
            print(f"  {it['id']} rep{rep}: passed={rec['passed']} "
                  f"wall={wall:.1f}s {rec['stats'].get('tok_s', '?')} tok/s", flush=True)
            cli.clear()
        else:
            continue
        break
    total_wall = time.time() - t0

    ok = [r for r in results if "error" not in r]
    n = len(ok)
    summary = {
        "model": "diffusiongemma-26B-A4B-it-Q4_K_M",
        "engine": "llama-diffusion-cli PR#24423, 1 stream, -n 1024, temp 0.2",
        "n": n,
        "strict_pass_rate": round(sum(r["passed"] for r in ok) / max(1, n), 3),
        "lenient_pass_rate": round(sum(r["lenient_passed"] for r in ok) / max(1, n), 3),
        "mean_episode_wall_s": round(sum(r["wall_s"] for r in ok) / max(1, n), 2),
        "suite_wall_s": round(total_wall, 1),
        "errors": len(results) - n,
    }
    (OUT / "episodes-diffusiongemma.json").write_text(json.dumps(
        {"results": results, "summary": summary}, indent=1))
    (OUT / "summary-diffusiongemma.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    try:
        cli.turn("/exit", timeout=10)
    except Exception:  # noqa: BLE001
        cli.proc.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
