#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "stop.sh must run as root" >&2
  exit 1
fi

VM_NAME=isolated-qwen36
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

