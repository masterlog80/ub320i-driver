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

## Quick Start

### 1. Copy firmware

```bash
sudo cp firmware/ub320i.fw /lib/firmware/dvb-usb-asv5211.fw
```

### 2. Install udev rules

```bash
sudo cp driver/90-ub320i.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 3. Build the kernel module

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

### 4. Install and load

```bash
cd driver
sudo make install KDIR=/lib/modules/$(uname -r)/build \
     KERNEL_SRC=/path/to/matching/kernel-source
sudo modprobe asv5211
```

Alternatively, add `--install` to `build_dvb.sh` to install the module and
firmware after building.

### 5. Plug in the device and verify

```bash
# Insert the UB320-i, then check:
dmesg | tail -20
# Look for: "KWorld UB320-i ASV5211 ISDB-T (ONE SEG) detected"

# Verify device nodes
ls /dev/dvb/adapter0/
# Should show: frontend0  demux0  dvr0  net0
```

### 6. Use with standard DVB applications

```bash
# Scan channels (Japan ISDB-T; use a channel list matching your region)
scan -a 0 -t ISDBT /usr/share/dvb/isdbt/channels-Japan > ~/.tzap/channels.conf

# Watch a channel
tvtime -a 0
vlc dvb://frequency=473142857:delivery-system=ISDBT:bandwidth=6
mpv dvb://frequency=473142857:delivery-system=ISDBT:bandwidth=6
```

### 7. Add your user to the `video` group

```bash
sudo usermod -aG video $USER
```

Log out and back in for the group change to take effect.

## Userspace Driver (Alternative)

If you cannot compile the kernel module, the Python userspace driver works without kernel modifications:

```bash
sudo pip3 install pyusb
sudo python3 load_firmware.py firmware/ub320i.fw   # Load firmware if device is cold
sudo python3 ub320i_driver.py --channel 13 --output channel-13.ts  # Receive channel 13
```

## Known Targets

- **BPI-M4 Berry** (Banana Pi) — intended target: Armbian kernel `5.4.125-legacy-sunxi64`
- Other architectures/kernels require a matching configured kernel build tree and compatibility verification

## Protocol Reference

The ASV5211 communicates via USB control and bulk transfers:

| Transfer | Direction | Endpoint | Purpose |
|---|---|---|---|
| Register write | OUT | Ctrl (0x90) | Write chip registers |
| Register read | IN | Ctrl (0x91) | Read chip registers |
| TS data | IN | Bulk 0x81 | 188-byte MPEG-TS packets |
| Status | IN | Bulk 0x82 | Tuner status updates |

Firmware loading uses segmented control transfers to the bootloader (`1738:5211`), after which the device re-enumerates as the operational device (`1b80:b320`).

## Troubleshooting

### Module won't load

```bash
sudo modprobe asv5211
dmesg | tail -20
```

- **`Unknown symbol dvb_register_frontend`** — Rebuild with correct `KDIR` and `KERNEL_SRC`.
- **`firmware not found`** — Verify `/lib/firmware/dvb-usb-asv5211.fw` exists.

### Device not detected

```bash
lsusb | grep -i 1b80
```

If you see `1738:5211` (cold/bootloader), check that `/lib/firmware/dvb-usb-asv5211.fw` exists and inspect firmware-loading messages in `dmesg`. The kernel driver is intended to bind to the cold USB ID, download firmware, and wait for re-enumeration as `1b80:b320`.

### Permission denied on `/dev/dvb/...`

```bash
groups                          # Check your groups
sudo usermod -aG video $USER    # Add to video group if missing
```

### `/dev/dvb/adapter0/frontend0` missing

```bash
lsmod | grep asv5211                           # Check module loaded
dmesg | grep -i dvb                            # Check kernel messages
sudo udevadm control --reload-rules            # Reload udev
sudo udevadm trigger --subsystem-match=dvb     # Trigger DVB devices
```

### Module parameter: frequency offset

If a known Japanese UHF channel does not lock, first confirm the channel number and centre frequency (channel 13 is 473.142857 MHz; channels are spaced 6 MHz apart). A small hardware-specific offset can be supplied with:

```bash
sudo modprobe asv5211 freq_offset=50   # Shift by +50 kHz

# Make persistent:
echo "options asv5211 freq_offset=50" | sudo tee /etc/modprobe.d/asv5211.conf
```

### Ensure module loads at boot

```bash
echo "asv5211" | sudo tee /etc/modules-load.d/asv5211.conf
```

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
