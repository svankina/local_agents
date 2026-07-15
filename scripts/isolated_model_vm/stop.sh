#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "stop.sh must run as root" >&2
  exit 1
fi

VM_NAME=isolated-qwen36
runuser -u svankina -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user stop isolated-model-vm-proxy.service || true
if [[ $(virsh domstate "$VM_NAME") == running ]]; then
  virsh shutdown "$VM_NAME"
  for _ in $(seq 1 60); do
    [[ $(virsh domstate "$VM_NAME") == "shut off" ]] && break
    sleep 1
  done
fi
if [[ $(virsh domstate "$VM_NAME") != "shut off" ]]; then
  echo "VM did not shut down within 60 seconds; refusing a forced power-off" >&2
  exit 1
fi

systemctl start nvidia-persistenced.service 2>/dev/null || true
systemctl start homer-asr.service
runuser -u ai-server -- env XDG_RUNTIME_DIR=/run/user/1011 systemctl --user start whisper-server.service
