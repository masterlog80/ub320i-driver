#!/bin/bash
# Build the asv5211 DVB-USB out-of-tree module.
#
# This script creates a self-contained build environment under a staging
# directory instead of modifying the installed kernel tree.
#
# Usage:
#   ./build_dvb.sh [options]
#
# Options:
#   --kernel-src DIR   Kernel source tree (default: ~/dvb-driver-build)
#   --staging DIR      Staging build directory (default: ~/dvb-build-staging)
#   --install          Copy the resulting module into the running kernel's
#                      module directory (requires sudo)
#
set -euo pipefail

# ---------- Defaults -------------------------------------------------------
KERNEL_SRC="${HOME}/dvb-driver-build"
STAGING="${HOME}/dvb-build-staging"
INSTALL=0

# ---------- Parse arguments ------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --kernel-src)  KERNEL_SRC="$2"; shift 2 ;;
        --staging)     STAGING="$2";    shift 2 ;;
        --install)     INSTALL=1;        shift   ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

if [[ ! -d "$KERNEL_SRC" ]]; then
    echo "ERROR: Kernel source not found at $KERNEL_SRC" >&2
    exit 1
fi

# ---------- Step 1: Create a clean staging tree ----------------------------
echo "=== Preparing staging directory: $STAGING ==="
rm -rf "$STAGING"
mkdir -p "$STAGING"

# Mirror only the media subsystem from the kernel source
for subdir in \
    drivers/media/dvb-core \
    drivers/media/dvb-frontends \
    drivers/media/usb/dvb-usb-v2 \
    drivers/media/usb/dvb-usb \
    drivers/media/mc \
    drivers/media/i2c \
    drivers/media/common \
    drivers/media/rc \
    drivers/media/tuners \
    include/media \
    include/uapi/linux/dvb \
    include/linux \
    include/uapi/linux \
    include/uapi
do
    src="$KERNEL_SRC/$subdir"
    if [[ -d "$src" ]]; then
        mkdir -p "$STAGING/$subdir"
        cp -r "$src"/. "$STAGING/$subdir/"
    fi
done

# ---------- Step 2: Enable DVB in .config ----------------------------------
echo "=== Enabling DVB config ==="
cp "$KERNEL_SRC/.config" "$STAGING/.config"
cat >> "$STAGING/.config" << 'EOF'
CONFIG_DVB_CORE=m
CONFIG_DVB_USB=m
CONFIG_DVB_USB_V2=m
CONFIG_DVB_USB_AF9035=m
CONFIG_MEDIA_CONTROLLER=y
CONFIG_DVB_NET=y
CONFIG_RC_CORE=y
CONFIG_RC_MAP=y
CONFIG_DVB_AF9033=m
CONFIG_DVB_AF9035=m
EOF

# ---------- Step 3: Resolve config in staging only -------------------------
echo "=== Running make oldconfig (staging only) ==="
cd "$STAGING"
make -s oldconfig defconfig < /dev/null 2>&1 | tail -5 || true

# ---------- Step 4: Build only the modules we need -------------------------
echo "=== Building DVB modules ==="
make -j"$(nproc)" \
    KBUILD_MODULES=1 \
    modules \
    drivers/media/dvb-core/built-in.a \
    drivers/media/dvb-core/dvb-core.ko \
    drivers/media/usb/dvb-usb/dvb-usb.ko \
    drivers/media/usb/dvb-usb-v2/dvb-usb-v2.ko \
    2>&1 | tail -50

echo "=== Build Complete ==="

# ---------- Step 5 (optional): Install -------------------------------------
if [[ $INSTALL -eq 1 ]]; then
    CURRENT_KERNEL="$(uname -r)"
    MOD_DIR="/lib/modules/${CURRENT_KERNEL}/kernel/drivers/media"
    echo "=== Installing modules for kernel $CURRENT_KERNEL ==="
    sudo make INSTALL_MOD_PATH="/" INSTALL_MOD_DIR="$(dirname "$MOD_DIR")" modules_install
    sudo depmod -a
    echo "=== Installation Complete ==="
else
    echo ""
    echo "Modules built in: $STAGING"
    echo "To install, run:  $0 --install"
fi
