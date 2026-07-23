#!/usr/bin/env python3
"""Temporarily enable or disable outbound networking for isolated-qwen36."""

import argparse
import base64
import json
import subprocess
import sys
import time
from collections.abc import Sequence

VM = "isolated-qwen36"
LIBVIRT_NETWORK = "default"
NETWORK_CONFIG = "/etc/systemd/network/80-temporary-access.network"
VIRSH = ("virsh", "-c", "qemu:///system")


class NetworkAccessError(RuntimeError):
    pass


def run(command: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=True)
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise NetworkAccessError(f"{' '.join(command)} failed: {detail}")
    return result


def virsh(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run((*VIRSH, *args), check=check)


def qga(execute: str, arguments: dict | None = None) -> dict | int:
    request: dict[str, object] = {"execute": execute}
    if arguments is not None:
        request["arguments"] = arguments
    response = virsh("qemu-agent-command", VM, json.dumps(request))
    payload = json.loads(response.stdout)
    if "error" in payload:
        raise NetworkAccessError(f"guest agent {execute} failed: {payload['error']}")
    return payload["return"]


def guest_exec(path: str, args: Sequence[str], timeout: float = 60) -> tuple[int, str, str]:
    started = qga(
        "guest-exec",
        {"path": path, "arg": list(args), "capture-output": True},
    )
    if not isinstance(started, dict) or "pid" not in started:
        raise NetworkAccessError(f"guest agent returned no pid for {path}")
    pid = started["pid"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = qga("guest-exec-status", {"pid": pid})
        if isinstance(status, dict) and status.get("exited"):
            stdout = base64.b64decode(status.get("out-data", "")).decode(errors="replace").strip()
            stderr = base64.b64decode(status.get("err-data", "")).decode(errors="replace").strip()
            return int(status.get("exitcode", 1)), stdout, stderr
        time.sleep(0.25)
    raise NetworkAccessError(f"guest command timed out: {path}")


def require_guest_success(path: str, args: Sequence[str], timeout: float = 60) -> str:
    code, stdout, stderr = guest_exec(path, args, timeout)
    if code != 0:
        raise NetworkAccessError(f"guest command failed ({code}): {path} {' '.join(args)}: {stderr or stdout}")
    return stdout


def guest_write(path: str, content: bytes, mode: str) -> None:
    handle = qga("guest-file-open", {"path": path, "mode": "w"})
    if not isinstance(handle, int):
        raise NetworkAccessError(f"guest agent returned invalid file handle for {path}")
    try:
        result = qga(
            "guest-file-write",
            {"handle": handle, "buf-b64": base64.b64encode(content).decode()},
        )
        if not isinstance(result, dict) or result.get("count") != len(content):
            raise NetworkAccessError(f"short guest write to {path}: {result}")
    finally:
        qga("guest-file-close", {"handle": handle})
    require_guest_success("/usr/bin/chmod", [mode, path])


def host_interfaces() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    output = virsh("domiflist", VM).stdout
    for line in output.splitlines()[2:]:
        fields = line.split()
        if len(fields) >= 5:
            _target, kind, source, _model, mac = fields[:5]
            rows.append((kind, source, mac))
    return rows


def guest_interfaces() -> list[str]:
    output = require_guest_success("/usr/bin/ls", ["-1", "/sys/class/net"])
    return sorted(name for name in output.splitlines() if name and name != "lo")


def wait_for_guest_interface(timeout: float = 15) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        interfaces = guest_interfaces()
        if len(interfaces) == 1:
            return interfaces[0]
        if len(interfaces) > 1:
            raise NetworkAccessError(f"expected one temporary guest interface, found: {interfaces}")
        time.sleep(0.5)
    raise NetworkAccessError("temporary network interface did not appear in the guest")


def disable(*, quiet: bool = False) -> None:
    if virsh("domstate", VM).stdout.strip() != "running":
        raise NetworkAccessError(f"{VM} is not running")

    require_guest_success(
        "/usr/bin/systemctl",
        ["stop", "systemd-networkd.service", "systemd-networkd.socket", "systemd-resolved.service"],
    )
    require_guest_success("/usr/bin/rm", ["-f", NETWORK_CONFIG, "/etc/resolv.conf"])
    guest_write("/etc/resolv.conf", b"", "0000")
    require_guest_success(
        "/usr/bin/systemctl",
        ["mask", "systemd-networkd.service", "systemd-networkd.socket", "systemd-resolved.service"],
    )

    for kind, source, mac in host_interfaces():
        if kind == "network" and source == LIBVIRT_NETWORK:
            virsh("detach-interface", VM, "network", "--mac", mac, "--live")

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if not guest_interfaces():
            routes = require_guest_success("/usr/sbin/ip", ["route", "show"])
            if routes:
                raise NetworkAccessError(f"guest still has IP routes after detach: {routes}")
            if not quiet:
                print(f"{VM}: network disabled; guest has loopback only and no IP routes")
            return
        time.sleep(0.5)
    raise NetworkAccessError("temporary guest interface did not disappear")


def enable() -> None:
    if virsh("domstate", VM).stdout.strip() != "running":
        raise NetworkAccessError(f"{VM} is not running")
    network_info = virsh("net-info", LIBVIRT_NETWORK).stdout
    if "Active:         yes" not in network_info:
        raise NetworkAccessError(f"libvirt network {LIBVIRT_NETWORK!r} is not active")

    existing = host_interfaces()
    unexpected = [row for row in existing if row[:2] != ("network", LIBVIRT_NETWORK)]
    if unexpected:
        raise NetworkAccessError(f"refusing to modify VM with unexpected interfaces: {unexpected}")

    try:
        if not existing:
            virsh("attach-interface", VM, "network", LIBVIRT_NETWORK, "--model", "virtio", "--live")
        interface = wait_for_guest_interface()
        config = f"[Match]\nName={interface}\n\n[Link]\nMTUBytes=1400\n\n[Network]\nDHCP=yes\n".encode()
        require_guest_success("/usr/bin/mkdir", ["-p", "/etc/systemd/network"])
        guest_write(NETWORK_CONFIG, config, "0644")
        require_guest_success(
            "/usr/bin/systemctl",
            ["unmask", "systemd-networkd.service", "systemd-networkd.socket", "systemd-resolved.service"],
        )
        require_guest_success("/usr/bin/rm", ["-f", "/etc/resolv.conf"])
        require_guest_success(
            "/usr/bin/ln",
            ["-s", "/run/systemd/resolve/stub-resolv.conf", "/etc/resolv.conf"],
        )
        require_guest_success(
            "/usr/bin/systemctl",
            ["start", "systemd-resolved.service", "systemd-networkd.service"],
        )

        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            routes = require_guest_success("/usr/sbin/ip", ["route", "show"])
            if any(line.startswith("default ") for line in routes.splitlines()):
                print(f"{VM}: network enabled temporarily on {interface}")
                print(routes)
                return
            time.sleep(1)
        raise NetworkAccessError("guest did not acquire a DHCP default route")
    except Exception:
        disable(quiet=True)
        raise


def status() -> None:
    state = virsh("domstate", VM).stdout.strip()
    print(f"VM: {state}")
    if state != "running":
        return
    print(f"Host interfaces: {host_interfaces() or 'none'}")
    print(f"Guest interfaces: {guest_interfaces() or 'loopback only'}")
    routes = require_guest_success("/usr/sbin/ip", ["route", "show"])
    print("Guest routes:")
    print(routes or "none")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("enable", "disable", "status"))
    args = parser.parse_args()
    try:
        {"enable": enable, "disable": disable, "status": status}[args.action]()
    except NetworkAccessError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
