#!/usr/bin/env python3
"""
UB320-i USB Protocol Explorer

Explores the USB control protocol of the KWorld UB320-i (1b80:b320)
to discover the register map and command set.

Usage:
    sudo python3 ub320i_explore.py                  # Full register scan
    sudo python3 ub320i_explore.py --write 0x10 0xFF  # Write register
    sudo python3 ub320i_explore.py --read 0x10        # Read register
    sudo python3 ub320i_explore.py --request 0x90     # Try specific request
"""

import argparse
import struct
import sys
import time

try:
    import usb.core
    import usb.util
except ImportError:
    print("Error: pyusb required. Install with: pip3 install pyusb")
    sys.exit(1)

VENDOR_ID = 0x1b80
PRODUCT_ID = 0xb320


def find_device():
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if dev is None:
        print("Device not found!")
        sys.exit(1)
    return dev


def claim_device(dev):
    cfg = dev.get_active_configuration()
    iface = cfg[(0, 0)]
    if dev.is_kernel_driver_active(0):
        try:
            dev.detach_kernel_driver(0)
            print("  Detached kernel driver")
        except Exception:
            pass
    try:
        usb.util.claim_interface(dev, iface)
    except Exception as e:
        print(f"  Warning: {e}")


def vendor_read(dev, request, value, index, length):
    try:
        data = dev.ctrl_transfer(0xC0, request, value, index, length, timeout=2000)
        return bytes(data)
    except usb.core.USBError as e:
        return None


def vendor_write(dev, request, value, index, data):
    try:
        written = dev.ctrl_transfer(0x40, request, value, index, data, timeout=2000)
        return written
    except usb.core.USBError as e:
        return None


KNOWN_REQUESTS = {
    0x90: "Register write (OUT) - used by ub320i_driver.py",
    0x91: "Register read (IN) - used by ub320i_driver.py",
    0xAB: "Firmware download segment 1-3 (OUT) - used by load_firmware.py",
    0xAC: "Firmware download segment 4 (OUT) - used by load_firmware.py",
}


def scan_requests(dev, write=False):
    """Try all vendor control request types.
    
    WARNING: Writing to unknown request IDs can trigger undocumented device
    behavior including hardware resets, configuration changes, or firmware
    operations. Read-only scanning is strongly preferred.
    """
    if write:
        print("WARNING: Writing to unknown vendor requests is dangerous.")
        print("  This may reset the device, change configuration, or trigger")
        print("  undocumented operations. Proceed with caution.")
        print()
        confirm = input("  Type 'YES' to continue with write scanning: ")
        if confirm != "YES":
            print("Aborted.")
            return
    
    print("Scanning vendor control requests...")
    print("  Known requests:")
    for req_id, desc in sorted(KNOWN_REQUESTS.items()):
        print(f"    0x{req_id:02X} - {desc}")
    print()
    if write:
        print("  Format: request | DIR=OUT (write 0xAA) | DIR=IN (read 4 bytes)")
    else:
        print("  Format: request | DIR=IN (read 4 bytes)")
    print()

    for req in range(0x10, 0xFF):
        status = ""
        in_result = vendor_read(dev, req, 0x0000, 0x0000, 4)
        
        if write:
            out_result = vendor_write(dev, req, 0x0000, 0x0000, b'\xAA')
        else:
            out_result = None
        
        if out_result is not None and in_result is not None:
            status = "R+W"
            if in_result:
                hex_data = ' '.join(f'{b:02x}' for b in in_result)
                status += f"  data: {hex_data}"
        elif out_result is not None:
            status = "W"
        elif in_result is not None:
            status = "R"
            if in_result:
                hex_data = ' '.join(f'{b:02x}' for b in in_result)
                status += f"  data: {hex_data}"
        else:
            continue  # Skip dead requests

        # Annotate known requests
        if req in KNOWN_REQUESTS:
            status += f" [KNOWN: {KNOWN_REQUESTS[req]}]"
        
        print(f"  0x{req:02X}  ->  {status}")
        time.sleep(0.01)


def scan_registers(dev, request, start=0, end=0x200, step=4):
    """Scan register space via a known working request."""
    print(f"Scanning registers 0x{start:04X}-0x{end:04X} (step={step}) via request 0x{request:02X}...")
    print(f"  Address   | Value (LE32)  | Hex")
    print("  " + "-" * 50)

    for addr in range(start, end, step):
        val = vendor_read(dev, request, addr, 0x0000, 4)
        if val and len(val) == 4:
            dword = struct.unpack('<I', val)[0]
            # Only print non-zero/non-pattern values
            if dword != 0 and dword != 0xFFFFFFFF:
                print(f"  0x{addr:04X}   | {dword:>10d}    | 0x{dword:08X}")
        time.sleep(0.01)


def interactive(dev):
    """Interactive protocol shell."""
    print("UB320-i Protocol Explorer (interactive)")
    print("Commands:")
    print("  wr <req> <value> <index> <hexdata>  - vendor write")
    print("  rd <req> <value> <index> <length>    - vendor read")
    print("  scan <req> <start> <end> <step>       - register scan")
    print("  reqs                                   - request scan")
    print("  quit                                   - exit")
    print()

    while True:
        try:
            cmd = input("ub320> ").strip()
            if not cmd:
                continue
            parts = cmd.split()

            if parts[0] == 'quit':
                break
            elif parts[0] == 'wr' and len(parts) >= 5:
                req = int(parts[1], 16)
                value = int(parts[2], 16)
                index = int(parts[3], 16)
                data = bytes.fromhex(parts[4])
                result = vendor_write(dev, req, value, index, data)
                print(f"  Wrote {result} bytes" if result is not None else "  Failed")
            elif parts[0] == 'rd' and len(parts) >= 5:
                req = int(parts[1], 16)
                value = int(parts[2], 16)
                index = int(parts[3], 16)
                length = int(parts[4], 16)
                result = vendor_read(dev, req, value, index, length)
                if result is not None:
                    print(f"  {result.hex()}")
                else:
                    print("  Failed")
            elif parts[0] == 'scan' and len(parts) >= 5:
                req = int(parts[1], 16)
                start = int(parts[2], 16)
                end = int(parts[3], 16)
                step = int(parts[4], 16)
                scan_registers(dev, req, start, end, step)
            elif parts[0] == 'reqs':
                scan_requests(dev)
            else:
                print("  Unknown command or wrong arguments")

        except (KeyboardInterrupt, EOFError):
            break
        except Exception as e:
            print(f"  Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="UB320-i USB Protocol Explorer")
    parser.add_argument('--scan-requests', action='store_true', help='Scan all vendor requests')
    parser.add_argument('--scan-registers', action='store_true', help='Scan register space')
    parser.add_argument('--request', type=str, help='Request ID for register scan (hex)')
    parser.add_argument('--read', type=str, help='Read single register (hex address)')
    parser.add_argument('--write', nargs=2, type=str, help='Write register (address hex, value hex)')
    parser.add_argument('--interactive', '-i', action='store_true', help='Interactive mode')

    args = parser.parse_args()

    dev = find_device()
    claim_device(dev)

    if args.scan_requests:
        scan_requests(dev)
        return 0

    if args.interactive:
        interactive(dev)
        return 0

    if args.read:
        addr = int(args.read, 16)
        if args.request:
            req = int(args.request, 16)
        else:
            req = 0x91  # Default read request
        data = vendor_read(dev, req, addr, 0x0000, 4)
        if data:
            print(f"  0x{addr:04X}: {data.hex()}")
        else:
            print(f"  Read failed for 0x{addr:04X}")
        return 0

    if args.write:
        addr = int(args.write[0], 16)
        value = int(args.write[1], 16)
        if args.request:
            req = int(args.request, 16)
        else:
            req = 0x90  # Default write request
        data = struct.pack('<I', value)
        result = vendor_write(dev, req, addr, 0x0000, data)
        print(f"  Wrote 0x{value:08X} to 0x{addr:04X} ({result} bytes)" if result else "  Write failed")
        return 0

    if args.scan_registers:
        req = int(args.request, 16) if args.request else 0x91
        scan_registers(dev, req)
        return 0

    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
