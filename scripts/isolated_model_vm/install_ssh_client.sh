#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -eq 0 ]]; then
  echo 'install_ssh_client.sh must run as the desktop user, not root' >&2
  exit 1
fi
command -v socat >/dev/null

SSH_DIR=${HOME}/.ssh
CONFIG=${SSH_DIR}/config
install -d -m 0700 "$SSH_DIR"
touch "$CONFIG"
chmod 0600 "$CONFIG"

python3 - "$CONFIG" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
block = """Host isolated-qwen36
    HostName isolated-qwen36
    User chat
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
    ProxyCommand socat STDIO VSOCK-CONNECT:36:2222
    HostKeyAlias isolated-qwen36-vsock
    StrictHostKeyChecking accept-new
"""
lines = text.splitlines(keepends=True)
start = next((i for i, line in enumerate(lines) if line.strip() == "Host isolated-qwen36"), None)
if start is None:
    if text and not text.endswith("\n"):
        text += "\n"
    if text and not text.endswith("\n\n"):
        text += "\n"
    path.write_text(text + block)
else:
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("Host ")), len(lines))
    lines[start:end] = [block]
    path.write_text("".join(lines))
PY

ssh -G -T isolated-qwen36 >/dev/null
echo 'Installed: ssh isolated-qwen36'
