import time
import numpy as np
from smoke_test_ai.drivers.aoa_hid import AoaHidDriver
from smoke_test_ai.drivers.screen_capture.base import ScreenCapture
from smoke_test_ai.ai.visual_analyzer import VisualAnalyzer
from smoke_test_ai.drivers.adb_controller import AdbController
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)


class SetupWizardAgent:
    SCREEN_OFF_BRIGHTNESS_THRESHOLD = 10

    def __init__(
        self,
        hid: AoaHidDriver,
        screen_capture: ScreenCapture,
        analyzer: VisualAnalyzer,
        adb: AdbController,
        screen_w: int = 1080,
        screen_h: int = 2400,
        hid_id: int = 2,
        keyboard_hid_id: int = 1,
        max_steps: int = 30,
        timeout: int = 300,
    ):
        self.hid = hid
        self.screen_capture = screen_capture
        self.analyzer = analyzer
        self.adb = adb
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.hid_id = hid_id
        self.keyboard_hid_id = keyboard_hid_id
        self.max_steps = max_steps
        self.timeout = timeout

    def run(self) -> bool:
        logger.info("Starting Setup Wizard automation...")
        deadline = time.time() + self.timeout
        consecutive_dark_frames = 0

        for step in range(self.max_steps):
            if time.time() > deadline:
                logger.warning("Setup Wizard timeout")
                return False

            if self.adb.is_connected():
                boot = self.adb.getprop("sys.boot_completed")
                if boot == "1":
                    logger.info("ADB connected and boot completed — Setup Wizard done")
                    return True

            image = self.screen_capture.capture()
            if image is None:
                logger.warning(f"Step {step}: Failed to capture screen, waiting...")
                time.sleep(3)
                continue

            if self._is_screen_off(image):
                consecutive_dark_frames += 1
                if consecutive_dark_frames <= 2:
                    # First attempts: mouse movement (safe, no side effects)
                    logger.warning(f"Step {step}: Screen appears off, waking via mouse movement...")
                    self.hid.wake_screen(self.hid_id)
                else:
                    # Persistent dark screen: escalate to Power key
                    logger.warning(f"Step {step}: Screen still off after {consecutive_dark_frames} attempts, using Power key...")
                    self.hid.wake_screen_power(self.keyboard_hid_id)
                    consecutive_dark_frames = 0  # Reset to avoid rapid Power key toggling
                time.sleep(2)
                continue

            consecutive_dark_frames = 0
            analysis = self.analyzer.analyze_setup_wizard(image)
            logger.info(
                f"Step {step}: state={analysis['screen_state']} "
                f"confidence={analysis.get('confidence', 0):.2f}"
            )

            if analysis.get("completed", False):
                logger.info("LLM reports Setup Wizard completed")
                return True

            action = analysis.get("action", {})
            self._execute_action(action)
            time.sleep(1)

        logger.warning(f"Setup Wizard did not complete within {self.max_steps} steps")
        return False

    def _execute_action(self, action: dict) -> None:
        action_type = action.get("type", "wait")

        if action_type == "tap":
            x, y = action.get("x", 540), action.get("y", 960)
            logger.info(f"  Action: tap ({x}, {y})")
            self.hid.tap(self.hid_id, x, y, self.screen_w, self.screen_h)

        elif action_type == "swipe":
            direction = action.get("direction", "up")
            cx, cy = self.screen_w // 2, self.screen_h // 2
            offsets = {
                "up": (cx, cy + 400, cx, cy - 400),
                "down": (cx, cy - 400, cx, cy + 400),
                "left": (cx + 400, cy, cx - 400, cy),
                "right": (cx - 400, cy, cx + 400, cy),
            }
            x1, y1, x2, y2 = offsets.get(direction, offsets["up"])
            logger.info(f"  Action: swipe {direction}")
            self.hid.swipe(self.hid_id, x1, y1, x2, y2, self.screen_w, self.screen_h)

        elif action_type == "type":
            text = action.get("text", "")
            logger.info(f"  Action: type '{text}'")
            if self.adb.is_connected():
                self.adb.shell(f"input text '{text}'")

        elif action_type == "wait":
            wait_sec = action.get("wait_seconds", 3)
            logger.info(f"  Action: wait {wait_sec}s")
            time.sleep(wait_sec)

    def _is_screen_off(self, image: np.ndarray) -> bool:
        """Detect if screen is off by checking average brightness."""
        mean_brightness = np.mean(image)
        return mean_brightness < self.SCREEN_OFF_BRIGHTNESS_THRESHOLD
