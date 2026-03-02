import struct
import time
import usb.core
import usb.util
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)

# AOA2 protocol request codes
ACCESSORY_GET_PROTOCOL = 51
ACCESSORY_SEND_STRING = 52
ACCESSORY_START = 53
ACCESSORY_REGISTER_HID = 54
ACCESSORY_UNREGISTER_HID = 55
ACCESSORY_SET_HID_REPORT_DESC = 56
ACCESSORY_SEND_HID_EVENT = 57

# Google Accessory mode VID / PIDs
GOOGLE_VID = 0x18D1
ACCESSORY_PID = 0x2D00
ACCESSORY_ADB_PID = 0x2D01

HID_KEYBOARD_DESCRIPTOR = bytes([
    0x05, 0x01, 0x09, 0x06, 0xA1, 0x01, 0x05, 0x07,
    0x19, 0xE0, 0x29, 0xE7, 0x15, 0x00, 0x25, 0x01,
    0x75, 0x01, 0x95, 0x08, 0x81, 0x02, 0x95, 0x01,
    0x75, 0x08, 0x81, 0x01, 0x95, 0x06, 0x75, 0x08,
    0x15, 0x00, 0x25, 0x65, 0x05, 0x07, 0x19, 0x00,
    0x29, 0x65, 0x81, 0x00, 0xC0,
])

# Android-compliant single-finger touchscreen digitizer with Contact ID
# and Contact Count — required for Android to process consecutive events.
# Report (7 bytes): tip_switch:1+pad:7 | contact_id:8 | X:16 | Y:16 | count:8
HID_TOUCH_DESCRIPTOR = bytes([
    0x05, 0x0D,        # Usage Page (Digitizer)
    0x09, 0x04,        # Usage (Touch Screen)
    0xA1, 0x01,        # Collection (Application)
    0x09, 0x22,        #   Usage (Finger)
    0xA1, 0x02,        #   Collection (Logical)
    # Tip Switch — 1 bit
    0x09, 0x42,        #     Usage (Tip Switch)
    0x15, 0x00,        #     Logical Minimum (0)
    0x25, 0x01,        #     Logical Maximum (1)
    0x75, 0x01,        #     Report Size (1)
    0x95, 0x01,        #     Report Count (1)
    0x81, 0x02,        #     Input (Data, Variable, Absolute)
    # Padding — 7 bits
    0x75, 0x07,
    0x95, 0x01,
    0x81, 0x01,        #     Input (Constant)
    # Contact ID — 1 byte
    0x09, 0x51,        #     Usage (Contact Identifier)
    0x15, 0x00,
    0x25, 0x01,
    0x75, 0x08,
    0x95, 0x01,
    0x81, 0x02,        #     Input (Data, Variable, Absolute)
    # X — 2 bytes
    0x05, 0x01,        #     Usage Page (Generic Desktop)
    0x09, 0x30,        #     Usage (X)
    0x15, 0x00,
    0x26, 0x10, 0x27,  #     Logical Maximum (10000)
    0x75, 0x10,        #     Report Size (16)
    0x95, 0x01,
    0x81, 0x02,        #     Input (Data, Variable, Absolute)
    # Y — 2 bytes
    0x09, 0x31,        #     Usage (Y)
    0x15, 0x00,
    0x26, 0x10, 0x27,  #     Logical Maximum (10000)
    0x75, 0x10,
    0x95, 0x01,
    0x81, 0x02,        #     Input (Data, Variable, Absolute)
    0xC0,              #   End Collection (Logical)
    # Contact Count — 1 byte
    0x05, 0x0D,        #   Usage Page (Digitizer)
    0x09, 0x54,        #   Usage (Contact Count)
    0x15, 0x00,
    0x25, 0x01,
    0x75, 0x08,
    0x95, 0x01,
    0x81, 0x02,        #   Input (Data, Variable, Absolute)
    0xC0,              # End Collection (Application)
])

# Keep old name as alias for backwards compatibility
HID_MOUSE_DESCRIPTOR = HID_TOUCH_DESCRIPTOR


class AoaHidDriver:
    """AOA2 HID driver with Accessory mode switching and rotation support.

    Args:
        vendor_id: USB Vendor ID of the Android device.
        product_id: USB Product ID of the Android device.
        rotation: Screen rotation in degrees (0, 90, 180, 270).
            0   = portrait (default)
            90  = landscape (device rotated 90° CW)
            180 = portrait upside-down
            270 = landscape (device rotated 90° CCW)
    """

    def __init__(self, vendor_id: int, product_id: int, rotation: int = 0):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.rotation = rotation
        self._device = None
        self._in_accessory_mode = False

    def _apply_rotation(self, hx: int, hy: int) -> tuple[int, int]:
        """Convert screen-logical (0-10000) coords to HID coords with rotation."""
        if self.rotation == 0:
            return hx, hy
        if self.rotation == 90:
            return 10000 - hy, hx
        if self.rotation == 180:
            return 10000 - hx, 10000 - hy
        if self.rotation == 270:
            return hy, 10000 - hx
        return hx, hy

    def find_device(self) -> None:
        """Find the USB device. Checks Accessory mode first, then normal mode."""
        # Scan all USB devices — keyword-based find can miss freshly
        # re-enumerated devices on some platforms (macOS).
        for dev in usb.core.find(find_all=True):
            if dev.idVendor == GOOGLE_VID and dev.idProduct in (
                ACCESSORY_PID, ACCESSORY_ADB_PID
            ):
                self._device = dev
                self._in_accessory_mode = True
                logger.info(f"Found device already in Accessory mode "
                            f"(VID=0x{GOOGLE_VID:04X} "
                            f"PID=0x{dev.idProduct:04X})")
                return

        # Find in normal mode
        for dev in usb.core.find(find_all=True):
            if dev.idVendor == self.vendor_id and dev.idProduct == self.product_id:
                self._device = dev
                logger.info(f"Found device: VID=0x{self.vendor_id:04X} "
                            f"PID=0x{self.product_id:04X}")
                return

        raise RuntimeError(
            f"Android device not found "
            f"(VID=0x{self.vendor_id:04X}, PID=0x{self.product_id:04X})")

    def start_accessory(self, re_enumerate_timeout: float = 5.0) -> None:
        """Switch device to AOA2 Accessory mode for HID support.

        Protocol: GET_PROTOCOL → SEND_STRING → START → wait re-enumerate.
        No-op if device is already in Accessory mode.
        """
        if self._in_accessory_mode:
            logger.info("Device already in Accessory mode, skipping switch")
            return
        if self._device is None:
            raise RuntimeError("Device not found. Call find_device() first.")

        # Step 1: Get AOA protocol version (must be >= 2 for HID)
        buf = self._device.ctrl_transfer(0xC0, ACCESSORY_GET_PROTOCOL, 0, 0, 2)
        protocol = buf[0] | (buf[1] << 8)
        logger.info(f"AOA protocol version: {protocol}")
        if protocol < 2:
            raise RuntimeError(
                f"AOA protocol v{protocol} does not support HID (need >= 2)")

        # Step 2: Send identification strings
        strings = [
            (0, "SmokeTestAI"),                 # manufacturer
            (1, "SmokeTestAI"),                 # model
            (2, "Smoke Test AI Controller"),    # description
            (3, "1.0"),                         # version
            (4, ""),                            # URI
            (5, "0"),                           # serial
        ]
        for idx, s in strings:
            data = s.encode("utf-8") + b"\x00"
            self._device.ctrl_transfer(0x40, ACCESSORY_SEND_STRING, 0, idx, data)
        logger.info("Sent accessory identification strings")

        # Step 3: Start Accessory mode (device will disconnect and re-enumerate)
        self._device.ctrl_transfer(0x40, ACCESSORY_START, 0, 0)
        logger.info("Sent START command, waiting for device re-enumeration...")
        self._device = None

        # Step 4: Wait for device to re-enumerate with Google Accessory VID
        # Use find(find_all=True) + manual filter because keyword-based find
        # can miss freshly re-enumerated devices on some platforms (macOS).
        deadline = time.time() + re_enumerate_timeout
        while time.time() < deadline:
            time.sleep(0.5)
            for dev in usb.core.find(find_all=True):
                if dev.idVendor == GOOGLE_VID and dev.idProduct in (
                    ACCESSORY_PID, ACCESSORY_ADB_PID
                ):
                    self._device = dev
                    self._in_accessory_mode = True
                    logger.info(f"Device re-enumerated as Accessory "
                                f"(VID=0x{GOOGLE_VID:04X} "
                                f"PID=0x{dev.idProduct:04X})")
                    # Allow Android to fully initialise the accessory
                    # USB configuration before registering HID devices.
                    time.sleep(2)
                    return

        raise RuntimeError(
            "Device did not re-enumerate in Accessory mode within "
            f"{re_enumerate_timeout}s")

    def register_hid(self, hid_id: int, descriptor: bytes) -> None:
        if self._device is None:
            raise RuntimeError("Device not found. Call find_device() first.")
        self._device.ctrl_transfer(0x40, ACCESSORY_REGISTER_HID, hid_id, len(descriptor))
        self._device.ctrl_transfer(0x40, ACCESSORY_SET_HID_REPORT_DESC, hid_id, 0, descriptor)
        # Give Android time to create the input device for this HID.
        time.sleep(0.5)
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

    def register_touch(self, hid_id: int) -> None:
        self.register_hid(hid_id, HID_TOUCH_DESCRIPTOR)

    def register_mouse(self, hid_id: int) -> None:
        """Alias for register_touch (backwards compatibility)."""
        self.register_touch(hid_id)

    def _touch_report(self, tip: int, x: int, y: int) -> bytes:
        """Build a 7-byte touch report with rotation applied."""
        hx, hy = self._apply_rotation(x, y)
        count = 1 if tip else 0
        return struct.pack("<BBHHB", tip, 0, hx, hy, count)

    def send_key(self, hid_id: int, key_code: int, modifiers: int = 0) -> None:
        report = struct.pack("BBBBBBBB", modifiers, 0, key_code, 0, 0, 0, 0, 0)
        self.send_hid_event(hid_id, report)
        time.sleep(0.05)
        report = struct.pack("BBBBBBBB", 0, 0, 0, 0, 0, 0, 0, 0)
        self.send_hid_event(hid_id, report)

    def tap(self, hid_id: int, x: int, y: int, screen_w: int = 1080, screen_h: int = 2400) -> None:
        abs_x = int((x / screen_w) * 10000)
        abs_y = int((y / screen_h) * 10000)
        self.send_hid_event(hid_id, self._touch_report(1, abs_x, abs_y))
        time.sleep(0.1)
        self.send_hid_event(hid_id, self._touch_report(0, abs_x, abs_y))

    def swipe(self, hid_id: int, x1: int, y1: int, x2: int, y2: int, screen_w: int = 1080, screen_h: int = 2400, steps: int = 10, duration: float = 0.3) -> None:
        delay = duration / steps
        for i in range(steps + 1):
            t = i / steps
            cx = int(x1 + (x2 - x1) * t)
            cy = int(y1 + (y2 - y1) * t)
            abs_x = int((cx / screen_w) * 10000)
            abs_y = int((cy / screen_h) * 10000)
            self.send_hid_event(hid_id, self._touch_report(1, abs_x, abs_y))
            time.sleep(delay)
        abs_x = int((x2 / screen_w) * 10000)
        abs_y = int((y2 / screen_h) * 10000)
        self.send_hid_event(hid_id, self._touch_report(0, abs_x, abs_y))

    def wake_screen(self, touch_hid_id: int) -> None:
        """Wake screen using touch tap.

        Sends a small touch-and-release at center to trigger user activity.
        If caller needs stronger wake, use wake_screen_power() instead.
        """
        logger.info("Waking screen via HID touch")
        self.send_hid_event(touch_hid_id, self._touch_report(1, 5000, 5000))
        time.sleep(0.05)
        self.send_hid_event(touch_hid_id, self._touch_report(0, 5000, 5000))

    def wake_screen_power(self, keyboard_hid_id: int) -> None:
        """Send HID Power key (0x66) to toggle screen. Use with caution —
        this is a toggle: it turns screen OFF if already ON."""
        logger.info("Sending HID Power key to toggle screen")
        self.send_key(keyboard_hid_id, 0x66)

    def close(self) -> None:
        self._device = None
