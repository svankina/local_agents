#!/usr/bin/env bash
set -euo pipefail


VM_NAME=isolated-qwen36
VIRSH=(virsh -c qemu:///system)
GPU_ADDRESS=0000:42:00.0
AUDIO_ADDRESS=0000:42:00.1

current_driver() {
  local address=$1
  local link="/sys/bus/pci/devices/$address/driver"
  [[ -L $link ]] && basename "$(readlink -f "$link")" || printf '%s\n' unbound
}

if [[ $("${VIRSH[@]}" domstate "$VM_NAME") == running ]]; then
  exit 0
fi

gpu_driver=$(current_driver "$GPU_ADDRESS")
audio_driver=$(current_driver "$AUDIO_ADDRESS")
if [[ $gpu_driver != vfio-pci || $audio_driver != vfio-pci ]]; then
  echo "Refusing unsafe live GPU detach: $GPU_ADDRESS uses $gpu_driver; $AUDIO_ADDRESS uses $audio_driver." >&2
  echo "Run gpu_mode.sh vm, reboot, then start the VM. Dynamic NVIDIA/VFIO rebinding is prohibited." >&2
  exit 1
fi

"${VIRSH[@]}" start "$VM_NAME"
