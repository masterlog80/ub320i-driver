# SPDX-License-Identifier: GPL-2.0-or-later
#
# Makefile for out-of-tree build of asv5211 DVB-USB driver
# Target kernel: 5.4.x (e.g. 5.4.125-legacy-sunxi64 on BPI-M4 Berry)
#
# Usage:
#   make KDIR=/lib/modules/$(uname -r)/build
#   sudo make install KDIR=/lib/modules/$(uname -r)/build
#

KDIR ?= /lib/modules/$(shell uname -r)/build
obj-m := asv5211.o
FW_NAME := dvb-usb-asv5211.fw

.PHONY: all clean install modules firmware-copy

all: modules

modules:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

install: modules firmware-copy
	install -d /lib/modules/$(shell uname -r)/kernel/drivers/media/usb/dvb-usb-v2
	install -m 0644 asv5211.ko /lib/modules/$(shell uname -r)/kernel/drivers/media/usb/dvb-usb-v2/
	depmod -a

# Copy firmware to the right place for the driver's request_firmware()
firmware-copy:
	@if [ -f $(CURDIR)/../firmware/ub320i.fw ]; then \
		install -d /lib/firmware; \
		install -m 0644 $(CURDIR)/../firmware/ub320i.fw /lib/firmware/$(FW_NAME); \
		echo "Firmware copied to /lib/firmware/$(FW_NAME)"; \
	else \
		echo "Firmware not found at ../firmware/ub320i.fw"; \
		echo "Place ub320i.fw in ../firmware/ or copy it manually to /lib/firmware/$(FW_NAME)"; \
	fi
