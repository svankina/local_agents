"""Cache-busting prefill probe for selected configs.

Launches one llama-server at a time using bench/configs.json, sends three chat
requests with unique large random prefixes, and records server-side prompt eval
throughput plus client wall-clock timings.
"""

import json
import pathlib
import re
import secrets
import statistics
import subprocess
import sys
import time

from common import chat, wait_healthy

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = pathlib.Path.home() / ".cache" / "llama.cpp"
RAW_ROOT = ROOT / "results" / "raw" / "prefill-probe"
OUT_PATH = ROOT / "results" / "prefill_probe.json"
CONFIGS = ["C1-gemma12b-base", "C4-gemma26b-gpu", "C7-qwen27b-q3", "C8-nex-mini-q3"]
PROMPT_EVAL_RE = re.compile(
    r"prompt eval time =\s*([0-9.]+) ms /\s*(\d+) tokens .*?\s([0-9.]+) tokens per second"
)
PROMPT_PROCESSING_RE = re.compile(
    r"prompt processing, n_tokens =\s*(\d+), progress =\s*([0-9.]+), t =\s*([0-9.]+) s /\s*([0-9.]+) tokens per second"
)


def run(cmd, **kwargs):
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=True, **kwargs).stdout


def stop_ollama_models():
    try:
        ps = subprocess.run(["ollama", "ps"], text=True, capture_output=True, check=False)
    except FileNotFoundError:
        return
    for line in ps.stdout.splitlines()[1:]:
        parts = line.split()
        if parts:
            subprocess.run(["ollama", "stop", parts[0]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def resolve_gpu_device():
    out = run(["llama-server", "--list-devices"])
    for line in out.splitlines():
        if "RTX 3090" in line:
            m = re.search(r"Vulkan[0-9]+", line)
            if m:
                return m.group(0)
    raise RuntimeError("could not resolve RTX 3090 Ti Vulkan device")


def expand_flags(config, gpu):
    configs = json.loads((ROOT / "bench" / "configs.json").read_text())
    flags = f"{configs['_common']} {configs[config]}"
    return flags.replace("<CACHE>", str(CACHE)).replace("<GPU>", gpu).split()


def random_prefix():
    vocab = [
        "able",
        "baker",
        "cable",
        "delta",
        "ember",
        "fable",
        "garden",
        "harbor",
        "island",
        "jungle",
        "kernel",
        "ladder",
        "market",
        "number",
        "orange",
        "planet",
        "quiet",
        "river",
        "silver",
        "timber",
        "unit",
        "velvet",
        "window",
        "yellow",
        "zephyr",
    ]
    words = [secrets.choice(vocab) for _ in range(7800)]
    return " ".join(words)


def parse_new_log(lines):
    evals = []
    processing = []
    for line in lines:
        m = PROMPT_PROCESSING_RE.search(line)
        if m:
            processing.append(
                {
                    "n_tokens": int(m.group(1)),
                    "progress": float(m.group(2)),
                    "seconds": float(m.group(3)),
                    "tokens_per_second": float(m.group(4)),
                    "line": line.rstrip(),
                }
            )
        m = PROMPT_EVAL_RE.search(line)
        if m:
            evals.append(
                {
                    "ms": float(m.group(1)),
                    "n_tokens": int(m.group(2)),
                    "tokens_per_second": float(m.group(3)),
                    "line": line.rstrip(),
                }
            )
    large_evals = [e for e in evals if e["n_tokens"] > 1000]
    return {
        "prompt_processing": processing,
        "prompt_eval": large_evals[-1] if large_evals else (evals[-1] if evals else None),
    }


def wait_for_new_eval(log_path, start_line, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        lines = log_path.read_text(errors="replace").splitlines()[start_line:]
        parsed = parse_new_log(lines)
        if parsed["prompt_eval"]:
            return parsed, lines
        time.sleep(0.5)
    lines = log_path.read_text(errors="replace").splitlines()[start_line:]
    return parse_new_log(lines), lines


def launch(config, raw_dir):
    stop_ollama_models()
    time.sleep(3)
    gpu = resolve_gpu_device()
    (raw_dir / "gpu_device.txt").write_text(f"resolved GPU device: {gpu}\n")
    vram_before = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader"],
        text=True,
        capture_output=True,
        check=False,
    ).stdout.strip()
    (raw_dir / "vram_before.txt").write_text(vram_before + "\n")
    log = (raw_dir / "server.log").open("w")
    proc = subprocess.Popen(["llama-server", *expand_flags(config, gpu)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    (ROOT / "results" / ".server.pid").write_text(str(proc.pid) + "\n")
    try:
        wait_healthy()
        vram_loaded = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader"],
            text=True,
            capture_output=True,
            check=False,
        ).stdout.strip()
        (raw_dir / "vram_loaded.txt").write_text(vram_loaded + "\n")
        return proc, log, vram_loaded
    except Exception:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        raise


def probe_config(config):
    raw_dir = RAW_ROOT / config
    raw_dir.mkdir(parents=True, exist_ok=True)
    proc = log_handle = None
    try:
        proc, log_handle, vram_loaded = launch(config, raw_dir)
        log_path = raw_dir / "server.log"
        trials = []
        for i in range(3):
            start_line = len(log_path.read_text(errors="replace").splitlines())
            prefix = random_prefix()
            body = chat(
                [
                    {
                        "role": "user",
                        "content": prefix + "\n\nSummarize the random prefix in one sentence.",
                    }
                ],
                max_tokens=32,
                timeout=900,
            )
            parsed, new_lines = wait_for_new_eval(log_path, start_line)
            trial = {
                "trial": i,
                "client_wall_s": body["_wall_s"],
                "usage": body.get("usage"),
                "server_prompt_eval": parsed["prompt_eval"],
                "server_prompt_processing": parsed["prompt_processing"],
                "raw_log_lines": new_lines,
            }
            trials.append(trial)
            (raw_dir / f"trial-{i}.json").write_text(json.dumps(trial, indent=2))
        tps = [t["server_prompt_eval"]["tokens_per_second"] for t in trials if t["server_prompt_eval"]]
        result = {
            "config": config,
            "vram_loaded": vram_loaded,
            "median_true_prefill_tps": round(statistics.median(tps), 1),
            "trials": trials,
        }
        (raw_dir / "summary.json").write_text(json.dumps(result, indent=2))
        return result
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if log_handle is not None:
            log_handle.close()


def main():
    results = {}
    for config in CONFIGS:
        print(f"probing {config}", flush=True)
        result = probe_config(config)
        results[config] = result
        OUT_PATH.write_text(json.dumps(results, indent=2))
        print(f"{config}: {result['median_true_prefill_tps']} t/s", flush=True)
    OUT_PATH.write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
