#!/usr/bin/env bash
# Build the ASV5211 driver as a normal out-of-tree kernel module.
#
# Usage:
#   ./build_dvb.sh [--kdir DIR] [--kernel-src DIR] [--install]
#
# KDIR is the configured kernel build tree (generated headers and
# Module.symvers). KERNEL_SRC supplies the internal DVB-USB v2 header.
# For an in-tree build they can be the same directory.

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
KDIR="/lib/modules/$(uname -r)/build"
KERNEL_SRC="${KERNEL_SRC:-}"
INSTALL=0

usage() {
    cat <<'USAGE'
Usage: ./build_dvb.sh [options]

Options:
  --kdir DIR       Configured kernel build directory
  --kernel-src DIR Matching full kernel source tree
  --install        Install module and firmware for the kernel in KDIR
  -h, --help       Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --kdir)
            [[ $# -ge 2 ]] || { echo "Missing value for --kdir" >&2; exit 2; }
            KDIR="$2"; shift 2 ;;
        --kernel-src)
            [[ $# -ge 2 ]] || { echo "Missing value for --kernel-src" >&2; exit 2; }
            KERNEL_SRC="$2"; shift 2 ;;
        --install) INSTALL=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

KERNEL_SRC="${KERNEL_SRC:-$KDIR}"
DRIVER_DIR="$ROOT_DIR/driver"
FIRMWARE="$ROOT_DIR/firmware/ub320i.fw"
DVB_USB_HEADER="$KERNEL_SRC/drivers/media/usb/dvb-usb-v2/dvb_usb.h"

[[ -d "$KDIR" ]] || { echo "ERROR: kernel build directory not found: $KDIR" >&2; exit 1; }
[[ -f "$DVB_USB_HEADER" ]] || {
    echo "ERROR: internal DVB-USB header not found: $DVB_USB_HEADER" >&2
    echo "Pass --kernel-src pointing to the matching kernel source tree." >&2
    exit 1
}
[[ -f "$FIRMWARE" ]] || { echo "ERROR: firmware not found: $FIRMWARE" >&2; exit 1; }

KERNEL_RELEASE="$(make -s -C "$KDIR" kernelrelease)"
[[ -n "$KERNEL_RELEASE" ]] || { echo "ERROR: could not determine kernel release from $KDIR" >&2; exit 1; }

echo "=== Building asv5211 for kernel $KERNEL_RELEASE ==="
make -C "$KDIR" M="$DRIVER_DIR" \
    EXTRA_CFLAGS="-I$KERNEL_SRC/drivers/media/usb/dvb-usb-v2" modules

echo "=== Build complete ==="
echo "Module: $DRIVER_DIR/asv5211.ko"

if [[ "$INSTALL" -eq 1 ]]; then
    echo "=== Installing module and firmware for $KERNEL_RELEASE ==="
    sudo make -C "$KDIR" M="$DRIVER_DIR" INSTALL_MOD_DIR=updates modules_install
    sudo install -D -m 0644 "$FIRMWARE" /lib/firmware/dvb-usb-asv5211.fw
    sudo depmod -a "$KERNEL_RELEASE"
    echo "=== Installation complete ==="
fi
