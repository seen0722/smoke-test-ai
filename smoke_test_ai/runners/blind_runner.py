import time
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

        result = handler(step)

        if action not in ("sleep", "wait_for_adb"):
            time.sleep(delay)

        return result

    def _do_tap(self, step: dict) -> bool:
        x, y = step["x"], step["y"]
        repeat = step.get("repeat", 1)
        delay = step.get("delay", 1.0)
        for i in range(repeat):
            self.hid.tap(self.touch_id, x, y, self.screen_w, self.screen_h)
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

    def _do_wait_for_adb(self, step: dict) -> bool:
        timeout = step.get("timeout", 30)
        return self._wait_for_adb(timeout)

    def _wait_for_adb(self, timeout: int) -> bool:
        """Release AOA -> poll ADB -> re-init AOA for RSA tap."""
        from smoke_test_ai.drivers.aoa_hid import (
            AoaHidDriver, HID_KEYBOARD_DESCRIPTOR,
        )

        logger.info("Releasing AOA for ADB connection...")
        self.hid.close()
        time.sleep(2)

        logger.info(f"Waiting for ADB (timeout={timeout}s)...")
        if not self.adb.wait_for_device(timeout=timeout):
            logger.error("ADB device not found within timeout")
            return False

        logger.info("ADB connected. Re-initializing AOA for RSA dialog...")
        cfg = self.aoa_config
        self.hid = AoaHidDriver(
            vendor_id=cfg["vendor_id"],
            product_id=cfg["product_id"],
            rotation=cfg.get("rotation", 0),
        )
        self.hid.find_device()
        self.hid.start_accessory()
        self.hid.register_hid(self.kbd_id, HID_KEYBOARD_DESCRIPTOR)
        self.hid.register_touch(self.touch_id)
        self.hid.register_consumer(self.consumer_id)

        logger.info("AOA re-initialized (Accessory+ADB mode)")
        return True
