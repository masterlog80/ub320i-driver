#!/usr/bin/env python3
"""
UB320-i Userspace Driver for Linux
KWorld ISDB-T UB320-i (AsicEn ASV5211)

This driver communicates with the loaded device (1b80:b320) via USB vendor
control transfers to configure the tuner and demodulator, then reads MPEG-TS
data from bulk endpoints.

Based on reverse engineering of the Windows BDA driver KWORLD_UB320i.sys
and AS11Loader.sys firmware loader.

Usage:
    python3 ub320i_driver.py --frequency 461750000 --output channel.ts
    python3 ub320i_driver.py --scan --output scan_results.txt
    python3 ub320i_driver.py --channels
"""

import argparse
import struct
import sys
import time
import threading
import os

try:
    import usb.core
    import usb.util
except ImportError:
    print("Error: pyusb required. Install with: pip3 install pyusb", file=sys.stderr)
    sys.exit(1)

# Device IDs
VENDOR_ID = 0x1b80
PRODUCT_ID = 0xb320

# USB control transfer constants
USB_DIR_OUT = 0x40  # Host-to-device, vendor, device
USB_DIR_IN = 0xC0   # Device-to-host, vendor, device
USB_DIR_IN_CLASS = 0xA0  # Device-to-host, class, interface

# Endpoints
EP_TS_IN = 0x81    # MPEG-TS bulk data
EP_STATUS_IN = 0x82  # Status/control data

# ISDB-T Japan parameters
ISDB_T_BANDWIDTH_6MHZ = 0
ISDB_T_BANDWIDTH_7MHZ = 1
ISDB_T_BANDWIDTH_8MHZ = 2

ISDB_T_ONESEG = True   # This is a 1-seg (mobile) tuner
ISDB_T_JAPAN_FREQ_MIN = 473_142_857   # Channel 13
ISDB_T_JAPAN_FREQ_MAX = 767_142_857   # Channel 62
ISDB_T_JAPAN_FREQ_STEP = 6_000_000  # Hz (6 MHz spacing)

# Register addresses inferred from firmware analysis
REG_TUNER_FREQ = 0x0010
REG_TUNER_BW = 0x0014
REG_TUNER_GAIN = 0x0018
REG_DEMOD_CONTROL = 0x0020
REG_DEMOD_STATUS = 0x0024
REG_DEMOD_SNR = 0x0028
REG_DEMOD_SIGNAL = 0x002C
REG_DEMOD_BER = 0x0030
REG_OUTPUT_CONTROL = 0x0040
REG_TS_PID_FILTER = 0x0044

# Default TS packet size
TS_PACKET_SIZE = 188


def write_reg(dev, reg, value, length=4):
    """Write a register value via vendor control transfer."""
    data = struct.pack('<I', value) if length == 4 else struct.pack('<H', value)
    if length == 2:
        data = struct.pack('<H', value)
    try:
        dev.ctrl_transfer(USB_DIR_OUT, 0x90, reg, 0x0000, data, timeout=2000)
    except usb.core.USBError as e:
        raise


def read_reg(dev, reg, length=4):
    """Read a register value via vendor control transfer."""
    try:
        data = dev.ctrl_transfer(USB_DIR_IN, 0x91, reg, 0x0000, length, timeout=2000)
        if length == 4:
            return struct.unpack('<I', bytes(data))[0]
        elif length == 2:
            return struct.unpack('<H', bytes(data))[0]
        return bytes(data)
    except usb.core.USBError as e:
        print(f"  Warning: read_reg(0x{reg:04X}) failed: {e}", file=sys.stderr)
        return None


def read_regs_block(dev, reg, count):
    """Read multiple consecutive registers."""
    results = []
    for i in range(count):
        val = read_reg(dev, reg + i * 4, 4)
        results.append(val)
    return results


def initialize_device(dev):
    """Initialize the device after firmware load."""
    print("Initializing device...", file=sys.stderr)

    # Reset device
    write_reg(dev, REG_DEMOD_CONTROL, 0x00000001)
    time.sleep(0.1)

    # Soft reset
    write_reg(dev, REG_DEMOD_CONTROL, 0x00000000)
    time.sleep(0.1)

    # Set ISDB-T mode (value inferred from firmware)
    write_reg(dev, REG_DEMOD_CONTROL, 0x00000002)
    time.sleep(0.05)

    # Set bandwidth for 6MHz (Japan mobile TV)
    write_reg(dev, REG_TUNER_BW, ISDB_T_BANDWIDTH_6MHZ)
    time.sleep(0.05)

    # Enable AGC
    write_reg(dev, REG_TUNER_GAIN, 0x00000001)
    time.sleep(0.05)

    # Set output to TS mode
    write_reg(dev, REG_OUTPUT_CONTROL, 0x00000001)
    time.sleep(0.05)

    # Configure PID filter for all PIDs (pass-through mode)
    write_reg(dev, REG_TS_PID_FILTER, 0xFFFFFFFF)
    time.sleep(0.05)

    print("  Device initialized", file=sys.stderr)


def tune_frequency(dev, frequency_hz):
    """Tune to a specific frequency in Hz."""
    if not (ISDB_T_JAPAN_FREQ_MIN <= frequency_hz <= ISDB_T_JAPAN_FREQ_MAX):
        print(f"  Warning: frequency {frequency_hz}Hz outside Japan ISDB-T range", file=sys.stderr)

    # Round to nearest frequency step
    freq = round(frequency_hz / ISDB_T_JAPAN_FREQ_STEP) * ISDB_T_JAPAN_FREQ_STEP

    print(f"  Tuning to {freq}Hz ({freq/1e6:.3f} MHz)...", file=sys.stderr)

    # Set frequency (firmware uses little-endian 32-bit frequency)
    write_reg(dev, REG_TUNER_FREQ, int(freq))
    time.sleep(0.5)

    # Start demodulation
    write_reg(dev, REG_DEMOD_CONTROL, 0x00000003)
    time.sleep(1.0)

    # Check lock status
    status = read_reg(dev, REG_DEMOD_STATUS)
    if status is not None:
        locked = bool(status & 0x01)
        if locked:
            snr = read_reg(dev, REG_DEMOD_SNR, 2)
            signal = read_reg(dev, REG_DEMOD_SIGNAL, 2)
            print(f"  Locked! SNR={snr}, Signal={signal}", file=sys.stderr)
            return True
        else:
            print("  No lock detected", file=sys.stderr)
            return False
    return False


def stop_capture(dev):
    """Stop TS capture."""
    write_reg(dev, REG_DEMOD_CONTROL, 0x00000000)
    time.sleep(0.1)


def read_ts_data(dev, timeout_ms=1000):
    """Read one TS packet from the device."""
    try:
        data = dev.read(EP_TS_IN, TS_PACKET_SIZE, timeout=timeout_ms)
        if data:
            return bytes(data)
    except usb.core.USBError as e:
        if e.errno != 110:  # Ignore timeout
            print(f"  USB read error: {e}", file=sys.stderr)
    return None


def scan_channels(dev, freq_min, freq_max, freq_step=1_562_500):
    """Scan for ISDB-T channels in the given frequency range."""
    print(f"Scanning {freq_min/1e6:.1f} - {freq_max/1e6:.1f} MHz (step {freq_step/1000} kHz)...", file=sys.stderr)

    channels = []
    freq = freq_min
    total = int((freq_max - freq_min) / freq_step) + 1

    while freq <= freq_max:
        progress = int((freq - freq_min) / freq_step)
        pct = (progress / total) * 100

        tune_frequency(dev, freq)

        status = read_reg(dev, REG_DEMOD_STATUS)
        if status and (status & 0x01):
            snr = read_reg(dev, REG_DEMOD_SNR, 2)
            channels.append((freq, snr))
            print(f"  [{pct:.0f}%] Channel found: {freq/1e6:.3f} MHz (SNR={snr})", file=sys.stderr)
        else:
            print(f"  [{pct:.0f}%] {freq/1e6:.3f} MHz ...", file=sys.stderr)

        freq += freq_step

    # Stop capture after scan
    stop_capture(dev)

    return channels


def get_channel_number(frequency_hz):
    """Convert frequency to Japan ISDB-T channel number."""
    # Japan terrestrial TV: Ch13=473.142857 MHz, 6 MHz spacing
    ch_num = round((frequency_hz - 473_142_857) / 6_000_000) + 13
    return ch_num


def main():
    parser = argparse.ArgumentParser(
        description="UB320-i Linux Userspace Driver for ISDB-T reception",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--frequency', '-f', type=int,
                        help='Frequency in Hz (e.g., 461750000)')
    parser.add_argument('--channel', '-c', type=int,
                        help='Japan ISDB-T channel number (13-62)')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='Output file for TS stream (default: stdout)')
    parser.add_argument('--scan', action='store_true',
                        help='Scan for channels')
    parser.add_argument('--scan-min', type=float, default=175.0,
                        help='Scan minimum frequency in MHz (default: 175)')
    parser.add_argument('--scan-max', type=float, default=770.0,
                        help='Scan maximum frequency in MHz (default: 770)')
    parser.add_argument('--duration', type=int, default=0,
                        help='Capture duration in seconds (0=infinite)')
    parser.add_argument('--status', action='store_true',
                        help='Show device status and exit')
    parser.add_argument('--init-only', action='store_true',
                        help='Just initialize device and exit')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug output')

    args = parser.parse_args()

    # Convert channel number to frequency if needed
    if args.channel and not args.frequency:
        args.frequency = 473_142_857 + (args.channel - 13) * 6_000_000
        print(f"Channel {args.channel} = {args.frequency}Hz ({args.frequency/1e6:.3f} MHz)", file=sys.stderr)

    # Find device
    print(f"Looking for device {VENDOR_ID:04X}:{PRODUCT_ID:04X}...", file=sys.stderr)
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)

    if dev is None:
        print("Device not found!", file=sys.stderr)
        print("Firmware may need to be loaded first:", file=sys.stderr)
        print("  sudo python3 load_firmware.py ub320i.fw", file=sys.stderr)
        return 1

    print(f"Found device on bus {dev.bus} address {dev.address}", file=sys.stderr)

    # Claim interface
    try:
        cfg = dev.get_active_configuration()
        iface = cfg[(0, 0)]
        if dev.is_kernel_driver_active(0):
            print("  Detaching kernel driver...", file=sys.stderr)
            dev.detach_kernel_driver(0)
        usb.util.claim_interface(dev, iface)
    except Exception as e:
        print(f"  Warning: could not claim interface: {e}", file=sys.stderr)
        print("  Try running with sudo", file=sys.stderr)

    # Initialize
    initialize_device(dev)

    if args.init_only:
        print("Initialization complete", file=sys.stderr)
        return 0

    # Status mode
    if args.status:
        print("Device Status:", file=sys.stderr)
        status = read_reg(dev, REG_DEMOD_STATUS)
        snr = read_reg(dev, REG_DEMOD_SNR, 2)
        signal = read_reg(dev, REG_DEMOD_SIGNAL, 2)
        ber = read_reg(dev, REG_DEMOD_BER, 2)
        print(f"  Status: 0x{status:08X}" if status else "  Status: unavailable", file=sys.stderr)
        print(f"  SNR: {snr}" if snr is not None else "  SNR: unavailable", file=sys.stderr)
        print(f"  Signal: {signal}" if signal is not None else "  Signal: unavailable", file=sys.stderr)
        print(f"  BER: {ber}" if ber is not None else "  BER: unavailable", file=sys.stderr)
        return 0

    # Scan mode
    if args.scan:
        channels = scan_channels(
            dev,
            int(args.scan_min * 1e6),
            int(args.scan_max * 1e6),
            1_562_500
        )

        if args.output:
            with open(args.output, 'w') as f:
                f.write("Frequency(MHz)\tChannel\tSNR\n")
                for freq, snr in channels:
                    ch = get_channel_number(freq)
                    f.write(f"{freq/1e6:.3f}\t{ch}\t{snr}\n")
            print(f"\nScan results saved to {args.output}", file=sys.stderr)
        else:
            print(f"\nFound {len(channels)} channels:", file=sys.stderr)
            for freq, snr in channels:
                ch = get_channel_number(freq)
                print(f"  Channel {ch}: {freq/1e6:.3f} MHz (SNR={snr})", file=sys.stderr)

        if not channels:
            print("No channels found. Try adjusting antenna or scan range.", file=sys.stderr)
        return 0 if channels else 1

    # Capture mode
    if not args.frequency:
        print("Error: --frequency or --channel required for capture mode", file=sys.stderr)
        parser.print_help()
        return 1

    # Tune
    if not tune_frequency(dev, args.frequency):
        print("Warning: tuning failed, attempting capture anyway...", file=sys.stderr)

    # Open output
    outfile = None
    if args.output:
        outfile = open(args.output, 'wb')
        print(f"Writing to {args.output}", file=sys.stderr)
    else:
        print("Writing to stdout (pipe to file or player)", file=sys.stderr)

    # Capture loop
    packets = 0
    bytes_written = 0
    start_time = time.time()
    try:
        while True:
            if args.duration and (time.time() - start_time) >= args.duration:
                break

            data = read_ts_data(dev, timeout_ms=500)
            if data:
                if outfile:
                    outfile.write(data)
                else:
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                packets += 1
                bytes_written += len(data)

                # Progress report every 1000 packets
                if packets % 1000 == 0:
                    elapsed = time.time() - start_time
                    rate = bytes_written / elapsed / 1024
                    print(f"\r  {packets} packets, {bytes_written/1024/1024:.1f} MB ({rate:.1f} KB/s)", file=sys.stderr, end='', flush=True)

    except KeyboardInterrupt:
        print(f"\n\nCapture stopped after {packets} packets ({bytes_written/1024/1024:.1f} MB)", file=sys.stderr)

    finally:
        stop_capture(dev)
        if outfile:
            outfile.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
