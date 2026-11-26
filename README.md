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
├── DVB_SETUP_GUIDE.md           ← Full setup instructions
├── README_UB320i.md             ← Device-specific notes
├── driver/
│   ├── asv5211.c                ← Kernel module source (5.4.x)
│   ├── Makefile                 ← Out-of-tree build
│   └── 90-ub320i.rules          ← udev rules
├── firmware/
│   └── ub320i.fw                ← Binary firmware (16 KB)
├── load_firmware.py             ← Standalone firmware loader (bootloader)
├── ub320i_driver.py             ← Userspace ISDB-T driver (PyUSB)
├── ub320i_explore.py            ← Protocol exploration tool
├── rules/
│   └── 99-ub320i.rules          ← Legacy udev rules
├── build_dvb.sh                 ← Automated build script
└── Makefile                     ← Top-level convenience build
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

### 3. Build and install the kernel module

```bash
cd driver
make KDIR=/lib/modules/$(uname -r)/build
sudo make install KDIR=/lib/modules/$(uname -r)/build
sudo modprobe asv5211
```

### 4. Connect the device and verify

```bash
# Plug in the UB320-i
dmesg | tail -20
# Look for: "KWorld UB320-i ASV5211 ISDB-T (ONE SEG) detected"

# Verify /dev/dvb was created
ls /dev/dvb/adapter0/
# Should show: frontend0  demux0  dvr0  net0
```

### 5. Use with standard DVB applications

```bash
# Scan for channels
scan -a 0 -t ISDBT /usr/share/dvb/isdbt/channels-Japan > ~/.tzap/channels.conf

# Watch a channel
tvtime -a 0

# Or use vlc
vlc dvb://frequency=547500000:delivery-system=ISDBT:bandwidth=6
```

## Userspace Driver (Alternative)

If you cannot compile the kernel module, the Python userspace driver works without kernel modifications:

```bash
sudo pip3 install pyusb
sudo python3 load_firmware.py      # Load firmware if device is cold
sudo python3 ub320i_driver.py      # Start receiving
```

See `DVB_SETUP_GUIDE.md` for full setup instructions including cross-compilation for the BPI-M4 Berry (sun50iw9).

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
