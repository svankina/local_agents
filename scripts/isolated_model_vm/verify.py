#!/usr/bin/env python3
import atexit
import base64
import json
import subprocess
import sys
import socket
import time
import urllib.request
import urllib.error
from pathlib import Path

VM = "isolated-qwen36"
REMOTE_API_PORT = 8089
ROOT = Path(__file__).resolve().parents[2]
IMAGE = ROOT / "docs/article/assets/fastfetch-3090ti.png"
API_KEY = Path.home() / ".local/share/isolated-model-vm/api.key"
MODEL = "/opt/models/Gemma4-31B-QAT-Uncensored-HauhauCS-Balanced-Q4_K_M.gguf"
TOKEN = API_KEY.read_text().strip()


def start_api_tunnel() -> tuple[subprocess.Popen[str], str]:
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        local_port = reservation.getsockname()[1]

    tunnel = subprocess.Popen(
        [
            "ssh",
            "-N",
            "-o",
            "BatchMode=yes",
            "-o",
            "ExitOnForwardFailure=yes",
            "-L",
            f"127.0.0.1:{local_port}:127.0.0.1:{REMOTE_API_PORT}",
            VM,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    for _ in range(50):
        if tunnel.poll() is not None:
            error = tunnel.stderr.read() if tunnel.stderr else ""
            raise RuntimeError(f"SSH API tunnel exited: {error.strip()}")
        try:
            with socket.create_connection(("127.0.0.1", local_port), timeout=0.2):
                return tunnel, f"http://127.0.0.1:{local_port}"
        except OSError:
            time.sleep(0.1)
    tunnel.terminate()
    raise TimeoutError("SSH API tunnel did not become ready")


TUNNEL, BASE = start_api_tunnel()
atexit.register(TUNNEL.terminate)


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def qga(path: str, args: list[str]) -> tuple[int, str, str]:
    request = {
        "execute": "guest-exec",
        "arguments": {"path": path, "arg": args, "capture-output": True},
    }
    started = json.loads(run("virsh", "qemu-agent-command", VM, json.dumps(request)))
    pid = started["return"]["pid"]
    for _ in range(120):
        status_request = {
            "execute": "guest-exec-status",
            "arguments": {"pid": pid},
        }
        status = json.loads(run("virsh", "qemu-agent-command", VM, json.dumps(status_request)))["return"]
        if status.get("exited"):
            stdout = base64.b64decode(status.get("out-data", "")).decode(errors="replace")
            stderr = base64.b64decode(status.get("err-data", "")).decode(errors="replace")
            return status.get("exitcode", 1), stdout.strip(), stderr.strip()
        time.sleep(0.25)
    raise TimeoutError(f"guest command timed out: {path}")


def request(path: str, payload: dict | None = None, timeout: int = 600) -> dict:
    body = None if payload is None else json.dumps(payload).encode()
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        **({} if body is None else {"Content-Type": "application/json"}),
    }
    with urllib.request.urlopen(urllib.request.Request(BASE + path, body, headers), timeout=timeout) as response:
        return json.load(response)


if run("virsh", "domstate", VM) != "running":
    raise RuntimeError(f"{VM} is not running")

xml = run("virsh", "dumpxml", VM)
if "<interface" in xml:
    raise AssertionError("VM XML contains a network interface")

code, links, error = qga("/usr/bin/ls", ["-1", "/sys/class/net"])
if code != 0 or links.splitlines() != ["lo"]:
    raise AssertionError(f"guest network devices are not loopback-only: {links!r} {error!r}")
code, routes, error = qga("/usr/sbin/ip", ["route", "show"])
if code != 0 or routes:
    raise AssertionError(f"guest has an IP route: {routes!r} {error!r}")
code, gpu, error = qga("/usr/bin/nvidia-smi", ["--query-gpu=name,memory.total", "--format=csv,noheader"])
if code != 0 or "RTX 3090 Ti" not in gpu:
    raise AssertionError(f"passed-through GPU unavailable: {gpu!r} {error!r}")
code, model_mode, error = qga("/usr/bin/stat", ["-c", "%U:%G %a", MODEL])
if code != 0 or model_mode != "root:root 444":
    raise AssertionError(f"model permissions are not locked down: {model_mode!r} {error!r}")
code, _, error = qga("/usr/sbin/runuser", ["-u", "llm", "--", "/usr/bin/test", "-w", MODEL])
if code != 1:
    raise AssertionError(f"llama service user can write the model: exit={code} {error!r}")
code, api_mode, error = qga("/usr/bin/stat", ["-c", "%U:%G %a", "/etc/llama/api.key"])
if code != 0 or api_mode != "root:llm 440":
    raise AssertionError(f"API key permissions are not locked down: {api_mode!r} {error!r}")

for _ in range(180):
    try:
        health = request("/health", timeout=2)
        if health.get("status") == "ok":
            break
    except Exception:
        time.sleep(2)
else:
    raise TimeoutError("llama-server did not become healthy")
unauthenticated_probe = urllib.request.Request(
    BASE + "/v1/chat/completions",
    b"{}",
    {"Content-Type": "application/json"},
)
try:
    urllib.request.urlopen(unauthenticated_probe, timeout=2)
except urllib.error.HTTPError as auth_error:
    if auth_error.code != 401:
        raise AssertionError(f"unauthenticated API returned HTTP {auth_error.code}, expected 401") from auth_error
else:
    raise AssertionError("unauthenticated API request succeeded")


props = request("/props")
context = props.get("default_generation_settings", {}).get("n_ctx")
if context != 262144:
    raise AssertionError(f"server context is {context}, expected 262144")

image_url = "data:image/png;base64," + base64.b64encode(IMAGE.read_bytes()).decode()
vision = request(
    "/v1/chat/completions",
    {
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Read the GPU 2 line in this screenshot. Reply with only the GPU model."},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        }],
        "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False},
        "max_tokens": 64,
    },
)
answer = vision["choices"][0]["message"]["content"]
if "3090" not in answer:
    raise AssertionError(f"vision response did not identify the GPU: {answer!r}")

result = {
    "vm": VM,
    "network_devices": links.splitlines(),
    "routes": [],
    "gpu": gpu,
    "context_tokens": context,
    "unauthenticated_status": 401,
    "health": health,
    "model_permissions": model_mode,
    "api_key_permissions": api_mode,
    "model_writable_by_service": False,
    "vision_answer": answer,
}
json.dump(result, sys.stdout, indent=2)
print()
