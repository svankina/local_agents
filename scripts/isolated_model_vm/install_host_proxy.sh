#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -eq 0 ]]; then
  echo "install_host_proxy.sh must run as the desktop user, not root" >&2
  exit 1
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
install -m 0644 "$SCRIPT_DIR/host/isolated-model-vm-proxy.service" "$UNIT_DIR/isolated-model-vm-proxy.service"
systemctl --user daemon-reload
systemctl --user enable isolated-model-vm-proxy.service
