# KWorld UB320-i (ASV5211) Linux ISDB-T ONE SEG Driver

Linux support for the **KWorld UB320-i** USB TV tuner, an **AsicEn ASV5211**-based ISDB-T ONE SEG receiver designed for the Japanese digital television market.

## Hardware

| Property | Value |
|---|---|
| Device | KWorld ISDB-T UB320-i / ONE SEG TV Tuner |
| Chipset | AsicEn ASV5211 (integrated tuner + demodulator) |
| USB IDs (bootloader) | `1738:5211` |
| USB IDs (operational) | `1b80:b320` |
| Standard | Japan ISDB-T (ONE SEG / mobile) |
| Frequency range | 175-770 MHz |
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
`drivers/media/usb/dvb-usb-v2/dvb_usb.h` inside your kernel source tree.
You must point `KERNEL_SRC` to it:

```bash
cd driver

# Default — kernel headers under /lib/modules/$(uname -r)/build
make KDIR=/lib/modules/$(uname -r)/build

# If kernel source is elsewhere (e.g. BPI-M4 Berry):
make KDIR=/lib/modules/$(uname -r)/build \
     KERNEL_SRC=/path/to/kernel/source
```

### 4. Install and load

```bash
sudo make install KDIR=/lib/modules/$(uname -r)/build
sudo modprobe asv5211
```

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
# Scan channels (Japan ISDB-T)
scan -a 0 -t ISDBT /usr/share/dvb/isdbt/channels-Japan > ~/.tzap/channels.conf

# Watch a channel
tvtime -a 0
vlc dvb://frequency=547500000:delivery-system=ISDBT:bandwidth=6
mpv dvb://frequency=547500000:delivery-system=ISDBT:bandwidth=6
```

### 7. Add your user to the `video` group

```bash
sudo usermod -aG video $USER
```

Log out and back in for the group change to take effect.

## Installation Details

See the **[INSTALL.md](INSTALL.md)** file for a complete step-by-step guide including:

- Kernel headers and build tool installation
- `KERNEL_SRC` path explanation and examples
- Module auto-load on boot configuration
- Frequency offset tuning
- Full troubleshooting section

## Userspace Driver (Alternative)

If you cannot compile the kernel module, the Python userspace driver works without kernel modifications:

```bash
sudo pip3 install pyusb
sudo python3 load_firmware.py      # Load firmware if device is cold
sudo python3 ub320i_driver.py      # Start receiving
```

## Known Targets

- **BPI-M4 Berry** (Banana Pi) — Armbian kernel `5.4.125-legacy-sunxi64`
- Any ARM64/x86_64 system running kernel 5.4.x with DVB-USB v2 framework

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

If you see `1738:5211` (cold/bootloader) instead of `1b80:b320` (warm/operational):

```bash
sudo rmmod asv5211
sudo modprobe asv5211
```

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

If channels aren't found at the expected frequency:

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
