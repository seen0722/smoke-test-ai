import pytest
from unittest.mock import patch, MagicMock
from smoke_test_ai.drivers.aoa_hid import (
    AoaHidDriver, HID_KEYBOARD_DESCRIPTOR,
    GOOGLE_VID, ACCESSORY_PID, ACCESSORY_ADB_PID,
    ACCESSORY_GET_PROTOCOL, ACCESSORY_SEND_STRING, ACCESSORY_START,
    HID_KEY_MAP, HID_SHIFT_MAP,
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

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_type_text(self, mock_find, mock_accessory_device):
        """type_text sends key events for each character."""
        mock_find.return_value = [mock_accessory_device]

        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1)
        driver.find_device()
        driver.register_hid(hid_id=1, descriptor=HID_KEYBOARD_DESCRIPTOR)

        initial_calls = mock_accessory_device.ctrl_transfer.call_count
        driver.type_text(hid_id=1, text="ab")

        # Each character: send_key sends 2 ctrl_transfer calls (press + release)
        added_calls = mock_accessory_device.ctrl_transfer.call_count - initial_calls
        assert added_calls == 4  # 2 chars * 2 events each

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_type_text_with_shift(self, mock_find, mock_accessory_device):
        """type_text applies shift modifier for uppercase letters."""
        mock_find.return_value = [mock_accessory_device]

        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1)
        driver.find_device()
        driver.register_hid(hid_id=1, descriptor=HID_KEYBOARD_DESCRIPTOR)

        driver.type_text(hid_id=1, text="A")

        # Find the key-down call (last two ctrl_transfers: press + release)
        calls = mock_accessory_device.ctrl_transfer.call_args_list
        # The press event for 'A' should have modifier 0x02 (LEFT_SHIFT)
        press_data = calls[-2][0][4]  # 5th positional arg = data bytes
        assert press_data[0] == 0x02  # modifier byte = LEFT_SHIFT

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_press_back(self, mock_find, mock_accessory_device):
        """press_back sends Consumer Control AC Back (0x0224)."""
        mock_find.return_value = [mock_accessory_device]

        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1)
        driver.find_device()
        driver.register_consumer(hid_id=3)

        initial_calls = mock_accessory_device.ctrl_transfer.call_count
        driver.press_back(hid_id=3)

        # send_consumer_key = 2 ctrl_transfer calls (press + release)
        added = mock_accessory_device.ctrl_transfer.call_count - initial_calls
        assert added == 2

        # Verify AC Back usage (0x0224) in press event
        press_data = mock_accessory_device.ctrl_transfer.call_args_list[-2][0][4]
        assert press_data == b'\x24\x02'  # 0x0224 little-endian

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_press_enter(self, mock_find, mock_accessory_device):
        """press_enter sends HID Enter key code (0x28)."""
        mock_find.return_value = [mock_accessory_device]

        driver = AoaHidDriver(vendor_id=0x099E, product_id=0x02B1)
        driver.find_device()
        driver.register_hid(hid_id=1, descriptor=HID_KEYBOARD_DESCRIPTOR)

        driver.press_enter(hid_id=1)

        press_data = mock_accessory_device.ctrl_transfer.call_args_list[-2][0][4]
        assert press_data[2] == 0x28  # key code byte

    def test_char_to_hid_lowercase(self):
        """_char_to_hid maps lowercase letters correctly."""
        key, shift = AoaHidDriver._char_to_hid('a')
        assert key == 0x04
        assert shift is False

    def test_char_to_hid_uppercase(self):
        """_char_to_hid maps uppercase letters with shift=True."""
        key, shift = AoaHidDriver._char_to_hid('A')
        assert key == 0x04
        assert shift is True

    def test_char_to_hid_unmapped(self):
        """_char_to_hid returns (0, False) for unmapped characters."""
        key, shift = AoaHidDriver._char_to_hid('\x80')
        assert key == 0
        assert shift is False

    def test_hid_key_map_completeness(self):
        """HID_KEY_MAP covers all lowercase letters and digits."""
        for ch in 'abcdefghijklmnopqrstuvwxyz':
            assert ch in HID_KEY_MAP
        for ch in '0123456789':
            assert ch in HID_KEY_MAP

    def test_hid_shift_map_completeness(self):
        """HID_SHIFT_MAP covers all uppercase letters."""
        for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            assert ch in HID_SHIFT_MAP
