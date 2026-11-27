# KWorld UB320-i (ASV5211) Linux DVB Driver

Experimental Linux support for the **KWorld UB320-i**, a Japanese ISDB-T ONE SEG USB TV tuner based on the **AsicEn ASV5211**.

> **Status: experimental — not yet demonstrated to build or operate on physical hardware.** The repository contains a Linux DVB-USB v2 kernel-driver prototype and earlier PyUSB userspace tools. Static analysis of the supplied Windows driver package confirms the USB identities and bootloader firmware-transfer layout, but it also shows that the Linux prototype's operational control protocol is not established. The immediate goal is to build the module against the target kernel and collect device evidence; this repository must not yet be treated as a working TV driver.

## Hardware and device identity

| Property | Value |
|---|---|
| Product | KWorld UB320-i USB TV tuner |
| Chipset | AsicEn ASV5211 |
| Reception standard | Japanese ISDB-T ONE SEG (mobile TV) |
| Bootloader / cold USB ID | \`1738:5211\` |
| Firmware-loaded / warm USB ID | \`1b80:b320\` |
| Japanese UHF channel plan | Channels 13–52 |
| Channel 13 centre frequency | 473.142857 MHz |
| Channel 52 centre frequency | 707.142857 MHz |
| Channel spacing | 6 MHz |
| Channel bandwidth configured by the prototype | 6 MHz |

The cold and warm identifiers are confirmed by the Windows INF/configuration files in the driver package analysed during development. The frequency range is the Japanese UHF channel plan used by the code; it is not evidence that the device tuning protocol works.

## Repository layout

The repository contains three related pieces of work: the Linux kernel module, an alternative direct-USB Python implementation, and tools used to load firmware and investigate the USB protocol.

~~~text
ub320i-driver/
├── README.md
├── LICENSE
├── Makefile                       # Convenience targets for legacy userspace tools and udev rules
├── build_dvb.sh                   # Out-of-tree Linux kernel module build/install helper
├── driver/
│   ├── asv5211.c                  # ASV5211 Linux DVB-USB v2 driver prototype
│   ├── Makefile                   # Kbuild external-module rules
│   ├── 90-ub320i.rules            # udev permissions for cold/warm USB IDs and DVB nodes
│   └── Windows/
│       └── Driver_UB320i_...zip   # Path reserved for the original Windows package (see note below)
├── firmware/
│   └── ub320i.fw                  # 16 KiB firmware image used by the loaders
├── load_firmware.py               # Standalone PyUSB firmware uploader
├── ub320i_driver.py               # Experimental PyUSB tuning/status/TS-capture prototype
├── ub320i_explore.py              # Low-level USB request/register exploration utility
└── rules/
    └── 99-ub320i.rules            # Alternate udev rule file with the same general purpose
~~~

### File responsibilities

| File or directory | Scope |
|---|---|
| **driver/asv5211.c** | Main Linux kernel module. Registers the USB device with the DVB-USB v2 framework, requests/downloads firmware for the cold ID, allocates a DVB frontend, and implements provisional power, tuning, status, and stream callbacks. |
| **driver/Makefile** | Standard external-module Kbuild file. Builds against a configured kernel build directory and adds the include path for the internal DVB-USB v2 header. It also provides module-install and firmware-copy targets. |
| **build_dvb.sh** | Repository-level wrapper around Kbuild. Checks the kernel build directory, matching source header and firmware file; optionally installs the module and firmware and runs depmod. |
| **firmware/ub320i.fw** | 16,384-byte firmware image requested by the kernel driver as **dvb-usb-asv5211.fw** after installation. The image has not been compared byte-for-byte with a firmware payload extracted from the Windows package. |
| **load_firmware.py** | Standalone PyUSB firmware loader for a cold \`1738:5211\` device. It sends the four known segments, checks for short transfers and waits for the warm \`1b80:b320\` ID. Its \`--dry-run\` option prints the transfer plan without sending USB commands. |
| **ub320i_driver.py** | Alternative userspace prototype for the warm device. It claims the USB interface, issues the currently assumed register requests, offers initialisation/status/tuning/channel-scan operations, and reads data from a provisional bulk endpoint. It does not use the Linux DVB frontend. |
| **ub320i_explore.py** | Low-level PyUSB utility for reading/writing vendor requests and scanning request/register ranges. It can issue arbitrary writes; it is a reverse-engineering aid, not a normal device-management tool. Avoid write scans and interactive writes on the physical tuner until the protocol is understood. |
| **driver/90-ub320i.rules** | udev rules for the cold and warm USB IDs and DVB device nodes. The root Makefile's \`install-rules\` target installs this file. |
| **rules/99-ub320i.rules** | Alternate udev rule file covering the same device IDs and DVB nodes. It is retained from the userspace-tooling layout; normally install only one of the two rule files. |
| **Makefile** | Convenience targets for udev setup and the older Python tools. It is not the kernel-module build entry point; use \`build_dvb.sh\` for the kernel module. The \`setup\` target prints suggested setup commands, while \`scan\`, \`explore\`, and \`capture\` invoke the experimental userspace code. |
| **driver/Windows/** | Intended location for the vendor Windows reference package. The ZIP path currently present in the Git tree is only a 2-byte CRLF file, not a usable archive. The Windows findings below come from the separate vendor package supplied for analysis during development; the checked-in placeholder does not reproduce that analysis input. |

## How the pieces are intended to fit together

The intended kernel-driver path is:

1. The tuner is connected in bootloader mode and enumerates as **1738:5211**.
2. The Linux DVB-USB v2 driver requests **dvb-usb-asv5211.fw** from the firmware loader and sends the image using the four segmented control transfers.
3. The device is expected to disconnect/re-enumerate with the operational identity **1b80:b320**.
4. The kernel driver should attach to the operational device, register one DVB adapter and an ISDB-T frontend, and expose the normal Linux DVB device nodes under **/dev/dvb/**.
5. DVB applications would then use the Linux DVB API for tuning and transport-stream reception.

Only the USB identity and bootloader transfer layout have Windows static-analysis support. Firmware transfer, operational probe, frontend registration, tuning, lock detection, and TS delivery have not yet been validated on the physical tuner.

The Python path is separate: it talks directly to the warm USB device through PyUSB, rather than using the kernel DVB frontend. Do not try to use the Python tool and the kernel driver against the same interface at the same time. The Python code attempts to detach an active kernel driver before claiming the interface and to restore it when it exits, but that does not make its assumed protocol correct.

## Linux kernel driver design

The kernel implementation is in **driver/asv5211.c** and uses the Linux DVB-USB v2 framework. It is an external module named **asv5211**; it does not replace or build the kernel's DVB subsystem.

The current source is organised around these responsibilities:

- **Device identification:** distinguishes the cold bootloader ID from the warm firmware-loaded ID.
- **Firmware download:** validates the firmware image size, sends the four segments, detects short transfers, and requests the DVB-USB framework's reconnect path after the final transfer.
- **DVB frontend allocation:** allocates and populates one frontend with the ISDB-T delivery system. The frontend release callback frees the allocation.
- **Power and initialisation:** runs a provisional register-write initialisation sequence when the framework powers the device.
- **Tuning:** accepts the Japanese channel-frequency range, applies the optional frequency offset, then writes the provisional mode, bandwidth and frequency values.
- **Frontend status/statistics:** reads provisional status, BER, signal-strength and SNR registers. The current lock interpretation and statistics widths remain unconfirmed.
- **Streaming:** configures a provisional bulk input endpoint and 188-byte transport-stream framing through the DVB-USB framework.

The source-level fixes already made include the DVB-USB v2 frontend lifecycle, the Linux 5.4 frequency-step field, the adapter-number parameter, checks for short USB transfers, and correct handling of the DVB-USB framework's power state. These are source/API corrections only; no target-kernel build or hardware test has yet been completed.

### Kernel module parameters

| Parameter | Meaning | Default |
|---|---|---|
| **freq_offset** | Signed frequency correction in kHz, applied after validating the requested Japanese UHF frequency. | 0 |
| **adapter_nr** | Requested DVB adapter number; passed to the DVB-USB framework. | -1 (framework default) |

For example, after the protocol has been validated, a small hardware-specific correction could be supplied with a module option such as \`freq_offset=50\` ( +50 kHz ). This parameter does not compensate for an incorrect register protocol or an incorrect channel-frequency plan.

### Provisional operational protocol in the Linux code

The Linux C driver and Python prototype currently share these assumptions:

| Item | Current prototype value | Evidence status |
|---|---|---|
| Register write | Vendor OUT request \`0x90\` | Assumed by the prototype; not corroborated by the observed Windows control path |
| Register read | Vendor IN request \`0x91\` | Assumed by the prototype; not corroborated by the observed Windows control path |
| Tuner frequency register | \`0x0010\` | Provisional register map |
| Tuner bandwidth register | \`0x0014\` | Provisional register map |
| Tuner gain/AGC register | \`0x0018\` | Provisional register map |
| Demodulator control/status | \`0x0020\` / \`0x0024\` | Provisional register map |
| SNR / signal / BER | \`0x0028\` / \`0x002C\` / \`0x0030\` | Provisional register map |
| Output / PID filter | \`0x0040\` / \`0x0044\` | Provisional register map |
| Lock indication | Bit 0 of the assumed status register | Not confirmed |
| TS input endpoint | Bulk IN \`0x81\` | Defined in the source, not confirmed by a live capture |
| Status endpoint constant | \`0x82\` | Defined in the source, not confirmed by a live capture |
| TS packet framing | 188 bytes | Assumed, not validated with a received stream |

These values explain what the current implementation attempts to do; they must not be treated as an established ASV5211 register specification. In particular, the Windows operational-driver analysis below shows a different vendor-control request path. Do not use this table as a basis for further register writes.

## Firmware transfer and bootloader behaviour

The firmware image in **firmware/ub320i.fw** is expected to be 0x4000 (16,384) bytes. Static disassembly of the Windows loader **AS11Loader.sys** confirms four vendor control-transfer segments:

| Segment | Request | Offset / wValue | Length | wIndex |
|---:|---:|---:|---:|---:|
| 1 | \`0xAB\` | \`0x0000\` | \`0x0C00\` | \`0x55DC\` |
| 2 | \`0xAB\` | \`0x2000\` | \`0x0400\` | \`0x55DC\` |
| 3 | \`0xAB\` | \`0x2800\` | \`0x1000\` | \`0x55DC\` |
| 4 | \`0xAC\` | \`0x3800\` | \`0x0800\` | \`0x55DC\` |

The segment lengths add up to 0x4000 bytes. This table reflects parameters identified in the Windows loader's static code, not an observed live USB transaction. It does not prove that the firmware file currently in this repository is identical to the firmware payload used by the vendor loader.

The kernel driver uses the Linux firmware-loader name **dvb-usb-asv5211.fw**. The standalone script takes a firmware path as an argument:

~~~bash
sudo python3 load_firmware.py firmware/ub320i.fw
~~~

To print the four planned requests without transmitting them:

~~~bash
python3 load_firmware.py firmware/ub320i.fw --dry-run
~~~

A successful return to the warm USB ID only demonstrates that the device re-enumerated. It does not prove the operational control protocol, tuning, lock status or stream path.

## Windows driver reference and reverse-engineering notes

The Windows driver package supplied for analysis was the KWorld UB320-i package **Driver_UB320i_V1.09.10.26.091026.zip**. Its INF/configuration material identifies the cold and warm USB IDs and reports:

- **DriverVer:** 10/26/2009, 1.09.10.26
- **AS11Loader.sys:** Windows bootloader/firmware-loader component
- **KWORLD_UB320i.sys:** operational Windows BDA driver
- INF and **TVDrv.ini** configuration entries associate the device with USB IDs **1738:5211** and **1b80:b320**.

### What static analysis established

**AS11Loader.sys — firmware loader**

Static disassembly of the x64 loader binary shows the four firmware vendor-device transfers listed in the previous section: three transfers using request **0xAB**, followed by a final transfer using **0xAC**, with the corresponding offsets, lengths and **wIndex 0x55DC**. This is the basis for the firmware-segment table implemented in the Linux driver and Python loader.

The supplied Windows ZIP did not contain a standalone firmware image that could be compared byte-for-byte with **firmware/ub320i.fw**. The transfer layout is therefore better supported than the exact contents/provenance of the repository firmware image.

**KWORLD_UB320i.sys — operational control path**

Static analysis of one operational USB control path found a vendor-device URB path with these properties:

| Field | Observed value |
|---|---|
| URB function | \`0x17\` — URB_FUNCTION_VENDOR_DEVICE |
| Direction | Device-to-host (IN) |
| Vendor request | \`0x14\` |
| wValue | \`(opcode << 8) | 0x00EE\` |
| wIndex | \`0x0000\` |
| Response length | 2 bytes |
| Response handling | First byte is checked as a status value (observed expected value: \`1\`); second byte is copied as the result |

The disassembly contained example command/opcode values including **01, 05, 06, 08, 09, 15, 4D, A1, A5, AC, AD, AE, AF, B9, BD, C0, C4 and C5**. The meaning and sequencing of these values have not been established.

This is an observed path in the operational Windows binary, not a complete protocol reconstruction. It does not prove that every operation uses this path, and it is not sufficient to infer the meaning of the opcodes or translate the Windows driver into Linux register operations.

### Why a live Windows USB capture is still required

The Linux prototype assumes register read/write requests **0x91/0x90**. The observed Windows operational path instead uses vendor request **0x14**, with an opcode embedded in wValue and a two-byte response. That mismatch is a strong reason not to trust the current Linux register map or initialisation sequence.

Static disassembly does not show the complete control flow and payloads for initialisation, channel tuning, status polling and stream start/stop. A USBPcap capture of the original Windows driver operating the device is needed to correlate those actions with actual USB transfers.

## Alternative PyUSB userspace implementation

The Python utilities predate the kernel module and provide an alternative way to experiment with the device without installing a kernel module. They currently encode the same provisional operational assumptions, so they are useful as code/history and as test scaffolding, not as a known-working driver.

### Firmware loader

The **load_firmware.py** script:

- Requires PyUSB for actual transfers.
- Validates that the image is exactly 16,384 bytes.
- Builds the four-segment transfer plan.
- Checks short writes and reports failures on non-final segments.
- Treats a USB error on the final segment as potentially consistent with device reset, then checks whether **1b80:b320** appears.
- Provides **--wait** to set the re-enumeration timeout and **--dry-run** to inspect the plan without sending USB requests.

### Userspace tuner prototype

The **ub320i_driver.py** script currently provides these command-line modes:

| Option | Intended purpose |
|---|---|
| **--channel N** | Convert a Japanese UHF channel number (13–52) to the corresponding centre frequency |
| **--frequency HZ** | Request a frequency in Hz |
| **--status** | Read the prototype's status, SNR, signal and BER values |
| **--init-only** | Run the provisional initialisation sequence and exit |
| **--scan** | Iterate through a channel range and test the provisional lock bit |
| **--scan-min-channel / --scan-max-channel** | Set the channel scan limits |
| **--duration SECONDS** | Limit capture duration |
| **--output FILE** | Write the received data or scan results to a file |

The Python tuner uses PyUSB control requests **0x90** and **0x91**, the provisional register addresses listed above, and a bulk read from endpoint **0x81**. It attempts to detach an active kernel driver before claiming USB interface 0 and to release the interface/re-attach the kernel driver during cleanup.

**Do not run the scan or capture modes as a hardware test yet.** Their tuning, lock and TS operations depend on the unverified operational protocol and endpoint assumptions. The fact that these options exist in the script does not mean that they have been demonstrated to work.

### USB protocol explorer

The **ub320i_explore.py** script exposes low-level vendor USB operations. Its read-oriented functions can inspect request responses and candidate register ranges; its write functions can transmit arbitrary vendor requests. It also offers an interactive shell.

The explorer can issue writes to unknown vendor requests and may reset the tuner, alter configuration or trigger undocumented behaviour. Until the Windows control protocol has been mapped, do not run its write scan, arbitrary write commands or interactive write commands against the physical device. Prefer a passive Windows USBPcap capture for protocol discovery.

## Build and install the Linux kernel module

The intended hardware target is a **Banana Pi BPI-M4 Berry** running Armbian. A previously used target kernel was **5.4.125-legacy-sunxi64**, but always use the exact kernel version reported by the device being tested. Do not assume that this version is still installed.

### 1. Prepare the target

Run these commands on the Linux device that will host the tuner:

~~~bash
sudo apt-get update
sudo apt-get install build-essential bc kmod usbutils
git clone https://github.com/masterlog80/ub320i-driver.git
cd ub320i-driver
~~~

### 2. Build and install against the running kernel

First try the configured build directory for the running kernel:

~~~bash
set -o pipefail
KDIR="/lib/modules/$(uname -r)/build"
./build_dvb.sh --kdir "$KDIR" --install 2>&1 | tee build.log
~~~

The driver includes the internal kernel header:

**drivers/media/usb/dvb-usb-v2/dvb_usb.h**

This header is not always installed with the public kernel headers. If the build reports that it is missing from KDIR, provide the matching full kernel source tree:

~~~bash
./build_dvb.sh \
    --kdir "$KDIR" \
    --kernel-src /path/to/matching/kernel/source \
    --install 2>&1 | tee build.log
~~~

The configured build tree and full source tree must match the kernel running on the target. The target kernel must already provide the DVB-USB v2 framework and its exported symbols. The script builds this driver as an external module; it does not build or replace the kernel media subsystem.

With **--install**, the script installs the module under the kernel's **updates** module directory, copies **firmware/ub320i.fw** to **/lib/firmware/dvb-usb-asv5211.fw**, and runs **depmod** for the kernel release detected from KDIR.

Keep **build.log**. If compilation fails, stop and retain the complete output rather than attempting device tuning.

### Optional: install udev permissions

The udev files set access permissions for the cold USB ID, warm USB ID and DVB device nodes. If non-root USB access is required for the PyUSB utilities, install one rule file only. The root Makefile uses **driver/90-ub320i.rules**:

~~~bash
sudo make install-rules
~~~

Alternatively, copy that file manually:

~~~bash
sudo install -m 0644 driver/90-ub320i.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
~~~

Add the intended user to the **video** group if that is how device access is managed on the target, then log out and back in. udev permissions do not correct protocol or driver issues.

## First Linux test: collect evidence before attempting reception

The first hardware test should answer only three questions:

1. Does the module compile against the exact target kernel?
2. Does the tuner move from the cold USB ID to the warm USB ID after firmware loading?
3. Does Linux register a DVB frontend?

Do not start with channel scanning or blind register experiments.

### 1. Start a live kernel log

With the tuner unplugged, create a test folder and start the live kernel log in **Terminal A**:

~~~bash
mkdir -p "$HOME/ub320i-test"
sudo dmesg -wT | tee "$HOME/ub320i-test/dmesg-live.txt"
~~~

In **Terminal B**, load the module:

~~~bash
sudo modprobe asv5211
~~~

If that command succeeds, plug in the UB320-i. Leave the log running for about 20 seconds, then press **Ctrl+C** in Terminal A. If modprobe fails, preserve the error and live log and do not continue to tuning.

The kernel driver should request **dvb-usb-asv5211.fw** when it sees the cold device (**1738:5211**). The firmware loader code then requests USB re-enumeration; the expected operational ID is **1b80:b320**.

### 2. Collect system, USB and DVB information

Run the following commands after plugging in the tuner:

~~~bash
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
~~~

If **dvb-fe-tool** is not installed, install **v4l-utils** and run that command again. At this stage it is only a frontend enumeration/capability check; it does not prove that tuning or reception works.

### 3. Interpret the initial result

| Observation | What it tells us |
|---|---|
| Build creates **driver/asv5211.ko** | The source compiled for this particular kernel build |
| Device appears as **1738:5211** and then **1b80:b320** | Firmware transfer progressed far enough for USB re-enumeration |
| **/dev/dvb/adapter0/frontend0** appears | The Linux DVB frontend registered |
| USB errors, repeated disconnects, or no warm ID | Firmware/probe path needs investigation |
| Warm ID appears but no DVB frontend | Operational probe or frontend registration needs investigation |

A successful build, warm USB ID or frontend node does **not** prove that the current register protocol, tuning, lock detection or transport stream works. Do not run channel scans, sustained stream captures or **ub320i_explore.py** write experiments as part of this first test.

## Windows USBPcap capture: next protocol investigation

The next essential evidence is a USB capture from the original Windows driver while the tuner is operating normally.

1. On Windows, install/use Wireshark with USBPcap available.
2. Start USBPcap capture on the USB controller used by the tuner **before** plugging it in.
3. Plug in the UB320-i and let the official KWorld driver load the firmware.
4. Open the KWorld TV application, tune to a channel known to receive at your location, and view it for 20–30 seconds.
5. Stop viewing and stop the capture.
6. Save the capture as a **.pcapng** file.

The capture should include the cold-device firmware upload, operational initialisation, channel tuning, stream start, data transfers and stream stop. For each relevant transfer, the useful fields are request type, request, value, index, payload, length, endpoint and timing. This will allow the Linux implementation to be compared with actual device traffic instead of inferred register operations.

## What to provide for the next debugging round

Please keep and provide:

1. **build.log** — complete build output, including errors if compilation fails.
2. **ub320i-test.tar.gz** — the Linux kernel, USB, module and DVB enumeration evidence bundle.
3. **Windows USBPcap .pcapng** — the complete capture from firmware load through tuning and stream stop, when available.
4. **Test conditions** — target board/kernel version, channel/frequency, antenna/signal conditions, and whether the KWorld Windows application successfully received the channel.

The next work can then proceed in evidence-based order: firmware/probe, operational control requests, device initialisation, channel tuning and lock detection, then transport-stream reception.

## Verification status and known limitations

| Area | Current evidence | Verified on physical hardware? |
|---|---|---|
| Cold/warm USB IDs | Windows INF/configuration analysis | No Linux test yet |
| Firmware request IDs, offsets, lengths and wIndex | Static disassembly of **AS11Loader.sys** | No live USB capture |
| Firmware image identity | Repository image is 16 KiB; supplied Windows package lacked a standalone payload for comparison | No |
| Linux module build | External-module build flow is implemented | No target-kernel build yet |
| DVB-USB frontend lifecycle | Source-level review and Linux 5.4 API corrections | No |
| Linux operational requests 0x90/0x91 | Existing prototype assumption only | No |
| Register addresses and widths | Existing prototype assumption only | No |
| Windows operational request 0x14 | One path identified by static disassembly of **KWORLD_UB320i.sys** | No live capture |
| Initialisation and tuning sequence | Prototype sequence only | No |
| Lock/status bit and signal statistics | Prototype interpretation only | No |
| TS endpoint and 188-byte framing | Prototype configuration only | No |
| DVB node creation | Requires build and target load test | No |
| MPEG-TS reception | No validated transport-stream capture | No |

A frequency plan or source-level build fix is not evidence of a working tuner. Before considering the driver functional, the project still needs a successful build on the target, a Linux probe/frontend test, a Windows USBPcap trace, and a validated TS capture with packet alignment and valid transport-stream tables.

## Target hardware

The original target is the **Banana Pi BPI-M4 Berry** running Armbian. A prior environment used kernel **5.4.125-legacy-sunxi64**. Other boards, architectures and kernel releases need their own matching configured kernel build tree and compatibility checks.

## Licensing and source notes

- **Kernel module:** source file uses SPDX identifier **GPL-2.0-or-later**.
- **Python userspace utilities:** intended to be covered by the repository's MIT license.
- **Firmware image:** © KWorld; included for personal use only. The repository's MIT license does not grant rights to redistribute third-party firmware.
- **Windows reference binaries:** proprietary vendor driver components. Their presence or analysis does not relicense them or grant redistribution rights.

The Windows package analysed during development is identified above for provenance. The current 2-byte file under **driver/Windows/** is not a copy of that package and cannot be used to reproduce the static analysis. Retain and distribute the original vendor package only where its licensing terms permit.

## Credits

This project combines Linux DVB-USB integration work, Python USB experiments, and reverse engineering of the KWorld Windows driver package.
