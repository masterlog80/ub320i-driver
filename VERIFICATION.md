# Verification Status

> Last updated: 2026-11-27

## Current status

This repository remains an experimental reverse-engineering project. The changes in this branch correct issues found during static review, but **the driver has not yet been built against the target kernel or tested with a physical UB320-i**.

Do not interpret source-level corrections as proof that the USB protocol is correct.

## Source-level corrections in this branch

- Use the Linux 5.4 DVB-USB v2 frontend attach and registration lifecycle.
- Add a frontend release callback for the allocated frontend object.
- Correct DVB frontend information fields and the Japanese UHF channel range.
- Return errors for short register reads/writes and failed statistics reads.
- Avoid modifying the DVB-USB framework's power counter from the driver's power callback.
- Treat incomplete firmware segments as failures; final-segment disconnect-style errors request USB re-enumeration.
- Anchor Python tuning quantization to channel 13 (473.142857 MHz), not to zero.
- Scan Japanese UHF channels 13-52 using their 6 MHz channel spacing.
- Use the standard external-module build/install flow instead of copying selected kernel directories into a partial staging tree.

The kernel statistics callbacks now use 16-bit reads to match the current Python implementation. **This remains an inferred register-width choice and must be confirmed using a Windows USB capture or hardware test.**

## Not yet verified

| Component | Current evidence | Hardware verified? |
|---|---|---|
| Firmware segment addresses and lengths | Reverse-engineered from local firmware/loader analysis | No |
| Firmware request IDs (0xAB/0xAC) | Binary analysis only | No |
| Register read/write requests (0x91/0x90) | Inferred from the current prototype | No |
| Register offsets and data widths | Inferred; not checked against live device | No |
| Initialization sequence | Speculative sequence in source | No |
| Tuner lock/status bit | Assumed bit 0; not confirmed | No |
| Transport stream endpoint and packet framing | Endpoint/188-byte packet assumption | No |
| Japanese channel frequencies | Mapping for channels 13-52, 6 MHz spacing | Standard mapping only |
| Kernel module compilation | Must be built against the exact target kernel tree | No |
| Frontend registration and DVB device nodes | Requires a successful target-kernel load | No |
| MPEG-TS reception | No capture validated for sync bytes, PIDs or PSI/SI | No |

## Build checks

Build against the configured kernel build directory matching the target kernel, with the corresponding source tree available for the internal DVB-USB v2 header:

```bash
./build_dvb.sh \
    --kdir /lib/modules/KERNEL_RELEASE/build \
    --kernel-src /path/to/matching/kernel-source
```

The target kernel must provide the DVB-USB v2 framework and its exported symbols. The helper builds this driver as an external module; it does not build or replace the kernel media subsystem.

A successful build only establishes source/API compatibility with that particular kernel build. It does not establish that the USB commands or register map work.

## Hardware verification procedure

### 1. Capture the Windows protocol

1. Connect the UB320-i to Windows with the original KWorld driver.
2. Capture USB traffic using USBPcap and Wireshark.
3. Capture a full sequence: cold-device firmware upload, operational-device initialization, channel tuning, stream start and stream stop.
4. Compare each transfer's request type, request, value, index, payload and length with the Linux implementation.

### 2. Verify firmware loading

1. Confirm that the cold USB identifier is `1738:5211`.
2. Compare every firmware segment offset, request ID, payload and length against the Windows capture.
3. Verify re-enumeration as `1b80:b320`.
4. Confirm that incomplete writes are reported as failures.

### 3. Verify DVB frontend operation

1. Build against the exact target kernel.
2. Load the module and connect the tuner.
3. Check `dmesg` for firmware, frontend-registration and USB errors.
4. Confirm that `/dev/dvb/adapter0/frontend0`, `demux0` and `dvr0` appear.
5. Verify that frontend tuning requests use the expected Japanese channel-centre frequencies.

### 4. Verify reception

1. Use a known-good Japanese ISDB-T antenna or signal source.
2. Tune to a known channel, for example channel 13 at 473.142857 MHz.
3. Confirm that lock status changes correctly when a valid signal is applied and removed.
4. Capture a transport stream.
5. Validate 188-byte packet alignment, sync bytes (`0x47`), continuity counters, PAT/PMT and service information with TSDuck or equivalent tools.
6. Run a sustained capture and check for USB errors, dropped packets and successful stop/start recovery.

## Safety and licensing notes

- Do not run the protocol explorer's write scan against unknown vendor requests on the physical tuner.
- A warm USB ID alone does not prove that the firmware image is correct.
- An apparent lock bit does not prove valid MPEG-TS reception.
- The firmware binary's redistribution rights remain a separate licensing question; the repository's MIT license does not automatically license third-party firmware.

## Conclusion

This branch is a source-level corrective pass, not a verified Linux driver release. A target-kernel build, Windows USB protocol capture and physical reception test are still required before calling the driver functional.
