#!/usr/bin/env bash
set -euo pipefail

VM_NAME=isolated-qwen36
VFIO_CONFIG=/etc/modprobe.d/vfio-qwen.conf
INITRAMFS_MODULES=/etc/initramfs-tools/modules
GPU_ADDRESS=0000:42:00.0
AUDIO_ADDRESS=0000:42:00.1
GPU_ID=10de:2203
AUDIO_ID=10de:1aef
KERNEL_OPTION="vfio-pci.ids=$GPU_ID,$AUDIO_ID"

current_driver() {
  local address=$1
  local link="/sys/bus/pci/devices/$address/driver"
  if [[ -L $link ]]; then
    basename "$(readlink -f "$link")"
  else
    printf '%s\n' unbound
  fi
}
status() {
  printf 'GPU driver: %s\n' "$(current_driver "$GPU_ADDRESS")"
  printf 'Audio driver: %s\n' "$(current_driver "$AUDIO_ADDRESS")"
  local ready=true module
  [[ -e $VFIO_CONFIG ]] || ready=false
  for module in vfio vfio_pci vfio_iommu_type1; do
    grep -qxF "$module" "$INITRAMFS_MODULES" || ready=false
  done
  grep -qF "$KERNEL_OPTION" /etc/kernelstub/configuration || ready=false
  if [[ $ready == true ]]; then
    echo 'Next boot mode: VM (vfio-pci)'
  elif [[ -e $VFIO_CONFIG ]]; then
    echo 'Next boot mode: incomplete VFIO configuration; do not start the VM'
  else
    echo 'Next boot mode: host (NVIDIA)'
  fi
}

require_root() {
  if [[ ${EUID} -ne 0 ]]; then
    echo "gpu_mode.sh $1 must run as root" >&2
    exit 1
  fi
}

require_vm_stopped() {
  if virsh dominfo "$VM_NAME" >/dev/null 2>&1 &&
     [[ $(virsh domstate "$VM_NAME") != "shut off" ]]; then
    echo "Refusing to change GPU boot mode while $VM_NAME is running" >&2
    exit 1
  fi
}

make_domain_static() (
  virsh dominfo "$VM_NAME" >/dev/null 2>&1 || return 0
  local xml
  xml=$(mktemp)
  trap 'rm -f "$xml"' EXIT
  virsh dumpxml --inactive "$VM_NAME" >"$xml"
  python3 - "$xml" <<'PY'
import sys
import xml.etree.ElementTree as ET

path = sys.argv[1]
tree = ET.parse(path)
root = tree.getroot()
for hostdev in root.findall("./devices/hostdev[@type='pci']"):
    hostdev.set("managed", "no")
tree.write(path, encoding="unicode")
PY
  virsh define "$xml" >/dev/null
)

configure_vm_mode() {
  require_root vm
  require_vm_stopped
  install -d -m 0755 /etc/modprobe.d
  cat >"$VFIO_CONFIG" <<EOF
# Keep the RTX 3090 Ti bound to VFIO from boot. Never hot-unbind the NVIDIA driver.
options vfio-pci ids=$GPU_ID,$AUDIO_ID disable_idle_d3=1 disable_vga=1
softdep nvidia pre: vfio-pci
softdep nvidia_drm pre: vfio-pci
softdep nvidia_modeset pre: vfio-pci
softdep snd_hda_intel pre: vfio-pci
EOF
  for module in vfio vfio_pci vfio_iommu_type1; do
    grep -qxF "$module" "$INITRAMFS_MODULES" || printf '%s\n' "$module" >>"$INITRAMFS_MODULES"
  done
  make_domain_static
  kernelstub --add-options "$KERNEL_OPTION"
  update-initramfs -u
  echo 'VM GPU mode configured. Reboot is required; no live driver detach was attempted.'
}

configure_host_mode() {
  require_root host
  require_vm_stopped
  rm -f "$VFIO_CONFIG"
  kernelstub --delete-options "$KERNEL_OPTION"
  update-initramfs -u
  echo 'Host GPU mode configured. Reboot is required; no live driver rebind was attempted.'
}

case ${1:-status} in
  status) status ;;
  vm) configure_vm_mode ;;
  host) configure_host_mode ;;
  *) echo "Usage: $0 {status|vm|host}" >&2; exit 2 ;;
esac
