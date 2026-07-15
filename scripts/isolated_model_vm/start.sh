#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "start.sh must run as root" >&2
  exit 1
fi

VM_NAME=isolated-qwen36
if [[ $(virsh domstate "$VM_NAME") == running ]]; then
  runuser -u svankina -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user start isolated-model-vm-proxy.service
  exit 0
fi

restore_host_gpu_services() {
  systemctl start nvidia-persistenced.service 2>/dev/null || true
  systemctl start homer-asr.service
  runuser -u ai-server -- env XDG_RUNTIME_DIR=/run/user/1011 systemctl --user start whisper-server.service
}
trap restore_host_gpu_services ERR INT TERM

systemctl stop homer-asr.service
runuser -u ai-server -- env XDG_RUNTIME_DIR=/run/user/1011 systemctl --user stop whisper-server.service
systemctl stop nvidia-persistenced.service 2>/dev/null || true
virsh start "$VM_NAME"
trap - ERR INT TERM

runuser -u svankina -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user start isolated-model-vm-proxy.service
