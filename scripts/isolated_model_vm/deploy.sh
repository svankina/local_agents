#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "deploy.sh must run as root" >&2
  exit 1
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
STATE_DIR=/home/svankina/.local/share/isolated-model-vm
exec > >(tee "$STATE_DIR/deploy.log") 2>&1

if ! virsh dominfo isolated-qwen36 >/dev/null 2>&1; then
  if [[ ! -f "$STATE_DIR/images/isolated-qwen36.prepared.qcow2" ]]; then
    runuser -u svankina -- env HOME=/home/svankina "$SCRIPT_DIR/build_image.sh"
  fi
  "$SCRIPT_DIR/provision.sh"
fi
"$SCRIPT_DIR/start.sh"
