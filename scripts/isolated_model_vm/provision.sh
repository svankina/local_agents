#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "provision.sh must run as root" >&2
  exit 1
fi

VM_NAME=isolated-qwen36
STATE_DIR=/home/svankina/.local/share/isolated-model-vm
PREPARED_DISK="$STATE_DIR/images/${VM_NAME}.prepared.qcow2"
VM_DISK="/var/lib/libvirt/images/${VM_NAME}.qcow2"
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec > >(tee "$STATE_DIR/provision.log") 2>&1

[[ -f "$PREPARED_DISK" ]]
qemu-img check "$PREPARED_DISK"
if virsh dominfo "$VM_NAME" >/dev/null 2>&1 || [[ -e "$VM_DISK" ]]; then
  echo "Refusing to overwrite existing VM or disk: $VM_NAME" >&2
  exit 1
fi

cleanup_incomplete_install() {
  status=$?
  if (( status != 0 )) && ! virsh dominfo "$VM_NAME" >/dev/null 2>&1; then
    rm -f "$VM_DISK"
  fi
  exit "$status"
}
trap cleanup_incomplete_install ERR

cp --reflink=auto --sparse=always "$PREPARED_DISK" "$VM_DISK"
chown libvirt-qemu:kvm "$VM_DISK"
chmod 0600 "$VM_DISK"

XML=$(mktemp)
trap 'rm -f "$XML"' EXIT
virt-install \
  --name "$VM_NAME" \
  --memory 16384 \
  --vcpus 12 \
  --cpu host-passthrough \
  --machine q35 \
  --osinfo ubuntu24.04 \
  --boot uefi,firmware.feature0.name=enrolled-keys,firmware.feature0.enabled=no,firmware.feature1.name=secure-boot,firmware.feature1.enabled=no \
  --import \
  --disk "path=$VM_DISK,bus=scsi,cache=none,discard=unmap" \
  --controller type=scsi,model=virtio-scsi \
  --hostdev 0000:42:00.0 \
  --hostdev 0000:42:00.1 \
  --network none \
  --channel unix,target.type=virtio,target.name=org.qemu.guest_agent.0 \
  --rng /dev/urandom \
  --graphics none \
  --console pty,target.type=serial \
  --noautoconsole \
  --print-xml >"$XML"

if grep -q '<interface' "$XML"; then
  echo 'Refusing VM definition containing a network interface' >&2
  exit 1
fi
virsh define "$XML"
virsh autostart --disable "$VM_NAME" >/dev/null 2>&1 || true
trap - ERR
