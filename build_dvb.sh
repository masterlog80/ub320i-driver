#!/bin/bash
set -ex

BUILD_DIR="/lib/modules/5.4.125-legacy-sunxi64/build"
SRC_DIR="$HOME/dvb-driver-build"

# Step 1: Copy DVB source files into kernel build tree
echo "=== Copying DVB sources ==="
sudo cp -rf $SRC_DIR/drivers/media/dvb-core/* $BUILD_DIR/drivers/media/dvb-core/
sudo cp -rf $SRC_DIR/drivers/media/dvb-frontends/* $BUILD_DIR/drivers/media/dvb-frontends/
sudo mkdir -p $BUILD_DIR/drivers/media/usb/dvb-usb-v2
sudo cp -rf $SRC_DIR/drivers/media/usb/dvb-usb-v2/* $BUILD_DIR/drivers/media/usb/dvb-usb-v2/
sudo mkdir -p $BUILD_DIR/drivers/media/usb/dvb-usb
sudo cp -rf $SRC_DIR/drivers/media/usb/dvb-usb/* $BUILD_DIR/drivers/media/usb/dvb-usb/
sudo cp -rf $SRC_DIR/drivers/media/mc/* $BUILD_DIR/drivers/media/mc/
sudo cp -rf $SRC_DIR/drivers/media/i2c/* $BUILD_DIR/drivers/media/i2c/
sudo cp -rf $SRC_DIR/drivers/media/common/* $BUILD_DIR/drivers/media/common/
sudo cp -rf $SRC_DIR/drivers/media/rc/* $BUILD_DIR/drivers/media/rc/
sudo cp -rf $SRC_DIR/drivers/media/tuners/* $BUILD_DIR/drivers/media/tuners/
sudo mkdir -p $BUILD_DIR/include/media
sudo cp -rf $SRC_DIR/include/media/* $BUILD_DIR/include/media/ 2>/dev/null || true
sudo mkdir -p $BUILD_DIR/include/uapi/linux/dvb
sudo cp -rf $SRC_DIR/include/uapi/linux/dvb/*.h $BUILD_DIR/include/uapi/linux/dvb/ 2>/dev/null || true

# Step 2: Enable DVB in .config
echo "=== Enabling DVB config ==="
CONFIG_FILE="$BUILD_DIR/.config"
if ! grep -q "^CONFIG_DVB_CORE" $CONFIG_FILE; then
cat >> $CONFIG_FILE << 'EOF'
CONFIG_DVB_CORE=m
CONFIG_DVB_USB=m
CONFIG_DVB_USB_V2=m
CONFIG_DVB_USB_AF9035=m
CONFIG_MEDIA_CONTROLLER=y
CONFIG_DVB_NET=y
CONFIG_RC_CORE=y
CONFIG_RC_MAP=y
CONFIG_DVB_AF9033=m
CONFIG_DVB_AF9035=m
EOF
fi

# Step 3: Run make oldconfig
echo "=== Running make oldconfig ==="
cd $BUILD_DIR
yes "" | sudo make oldconfig 2>&1 | tail -5

# Step 4: Build DVB modules
echo "=== Building DVB modules ==="
sudo make -j$(nproc) modules 2>&1 | tail -50

echo "=== Build Complete ==="
