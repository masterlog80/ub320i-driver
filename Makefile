.PHONY: install setup scan clean

PREFIX ?= /usr/local
FW_FILE = ub320i.fw

# Install udev rules and set permissions
install-rules:
	sudo cp rules/99-ub320i.rules /etc/udev/rules.d/
	sudo udevadm control --reload-rules
	sudo udevadm trigger
	@echo "udev rules installed. Replug the USB device."

# One-time setup
setup:
	@echo "=== UB320-i Setup ==="
	@echo "1. Install Python dependencies:"
	@echo "   pip3 install pyusb"
	@echo "2. Install udev rules:"
	@echo "   make install-rules"
	@echo "3. Load firmware (if needed):"
	@echo "   sudo python3 load_firmware.py $(FW_FILE)"
	@echo "4. Test driver:"
	@echo "   sudo python3 ub320i_driver.py --status"

# Scan for channels
scan:
	sudo python3 ub320i_driver.py --scan --output scan_results.txt

# Explore protocol
explore:
	sudo python3 ub320i_explore.py --interactive

# Capture channel
capture:
	sudo python3 ub320i_driver.py --frequency $(FREQ) --output $(OUTPUT)

clean:
	rm -f *.ts scan_results.txt
