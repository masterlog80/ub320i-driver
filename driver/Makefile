# SPDX-License-Identifier: GPL-2.0-or-later
#
# Out-of-tree build for the ASV5211 DVB-USB v2 driver.
#
# KDIR       Configured kernel build directory (generated headers + Module.symvers).
# KERNEL_SRC Matching kernel source tree containing drivers/media/usb/
#            dvb-usb-v2/dvb_usb.h. It can be the same path as KDIR.
#
# Example:
#   make KDIR=/lib/modules/$(uname -r)/build KERNEL_SRC=/usr/src/linux
#   sudo make install KDIR=/lib/modules/$(uname -r)/build KERNEL_SRC=/usr/src/linux

KDIR ?= /lib/modules/$(shell uname -r)/build
KERNEL_SRC ?= $(KDIR)

obj-m := asv5211.o
FW_NAME := dvb-usb-asv5211.fw
DVB_USB_INTERNAL := $(KERNEL_SRC)/drivers/media/usb/dvb-usb-v2
KERNELRELEASE := $(shell $(MAKE) -s -C "$(KDIR)" kernelrelease 2>/dev/null)

.PHONY: all modules clean modules_install install firmware-copy

all: modules

modules:
	$(MAKE) -C "$(KDIR)" M="$(CURDIR)" EXTRA_CFLAGS="-I$(DVB_USB_INTERNAL)" modules

clean:
	$(MAKE) -C "$(KDIR)" M="$(CURDIR)" clean

modules_install: modules
	$(MAKE) -C "$(KDIR)" M="$(CURDIR)" INSTALL_MOD_DIR=updates modules_install

firmware-copy:
	install -D -m 0644 "$(CURDIR)/../firmware/ub320i.fw" "/lib/firmware/$(FW_NAME)"

install: modules_install firmware-copy
	depmod -a "$(KERNELRELEASE)"
