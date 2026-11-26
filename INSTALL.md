# Installation Guide — KWorld UB320-i (ASV5211) Linux Driver

Step-by-step instructions to get `/dev/dvb/adapter0/frontend0` working on your system.

## Prerequisites

- Linux kernel **5.4.x** (tested on `5.4.125-legacy-sunxi64` / Armbian BPI-M4 Berry)
- Kernel headers for your running kernel
- Build essentials (`gcc`, `make`, `kmod`)

## Step 1 — Install kernel headers and build tools

```bash
sudo apt update
sudo apt install linux-headers-$(uname -r) build-essential kmod
```

> **BPI-M4 Berry (Armbian):** Kernel source may be in a separate tree
> (e.g. `~/dvb-driver-build`). Note the path — you'll need it in Step 4.

## Step 2 — Copy firmware

```bash
sudo cp firmware/ub320i.fw /lib/firmware/dvb-usb-asv5211.fw
```

## Step 3 — Install udev rules

```bash
sudo cp driver/90-ub320i.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

This ensures:

- USB device permissions are correct (`0660`, group `video`)
- DVB character devices (`/dev/dvb/adapterN/frontend0`, etc.) get proper permissions

## Step 4 — Build the kernel module

```bash
cd driver

# Standard case — kernel headers are under /lib/modules/$(uname -r)/build
make KDIR=/lib/modules/$(uname -r)/build

# If kernel source is elsewhere (e.g. BPI-M4 Berry):
make KDIR=/lib/modules/$(uname -r)/build \
     KERNEL_SRC=~/dvb-driver-build
```

### What is `KERNEL_SRC`?

The driver includes `dvb_usb.h`, an **internal kernel header** located at:

```
<kernel-source>/drivers/media/usb/dvb-usb-v2/dvb_usb.h
```

It is **not** in the public UAPI headers. The Makefile adds an `-I` flag so the compiler can find it. `KERNEL_SRC` tells the Makefile where your kernel source tree root is.

### Common `KERNEL_SRC` values

| System | Path |
|---|---|
| Standard Debian/Ubuntu | `/lib/modules/$(uname -r)/build` (default) |
| BPI-M4 Berry (Armbian) | `~/dvb-driver-build` |
| Custom build tree | Path to your kernel source root |

## Step 5 — Install and load the module

```bash
sudo make install KDIR=/lib/modules/$(uname -r)/build
sudo modprobe asv5211
```

## Step 6 — Plug in the USB tuner

Insert the KWorld UB320-i into a USB port.

### Verify with dmesg

```bash
dmesg | tail -20
```

Expected output:

```
dvb-usb-asv5211: KWorld UB320-i ASV5211 ISDB-T (ONE SEG) detected
dvb-usb-asv5211: ASV5211 ISDB-T frontend registered
```

### Verify device nodes

```bash
ls -la /dev/dvb/adapter0/
```

Expected output:

```
total 0
drwxr-xr-x 2 root root    120 Nov 26 12:00 .
drwxr-xr-x 4 root root     60 Nov 26 12:00 ..
crw-rw---- 1 root video 212, 0 Nov 26 12:00 demux0
crw-rw---- 1 root video 212, 4 Nov 26 12:00 dvr0
crw-rw---- 1 root video 212, 1 Nov 26 12:00 frontend0
crw-rw---- 1 root video 212, 2 Nov 26 12:00 net0
```

## Step 7 — Add your user to the `video` group

```bash
sudo usermod -aG video $USER
```

**Log out and back in** for the group change to take effect. Without this, you'll need `sudo` for every DVB application.

## Step 8 — Use with DVB applications

### Scan for channels (Japan ISDB-T)

```bash
scan -a 0 -t ISDBT /usr/share/dvb/isdbt/channels-Japan > ~/.tzap/channels.conf
```

### Watch a channel

```bash
# tvtime
tvtime -a 0

# vlc
vlc dvb://frequency=547500000:delivery-system=ISDBT:bandwidth=6

# mpv
mpv dvb://frequency=547500000:delivery-system=ISDBT:bandwidth=6

# gstreamer
gst-launch-1.0 dvbsrc device=/dev/dvb/adapter0/frontend0 ! filesink location=output.ts
```

## Troubleshooting

### Module won't load

```bash
sudo modprobe asv5211
dmesg | tail -20
```

- **`Unknown symbol dvb_register_frontend`** — Kernel module version mismatch. Rebuild with the correct `KDIR`.
- **`firmware not found`** — Verify `/lib/firmware/dvb-usb-asv5211.fw` exists.

### Device not detected

```bash
lsusb | grep -i 1b80
```

- If you see `1738:5211` (cold/bootloader) instead of `1b80:b320` (warm/operational), the firmware wasn't loaded. Try:
  ```bash
  sudo rmmod asv5211
  sudo modprobe asv5211
  ```
- If nothing shows, check USB port power and try a different port.

### `/dev/dvb/adapter0/frontend0` missing

```bash
# Check if the module loaded
lsmod | grep asv5211

# Check kernel messages
dmesg | grep -i dvb

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Manually trigger DVB device creation
sudo udevadm trigger --subsystem-match=dvb
```

### Permission denied on `/dev/dvb/...`

```bash
# Check your groups
groups

# Add to video group if missing
sudo usermod -aG video $USER
# Then log out and back in
```

### Module auto-loads on boot

The `make install` step places the `.ko` in the kernel module directory and runs `depmod`. The module loads automatically via `modprobe` when udev detects the USB device.

To ensure it loads at boot, add it to your initramfs:

```bash
# Debian/Ubuntu
echo "asv5211" | sudo tee /etc/modules-load.d/asv5211.conf

# Or add to /etc/modules:
echo "asv5211" | sudo tee -a /etc/modules
```

### Module parameter: frequency offset

If channels aren't found at the expected frequency, try adjusting the offset:

```bash
sudo modprobe asv5211 freq_offset=50   # Shift by +50 kHz
# or make it persistent:
echo "options asv5211 freq_offset=50" | sudo tee /etc/modprobe.d/asv5211.conf
```
