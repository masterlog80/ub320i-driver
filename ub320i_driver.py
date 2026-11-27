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
ISDB_T_JAPAN_FREQ_MAX = 707_142_857   # Channel 52
ISDB_T_FIRST_CHANNEL = 13
ISDB_T_LAST_CHANNEL = 52
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
    if length == 4:
        data = struct.pack('<I', value)
    elif length == 2:
        data = struct.pack('<H', value)
    else:
        raise ValueError("register writes support only 2-byte or 4-byte values")

    written = dev.ctrl_transfer(USB_DIR_OUT, 0x90, reg, 0x0000, data, timeout=2000)
    if written != len(data):
        raise IOError(f"short register write at 0x{reg:04X}: {written}/{len(data)} bytes")


def read_reg(dev, reg, length=4):
    """Read a register value via vendor control transfer."""
    try:
        data = bytes(dev.ctrl_transfer(USB_DIR_IN, 0x91, reg, 0x0000, length, timeout=2000))
        if len(data) != length:
            raise IOError(f"short register read at 0x{reg:04X}: {len(data)}/{length} bytes")
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


def channel_frequency(channel):
    """Return the Japanese ISDB-T channel centre frequency in Hz."""
    if not ISDB_T_FIRST_CHANNEL <= channel <= ISDB_T_LAST_CHANNEL:
        raise ValueError(
            f"channel must be between {ISDB_T_FIRST_CHANNEL} and {ISDB_T_LAST_CHANNEL}"
        )
    return ISDB_T_JAPAN_FREQ_MIN + (channel - ISDB_T_FIRST_CHANNEL) * ISDB_T_JAPAN_FREQ_STEP


def tune_frequency(dev, frequency_hz):
    """Tune to the nearest valid Japanese UHF ISDB-T channel centre."""
    if not (ISDB_T_JAPAN_FREQ_MIN <= frequency_hz <= ISDB_T_JAPAN_FREQ_MAX):
        print(f"  Frequency {frequency_hz}Hz outside Japanese UHF channel range", file=sys.stderr)
        return False

    # Quantize relative to channel 13, not to zero.
    channel_index = round(
        (frequency_hz - ISDB_T_JAPAN_FREQ_MIN) / ISDB_T_JAPAN_FREQ_STEP
    )
    freq = ISDB_T_JAPAN_FREQ_MIN + channel_index * ISDB_T_JAPAN_FREQ_STEP
    if not (ISDB_T_JAPAN_FREQ_MIN <= freq <= ISDB_T_JAPAN_FREQ_MAX):
        print(f"  Rounded frequency {freq}Hz is outside the supported channel range", file=sys.stderr)
        return False

    print(f"  Tuning to {freq}Hz ({freq/1e6:.6f} MHz)...", file=sys.stderr)
    write_reg(dev, REG_TUNER_FREQ, int(freq))
    time.sleep(0.5)

    write_reg(dev, REG_DEMOD_CONTROL, 0x00000003)
    time.sleep(1.0)

    status = read_reg(dev, REG_DEMOD_STATUS)
    if status is not None:
        if status & 0x01:
            snr = read_reg(dev, REG_DEMOD_SNR, 2)
            signal = read_reg(dev, REG_DEMOD_SIGNAL, 2)
            print(f"  Locked! SNR={snr}, Signal={signal}", file=sys.stderr)
            return True
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


def scan_channels(dev, first_channel=ISDB_T_FIRST_CHANNEL,
                  last_channel=ISDB_T_LAST_CHANNEL):
    """Scan Japanese UHF channels 13-52 using their 6 MHz channel raster."""
    if first_channel < ISDB_T_FIRST_CHANNEL or last_channel > ISDB_T_LAST_CHANNEL:
        raise ValueError(
            f"scan channel range must be {ISDB_T_FIRST_CHANNEL}-{ISDB_T_LAST_CHANNEL}"
        )
    if first_channel > last_channel:
        raise ValueError("scan start channel must not exceed scan end channel")

    channels = []
    channel_count = last_channel - first_channel + 1
    print(
        f"Scanning ISDB-T channels {first_channel}-{last_channel} "
        f"({channel_frequency(first_channel)/1e6:.6f}-"
        f"{channel_frequency(last_channel)/1e6:.6f} MHz)...",
        file=sys.stderr,
    )

    try:
        for index, channel in enumerate(range(first_channel, last_channel + 1), 1):
            freq = channel_frequency(channel)
            pct = index / channel_count * 100
            tune_frequency(dev, freq)

            status = read_reg(dev, REG_DEMOD_STATUS)
            if status is not None and (status & 0x01):
                snr = read_reg(dev, REG_DEMOD_SNR, 2)
                channels.append((freq, snr))
                print(
                    f"  [{pct:.0f}%] Channel {channel}: {freq/1e6:.6f} MHz (SNR={snr})",
                    file=sys.stderr,
                )
            else:
                print(
                    f"  [{pct:.0f}%] Channel {channel}: {freq/1e6:.6f} MHz ...",
                    file=sys.stderr,
                )
    finally:
        stop_capture(dev)

    return channels


def get_channel_number(frequency_hz):
    """Convert frequency to Japan ISDB-T channel number."""
    # Japan terrestrial TV: Ch13=473.142857 MHz, 6 MHz spacing
    return round((frequency_hz - ISDB_T_JAPAN_FREQ_MIN) / ISDB_T_JAPAN_FREQ_STEP) + ISDB_T_FIRST_CHANNEL


def release_device(dev, iface, kernel_driver_was_active, interface_claimed=True):
    """Release USB interface and restore kernel driver."""
    if interface_claimed and iface is not None:
        try:
            usb.util.release_interface(dev, iface)
        except usb.core.USBError as e:
            print(f"  Warning: could not release interface: {e}", file=sys.stderr)
    if kernel_driver_was_active:
        try:
            dev.attach_kernel_driver(0)
            print("  Kernel driver re-attached", file=sys.stderr)
        except usb.core.USBError as e:
            print(f"  Warning: could not re-attach kernel driver: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="UB320-i Linux Userspace Driver for ISDB-T reception",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--frequency', '-f', type=int,
                        help='Frequency in Hz (e.g., 473142857, channel 13)')
    parser.add_argument('--channel', '-c', type=int,
                        help='Japan ISDB-T UHF channel number (13-52)')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='Output file for TS stream (default: stdout)')
    parser.add_argument('--scan', action='store_true',
                        help='Scan for channels')
    parser.add_argument('--scan-min-channel', type=int, default=ISDB_T_FIRST_CHANNEL,
                        help='First Japanese UHF channel to scan (default: 13)')
    parser.add_argument('--scan-max-channel', type=int, default=ISDB_T_LAST_CHANNEL,
                        help='Last Japanese UHF channel to scan (default: 52)')
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
    if args.channel is not None and args.frequency is not None:
        parser.error('--channel and --frequency cannot be used together')
    if args.channel is not None:
        try:
            args.frequency = channel_frequency(args.channel)
        except ValueError as e:
            parser.error(str(e))
        print(f"Channel {args.channel} = {args.frequency}Hz ({args.frequency/1e6:.6f} MHz)", file=sys.stderr)

    # Find device
    print(f"Looking for device {VENDOR_ID:04X}:{PRODUCT_ID:04X}...", file=sys.stderr)
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)

    if dev is None:
        print("Device not found!", file=sys.stderr)
        print("Firmware may need to be loaded first:", file=sys.stderr)
        print("  sudo python3 load_firmware.py firmware/ub320i.fw", file=sys.stderr)
        return 1

    print(f"Found device on bus {dev.bus} address {dev.address}", file=sys.stderr)

    # Claim interface
    iface = None
    interface_claimed = False
    kernel_driver_was_active = False
    try:
        cfg = dev.get_active_configuration()
        iface = cfg[(0, 0)]
        kernel_driver_was_active = dev.is_kernel_driver_active(0)
        if kernel_driver_was_active:
            print("  Detaching kernel driver...", file=sys.stderr)
            dev.detach_kernel_driver(0)
        usb.util.claim_interface(dev, iface)
        interface_claimed = True
    except Exception as e:
        print(f"  Error: could not claim interface: {e}", file=sys.stderr)
        print("  Try running with sudo", file=sys.stderr)
        release_device(dev, iface, kernel_driver_was_active, interface_claimed)
        return 1

    try:
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
            print(f"  Status: 0x{status:08X}" if status is not None else "  Status: unavailable", file=sys.stderr)
            print(f"  SNR: {snr}" if snr is not None else "  SNR: unavailable", file=sys.stderr)
            print(f"  Signal: {signal}" if signal is not None else "  Signal: unavailable", file=sys.stderr)
            print(f"  BER: {ber}" if ber is not None else "  BER: unavailable", file=sys.stderr)
            return 0

        # Scan mode
        if args.scan:
            if args.frequency is not None or args.channel is not None:
                parser.error('--scan cannot be combined with --frequency or --channel')
            try:
                channels = scan_channels(
                    dev,
                    args.scan_min_channel,
                    args.scan_max_channel,
                )
            except ValueError as e:
                parser.error(str(e))

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

    finally:
        # Always release the USB interface and restore the kernel driver
        release_device(dev, iface, kernel_driver_was_active, interface_claimed)

    return 0


if __name__ == '__main__':
    sys.exit(main())
