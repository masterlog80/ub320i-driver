# KWorld UB320-i (ASV5211) Linux ISDB-T ONE SEG Driver

Linux support for the **KWorld UB320-i** USB TV tuner, an **AsicEn ASV5211**-based ISDB-T ONE SEG receiver designed for the Japanese digital television market.

> **Experimental:** the driver and USB protocol have not yet been verified against physical hardware. See [VERIFICATION.md](VERIFICATION.md) before attempting installation.

## Hardware

| Property | Value |
|---|---|
| Device | KWorld ISDB-T UB320-i / ONE SEG TV Tuner |
| Chipset | AsicEn ASV5211 (integrated tuner + demodulator) |
| USB IDs (bootloader) | `1738:5211` |
| USB IDs (operational) | `1b80:b320` |
| Standard | Japan ISDB-T (ONE SEG / mobile) |
| Japanese UHF channel range | 473.142857-707.142857 MHz (channels 13-52) |
| Bandwidth | 6 MHz |

## Repository Layout

```
ub320i-driver/
├── README.md                    ← You are here
├── VERIFICATION.md              ← Verification status & testing procedure
├── driver/
│   ├── asv5211.c                ← Kernel module source (5.4.x)
│   ├── Makefile                 ← Out-of-tree build
│   └── 90-ub320i.rules          ← udev rules
├── firmware/
│   └── ub320i.fw                ← Binary firmware (16 KB)
├── load_firmware.py             ← Standalone firmware loader
├── ub320i_driver.py             ← Userspace ISDB-T driver (PyUSB)
└── ub320i_explore.py            ← Protocol exploration tool
```

---

## Quick Start (On-Target)

These commands run on the target device (e.g., BPI-M4 Berry with kernel `5.4.125-legacy-sunxi64`).

### 1. Install prerequisites

```bash
sudo pip3 install pyusb
sudo apt-get install build-essential kmod
```

### 2. Copy firmware

```bash
sudo cp firmware/ub320i.fw /lib/firmware/dvb-usb-asv5211.fw
```

### 3. Install udev rules

```bash
sudo cp driver/90-ub320i.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 4. Build the kernel module

The driver uses `dvb_usb.h`, an **internal kernel header** located at
`drivers/media/usb/dvb-usb-v2/dvb_usb.h`. Build against a configured kernel
build tree matching the target kernel. If that internal header is not present
in the build directory, supply the matching full kernel source tree.

```bash
cd driver

# Build for the currently running kernel
make KDIR=/lib/modules/$(uname -r)/build

# If source and configured build directories are separate
make KDIR=/path/to/configured-kernel-build \
     KERNEL_SRC=/path/to/matching/kernel-source
```

You can alternatively build from the repository root:

```bash
./build_dvb.sh --kdir /lib/modules/$(uname -r)/build \
    --kernel-src /path/to/matching/kernel-source
```

The target kernel must already provide the DVB-USB v2 framework and its
exported symbols. This builds the driver as an external module; it does not
build or replace the kernel media subsystem.

### 5. Install and load

```bash
cd driver
sudo make install KDIR=/lib/modules/$(uname -r)/build \
     KERNEL_SRC=/path/to/matching/kernel-source
sudo modprobe asv5211
```

Alternatively, add `--install` to `build_dvb.sh` to install the module and
firmware after building.

### 6. Plug in the device and verify

```bash
# Insert the UB320-i, then check:
dmesg | tail -20
# Look for: "KWorld UB320-i ASV5211 ISDB-T (ONE SEG) detected"

# Verify device nodes
ls -la /dev/dvb/adapter0/
# Expected: frontend0  demux0  dvr0  net0

# Check USB state
lsusb | grep -E '1b80|1738'
# Expected: 1b80:b320 (warm/operational)
```

If you see `1738:5211` (cold/bootloader), check that `/lib/firmware/dvb-usb-asv5211.fw` exists and inspect firmware-loading messages in `dmesg`. The kernel driver is intended to bind to the cold USB ID, download firmware, and wait for re-enumeration as `1b80:b320`.

### 7. Add your user to the `video` group

```bash
sudo usermod -aG video $USER
```

Log out and back in for the group change to take effect.

### 8. Use with standard DVB applications

```bash
# Check frontend status
dvb-fe-tool -S -a 0

# Scan channels (Japan ISDB-T; use a channel list matching your region)
scan -a 0 -t ISDBT /usr/share/dvb/isdbt/channels-Japan > ~/.tzap/channels.conf

# Watch a channel
tvtime -a 0
vlc dvb://frequency=473142857:delivery-system=ISDBT:bandwidth=6
mpv dvb://frequency=473142857:delivery-system=ISDBT:bandwidth=6

# Or manually tune to a known frequency:
dvb-fe-tool -S -a 0 -f 473142857

# Capture 30 seconds of raw transport stream
timeout 30 dd if=/dev/dvb/adapter0/dvr0 bs=188 count=10000 of=test.ts

# Check for valid MPEG-TS sync bytes (0x47) at every 188-byte boundary:
xxd test.ts | head -20
```

---

## Userspace Driver (Alternative)

If you cannot compile the kernel module, the Python userspace driver works without kernel modifications:

```bash
sudo pip3 install pyusb
sudo python3 load_firmware.py firmware/ub320i.fw   # Load firmware if device is cold
sudo python3 ub320i_driver.py --channel 13 --output channel-13.ts  # Receive channel 13
```

---

## Hardware Testing Guide

### Getting the driver onto the target

**Option A — Clone directly on the device:**

```bash
git clone https://github.com/masterlog80/ub320i-driver.git
cd ub320i-driver
```

**Option B — Push from a development machine:**

```bash
rsync -avz --exclude=.git -e "ssh -i ~/.ssh/id_key" \
  ub320i-driver/ lorenzo@192.168.10.3:ub320i-driver/
```

### Expected results

| Check | Expected | Not working |
|---|---|---|
| `dmesg` | "KWorld UB320-i ... detected" | "No such device" or errors |
| `/dev/dvb/adapter0/frontend0` | Exists | Missing — module not loaded |
| `lsusb` | `1b80:b320` | `1738:5211` — firmware not loaded |
| `dvb-fe-tool -S` | Reports lock status | "Device or resource busy" |
| `test.ts` | Sync byte `0x47` every 188 bytes | Random garbage or empty |

### Troubleshooting

```bash
# Module errors:
dmesg | grep -i asv5211

# Permission denied:
sudo usermod -aG video lorenzo

# Reload module:
sudo rmmod asv5211 && sudo modprobe asv5211

# Reload udev:
sudo udevadm control --reload-rules && sudo udevadm trigger

# /dev/dvb/adapter0/frontend0 missing:
lsmod | grep asv5211
dmesg | grep -i dvb
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=dvb

# Module parameter: frequency offset
# If a known Japanese UHF channel does not lock, first confirm the channel
# number and centre frequency (channel 13 is 473.142857 MHz; channels are
# spaced 6 MHz apart). A small hardware-specific offset can be supplied with:
sudo modprobe asv5211 freq_offset=50   # Shift by +50 kHz
echo "options asv5211 freq_offset=50" | sudo tee /etc/modprobe.d/asv5211.conf

# Ensure module loads at boot:
echo "asv5211" | sudo tee /etc/modules-load.d/asv5211.conf
```

---

## Protocol Reference

The ASV5211 communicates via USB control and bulk transfers:

| Transfer | Direction | Endpoint | Purpose |
|---|---|---|---|
| Register write | OUT | Ctrl (0x90) | Write chip registers |
| Register read | IN | Ctrl (0x91) | Read chip registers |
| TS data | IN | Bulk 0x81 | 188-byte MPEG-TS packets |
| Status | IN | Bulk 0x82 | Tuner status updates |

Firmware loading uses segmented control transfers to the bootloader (`1738:5211`), after which the device re-enumerates as the operational device (`1b80:b320`).

---

## Known Targets

- **BPI-M4 Berry** (Banana Pi) — intended target: Armbian kernel `5.4.125-legacy-sunxi64`
- Other architectures/kernels require a matching configured kernel build tree and compatibility verification

## Reverse Engineering Sources

- Windows BDA drivers: `KWORLD_UB320i.sys`, `AS11Loader.sys`
- Python userspace drivers in this repository
- Windows INF files in `Driver_UB320i_V1.09.10.26.091026/`

## License

Kernel driver: GPL-2.0-or-later
Userspace scripts: MIT
Firmware binary: © KWorld — included for personal use only

## Credits

Driver developed through reverse engineering by the OpenClaw Community.
