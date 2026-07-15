#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -eq 0 ]]; then
  echo "build_image.sh must run without root" >&2
  exit 1
fi

STATE_DIR="$HOME/.local/share/isolated-model-vm"
BASE_IMAGE="$STATE_DIR/images/noble-server-cloudimg-amd64.img"
VM_DISK="$STATE_DIR/images/isolated-qwen36.prepared.qcow2"
MODEL="$STATE_DIR/models/Qwen3.6-35B-A3B-uncensored-heretic-Native-MTP-Preserved-Q3_K_L.gguf"
MMPROJ="$STATE_DIR/models/Qwen3.6-35B-A3B-uncensored-heretic-Native-MTP-Preserved-mmproj-BF16.gguf"
API_KEY="$STATE_DIR/api.key"
LLAMA_DIR="$HOME/.local/opt/llama.cpp-cuda-b9592"
CUDA_LIB="$HOME/.local/opt/cuda-pip-cu13/lib/python3.12/site-packages/nvidia/cu13/lib"
APPLIANCE="$STATE_DIR/appliance/root"
DEB_DIR="$STATE_DIR/offline-debs/archives"
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export SUPERMIN_KERNEL="$APPLIANCE/boot/vmlinuz-7.0.11-76070011-generic"
export SUPERMIN_MODULES="$APPLIANCE/usr/lib/modules/7.0.11-76070011-generic"
export SUPERMIN_KERNEL_VERSION=7.0.11-76070011-generic
exec > >(tee "$STATE_DIR/build-image.log") 2>&1

printf '%s  %s\n' \
  ffe6203da54deeb6db5d2a98a83f9ec8e55f149d3f7ba622e1abe5fa966ee3d6 "$BASE_IMAGE" \
  6bddab4c45de8718e4c30fed6d8ab9f71f68ff4509cf7683e578d312a5822d4b "$MODEL" \
  d6050bb82a0187e1b0655f1c5daef60c9479273fbd7402ff25d3137df2e071ce "$MMPROJ" \
  | sha256sum --check --strict
[[ -x "$LLAMA_DIR/bin/llama-server" ]]
[[ -f "$CUDA_LIB/libcudart.so.13" ]]
[[ -s "$API_KEY" ]]
[[ -f "$SUPERMIN_KERNEL" ]]
[[ -f "$SUPERMIN_MODULES/modules.dep" ]]
mkdir -p "$DEB_DIR/partial"
virt-cat -a "$BASE_IMAGE" /var/lib/dpkg/status >"$STATE_DIR/offline-debs/status"
apt-get \
  -o "Dir::State::status=$STATE_DIR/offline-debs/status" \
  -o "Dir::Cache::archives=$DEB_DIR" \
  -o Debug::NoLocking=1 \
  --download-only --no-install-recommends --assume-yes install \
  nvidia-driver-580-open socat qemu-guest-agent
DEBS=("$DEB_DIR"/*.deb)
[[ -e "${DEBS[0]}" ]]
sha256sum "${DEBS[@]}" >"$STATE_DIR/offline-debs/SHA256SUMS"
if [[ -e "$VM_DISK" ]]; then
  echo "Refusing to overwrite prepared image: $VM_DISK" >&2
  exit 1
fi

cleanup_incomplete_disk() {
  status=$?
  (( status == 0 )) || rm -f "$VM_DISK"
  exit "$status"
}
trap cleanup_incomplete_disk ERR

qemu-img create -f qcow2 "$VM_DISK" 80G
virt-resize --expand /dev/sda1 "$BASE_IMAGE" "$VM_DISK"
virt-customize -a "$VM_DISK" \
  --hostname isolated-qwen36 \
  --copy-in "$DEB_DIR":/tmp \
  --run-command 'export DEBIAN_FRONTEND=noninteractive; dpkg -i /tmp/archives/*.deb || apt-get --no-download --fix-broken install -y' \
  --run-command 'rm -rf /tmp/archives /var/lib/apt/lists/* /var/cache/apt/archives/*' \
  --run-command 'rm -f /etc/resolv.conf && install -m 000 /dev/null /etc/resolv.conf' \
  --mkdir /opt/models \
  --mkdir /opt/cuda \
  --mkdir /etc/llama \
  --mkdir /var/lib/llama \
  --copy-in "$MODEL":/opt/models \
  --copy-in "$MMPROJ":/opt/models \
  --copy-in "$API_KEY":/etc/llama \
  --copy-in "$LLAMA_DIR":/opt \
  --copy-in "$CUDA_LIB":/opt/cuda \
  --copy-in "$SCRIPT_DIR/guest/nvidia-driver-ready.service":/etc/systemd/system \
  --copy-in "$SCRIPT_DIR/guest/llama-server.service":/etc/systemd/system \
  --copy-in "$SCRIPT_DIR/guest/llama-vsock-proxy.service":/etc/systemd/system \
  --run-command 'mv /opt/llama.cpp-cuda-b9592 /opt/llama.cpp' \
  --run-command 'useradd --system --home-dir /var/lib/llama --shell /usr/sbin/nologin llm' \
  --run-command 'chown llm:llm /var/lib/llama' \
  --run-command 'chown root:llm /etc/llama/api.key && chmod 0440 /etc/llama/api.key' \
  --run-command 'chown -R root:root /opt/models /opt/llama.cpp /opt/cuda' \
  --run-command 'chmod -R go-w /opt/models /opt/llama.cpp /opt/cuda' \
  --run-command 'chmod 0444 /opt/models/*.gguf' \
  --run-command 'passwd --lock root' \
  --run-command 'rm -f /etc/netplan/*' \
  --run-command 'systemctl mask ssh.service ssh.socket systemd-networkd.service systemd-networkd.socket systemd-resolved.service NetworkManager.service NetworkManager-wait-online.service ModemManager.service apt-daily.service apt-daily.timer apt-daily-upgrade.service apt-daily-upgrade.timer unattended-upgrades.service' \
  --run-command 'systemctl enable qemu-guest-agent.service nvidia-driver-ready.service llama-server.service llama-vsock-proxy.service'

virt-cat -a "$VM_DISK" /etc/systemd/system/llama-server.service >/dev/null
virt-cat -a "$VM_DISK" /etc/systemd/system/llama-vsock-proxy.service >/dev/null
trap - ERR
