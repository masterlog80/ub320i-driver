# UB320-i TV Tuner Setup - Master Index

## Device
- **KWorld ISDB-T UB320-i** (Afatech / AsicEn ASV5211)
- USB IDs: `1b80:b320` (firmware loaded), `1738:5211` (bootloader)
- Kernel: `5.4.125-legacy-sunxi64` on BPI-M4Berry / Armbian

## Goal
Create `/dev/dvb/adapter0/frontend0` so standard DVB applications (vlc, mplayer, dvbstream, etc.) can receive TV channels.

## Files in This Directory

| File | Description |
|------|-------------|
| `DVB_SETUP_GUIDE.md` | Complete step-by-step DVB kernel module build guide |
| `dvb-driver-build/build_dvb.sh` | Automated build script (copies sources, enables config, compiles) |
| `dvb-driver-build/drivers/media/` | Extracted kernel source (~593 .c files) |
| `dvb-driver-build/include/` | Extracted kernel headers |
| `ub320i-driver/ub320i_driver.py` | Userspace Python USB driver |
| `ub320i-driver/ub320i_explore.py` | USB protocol explorer |
| `ub320i-driver/load_firmware.py` | Firmware loader |
| `ub320i-driver/ub320i.fw` | Device firmware binary |
| `ub320i-driver/setup.sh` | Setup automation |
| `ub320i-driver/rules/99-ub320i.rules` | udev rules |
| `ub320i-driver/Makefile` | Build configuration |

## Quick Start

### Option 1: Kernel Module Approach (Preferred)
```bash
cd ~/dvb-driver-build
sudo bash build_dvb.sh
```
See `~/DVB_SETUP_GUIDE.md` for full details and manual steps.

### Option 2: Userspace Driver (Fallback)
```bash
cd ~/ub320i-driver
python3 ub320i_driver.py
```

## Verification
```bash
# Check USB device is recognized
lsusb | grep -i "1b80\|b320"

# After loading driver, check for DVB nodes
ls -la /dev/dvb/adapter0/

# List loaded DVB modules
lsmod | grep dvb
```

## Problem Summary
The kernel `5.4.125-legacy-sunxi64` was compiled without DVB subsystem support:
- `CONFIG_DVB_CORE` = unset
- `CONFIG_DVB_USB_V2` = unset
- `CONFIG_DVB_FRONTENDS` = unset

The solution extracts DVB source from linux-5.4.125, copies it into the existing
kernel build tree, enables DVB in `.config`, and compiles out-of-tree modules.
