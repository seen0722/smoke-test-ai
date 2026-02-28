import struct
import time
import usb.core
import usb.util
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)

ACCESSORY_REGISTER_HID = 54
ACCESSORY_UNREGISTER_HID = 55
ACCESSORY_SET_HID_REPORT_DESC = 56
ACCESSORY_SEND_HID_EVENT = 57

HID_KEYBOARD_DESCRIPTOR = bytes([
    0x05, 0x01, 0x09, 0x06, 0xA1, 0x01, 0x05, 0x07,
    0x19, 0xE0, 0x29, 0xE7, 0x15, 0x00, 0x25, 0x01,
    0x75, 0x01, 0x95, 0x08, 0x81, 0x02, 0x95, 0x01,
    0x75, 0x08, 0x81, 0x01, 0x95, 0x06, 0x75, 0x08,
    0x15, 0x00, 0x25, 0x65, 0x05, 0x07, 0x19, 0x00,
    0x29, 0x65, 0x81, 0x00, 0xC0,
])

HID_MOUSE_DESCRIPTOR = bytes([
    0x05, 0x01, 0x09, 0x02, 0xA1, 0x01, 0x09, 0x01,
    0xA1, 0x00, 0x05, 0x09, 0x19, 0x01, 0x29, 0x03,
    0x15, 0x00, 0x25, 0x01, 0x95, 0x03, 0x75, 0x01,
    0x81, 0x02, 0x95, 0x01, 0x75, 0x05, 0x81, 0x01,
    0x05, 0x01, 0x09, 0x30, 0x09, 0x31,
    0x16, 0x00, 0x00, 0x26, 0x10, 0x27,
    0x36, 0x00, 0x00, 0x46, 0x10, 0x27,
    0x75, 0x10, 0x95, 0x02, 0x81, 0x02,
    0xC0, 0xC0,
])

class AoaHidDriver:
    def __init__(self, vendor_id: int, product_id: int):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self._device = None

    def find_device(self) -> None:
        self._device = usb.core.find(idVendor=self.vendor_id, idProduct=self.product_id)
        if self._device is None:
            raise RuntimeError(f"Android device not found (VID=0x{self.vendor_id:04X}, PID=0x{self.product_id:04X})")
        logger.info(f"Found device: VID=0x{self.vendor_id:04X} PID=0x{self.product_id:04X}")

    def register_hid(self, hid_id: int, descriptor: bytes) -> None:
        if self._device is None:
            raise RuntimeError("Device not found. Call find_device() first.")
        self._device.ctrl_transfer(0x40, ACCESSORY_REGISTER_HID, hid_id, len(descriptor))
        self._device.ctrl_transfer(0x40, ACCESSORY_SET_HID_REPORT_DESC, hid_id, 0, descriptor)
        logger.info(f"Registered HID device {hid_id}, descriptor size={len(descriptor)}")

    def unregister_hid(self, hid_id: int) -> None:
        if self._device is None:
            return
        self._device.ctrl_transfer(0x40, ACCESSORY_UNREGISTER_HID, hid_id, 0)
        logger.info(f"Unregistered HID device {hid_id}")

    def send_hid_event(self, hid_id: int, data: bytes) -> None:
        if self._device is None:
            raise RuntimeError("Device not found.")
        self._device.ctrl_transfer(0x40, ACCESSORY_SEND_HID_EVENT, hid_id, 0, data)

    def register_mouse(self, hid_id: int) -> None:
        self.register_hid(hid_id, HID_MOUSE_DESCRIPTOR)

    def send_key(self, hid_id: int, key_code: int, modifiers: int = 0) -> None:
        report = struct.pack("BBBBBBBB", modifiers, 0, key_code, 0, 0, 0, 0, 0)
        self.send_hid_event(hid_id, report)
        time.sleep(0.05)
        report = struct.pack("BBBBBBBB", 0, 0, 0, 0, 0, 0, 0, 0)
        self.send_hid_event(hid_id, report)

    def tap(self, hid_id: int, x: int, y: int, screen_w: int = 1080, screen_h: int = 2400) -> None:
        abs_x = int((x / screen_w) * 10000)
        abs_y = int((y / screen_h) * 10000)
        report = struct.pack("<BHH", 0x01, abs_x, abs_y)
        self.send_hid_event(hid_id, report)
        time.sleep(0.1)
        report = struct.pack("<BHH", 0x00, abs_x, abs_y)
        self.send_hid_event(hid_id, report)

    def swipe(self, hid_id: int, x1: int, y1: int, x2: int, y2: int, screen_w: int = 1080, screen_h: int = 2400, steps: int = 10, duration: float = 0.3) -> None:
        delay = duration / steps
        for i in range(steps + 1):
            t = i / steps
            cx = int(x1 + (x2 - x1) * t)
            cy = int(y1 + (y2 - y1) * t)
            abs_x = int((cx / screen_w) * 10000)
            abs_y = int((cy / screen_h) * 10000)
            report = struct.pack("<BHH", 0x01, abs_x, abs_y)
            self.send_hid_event(hid_id, report)
            time.sleep(delay)
        report = struct.pack("<BHH", 0x00, abs_x, abs_y)
        self.send_hid_event(hid_id, report)

    def close(self) -> None:
        self._device = None
