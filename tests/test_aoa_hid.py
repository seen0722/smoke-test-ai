import pytest
from unittest.mock import patch, MagicMock
from smoke_test_ai.drivers.aoa_hid import AoaHidDriver, HID_KEYBOARD_DESCRIPTOR

@pytest.fixture
def mock_usb_device():
    device = MagicMock()
    device.idVendor = 0x18D1
    device.idProduct = 0x4EE2
    return device

class TestAoaHidDriver:
    def test_hid_keyboard_descriptor_exists(self):
        assert len(HID_KEYBOARD_DESCRIPTOR) > 0

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_find_device(self, mock_find, mock_usb_device):
        mock_find.return_value = mock_usb_device
        driver = AoaHidDriver(vendor_id=0x18D1, product_id=0x4EE2)
        driver.find_device()
        assert driver._device is not None

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_find_device_not_found(self, mock_find):
        mock_find.return_value = None
        driver = AoaHidDriver(vendor_id=0x18D1, product_id=0x4EE2)
        with pytest.raises(RuntimeError, match="Android device not found"):
            driver.find_device()

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_register_hid(self, mock_find, mock_usb_device):
        mock_find.return_value = mock_usb_device
        driver = AoaHidDriver(vendor_id=0x18D1, product_id=0x4EE2)
        driver.find_device()
        driver.register_hid(hid_id=1, descriptor=HID_KEYBOARD_DESCRIPTOR)
        assert mock_usb_device.ctrl_transfer.call_count == 2

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_send_key_event(self, mock_find, mock_usb_device):
        mock_find.return_value = mock_usb_device
        driver = AoaHidDriver(vendor_id=0x18D1, product_id=0x4EE2)
        driver.find_device()
        driver.register_hid(hid_id=1, descriptor=HID_KEYBOARD_DESCRIPTOR)
        driver.send_key(hid_id=1, key_code=0x28)
        assert mock_usb_device.ctrl_transfer.call_count == 2 + 2

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_unregister_hid(self, mock_find, mock_usb_device):
        mock_find.return_value = mock_usb_device
        driver = AoaHidDriver(vendor_id=0x18D1, product_id=0x4EE2)
        driver.find_device()
        driver.register_hid(hid_id=1, descriptor=HID_KEYBOARD_DESCRIPTOR)
        driver.unregister_hid(hid_id=1)
        assert mock_usb_device.ctrl_transfer.call_count == 3

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_tap(self, mock_find, mock_usb_device):
        mock_find.return_value = mock_usb_device
        driver = AoaHidDriver(vendor_id=0x18D1, product_id=0x4EE2)
        driver.find_device()
        driver.register_mouse(hid_id=2)
        driver.tap(hid_id=2, x=540, y=960, screen_w=1080, screen_h=2400)
        assert mock_usb_device.ctrl_transfer.call_count >= 4
