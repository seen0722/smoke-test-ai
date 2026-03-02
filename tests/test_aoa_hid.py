import pytest
from unittest.mock import patch, MagicMock
from smoke_test_ai.drivers.aoa_hid import (
    AoaHidDriver, HID_KEYBOARD_DESCRIPTOR,
    GOOGLE_VID, ACCESSORY_PID, ACCESSORY_ADB_PID,
    ACCESSORY_GET_PROTOCOL, ACCESSORY_SEND_STRING, ACCESSORY_START,
)


def _make_device(vid, pid):
    dev = MagicMock()
    dev.idVendor = vid
    dev.idProduct = pid
    return dev


@pytest.fixture
def mock_usb_device():
    return _make_device(0x099E, 0x02B1)


@pytest.fixture
def mock_accessory_device():
    return _make_device(GOOGLE_VID, ACCESSORY_PID)


class TestAoaHidDriver:
    def test_hid_keyboard_descriptor_exists(self):
        assert len(HID_KEYBOARD_DESCRIPTOR) > 0

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_find_device_normal_mode(self, mock_find, mock_usb_device):
        """Find device in normal (non-Accessory) mode."""
        mock_find.return_value = [mock_usb_device]

        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1)
        driver.find_device()
        assert driver._device is mock_usb_device
        assert driver._in_accessory_mode is False

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_find_device_already_accessory(self, mock_find, mock_accessory_device):
        """Find device already in Accessory mode."""
        mock_find.return_value = [mock_accessory_device]

        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1)
        driver.find_device()
        assert driver._device is mock_accessory_device
        assert driver._in_accessory_mode is True

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_find_device_not_found(self, mock_find):
        mock_find.return_value = []
        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1)
        with pytest.raises(RuntimeError, match="Android device not found"):
            driver.find_device()

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_start_accessory_full_flow(self, mock_find, mock_usb_device, mock_accessory_device):
        """Full AOA2 handshake: GET_PROTOCOL -> SEND_STRING -> START -> re-enumerate."""
        # find_device: only normal device visible
        mock_find.return_value = [mock_usb_device]

        # GET_PROTOCOL returns version 2
        mock_usb_device.ctrl_transfer.return_value = bytes([2, 0])

        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1)
        driver.find_device()

        # After START, re-enumerate finds Accessory device
        mock_find.return_value = [mock_accessory_device]

        driver.start_accessory(re_enumerate_timeout=2.0)

        assert driver._device is mock_accessory_device
        assert driver._in_accessory_mode is True

        # Verify ctrl_transfer calls: GET_PROTOCOL + 6 SEND_STRING + START = 8
        calls = mock_usb_device.ctrl_transfer.call_args_list
        assert calls[0][0][1] == ACCESSORY_GET_PROTOCOL
        for i in range(1, 7):
            assert calls[i][0][1] == ACCESSORY_SEND_STRING
        assert calls[7][0][1] == ACCESSORY_START

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_start_accessory_skips_if_already(self, mock_find, mock_accessory_device):
        """start_accessory is a no-op if already in Accessory mode."""
        mock_find.return_value = [mock_accessory_device]

        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1)
        driver.find_device()
        assert driver._in_accessory_mode is True

        driver.start_accessory()
        mock_accessory_device.ctrl_transfer.assert_not_called()

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_start_accessory_protocol_too_low(self, mock_find, mock_usb_device):
        """Raise error if AOA protocol version < 2."""
        mock_find.return_value = [mock_usb_device]
        mock_usb_device.ctrl_transfer.return_value = bytes([1, 0])

        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1)
        driver.find_device()
        with pytest.raises(RuntimeError, match="does not support HID"):
            driver.start_accessory()

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_start_accessory_re_enumerate_timeout(self, mock_find, mock_usb_device):
        """Raise error if device does not re-enumerate in time."""
        mock_find.return_value = [mock_usb_device]
        mock_usb_device.ctrl_transfer.return_value = bytes([2, 0])

        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1)
        driver.find_device()

        # After START, nothing found
        mock_find.return_value = []

        with pytest.raises(RuntimeError, match="did not re-enumerate"):
            driver.start_accessory(re_enumerate_timeout=1.0)

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_register_hid(self, mock_find, mock_accessory_device):
        """Register HID on Accessory-mode device."""
        mock_find.return_value = [mock_accessory_device]

        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1)
        driver.find_device()
        driver.register_hid(hid_id=1, descriptor=HID_KEYBOARD_DESCRIPTOR)
        assert mock_accessory_device.ctrl_transfer.call_count == 2

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_send_key_event(self, mock_find, mock_accessory_device):
        mock_find.return_value = [mock_accessory_device]

        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1)
        driver.find_device()
        driver.register_hid(hid_id=1, descriptor=HID_KEYBOARD_DESCRIPTOR)
        driver.send_key(hid_id=1, key_code=0x28)
        assert mock_accessory_device.ctrl_transfer.call_count == 4

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_unregister_hid(self, mock_find, mock_accessory_device):
        mock_find.return_value = [mock_accessory_device]

        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1)
        driver.find_device()
        driver.register_hid(hid_id=1, descriptor=HID_KEYBOARD_DESCRIPTOR)
        driver.unregister_hid(hid_id=1)
        assert mock_accessory_device.ctrl_transfer.call_count == 3

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_tap(self, mock_find, mock_accessory_device):
        mock_find.return_value = [mock_accessory_device]

        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1)
        driver.find_device()
        driver.register_mouse(hid_id=2)
        driver.tap(hid_id=2, x=540, y=960, screen_w=1080, screen_h=2400)
        assert mock_accessory_device.ctrl_transfer.call_count == 4

    def test_rotation_0(self):
        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1, rotation=0)
        assert driver._apply_rotation(1000, 2000) == (1000, 2000)

    def test_rotation_90(self):
        """Landscape: screen (x, y) -> HID (10000-y, x)."""
        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1, rotation=90)
        # center stays center
        assert driver._apply_rotation(5000, 5000) == (5000, 5000)
        # top-left -> rotated
        assert driver._apply_rotation(1000, 1000) == (9000, 1000)
        # bottom-right -> rotated
        assert driver._apply_rotation(9000, 9000) == (1000, 9000)

    def test_rotation_180(self):
        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1, rotation=180)
        assert driver._apply_rotation(1000, 2000) == (9000, 8000)

    def test_rotation_270(self):
        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1, rotation=270)
        assert driver._apply_rotation(1000, 2000) == (2000, 9000)

    def test_touch_report_includes_contact_fields(self):
        """Touch report is 7 bytes: tip+pad | contact_id | X | Y | count."""
        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1)
        report = driver._touch_report(1, 5000, 3000)
        assert len(report) == 7
        # tip=1, contact_id=0, X=5000, Y=3000, count=1
        assert report[0] == 0x01  # tip switch
        assert report[1] == 0x00  # contact id
        assert report[6] == 0x01  # contact count
