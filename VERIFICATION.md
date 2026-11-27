# Verification Status

> **Last updated:** 2026-11-27

## Short answer

**Nothing in this repository has been verified against actual hardware.** The driver compiles and the Python scripts run, but the USB protocol they speak is speculative.

## What was done

| Component | Method | Verified? |
|---|---|---|
| Firmware transfer (`load_firmware.py`) | Analyzed `ub320i.fw` structure (16 KB, segmented at offsets matching `AS11Loader.sys` patterns) | ❌ No live capture |
| Register map (`0x0010`–`0x0044`) | Inferred from firmware byte sequences and similar ASV5211 driver patterns | ❌ No hardware response |
| USB control requests (`0x90` OUT, `0x91` IN) | Guessed from common vendor-request conventions for DVB-USB v2 devices | ❌ Not confirmed |
| Firmware download requests (`0xAB`/`0xAC`) | Observed in firmware loader binary; segment boundaries match 16 KB split | ⚠️ Partially — from binary analysis only |
| ISDB-T frequency mapping | Based on Japanese ARIB STD-B31 standard (6 MHz spacing, Ch13 = 473.142857 MHz) | ✅ Standard is correct |
| Kernel module API usage | Pattern-matched against Linux `dvb-usb-v2` framework and drivers like `dvb-usb-af9035` | ⚠️ API usage is structurally sound but hardware-specific callbacks are untested |

## What was NOT done

- **No USB packet captures** of the Windows driver (`KWORLD_UB320i.sys` / `AS11Loader.sys`) in action.
- **No live hardware testing** — the driver was never loaded onto a running kernel with a physical UB320-i attached.
- **No lock verification** — `FE_HAS_LOCK` has never been confirmed against a real ISDB-T transmission.
- **No MPEG-TS validation** — captured stream data was never checked for valid sync bytes (`0x47`), PID structure, or PSI/SI tables.
- **No firmware transfer verification** — the segmented download sequence was never confirmed to produce a functional device re-enumeration.

## How to verify (concrete steps)

### 1. Capture the Windows driver protocol

1. Install the device on Windows with the official `KWORLD_UB320i.sys` driver.
2. Run [USBlyzer](https://www.batchlabs.com/), [USBPcap](https://desowin.org/usbpcap/), or [Wireshark](https://www.wireshark.org/) with USB capture enabled.
3. Trigger a full cycle: firmware load → tune → capture → stop.
4. Compare every control transfer (request, value, index, data) against `ub320i_driver.py` and `asv5211.c`.

### 2. Verify firmware transfer

1. Capture `AS11Loader.sys` transferring firmware to the cold device (`1738:5211`).
2. Confirm each segment's request ID, offset, length, and data match `load_firmware.py` / `SEGMENTS`.
3. Confirm the device re-enumerates to `1b80:b320` after the final segment.

### 3. Test the kernel module on hardware

1. Build against the target kernel (`5.4.125-legacy-sunxi64`).
2. Load with `modprobe asv5211` and attach the device.
3. Check `dmesg` for firmware load, frontend registration, and error messages.
4. Verify `/dev/dvb/adapter0/frontend0` exists.

### 4. Verify ISDB-T lock and stream

1. Point an antenna at a known ISDB-T transmitter in Japan (or a signal generator).
2. Tune with `dvb-fe-tool -S -a 0 -f <frequency>` or `w_scan -c JP -t ISDBT`.
3. Check lock status: `dvb-fe-tool -S -a 0` should report `FE_HAS_LOCK` and `FE_HAS_VITERBI`.
4. Capture a stream: `dvb-streamer -o test.ts -d 10 /dev/dvb/adapter0/dvr0`
5. Validate the TS: `tsduck --input test.ts --stats` or check sync bytes with `xxd test.ts | head`.

### 5. Cross-reference with other ASV5211 drivers

Search for:
- Linux mainline patches mentioning "ASV5211" or "asicen"
- Other reverse-engineered implementations on GitHub
- DVB forum discussions about the UB320-i

## What could be wrong

Even if the driver compiles and loads, these issues are likely without verification:

- **Wrong register offsets** — writes hit non-existent or unrelated registers.
- **Wrong data widths** — 16-bit vs 32-bit vs 8-bit mismatches.
- **Missing initialization steps** — hardware requires a specific sequence not captured here.
- **Wrong tuner control** — the integrated tuner may need I2C commands we haven't discovered.
- **Firmware corruption** — if the segmented transfer uses wrong request IDs or offsets, the device won't function even if it re-enumerates.
- **Timing issues** — delays between steps may be critical.

## Conclusion

This repository is a **starting point**, not a working driver. It documents a best-effort reverse engineering attempt but needs hardware verification before it can be trusted.
