# KWorld UB320-i DVB Driver Setup Guide

## Device Information
- **Device:** KWorld ISDB-T UB320-i / Afatech ISDB-T UB320-i
- **Chipset:** AsicEn ASV5211
- **USB IDs:** 1738:5211 (bootloader), 1b80:b320 (operational)
- **Kernel:** 5.4.125-legacy-sunxi64 (Armbian / BPI-M4Berry)
- **Target:** `/dev/dvb/adapter0/frontend0`

## Problem
The kernel `5.4.125-legacy-sunxi64` was compiled without DVB subsystem support:
- `CONFIG_DVB_CORE` = unset
- `CONFIG_DVB_USB_V2` = unset
- `CONFIG_DVB_FRONTENDS` = unset

This means standard kernel DVB drivers cannot load, so TV tuner applications
(vlc, mplayer, dvbstream, zap, etc.) cannot access the device via `/dev/dvb/`.

## Solution: Out-of-Tree Module Compilation
Download full kernel source (linux-5.4.125), extract DVB-related directories,
copy them into the existing kernel build tree, enable DVB in `.config`, and
compile modules against existing headers — no full kernel rebuild needed.

## Directory Layout on Device

```
/home/lorenzo/
├── ub320i-driver/           # Userspace driver (firmware, Python driver)
│   ├── ub320i_driver.py     # Userspace USB driver
│   ├── ub320i_explore.py   # Protocol explorer
│   ├── load_firmware.py     # Firmware loader
│   ├── ub320i.fw            # Device firmware binary
│   ├── Makefile
│   ├── setup.sh
│   └── rules/
│       └── 99-ub320i.rules  # udev rules
│
├── dvb-driver-build/        # Kernel module build environment
│   ├── build_dvb.sh         # Main build script
│   ├── drivers/media/       # Extracted kernel source (~600 .c files)
│   │   ├── dvb-core/        # DVB core subsystem (~12 files)
│   │   ├── dvb-frontends/   # Frontend demodulators (~135 files)
│   │   ├── usb/dvb-usb-v2/  # V2 USB DVB framework (~21 files)
│   │   ├── usb/dvb-usb/     # V1 USB DVB framework
│   │   ├── mc/              # Media controller
│   │   ├── i2c/             # I2C media devices (tuners, demodulators)
│   │   ├── common/          # Common media utilities
│   │   ├── rc/              # IR remote control
│   │   └── tuners/          # Analog tuners
│   └── include/             # Extracted kernel headers
│       ├── media/
│       └── uapi/linux/dvb/
```

## Step-by-Step Instructions

### Prerequisites
```bash
# Verify kernel and build environment
uname -r
# Expected: 5.4.125-legacy-sunxi64

# Check kernel headers exist
ls /lib/modules/5.4.125-legacy-sunxi64/build/.config

# Verify build tools
which gcc make
gcc --version
```

### Step 1: Download Kernel Source
```bash
cd ~
mkdir -p dvb-driver-build
cd dvb-driver-build
wget https://cdn.kernel.org/pub/linux/kernel/v5.x/linux-5.4.125.tar.xz
```

### Step 2: Extract DVB Source Directories
```bash
tar -xf linux-5.4.125.tar.xz --strip-components=1 \
  "linux-5.4.125/drivers/media/dvb-core" \
  "linux-5.4.125/drivers/media/dvb-frontends" \
  "linux-5.4.125/drivers/media/usb/dvb-usb-v2" \
  "linux-5.4.125/drivers/media/usb/dvb-usb" \
  "linux-5.4.125/drivers/media/tuners" \
  "linux-5.4.125/drivers/media/common" \
  "linux-5.4.125/drivers/media/mc" \
  "linux-5.4.125/drivers/media/i2c" \
  "linux-5.4.125/drivers/media/rc" \
  "linux-5.4.125/include/media" \
  "linux-5.4.125/include/uapi/linux/dvb" \
  "linux-5.4.125/include/uapi/linux/media.h" \
  "linux-5.4.125/include/uapi/linux/videodev2.h" \
  "linux-5.4.125/include/uapi/linux/rc-core.h" \
  "linux-5.4.125/include/uapi/linux/lirc.h" \
  "linux-5.4.125/include/uapi/linux/cec.h" \
  "linux-5.4.125/include/linux/dvb" \
  "linux-5.4.125/include/linux/media.h" \
  "linux-5.4.125/include/linux/videodev2.h" \
  "linux-5.4.125/include/linux/i2c.h" \
  "linux-5.4.125/include/linux/mod_devicetable.h"

# Verify extraction
find drivers/media/ -name "*.c" | wc -l
# Expected: ~593

# Clean up tarball (saves ~100MB)
rm linux-5.4.125.tar.xz
```

### Step 3: Copy Sources into Kernel Build Tree
```bash
BUILD_DIR="/lib/modules/5.4.125-legacy-sunxi64/build"
SRC_DIR="$HOME/dvb-driver-build"

sudo cp -rf $SRC_DIR/drivers/media/dvb-core/* $BUILD_DIR/drivers/media/dvb-core/
sudo cp -rf $SRC_DIR/drivers/media/dvb-frontends/* $BUILD_DIR/drivers/media/dvb-frontends/
sudo mkdir -p $BUILD_DIR/drivers/media/usb/dvb-usb-v2
sudo cp -rf $SRC_DIR/drivers/media/usb/dvb-usb-v2/* $BUILD_DIR/drivers/media/usb/dvb-usb-v2/
sudo mkdir -p $BUILD_DIR/drivers/media/usb/dvb-usb
sudo cp -rf $SRC_DIR/drivers/media/usb/dvb-usb/* $BUILD_DIR/drivers/media/usb/dvb-usb/
sudo cp -rf $SRC_DIR/drivers/media/mc/* $BUILD_DIR/drivers/media/mc/
sudo cp -rf $SRC_DIR/drivers/media/i2c/* $BUILD_DIR/drivers/media/i2c/
sudo cp -rf $SRC_DIR/drivers/media/common/* $BUILD_DIR/drivers/media/common/
sudo cp -rf $SRC_DIR/drivers/media/rc/* $BUILD_DIR/drivers/media/rc/
sudo cp -rf $SRC_DIR/drivers/media/tuners/* $BUILD_DIR/drivers/media/tuners/
sudo mkdir -p $BUILD_DIR/include/media
sudo cp -rf $SRC_DIR/include/media/* $BUILD_DIR/include/media/ 2>/dev/null || true
sudo mkdir -p $BUILD_DIR/include/uapi/linux/dvb
sudo cp -rf $SRC_DIR/include/uapi/linux/dvb/*.h $BUILD_DIR/include/uapi/linux/dvb/ 2>/dev/null || true
```

### Step 4: Enable DVB in Kernel Config
```bash
sudo sh -c "cat >> /lib/modules/5.4.125-legacy-sunxi64/build/.config << 'EOF'
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
EOF"
```

### Step 5: Run Make Oldconfig
```bash
cd /lib/modules/5.4.125-legacy-sunxi64/build
yes "" | sudo make oldconfig 2>&1 | tail -5
```

### Step 6: Build DVB Modules
```bash
cd /lib/modules/5.4.125-legacy-sunxi64/build
sudo make -j$(nproc) modules 2>&1 | tail -50
```

This will compile all DVB-related modules. The build takes several minutes.
Key output files:
- `drivers/media/dvb-core/dvb-core.ko`
- `drivers/media/dvb-frontends/*.ko`
- `drivers/media/usb/dvb-usb-v2/*.ko`
- `drivers/media/mc/media.ko`
- `drivers/media/rc/rc-core.ko`

### Step 7: Install Modules
```bash
sudo make modules_install
```

### Step 8: Load Modules
```bash
# Load core modules
sudo modprobe dvb-core
sudo modprobe dvb-usb-v2

# Check for AF9035 driver (covers many USB DVB-T devices)
sudo modprobe dvb-usb-af9035

# List loaded DVB modules
lsmod | grep dvb
```

### Step 9: Verify Device Node
```bash
# Check for DVB device nodes
ls -la /dev/dvb/
# Expected: adapter0 directory

ls -la /dev/dvb/adapter0/
# Expected: demux0, demux1, demux2, dvr0, frontend0, net0

# Test with dvb-fe-tool (if installed)
dvb-fe-tool /dev/dvb/adapter0/frontend0
```

### Step 10: Test TV Tuner
```bash
# Install dvb-tools if not present
sudo apt install dvb-utils

# Scan for channels
szap -s 0  # Test first transponder
w_scan -f 6 -c BR > ~/.config/mpv/isdbt.conf  # Scan Brazilian ISDB-T

# Watch with vlc
vlc dvb://frequency=482000000:bandwidth=8:inversion=0:modulation=64QAM

# Watch with mplayer
mplayer tv:// -tv driver=dvb:device=/dev/dvb/adapter0/frontend0
```

## Quick Build (All-in-One Script)
The `build_dvb.sh` script in `~/dvb-driver-build/` combines all steps:
```bash
cd ~/dvb-driver-build
sudo bash build_dvb.sh
```

## Troubleshooting

### "Permission denied" when copying sources
Use `sudo` for all copy operations into `/lib/modules/`.

### "Module not found" after build
Run `sudo make modules_install` to copy modules to `/lib/modules/`.

### Build fails with missing headers
Ensure the `linux-headers-5.4.125-legacy-sunxi64` package is installed:
```bash
sudo apt install linux-headers-legacy-sunxi64
```

### Device not detected by AF9035 driver
The ASV5211 chipset may not be covered by AF9035. Check available frontend
drivers:
```bash
grep -r "ASV5211\|asic_en\|1738\|5211\|1b80\|b320" ~/dvb-driver-build/drivers/media/
```

If no kernel driver supports the chipset, the userspace driver in
`~/ub320i-driver/` provides an alternative approach.

### Disk space constraints
The build requires ~1.5GB free space. If space is limited:
```bash
# Clean build artifacts
cd /lib/modules/5.4.125-legacy-sunxi64/build
sudo make modules_clean

# Remove source tarball after extraction
rm ~/dvb-driver-build/linux-5.4.125.tar.xz
```

## Userspace Driver Fallback
If the kernel module approach doesn't work (chipset not supported),
use the userspace driver:
```bash
cd ~/ub320i-driver
python3 ub320i_driver.py
```

## Files Summary
| File | Purpose |
|------|---------|
| `~/dvb-driver-build/build_dvb.sh` | Automated build script |
| `~/dvb-driver-build/drivers/media/` | Extracted kernel source |
| `~/dvb-driver-build/include/` | Extracted kernel headers |
| `~/ub320i-driver/ub320i_driver.py` | Userspace Python driver |
| `~/ub320i-driver/ub320i_explore.py` | USB protocol explorer |
| `~/ub320i-driver/load_firmware.py` | Firmware loader |
| `~/ub320i-driver/ub320i.fw` | Device firmware binary |
| `~/ub320i-driver/rules/99-ub320i.rules` | udev rules |
| `~/ub320i-driver/setup.sh` | Setup automation |
