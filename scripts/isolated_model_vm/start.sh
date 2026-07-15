#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "start.sh must run as root" >&2
  exit 1
fi

VM_NAME=isolated-qwen36
terminate_gpu_users() {
  local devices=(/dev/nvidia*)
  [[ -e "${devices[0]}" ]] || return 0
  fuser -k -TERM "${devices[@]}" 2>/dev/null || true
  for _ in $(seq 1 10); do
    fuser -s "${devices[@]}" 2>/dev/null || return 0
    sleep 1
  done
  fuser -k -KILL "${devices[@]}" 2>/dev/null || true
}

if [[ $(virsh domstate "$VM_NAME") == running ]]; then
  runuser -u svankina -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user start isolated-model-vm-proxy.service
  exit 0
fi

restore_host_gpu_services() {
  modprobe nvidia 2>/dev/null || true
  modprobe nvidia_uvm 2>/dev/null || true
  modprobe nvidia_drm 2>/dev/null || true
  systemctl start nvidia-persistenced.service 2>/dev/null || true
  systemctl start plexmediaserver.service
  systemctl start homer-asr.service
  runuser -u ai-server -- env XDG_RUNTIME_DIR=/run/user/1011 systemctl --user start whisper-server.service
}
trap restore_host_gpu_services ERR INT TERM

systemctl stop homer-asr.service
systemctl stop plexmediaserver.service
runuser -u ai-server -- env XDG_RUNTIME_DIR=/run/user/1011 systemctl --user stop whisper-server.service
systemctl stop nvidia-persistenced.service 2>/dev/null || true
terminate_gpu_users
modprobe -r nvidia_drm nvidia_modeset nvidia_uvm nvidia
virsh start "$VM_NAME"
trap - ERR INT TERM

runuser -u svankina -- env XDG_RUNTIME_DIR=/run/user/1000 systemctl --user start isolated-model-vm-proxy.service
