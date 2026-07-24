#!/usr/bin/env bash
set -euo pipefail


VM_NAME=isolated-qwen36
VIRSH=(virsh -c qemu:///system)
if [[ $("${VIRSH[@]}" domstate "$VM_NAME") == running ]]; then
  "${VIRSH[@]}" shutdown "$VM_NAME"
  for _ in $(seq 1 60); do
    [[ $("${VIRSH[@]}" domstate "$VM_NAME") == "shut off" ]] && break
    sleep 1
  done
fi
if [[ $("${VIRSH[@]}" domstate "$VM_NAME") != "shut off" ]]; then
  echo "VM did not shut down within 60 seconds; refusing a forced power-off" >&2
  exit 1
fi

