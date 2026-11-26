#!/usr/bin/env python3
"""
UB320-i Firmware Loader (copy for convenience in driver package)

Loads the ASV5211 firmware into the KWorld UB320-i bootloader (1738:5211),
causing the device to re-enumerate as 1b80:b320.

Usage:
    sudo python3 load_firmware.py ub320i.fw
"""
import argparse
import sys
import time

COLD = (0x1738, 0x5211)
WARM = (0x1B80, 0xB320)
IMAGE_SIZE = 0x4000
W_INDEX = 0x55DC
BM_REQUEST_TYPE = 0x40
SEGMENTS = ((0x0000, 0x0C00, 0xAB), (0x2000, 0x0400, 0xAB), (0x2800, 0x1000, 0xAB), (0x3800, 0x0800, 0xAC))


def plan(image):
    if len(image) != IMAGE_SIZE:
        raise ValueError(f"firmware must be {IMAGE_SIZE} bytes, got {len(image)}")
    return [(BM_REQUEST_TYPE, req, off, W_INDEX, image[off:off + ln]) for off, ln, req in SEGMENTS]


def send(dev, transfers, log=print):
    for n, (bm, req, value, index, data) in enumerate(transfers, 1):
        log(f"  [{n}/{len(transfers)}] bmRequestType={bm:#04x} bRequest={req:#04x} wValue={value:#06x} "
            f"wIndex={index:#06x} len={len(data):#06x}")
        written = dev.ctrl_transfer(bm, req, value, index, data, timeout=5000)
        if written != len(data):
            raise IOError(f"short transfer: {written} of {len(data)} bytes")


def wait_for(usb_core, ids, seconds):
    end = time.time() + seconds
    while time.time() < end:
        dev = usb_core.find(idVendor=ids[0], idProduct=ids[1])
        if dev is not None:
            return dev
        time.sleep(0.25)
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("firmware")
    ap.add_argument("--dry-run", action="store_true", help="print the transfers, send nothing")
    ap.add_argument("--wait", type=float, default=10, help="seconds to wait for 1b80:b320 afterwards")
    args = ap.parse_args(argv)
    image = open(args.firmware, "rb").read()
    transfers = plan(image)
    if args.dry_run:
        for bm, req, value, index, data in transfers:
            print(f"  bmRequestType={bm:#04x} bRequest={req:#04x} wValue={value:#06x} wIndex={index:#06x} len={len(data):#06x}")
        print("dry run: nothing sent")
        return 0

    import usb.core
    if usb.core.find(idVendor=WARM[0], idProduct=WARM[1]) is not None:
        print("A 1b80:b320 device is already present: firmware is loaded.")
        return 0
    dev = usb.core.find(idVendor=COLD[0], idProduct=COLD[1])
    if dev is None:
        print("No 1738:5211 device found. Is the stick plugged in?")
        return 1
    print(f"Found {COLD[0]:04x}:{COLD[1]:04x} on bus {dev.bus} address {dev.address}; sending firmware")
    try:
        send(dev, transfers)
    except usb.core.USBError:
        print("USB error during transfer (may be normal on last request)")
    print(f"Waiting up to {args.wait:.0f}s for {WARM[0]:04x}:{WARM[1]:04x} ...")
    warm = wait_for(usb.core, WARM, args.wait)
    if warm is None:
        print("The stick did NOT re-enumerate as 1b80:b320.")
        return 2
    print("SUCCESS: the stick re-enumerated as 1b80:b320.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
