# Testing Guide — KWorld UB320-i on BPI-M4 Berry

> **Target:** BPI-M4 Berry running kernel `5.4.125-legacy-sunxi64`
> **Device:** KWorld UB320-i (ASV5211) — USB IDs `1738:5211` (cold) / `1b80:b320` (warm)
> **SSH:** `lorenzo@192.168.10.3` (key `~/.ssh/id_key`)

---

## Step 1 — Get the driver onto the target

### Option A: Clone directly on the device

```bash
ssh -i ~/.ssh/id_key lorenzo@192.168.10.3

# On the device:
git clone https://github.com/masterlog80/ub320i-driver.git
cd ub320i-driver
```

### Option B: Push from this machine

```bash
rsync -avz --exclude=.git -e "ssh -i ~/.ssh/id_key" \
  ub320i-repo/ lorenzo@192.168.10.3:ub320i-driver/
```

---

## Step 2 — Install prerequisites

```bash
# Python dependencies
sudo pip3 install pyusb

# Kernel build tools (for kernel module path)
sudo apt-get install build-essential kmod
```

---

## Step 3 — Install firmware and udev rules

```bash
sudo cp firmware/ub320i.fw /lib/firmware/dvb-usb-asv5211.fw
sudo cp driver/90-ub320i.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

---

## Step 4 — Build and load the kernel module

```bash
cd driver

# Build (uses staging dir, does NOT modify the live kernel tree)
make KDIR=/lib/modules/5.4.125-legacy-sunxi64/build \
     KERNEL_SRC=/home/lorenzo/dvb-driver-build

# Install and load
sudo make install KDIR=/lib/modules/5.4.125-legacy-sunxi64/build
sudo modprobe asv5211
```

---

## Step 5 — Plug in the device and check

```bash
# Insert the UB320-i USB device, then:
dmesg | tail -20
# Expected: "KWorld UB320-i ASV5211 ISDB-T (ONE SEG) detected"

# Check device nodes
ls -la /dev/dvb/adapter0/
# Expected: frontend0  demux0  dvr0  net0

# Check USB state
lsusb | grep -E '1b80|1738'
# Expected: 1b80:b320 (warm/operational)
# If you see 1738:5211 (cold/bootloader), load firmware:
#   sudo python3 /home/lorenzo/ub320i-driver/load_firmware.py firmware/ub320i.fw
```

---

## Step 6 — Test with standard DVB tools

### Check frontend status

```bash
dvb-fe-tool -S -a 0
```

### Scan for channels (Japan ISDB-T)

```bash
# If channels.conf does not exist:
w_scan -c JP -t ISDBT -o 5 > ~/.tzap/channels.conf

# Or manually tune to a known frequency:
# Channel 24 (Tokyo) = 547.5 MHz = 547500000 Hz
dvb-fe-tool -S -a 0 -f 547500000
```

### Capture a stream

```bash
# Capture 30 seconds of raw transport stream
timeout 30 dd if=/dev/dvb/adapter0/dvr0 bs=188 count=10000 of=test.ts

# Check for valid MPEG-TS sync bytes (0x47) at every 188-byte boundary:
xxd test.ts | head -20
```

---

## Step 7 — Userspace driver (alternative, no kernel module)

```bash
sudo python3 load_firmware.py firmware/ub320i.fw   # If device is cold
sudo python3 ub320i_driver.py --frequency 547500000 --output test.ts
```

---

## Expected results

| Check | Expected | Not working |
|---|---|---|
| `dmesg` | "KWorld UB320-i ... detected" | "No such device" or errors |
| `/dev/dvb/adapter0/frontend0` | Exists | Missing — module not loaded |
| `lsusb` | `1b80:b320` | `1738:5211` — firmware not loaded |
| `dvb-fe-tool -S` | Reports lock status | "Device or resource busy" |
| `test.ts` | Sync byte `0x47` every 188 bytes | Random garbage or empty |

---

## Troubleshooting

```bash
# Module errors:
dmesg | grep -i asv5211

# Permission denied:
sudo usermod -aG video lorenzo

# Firmware issues:
sudo python3 load_firmware.py firmware/ub320i.fw

# Reload module:
sudo rmmod asv5211 && sudo modprobe asv5211

# Reload udev:
sudo udevadm control --reload-rules && sudo udevadm trigger
```
