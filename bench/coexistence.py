"""Task 12 coexistence test: C5 senior plus C1 worker under concurrent load."""

import concurrent.futures
import json
import pathlib
import re
import subprocess
import time

from common import chat, parse_timings, wait_healthy

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = pathlib.Path.home() / ".cache" / "llama.cpp"
RAW = ROOT / "results" / "raw" / "coexistence"
OUT = ROOT / "results" / "coexistence.json"

PROMPT_1K = (
    "You are summarizing a design document. "
    + "The system ingests events, deduplicates them, and routes them to workers. " * 60
)


def run(cmd, check=True):
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=check)


def stop_ollama_models():
    try:
        ps = run(["ollama", "ps"], check=False)
    except FileNotFoundError:
        return
    for line in ps.stdout.splitlines()[1:]:
        parts = line.split()
        if parts:
            subprocess.run(["ollama", "stop", parts[0]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def resolve_gpu_device():
    out = run(["llama-server", "--list-devices"]).stdout
    for line in out.splitlines():
        if "RTX 3090" in line:
            m = re.search(r"Vulkan[0-9]+", line)
            if m:
                return m.group(0)
    raise RuntimeError("could not resolve RTX 3090 Ti Vulkan device")


def expand_flags(config, gpu, port, extra=()):
    configs = json.loads((ROOT / "bench" / "configs.json").read_text())
    common = configs["_common"].replace("--port 8089", f"--port {port}")
    flags = f"{common} {configs[config]} {' '.join(extra)}"
    return flags.replace("<CACHE>", str(CACHE)).replace("<GPU>", gpu).split()


def gpu_memory_snapshot():
    total = run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader"], check=False).stdout.strip()
    apps = run(
        ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader"],
        check=False,
    ).stdout.strip()
    table = run(["nvidia-smi"], check=False).stdout
    return {"total": total, "compute_apps": apps, "nvidia_smi": table}


def launch(name, config, port, gpu, extra=()):
    log_path = RAW / f"{name}.server.log"
    log = log_path.open("w")
    proc = subprocess.Popen(["llama-server", *expand_flags(config, gpu, port, extra)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    wait_healthy(base=f"http://127.0.0.1:{port}")
    return {"name": name, "config": config, "port": port, "pid": proc.pid, "proc": proc, "log": log}


def one_request(name, base):
    body = chat(
        [{"role": "user", "content": PROMPT_1K + "\nSummarize in detail."}],
        max_tokens=256,
        base=base,
        timeout=900,
    )
    timings = parse_timings(body)
    timings["client_wall_s"] = body["_wall_s"]
    timings["usage"] = body.get("usage")
    timings["name"] = name
    return timings


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    stop_ollama_models()
    time.sleep(3)
    gpu = resolve_gpu_device()
    (RAW / "gpu_device.txt").write_text(f"resolved GPU device: {gpu}\n")
    before = gpu_memory_snapshot()
    servers = []
    try:
        senior = launch("senior-c5", "C5-gemma26b-cmoe", 8089, gpu)
        servers.append(senior)
        after_senior = gpu_memory_snapshot()
        worker = launch(
            "worker-c1-par2",
            "C1-gemma12b-base",
            8090,
            gpu,
            extra=("--parallel", "2", "--cache-type-k", "q8_0", "--cache-type-v", "q8_0"),
        )
        servers.append(worker)
        loaded = gpu_memory_snapshot()
        (RAW / "memory-before.json").write_text(json.dumps(before, indent=2))
        (RAW / "memory-after-senior.json").write_text(json.dumps(after_senior, indent=2))
        (RAW / "memory-loaded.json").write_text(json.dumps(loaded, indent=2))

        t0 = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futures = [
                ex.submit(one_request, "senior", "http://127.0.0.1:8089"),
                ex.submit(one_request, "worker-0", "http://127.0.0.1:8090"),
                ex.submit(one_request, "worker-1", "http://127.0.0.1:8090"),
            ]
            requests = [f.result() for f in futures]
        wall_s = round(time.monotonic() - t0, 3)
        under_load = gpu_memory_snapshot()
        (RAW / "memory-after-load.json").write_text(json.dumps(under_load, indent=2))
        (RAW / "requests.json").write_text(json.dumps(requests, indent=2))

        senior_results = [r for r in requests if r["name"] == "senior"]
        worker_results = [r for r in requests if r["name"].startswith("worker")]
        worker_tokens = sum(r.get("predicted_n") or 0 for r in worker_results)
        worker_wall = max(r["client_wall_s"] for r in worker_results)
        result = {
            "gpu_device": gpu,
            "senior": {"config": "C5-gemma26b-cmoe", "port": 8089, "pid": senior["pid"]},
            "worker": {
                "config": "C1-gemma12b-base",
                "port": 8090,
                "pid": worker["pid"],
                "extra_flags": ["--parallel", "2", "--cache-type-k", "q8_0", "--cache-type-v", "q8_0"],
            },
            "memory_before": before,
            "memory_after_senior": after_senior,
            "memory_loaded": loaded,
            "memory_after_load": under_load,
            "concurrent_wall_s": wall_s,
            "requests": requests,
            "senior_decode_tps": senior_results[0]["decode_tps"],
            "worker_per_stream_decode_tps": [r["decode_tps"] for r in worker_results],
            "worker_aggregate_decode_tps": round(worker_tokens / worker_wall, 1),
            "fits_22_5gb_budget": parse_mib(loaded["total"]) <= 22500,
        }
        OUT.write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
    finally:
        for server in reversed(servers):
            proc = server["proc"]
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            server["log"].close()


def parse_mib(value):
    m = re.search(r"(\d+)", value or "")
    return int(m.group(1)) if m else 0


if __name__ == "__main__":
    main()
