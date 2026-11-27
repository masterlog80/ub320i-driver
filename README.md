# KWorld UB320-i (ASV5211) Linux DVB Driver

Experimental Linux support for the KWorld UB320-i Japanese ISDB-T ONE SEG USB tuner.

> **Status: not yet working or hardware-verified.** PR #1 corrected the Linux DVB-USB integration and build process. The Windows driver package confirms the bootloader firmware-transfer parameters, but it also exposed an important mismatch in the Linux prototype's operational USB-control protocol. The first goal is to build the module and collect reliable device logs—not to expect TV reception yet.

## Current findings

### Confirmed from the supplied Windows driver package

- Bootloader USB ID: `1738:5211`
- Operational USB ID: `1b80:b320`
- The Windows loader binary contains four firmware transfers:

  | Request | Offset (`wValue`) | Length | `wIndex` |
  |---|---:|---:|---:|
  | `0xAB` | `0x0000` | `0x0C00` | `0x55DC` |
  | `0xAB` | `0x2000` | `0x0400` | `0x55DC` |
  | `0xAB` | `0x2800` | `0x1000` | `0x55DC` |
  | `0xAC` | `0x3800` | `0x0800` | `0x55DC` |

  This is confirmation from static disassembly of `AS11Loader.sys`, not a live USB capture. The supplied Windows ZIP did not include a standalone firmware image, so `firmware/ub320i.fw` has not been compared byte-for-byte with the Windows firmware payload.

### Still unknown — the main work remaining

The Linux prototype currently assumes register control requests `0x90` (OUT) and `0x91` (IN), a set of register addresses, and a simple initialization sequence. Static analysis of one operational control path in the Windows `KWORLD_UB320i.sys` instead shows vendor request `0x14`, with a command encoded in `wValue` and a two-byte IN response containing a status byte.

This is evidence that the current Linux operational protocol is incomplete or incorrect. It is **not** enough to translate the entire Windows protocol: the command meanings and full initialization/tuning sequence have not yet been established.

The following are therefore still unverified:

- Register requests, register addresses, and data widths used by the Linux prototype
- Device initialization and channel-tuning sequence
- Signal/lock status bit and statistics
- USB streaming endpoint(s)
- MPEG-TS packet format and sustained reception
- Kernel build and operation on the target hardware

The Japanese ISDB-T UHF channel raster used by the project is channels 13–52, starting at 473.142857 MHz with 6 MHz spacing. This frequency plan does not prove that the tuner protocol is correct.

## Next steps: test and collect evidence

Follow these steps in order. **Do not start with channel scanning or blind register experiments.** First establish whether the module builds, whether the device changes from its cold to warm USB ID, and whether Linux registers a DVB frontend.

### 1. Prepare the target

Run these commands on the Linux device that will host the tuner:

```bash
sudo apt-get update
sudo apt-get install build-essential bc kmod usbutils
git clone https://github.com/masterlog80/ub320i-driver.git
cd ub320i-driver
```

Build against the kernel that is actually running on this device. Do not use headers or source from a different kernel release.

### 2. Build and install the module

First try the configured build directory for the running kernel:

```bash
set -o pipefail
KDIR="/lib/modules/$(uname -r)/build"
./build_dvb.sh --kdir "$KDIR" --install 2>&1 | tee build.log
```

The driver also needs the internal kernel header:

`drivers/media/usb/dvb-usb-v2/dvb_usb.h`

If the build reports that this header is missing from `KDIR`, provide the **matching full kernel source tree**:

```bash
./build_dvb.sh \
    --kdir "$KDIR" \
    --kernel-src /path/to/matching/kernel/source \
    --install 2>&1 | tee build.log
```

The source tree must match `uname -r` and the configured kernel build tree. The script builds and installs the external module, copies the repository firmware to `/lib/firmware/dvb-usb-asv5211.fw`, and runs `depmod`.

Keep `build.log`. If the build fails, stop here and send that file together with the kernel version and the complete error.

### 3. Load the driver and record the first USB connection

With the tuner unplugged, create a test folder and start the live kernel log in **Terminal A**:

```bash
mkdir -p "$HOME/ub320i-test"
sudo dmesg -wT | tee "$HOME/ub320i-test/dmesg-live.txt"
```

In **Terminal B**, load the module:

```bash
sudo modprobe asv5211
```

If that command succeeds, plug in the UB320-i. Leave the log running for about 20 seconds, then press **Ctrl+C** in Terminal A. If `modprobe` fails, keep the error and the live log; do not continue to tuning.

The kernel driver should request `dvb-usb-asv5211.fw` when it sees the cold device (`1738:5211`). The firmware loader code then requests USB re-enumeration; the expected operational ID is `1b80:b320`.

### 4. Record what Linux detected

Run the following commands after plugging in the tuner:

```bash
OUT="$HOME/ub320i-test"
uname -a > "$OUT/system.txt"
uname -r >> "$OUT/system.txt"
lsusb -nn > "$OUT/lsusb.txt"
lsusb -t > "$OUT/lsusb-tree.txt"
lsmod | grep -E 'asv5211|dvb_usb' > "$OUT/modules.txt" || true
modinfo asv5211 > "$OUT/modinfo.txt" 2>&1 || true
sudo dmesg -T > "$OUT/dmesg-full.txt"

for id in 1738:5211 1b80:b320; do
    sudo lsusb -v -d "$id" > "$OUT/usb-$id.txt" 2>&1 || true
done

find /dev/dvb -maxdepth 3 -ls > "$OUT/dvb-devices.txt" 2>&1 || true
dvb-fe-tool -a 0 > "$OUT/dvb-fe-tool.txt" 2>&1 || true

tar -czf "$HOME/ub320i-test.tar.gz" -C "$HOME" ub320i-test
```

If `dvb-fe-tool` is not installed, install `v4l-utils` and run that command again. At this stage it is only a frontend enumeration/capability check; it does not prove that tuning or reception works.

### 5. Check the initial result

| Observation | What it tells us |
|---|---|
| Build creates `driver/asv5211.ko` | The source compiled for this kernel |
| Device appears as `1738:5211` and then `1b80:b320` | Firmware transfer completed far enough for USB re-enumeration |
| `/dev/dvb/adapter0/frontend0` appears | The Linux DVB frontend registered |
| USB errors, repeated disconnects, or no warm ID | Firmware/probe path needs investigation |
| Warm ID appears but no DVB frontend | Operational probe or frontend registration needs investigation |

A successful build, warm USB ID, or frontend node does **not** prove that the current register protocol, tuning, lock detection, or transport stream works.

For this first test, do not run channel scans, sustained stream captures, or `ub320i_explore.py` write experiments. The operational commands are not yet sufficiently understood. Once we have the initial logs and a Windows trace, we can correct the protocol before attempting reception.

### 6. Capture the working Windows protocol

The next essential evidence is a USB capture from the official Windows driver:

1. On Windows, install/use Wireshark with USBPcap available.
2. Start USBPcap capture on the USB controller used by the tuner **before** plugging it in.
3. Plug in the UB320-i and let the official driver load the firmware.
4. Open the KWorld TV application, tune to a channel that is known to receive at your location, start viewing for 20–30 seconds, then stop.
5. Save the capture as a `.pcapng` file.

The capture should include the cold-device firmware upload, operational initialization, channel tuning, stream start, data transfers, and stream stop. This will let us map the real request type, request, value, index, payload, lengths and streaming endpoints instead of guessing from the partial static disassembly.

## What to send for the next fix

Please provide:

1. `build.log` (or the complete build error)
2. `ub320i-test.tar.gz`
3. The Windows USBPcap `.pcapng` capture, when available
4. The channel/frequency tested and whether the KWorld application successfully received it on Windows

These files will let us work through the next fixes in evidence-based order: firmware/probe, operational control requests, initialization, tuning/lock detection, then transport-stream reception.

## Hardware target

The original target for this project is the BPI-M4 Berry running Armbian. Always build against the actual kernel running on the target; other boards and kernel versions need their own build and compatibility checks.

## License

- Kernel driver: GPL-2.0-or-later
- Userspace scripts: MIT
- Firmware: © KWorld; included for personal use only
