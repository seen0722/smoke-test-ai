import subprocess
import time
import usb.core
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)


class BlindRunner:
    """Execute a YAML-defined action sequence via AOA2 HID (blind, no vision)."""

    def __init__(self, hid, adb, aoa_config: dict, flow_config: dict):
        self.hid = hid
        self.adb = adb
        self.aoa_config = aoa_config
        self.flow_config = flow_config

        res = flow_config.get("screen_resolution", [1080, 2400])
        self.screen_w = res[0]
        self.screen_h = res[1]

        self.touch_id = aoa_config.get("touch_hid_id", 2)
        self.kbd_id = aoa_config.get("keyboard_hid_id", 1)
        self.consumer_id = aoa_config.get("consumer_hid_id", 3)

    def run(self) -> bool:
        """Execute all steps sequentially. Returns True if completed."""
        steps = self.flow_config.get("steps", [])
        total = len(steps)
        for i, step in enumerate(steps):
            desc = step.get("description", step["action"])
            logger.info(f"Step {i + 1}/{total}: {desc}")
            success = self._execute_step(step)
            if not success:
                return False
        logger.info("All steps completed")
        return True

    def _execute_step(self, step: dict) -> bool:
        action = step["action"]
        delay = step.get("delay", 1.0)

        handler = {
            "tap": self._do_tap,
            "swipe": self._do_swipe,
            "type": self._do_type,
            "key": self._do_key,
            "wake": self._do_wake,
            "home": self._do_home,
            "back": self._do_back,
            "sleep": self._do_sleep,
            "wait_for_adb": self._do_wait_for_adb,
        }.get(action)

        if handler is None:
            logger.warning(f"Unknown action '{action}', skipping")
            time.sleep(delay)
            return True

        try:
            result = handler(step)
        except usb.core.USBError as e:
            logger.warning(f"USB disconnected during '{action}': {e}")
            logger.info("Auto-reconnecting AOA...")
            if self._reconnect_aoa():
                result = True  # Step likely triggered USB re-enum, continue
            else:
                return False

        if action not in ("sleep", "wait_for_adb"):
            time.sleep(delay)

        return result

    def _do_tap(self, step: dict) -> bool:
        x, y = step["x"], step["y"]
        repeat = step.get("repeat", 1)
        delay = step.get("delay", 1.0)
        press_duration = step.get("press_duration", 0.05)
        for i in range(repeat):
            self.hid.tap(self.touch_id, x, y, self.screen_w, self.screen_h, press_duration=press_duration)
            if repeat > 1 and i < repeat - 1:
                time.sleep(delay)
        return True

    def _do_swipe(self, step: dict) -> bool:
        self.hid.swipe(
            self.touch_id,
            step["x1"], step["y1"], step["x2"], step["y2"],
            self.screen_w, self.screen_h,
            duration=step.get("duration", 0.3),
        )
        return True

    def _do_type(self, step: dict) -> bool:
        self.hid.type_text(self.kbd_id, step["text"])
        return True

    def _do_key(self, step: dict) -> bool:
        key = step["key"]
        if key == "enter":
            self.hid.press_enter(self.kbd_id)
        elif key == "tab":
            self.hid.send_key(self.kbd_id, 0x2B)
        else:
            logger.warning(f"Unknown key '{key}', skipping")
        return True

    def _do_wake(self, step: dict) -> bool:
        self.hid.wake_screen(self.touch_id)
        return True

    def _do_home(self, step: dict) -> bool:
        self.hid.press_home(self.consumer_id)
        return True

    def _do_back(self, step: dict) -> bool:
        self.hid.press_back(self.consumer_id)
        return True

    def _do_sleep(self, step: dict) -> bool:
        time.sleep(step.get("duration", 1.0))
        return True

    def _reconnect_aoa(self) -> bool:
        """Re-establish AOA connection after USB disconnection."""
        return self._wait_for_adb(timeout=30)

    def _do_wait_for_adb(self, step: dict) -> bool:
        timeout = step.get("timeout", 30)
        return self._wait_for_adb(timeout)

    def _wait_for_adb(self, timeout: int) -> bool:
        """Wait for USB re-enumeration, re-init AOA if needed."""
        from smoke_test_ai.drivers.aoa_hid import (
            AoaHidDriver, HID_KEYBOARD_DESCRIPTOR,
            GOOGLE_VID, ACCESSORY_PID, ACCESSORY_ADB_PID,
        )

        logger.info("Closing AOA, waiting for USB re-enumeration...")
        self.hid.close()
        time.sleep(3)

        cfg = self.aoa_config
        deadline = time.time() + timeout
        found_mode = None

        while time.time() < deadline:
            # Check USB devices via PyUSB
            try:
                for dev in usb.core.find(find_all=True):
                    if dev.idVendor == GOOGLE_VID and dev.idProduct == ACCESSORY_ADB_PID:
                        found_mode = "accessory_adb"
                        break
                    if dev.idVendor == GOOGLE_VID and dev.idProduct == ACCESSORY_PID:
                        found_mode = "accessory"
                        break
                    # Match by VID only — PID may change after USB debugging toggle
                    if dev.idVendor == cfg["vendor_id"]:
                        found_mode = "normal"
                        logger.info(
                            f"Device found: VID=0x{dev.idVendor:04X} "
                            f"PID=0x{dev.idProduct:04X}"
                        )
                        break
            except Exception as e:
                logger.debug(f"PyUSB scan error: {e}")

            # Fallback: check ADB if PyUSB didn't find it
            if not found_mode and self.adb is not None:
                if self.adb.is_connected(allow_unauthorized=True):
                    found_mode = "normal"
                    logger.info("Device detected via ADB (PyUSB missed it)")

            if found_mode:
                break
            time.sleep(1)

        if not found_mode:
            logger.error(f"Device not found after USB re-enumeration (timeout={timeout}s)")
            return False

        logger.info(f"Device found in {found_mode} mode")

        # Re-init AOA with retry (PyUSB/libusb may need time on macOS)
        reinit_deadline = time.time() + 30
        while True:
            # Force libusb to release cached device handles
            try:
                for d in usb.core.find(find_all=True):
                    usb.util.dispose_resources(d)
            except Exception:
                pass

            try:
                self.hid = AoaHidDriver(
                    vendor_id=cfg["vendor_id"],
                    product_id=cfg["product_id"],
                    rotation=cfg.get("rotation", 0),
                )
                self.hid.find_device()
                break
            except RuntimeError:
                if time.time() >= reinit_deadline:
                    # Last resort: check ioreg to confirm device is on bus
                    vid = f"{cfg['vendor_id']:04x}"
                    try:
                        out = subprocess.run(
                            ["ioreg", "-p", "IOUSB", "-l"],
                            capture_output=True, text=True, timeout=5,
                        ).stdout
                        if vid in out.lower():
                            logger.error(
                                f"Device visible in ioreg (VID={vid}) but "
                                "PyUSB/libusb cannot access it. "
                                "Try replugging USB cable."
                            )
                        else:
                            logger.error("Device not found on USB bus")
                    except Exception:
                        logger.error("Failed to re-init AOA: PyUSB cannot find device")
                    return False
                logger.info("PyUSB can't find device yet, retrying...")
                time.sleep(3)

        if found_mode == "accessory_adb":
            logger.info("Device in Accessory+ADB mode, re-registering HID...")
        else:
            logger.info("Re-initializing AOA...")
            self.hid.start_accessory()

        self.hid.register_hid(self.kbd_id, HID_KEYBOARD_DESCRIPTOR)
        self.hid.register_touch(self.touch_id)
        self.hid.register_consumer(self.consumer_id)

        logger.info("AOA ready, continuing playback")
        return True
