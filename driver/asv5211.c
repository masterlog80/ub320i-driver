// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * ASV5211 - AsicEn ASV5211 ISDB-T USB DVB driver
 *
 * Supports:
 *   KWorld ISDB-T UB320-i (ONE SEG tuner, Japan ISDB-T mobile)
 *
 * Based on reverse engineering of:
 *   - Windows BDA driver KWORLD_UB320i.sys / AS11Loader.sys
 *   - Python userspace driver (ub320i_driver.py, load_firmware.py)
 *
 * The ASV5211 is a combined USB tuner/demodulator on a single chip.
 * Device arrives in bootloader mode (1738:5211), loads firmware, then
 * re-enumerates as operational device (1b80:b320).
 *
 * Protocol summary:
 *   Firmware load: segmented control transfers to bootloader (1738:5211)
 *   Register write: ctrl_transfer(0x40, 0x90, reg_addr, 0, data)
 *   Register read:  ctrl_transfer(0xC0, 0x91, reg_addr, 0, len)
 *   TS data:        bulk IN on endpoint 0x81 (188-byte MPEG-TS packets)
 *   Status:         bulk IN on endpoint 0x82
 *
 * Copyright (C) 2024 OpenClaw Community
 */

#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/module.h>
#include <linux/init.h>
#include <linux/delay.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/usb.h>
#include <linux/usb/input.h>

#include <media/rc-core.h>
#include <media/dvb_frontend.h>
#include <media/dvb_demux.h>
#include <media/dvb_net.h>
#include <media/dmxdev.h>
#include <media/dvb_usb.h>

/* ------------------------------------------------------------------ */
/* Module parameters                                                   */
/* ------------------------------------------------------------------ */

static int freq_offset;
module_param(freq_offset, int, 0644);
MODULE_PARM_DESC(freq_offset, "Override the frequency offset in kHz");

static int adapt_nr = -1;
module_param_named(adapter_nr, adapt_nr, int, 0444);
MODULE_PARM_DESC(adapter_nr, "Override the adapter number (default = -1)");

/* ------------------------------------------------------------------ */
/* USB identifiers                                                     */
/* ------------------------------------------------------------------ */

#define USB_VID_ASICEN_COLD   0x1738	/* Bootloader vendor */
#define USB_PID_ASICEN_COLD   0x5211	/* Bootloader product */
#define USB_VID_ASICEN_WARM   0x1b80	/* Operational vendor */
#define USB_PID_ASICEN_WARM   0xb320	/* Operational product */

/* ------------------------------------------------------------------ */
/* Firmware loading constants (from load_firmware.py)                  */
/* ------------------------------------------------------------------ */

#define ASV5211_FW_SIZE		0x4000
#define ASV5211_FW_W_INDEX	0x55DC

struct asv5211_fw_seg {
	u16 offset;
	u16 length;
	u8  request;
};

static const struct asv5211_fw_seg asv5211_fw_segments[] = {
	{ 0x0000, 0x0C00, 0xAB },
	{ 0x2000, 0x0400, 0xAB },
	{ 0x2800, 0x1000, 0xAB },
	{ 0x3800, 0x0800, 0xAC },
};
#define ASV5211_FW_SEGMENTS	ARRAY_SIZE(asv5211_fw_segments)

/* ------------------------------------------------------------------ */
/* Register addresses (from ub320i_driver.py reverse engineering)      */
/* ------------------------------------------------------------------ */

#define ASV5211_REG_TUNER_FREQ		0x0010
#define ASV5211_REG_TUNER_BW		0x0014
#define ASV5211_REG_TUNER_GAIN		0x0018
#define ASV5211_REG_DEMOD_CONTROL	0x0020
#define ASV5211_REG_DEMOD_STATUS	0x0024
#define ASV5211_REG_DEMOD_SNR		0x0028
#define ASV5211_REG_DEMOD_SIGNAL	0x002C
#define ASV5211_REG_DEMOD_BER		0x0030
#define ASV5211_REG_OUTPUT_CONTROL	0x0040
#define ASV5211_REG_TS_PID_FILTER	0x0044

/* Control transfer request types */
#define ASV5211_REQ_WRITE_REG		0x90
#define ASV5211_REQ_READ_REG		0x91

/* Demod control register values */
#define ASV5211_DEMOD_RESET		0x00000001
#define ASV5211_DEMOD_SOFT_RESET	0x00000000
#define ASV5211_DEMOD_ISDBT_MODE	0x00000002
#define ASV5211_DEMOD_START		0x00000003

/* Bandwidth modes */
#define ASV5211_BW_6MHZ			0
#define ASV5211_BW_7MHZ			1
#define ASV5211_BW_8MHZ			2

/* Status bits */
#define ASV5211_STATUS_LOCKED		0x01

/* ------------------------------------------------------------------ */
/* USB endpoints                                                       */
/* ------------------------------------------------------------------ */

#define ASV5211_EP_TS_IN		0x81	/* MPEG-TS bulk IN */
#define ASV5211_EP_STATUS_IN		0x82	/* Status/control bulk IN */

/* TS packet size */
#define TS_PACKET_SIZE		188

/* ------------------------------------------------------------------ */
/* Private data structure                                              */
/* ------------------------------------------------------------------ */

struct asv5211_state {
	struct mutex lock;
};

/* ------------------------------------------------------------------ */
/* Helper: USB control transfers (all register R/W)                    */
/* ------------------------------------------------------------------ */

static int asv5211_write_regs(struct dvb_usb_device *d,
			      u16 reg, u8 *data, u16 len)
{
	int rc;

	mutex_lock(&d->usb_mutex);
	rc = usb_control_msg(d->udev,
			     usb_sndctrlpipe(d->udev, 0),
			     ASV5211_REQ_WRITE_REG,
			     USB_DIR_OUT | USB_TYPE_VENDOR,
			     reg, 0x0000,
			     data, len, 2000);
	mutex_unlock(&d->usb_mutex);

	if (rc < 0)
		dev_err(&d->intf->dev,
			"write_regs failed: reg=0x%04x len=%d err=%d\n",
			reg, len, rc);

	return rc < 0 ? rc : 0;
}

static int asv5211_read_regs(struct dvb_usb_device *d,
			     u16 reg, u8 *data, u16 len)
{
	int rc;

	mutex_lock(&d->usb_mutex);
	rc = usb_control_msg(d->udev,
			     usb_rcvctrlpipe(d->udev, 0),
			     ASV5211_REQ_READ_REG,
			     USB_DIR_IN | USB_TYPE_VENDOR,
			     reg, 0x0000,
			     data, len, 2000);
	mutex_unlock(&d->usb_mutex);

	if (rc < 0)
		dev_err(&d->intf->dev,
			"read_regs failed: reg=0x%04x len=%d err=%d\n",
			reg, len, rc);

	return rc;
}

static int asv5211_write_reg32(struct dvb_usb_device *d, u16 reg, u32 val)
{
	__le32 data = cpu_to_le32(val);
	return asv5211_write_regs(d, reg, (u8 *)&data, 4);
}

static int asv5211_write_reg16(struct dvb_usb_device *d, u16 reg, u16 val)
{
	__le16 data = cpu_to_le16(val);
	return asv5211_write_regs(d, reg, (u8 *)&data, 2);
}

static int asv5211_read_reg32(struct dvb_usb_device *d, u16 reg, u32 *val)
{
	__le32 data;
	int rc = asv5211_read_regs(d, reg, (u8 *)&data, 4);
	if (rc == 4)
		*val = le32_to_cpu(data);
	return rc;
}

static int asv5211_read_reg16(struct dvb_usb_device *d, u16 reg, u16 *val)
{
	__le16 data;
	int rc = asv5211_read_regs(d, reg, (u8 *)&data, 2);
	if (rc == 2)
		*val = le16_to_cpu(data);
	return rc;
}

/* ------------------------------------------------------------------ */
/* Firmware download                                                   */
/* ------------------------------------------------------------------ */

static int asv5211_download_firmware(struct dvb_usb_device *d,
				     const struct firmware *firmware)
{
	int i, rc;

	if (!firmware) {
		dev_err(&d->intf->dev, "firmware data is NULL\n");
		return -ENOENT;
	}

	if (firmware->size != ASV5211_FW_SIZE) {
		dev_err(&d->intf->dev,
			"firmware size mismatch: expected %u, got %zu\n",
			ASV5211_FW_SIZE, firmware->size);
		return -EINVAL;
	}

	dev_info(&d->intf->dev, "downloading firmware (%zu bytes)\n",
		 firmware->size);

	for (i = 0; i < ASV5211_FW_SEGMENTS; i++) {
		const struct asv5211_fw_seg *seg = &asv5211_fw_segments[i];

		dev_info(&d->intf->dev,
			 "  segment %d/%d: offset=0x%04x len=%u req=0x%02x\n",
			 i + 1, ASV5211_FW_SEGMENTS,
			 seg->offset, seg->length, seg->request);

		rc = usb_control_msg(d->udev,
				     usb_sndctrlpipe(d->udev, 0),
				     seg->request,
				     USB_DIR_OUT | USB_TYPE_VENDOR,
				     seg->offset, ASV5211_FW_W_INDEX,
				     (u8 *)firmware->data + seg->offset,
				     seg->length, 5000);

		if (rc < 0) {
			dev_err(&d->intf->dev,
				"firmware segment %d failed: %d\n", i, rc);
			return rc;
		}
		if (rc != seg->length) {
			dev_warn(&d->intf->dev,
				 "firmware segment %d: short write (%d/%u)\n",
				 i, rc, seg->length);
			/* May be normal on last segment (device resets) */
		}
	}

	dev_info(&d->intf->dev, "firmware download complete\n");
	return 0;
}

/* ------------------------------------------------------------------ */
/* Device state identification                                         */
/* ------------------------------------------------------------------ */

static int asv5211_identify_state(struct dvb_usb_device *d,
				  const char **firmware)
{
	/* Only binds to warm device (1b80:b320). Firmware already loaded.
	 * Return WARM so the framework skips re-downloading. */
	*firmware = NULL;
	return WARM;
}

/* ------------------------------------------------------------------ */
/* Device initialization (called on power-up / frontend init)          */
/* ------------------------------------------------------------------ */

static int asv5211_init_device(struct dvb_usb_device *d)
{
	struct asv5211_state *st = d_to_priv(d);
	int rc = 0;

	mutex_lock(&st->lock);

	/* Hardware reset */
	rc = asv5211_write_reg32(d, ASV5211_REG_DEMOD_CONTROL,
				 ASV5211_DEMOD_RESET);
	if (rc) goto out;
	msleep(100);

	/* Soft reset */
	rc = asv5211_write_reg32(d, ASV5211_REG_DEMOD_CONTROL,
				 ASV5211_DEMOD_SOFT_RESET);
	if (rc) goto out;
	msleep(100);

	/* Set ISDB-T mode */
	rc = asv5211_write_reg32(d, ASV5211_REG_DEMOD_CONTROL,
				 ASV5211_DEMOD_ISDBT_MODE);
	if (rc) goto out;
	msleep(50);

	/* Set bandwidth to 6 MHz (Japan ISDB-T mobile standard) */
	rc = asv5211_write_reg32(d, ASV5211_REG_TUNER_BW,
				 ASV5211_BW_6MHZ);
	if (rc) goto out;
	msleep(50);

	/* Enable AGC */
	rc = asv5211_write_reg32(d, ASV5211_REG_TUNER_GAIN, 1);
	if (rc) goto out;
	msleep(50);

	/* Set output to transport stream mode */
	rc = asv5211_write_reg32(d, ASV5211_REG_OUTPUT_CONTROL, 1);
	if (rc) goto out;
	msleep(50);

	/* PID filter: pass-through (all PIDs) */
	rc = asv5211_write_reg32(d, ASV5211_REG_TS_PID_FILTER,
				 0xFFFFFFFF);
	if (rc) goto out;
	msleep(50);

out:
	mutex_unlock(&st->lock);
	return rc;
}

/* ------------------------------------------------------------------ */
/* Power control                                                       */
/* ------------------------------------------------------------------ */

static int asv5211_power_ctrl(struct dvb_usb_device *d, int on)
{
	if (on) {
		d->powered = 1;
		return asv5211_init_device(d);
	}
	d->powered = 0;
	return 0;
}

/* ------------------------------------------------------------------ */
/* Streaming control                                                   */
/* ------------------------------------------------------------------ */

static int asv5211_streaming_ctrl(struct dvb_frontend *fe, int on)
{
	struct dvb_usb_adapter *adap = fe_to_adap(fe);
	struct dvb_usb_device *d = adap_to_d(adap);
	struct asv5211_state *st = d_to_priv(d);
	int rc = 0;

	mutex_lock(&st->lock);

	if (on) {
		/* Start demodulation -> TS stream flows on bulk endpoint */
		rc = asv5211_write_reg32(d, ASV5211_REG_DEMOD_CONTROL,
					 ASV5211_DEMOD_START);
		if (rc) {
			dev_err(&d->intf->dev,
				"failed to start streaming: %d\n", rc);
		}
		msleep(100);
	} else {
		rc = asv5211_write_reg32(d, ASV5211_REG_DEMOD_CONTROL,
					 ASV5211_DEMOD_SOFT_RESET);
		if (rc)
			dev_warn(&d->intf->dev,
				 "failed to stop streaming: %d\n", rc);
		msleep(50);
	}

	mutex_unlock(&st->lock);
	return rc;
}

/* ------------------------------------------------------------------ */
/* Stream configuration                                                */
/* ------------------------------------------------------------------ */

static int asv5211_get_stream_config(struct dvb_frontend *fe,
				     u8 *input_ts_type,
				     struct usb_data_stream_properties *stream)
{
	/* ASV5211 outputs standard 188-byte MPEG-TS packets */
	*input_ts_type = DVB_USB_FE_TS_TYPE_188;

	stream->type = USB_BULK;
	stream->count = 10;
	stream->endpoint = ASV5211_EP_TS_IN;
	stream->u.bulk.buffersize = 2 * TS_PACKET_SIZE;

	return 0;
}

/* ------------------------------------------------------------------ */
/* Frontend operations (ASV5211 integrates tuner + demod on-chip)     */
/* ------------------------------------------------------------------ */

static int asv5211_fe_init(struct dvb_frontend *fe)
{
	struct dvb_usb_device *d = fe_to_d(fe);
	return asv5211_init_device(d);
}

static int asv5211_fe_sleep(struct dvb_frontend *fe)
{
	struct dvb_usb_device *d = fe_to_d(fe);
	struct asv5211_state *st = d_to_priv(d);

	mutex_lock(&st->lock);
	asv5211_write_reg32(d, ASV5211_REG_DEMOD_CONTROL,
			    ASV5211_DEMOD_SOFT_RESET);
	mutex_unlock(&st->lock);

	return 0;
}

static int asv5211_fe_set_params(struct dvb_frontend *fe)
{
	struct dvb_usb_device *d = fe_to_d(fe);
	struct asv5211_state *st = d_to_priv(d);
	u32 frequency_hz;
	int rc = 0;

	/* fe->frequency is in kHz in the DVB API v5 */
	frequency_hz = fe->frequency * 1000;
	if (freq_offset)
		frequency_hz += freq_offset * 1000;

	dev_dbg(&d->intf->dev,
		"set_params: freq=%u kHz (%u Hz) delivery=%d\n",
		fe->frequency, frequency_hz, fe->delivery_system);

	mutex_lock(&st->lock);

	/* Reset to ISDB-T mode */
	rc = asv5211_write_reg32(d, ASV5211_REG_DEMOD_CONTROL,
				 ASV5211_DEMOD_ISDBT_MODE);
	if (rc) goto out;
	msleep(50);

	/* Bandwidth: Japan ISDB-T mobile is 6 MHz */
	rc = asv5211_write_reg32(d, ASV5211_REG_TUNER_BW,
				 ASV5211_BW_6MHZ);
	if (rc) goto out;
	msleep(50);

	/* Set frequency */
	rc = asv5211_write_reg32(d, ASV5211_REG_TUNER_FREQ, frequency_hz);
	if (rc) goto out;
	msleep(500);

	/* Start demodulation */
	rc = asv5211_write_reg32(d, ASV5211_REG_DEMOD_CONTROL,
				 ASV5211_DEMOD_START);
	if (rc) goto out;
	msleep(1000);

out:
	mutex_unlock(&st->lock);
	return rc;
}

static int asv5211_fe_read_status(struct dvb_frontend *fe,
				  enum fe_status *status)
{
	struct dvb_usb_device *d = fe_to_d(fe);
	struct asv5211_state *st = d_to_priv(d);
	u32 raw_status = 0;
	int rc;

	*status = 0;

	mutex_lock(&st->lock);
	rc = asv5211_read_reg32(d, ASV5211_REG_DEMOD_STATUS, &raw_status);
	if (rc != 4) {
		dev_dbg(&d->intf->dev, "status read failed: %d\n", rc);
		*status = FE_HAS_SIGNAL;
		goto out;
	}

	dev_dbg(&d->intf->dev,
		"read_status: raw=0x%08x\n", raw_status);

	/* Always report signal present (tuner is always on) */
	*status = FE_HAS_SIGNAL;

	if (raw_status & ASV5211_STATUS_LOCKED) {
		*status |= FE_HAS_CARRIER | FE_HAS_LOCK;
	}

out:
	mutex_unlock(&st->lock);
	return 0;
}

static int asv5211_fe_read_ber(struct dvb_frontend *fe, u32 *ber)
{
	struct dvb_usb_device *d = fe_to_d(fe);
	struct asv5211_state *st = d_to_priv(d);
	u32 val = 0;

	mutex_lock(&st->lock);
	asv5211_read_reg32(d, ASV5211_REG_DEMOD_BER, &val);
	mutex_unlock(&st->lock);

	*ber = val;
	return 0;
}

static int asv5211_fe_read_signal_strength(struct dvb_frontend *fe,
					   u16 *strength)
{
	struct dvb_usb_device *d = fe_to_d(fe);
	struct asv5211_state *st = d_to_priv(d);
	u32 val = 0;

	mutex_lock(&st->lock);
	asv5211_read_reg32(d, ASV5211_REG_DEMOD_SIGNAL, &val);
	mutex_unlock(&st->lock);

	*strength = (val > 65535) ? 65535 : (u16)val;
	return 0;
}

static int asv5211_fe_read_snr(struct dvb_frontend *fe, u16 *snr)
{
	struct dvb_usb_device *d = fe_to_d(fe);
	struct asv5211_state *st = d_to_priv(d);
	u32 val = 0;

	mutex_lock(&st->lock);
	asv5211_read_reg32(d, ASV5211_REG_DEMOD_SNR, &val);
	mutex_unlock(&st->lock);

	*snr = (val > 65535) ? 65535 : (u16)val;
	return 0;
}

/* ------------------------------------------------------------------ */
/* Frontend attach / detach                                            */
/* ------------------------------------------------------------------ */

static int asv5211_frontend_attach(struct dvb_usb_adapter *adap)
{
	struct dvb_frontend *fe;

	/* Register the frontend with the DVB core */
	fe = dvb_register_frontend(&adap->dvb_adap, &asv5211_ops);
	if (!fe) {
		dev_err(&adap_to_d(adap)->intf->dev,
			"frontend registration failed\n");
		return -ENODEV;
	}

	dev_info(&adap_to_d(adap)->intf->dev,
		 "ASV5211 ISDB-T frontend registered\n");

	return 0;
}

static void asv5211_frontend_detach(struct dvb_usb_adapter *adap)
{
	if (adap->fe[0]) {
		dvb_unregister_frontend(adap->fe[0]);
		adap->fe[0] = NULL;
	}
}

/* ------------------------------------------------------------------ */
/* Frontend ops table (static, for dvb_register_frontend)             */
/* ------------------------------------------------------------------ */

static struct dvb_frontend_ops asv5211_ops = {
	.delsys = { SYS_ISDBT },

	.info = {
		.name			= "AsicEn ASV5211 ISDB-T",
		.frequency_min_hz	= 175000000,
		.frequency_max_hz	= 770000000,
		.frequency_stepsize_hz	= 156250,
		.frequency_tolerance_hz	= 0,
		.symbol_rate_min	= 0,
		.symbol_rate_max	= 0,
		.symbol_rate_tolerance	= 0,
		.caps			= FE_CAP_QAM_AUTO | FE_HAS_TUNER,
	},

	.init			= asv5211_fe_init,
	.sleep		= asv5211_fe_sleep,
	.set_params	= asv5211_fe_set_params,
	.read_status	= asv5211_fe_read_status,
	.read_ber	= asv5211_fe_read_ber,
	.read_signal_strength = asv5211_fe_read_signal_strength,
	.read_snr	= asv5211_fe_read_snr,
};

/* ------------------------------------------------------------------ */
/* Adapter properties                                                  */
/* ------------------------------------------------------------------ */

static struct dvb_usb_adapter_properties asv5211_adapter_props = {
	.caps			= 0,
	.pid_filter_count	= 0,

	.stream = {
		.type		= USB_BULK,
		.count		= 10,
		.endpoint	= ASV5211_EP_TS_IN,
		.u		= {
			.bulk = {
				.buffersize = 2 * TS_PACKET_SIZE,
			},
		},
	},

	.frontend_attach	= asv5211_frontend_attach,
	.frontend_detach	= asv5211_frontend_detach,
};

/* ------------------------------------------------------------------ */
/* Probe / Disconnect                                                  */
/* ------------------------------------------------------------------ */

static int asv5211_probe(struct dvb_usb_device *d)
{
	struct asv5211_state *st = d_to_priv(d);

	mutex_init(&st->lock);

	dev_info(&d->intf->dev,
		 "KWorld UB320-i ASV5211 ISDB-T (ONE SEG) detected\n");

	return 0;
}

static void asv5211_disconnect(struct dvb_usb_device *d)
{
	dev_info(&d->intf->dev, "device disconnected\n");
}

/* ------------------------------------------------------------------ */
/* Device properties                                                   */
/* ------------------------------------------------------------------ */

static const struct dvb_usb_device_properties asv5211_properties = {
	.driver_name		= KBUILD_MODNAME,
	.owner			= THIS_MODULE,

	.size_of_priv		= sizeof(struct asv5211_state),

	.probe			= asv5211_probe,
	.disconnect		= asv5211_disconnect,

	.identify_state		= asv5211_identify_state,
	.firmware		= "dvb-usb-asv5211.fw",
	.download_firmware	= asv5211_download_firmware,

	.num_adapters		= 1,
	.adapter			= { &asv5211_adapter_props },

	.power_ctrl		= asv5211_power_ctrl,
	.streaming_ctrl		= asv5211_streaming_ctrl,
	.get_stream_config	= asv5211_get_stream_config,
};

/* ------------------------------------------------------------------ */
/* USB device table                                                    */
/* ------------------------------------------------------------------ */

static const struct usb_device_id asv5211_table[] = {
	{ DVB_USB_DEVICE(USB_VID_ASICEN_WARM, USB_PID_ASICEN_WARM,
			 &asv5211_properties,
			 "KWorld UB320-i ISDB-T (ASV5211)",
			 NULL) },
	{ },
};
MODULE_DEVICE_TABLE(usb, asv5211_table);

/* ------------------------------------------------------------------ */
/* USB driver registration                                             */
/* ------------------------------------------------------------------ */

static struct usb_driver asv5211_driver = {
	.name			= "dvb-usb-asv5211",
	.id_table		= asv5211_table,
	.probe			= dvb_usbv2_probe,
	.disconnect		= dvb_usbv2_disconnect,
	.suspend		= dvb_usbv2_suspend,
	.resume			= dvb_usbv2_resume,
	.reset_resume		= dvb_usbv2_reset_resume,
	.disable_hub_initiated_lpm = 1,
};
module_usb_driver(asv5211_driver);

MODULE_AUTHOR("OpenClaw Community");
MODULE_DESCRIPTION("DVB-USB driver for AsicEn ASV5211 ISDB-T ONE SEG tuners");
MODULE_LICENSE("GPL");
