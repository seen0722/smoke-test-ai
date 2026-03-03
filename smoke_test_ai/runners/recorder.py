import subprocess
import time
import cv2
import numpy as np
import yaml
from pathlib import Path
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)

WINDOW_NAME = "smoke-test recorder"
HELP_TEXT = (
    "click=tap | drag=swipe | t=type | k=key | w=wake | h=home | "
    "b=back | s=sleep | a=wait_for_adb | n=screenshot | q=quit"
)


class StepRecorder:
    """Interactive CLI recorder: ADB screencap + OpenCV -> YAML steps.

    Architecture: non-blocking event loop to work on macOS Cocoa backend.
    Mouse callback only stores coordinates; all terminal I/O happens in
    the main loop after cv2.waitKey returns.
    """

    def __init__(self, serial: str | None, device_name: str, output_path: Path):
        self.serial = serial
        self.device_name = device_name
        self.output_path = output_path
        self.steps: list[dict] = []
        self._mouse_down: tuple[int, int] | None = None
        self._pending_tap: tuple[int, int] | None = None
        self._pending_swipe: tuple[int, int, int, int] | None = None

    def _adb_input(self, *args: str) -> None:
        """Send input command to DUT via ADB."""
        cmd = ["adb"]
        if self.serial:
            cmd.extend(["-s", self.serial])
        cmd.extend(["shell", "input", *args])
        subprocess.run(cmd, capture_output=True, timeout=5)

    def _adb_tap(self, x: int, y: int) -> None:
        self._adb_input("tap", str(x), str(y))

    def _adb_swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self._adb_input("swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms))

    def _refresh_screenshot(self) -> None:
        """Capture and display a fresh screenshot."""
        img = self._adb_screencap()
        if img is not None:
            self._current_image = img
            cv2.imshow(WINDOW_NAME, img)

    def _adb_screencap(self) -> np.ndarray | None:
        cmd = ["adb"]
        if self.serial:
            cmd.extend(["-s", self.serial])
        cmd.extend(["exec-out", "screencap", "-p"])
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            if result.returncode != 0:
                logger.error(f"screencap failed: {result.stderr}")
                return None
            arr = np.frombuffer(result.stdout, dtype=np.uint8)
            return cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except subprocess.TimeoutExpired:
            logger.error("screencap timed out")
            return None

    def _mouse_callback(self, event, x, y, flags, param):
        """Only store coordinates — NO terminal I/O here."""
        if event == cv2.EVENT_LBUTTONDOWN:
            self._mouse_down = (x, y)
        elif event == cv2.EVENT_LBUTTONUP:
            if self._mouse_down is None:
                return
            sx, sy = self._mouse_down
            dx = abs(x - sx)
            dy = abs(y - sy)
            if dx > 20 or dy > 20:
                self._pending_swipe = (sx, sy, x, y)
            else:
                self._pending_tap = (x, y)
            self._mouse_down = None

    def _handle_pending_tap(self) -> None:
        """Process a pending tap event with terminal I/O."""
        x, y = self._pending_tap
        self._pending_tap = None

        print(f"\n  Tap at ({x}, {y})")
        desc = input("  Description []: ").strip()
        delay = input("  Delay after [1.0]: ").strip() or "1.0"
        repeat = input("  Repeat [1]: ").strip() or "1"
        repeat_n = int(repeat)

        step = {
            "action": "tap", "x": x, "y": y,
            "delay": float(delay),
            "description": desc or f"Tap ({x},{y})",
        }
        if repeat_n > 1:
            step["repeat"] = repeat_n
        self.steps.append(step)

        print(f"  -> Recorded tap — sending to DUT...")
        for i in range(repeat_n):
            self._adb_tap(x, y)
            if repeat_n > 1 and i < repeat_n - 1:
                time.sleep(float(delay))
        time.sleep(float(delay))
        self._refresh_screenshot()

    def _handle_pending_swipe(self) -> None:
        """Process a pending swipe event with terminal I/O."""
        sx, sy, ex, ey = self._pending_swipe
        self._pending_swipe = None

        print(f"\n  Swipe ({sx},{sy}) -> ({ex},{ey})")
        desc = input("  Description []: ").strip()
        dur = input("  Duration [0.3]: ").strip() or "0.3"
        delay = input("  Delay after [1.5]: ").strip() or "1.5"

        self.steps.append({
            "action": "swipe",
            "x1": sx, "y1": sy, "x2": ex, "y2": ey,
            "duration": float(dur), "delay": float(delay),
            "description": desc or f"Swipe ({sx},{sy})->({ex},{ey})",
        })

        print(f"  -> Recorded swipe — sending to DUT...")
        self._adb_swipe(sx, sy, ex, ey, int(float(dur) * 1000))
        time.sleep(float(delay))
        self._refresh_screenshot()

    def run(self) -> None:
        """Main recording loop (non-blocking for macOS compatibility)."""
        print(f"Recording setup flow for '{self.device_name}'")
        print(f"Controls: {HELP_TEXT}")
        print()

        self._current_image = self._adb_screencap()
        if self._current_image is None:
            print("ERROR: Could not capture screenshot. Check ADB connection.")
            return

        screen_h, screen_w = self._current_image.shape[:2]
        print(f"Screen resolution: {screen_w}x{screen_h}")
        print("Click on the OpenCV window, then check terminal for prompts.\n")

        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(WINDOW_NAME, self._mouse_callback)
        cv2.imshow(WINDOW_NAME, self._current_image)

        while True:
            # Non-blocking wait — lets macOS Cocoa process mouse events
            key = cv2.waitKey(100) & 0xFF

            # Check for pending mouse events first
            if self._pending_tap is not None:
                self._handle_pending_tap()
                continue
            if self._pending_swipe is not None:
                self._handle_pending_swipe()
                continue

            # Then handle keyboard
            if key == 255:
                continue  # no key pressed
            elif key == ord("q"):
                break
            elif key == ord("n"):
                self._refresh_screenshot()
                print("  Screenshot refreshed")
            elif key == ord("t"):
                text = input("  Text to type: ").strip()
                delay = input("  Delay after [1.0]: ").strip() or "1.0"
                if text:
                    self.steps.append({"action": "type", "text": text, "delay": float(delay)})
                    print(f"  -> Recorded type: '{text}' — sending to DUT...")
                    self._adb_input("text", text)
                    time.sleep(float(delay))
                    self._refresh_screenshot()
            elif key == ord("w"):
                self.steps.append({"action": "wake", "delay": 1.0})
                print("  Recorded wake")
            elif key == ord("h"):
                self.steps.append({"action": "home", "delay": 1.0})
                print("  Recorded home")
            elif key == ord("b"):
                self.steps.append({"action": "back", "delay": 1.0})
                print("  Recorded back")
            elif key == ord("s"):
                dur = input("  Sleep duration [2.0]: ").strip() or "2.0"
                self.steps.append({"action": "sleep", "duration": float(dur)})
                print(f"  Recorded sleep {dur}s")
            elif key == ord("a"):
                timeout = input("  ADB wait timeout [30]: ").strip() or "30"
                self.steps.append({
                    "action": "wait_for_adb", "timeout": int(timeout),
                    "description": "Release AOA, wait for ADB, re-init AOA",
                })
                print(f"  Recorded wait_for_adb (timeout={timeout}s)")
            elif key == ord("k"):
                key_name = input("  Key name (enter/tab): ").strip()
                self.steps.append({"action": "key", "key": key_name, "delay": 1.0})
                print(f"  Recorded key: {key_name}")

        cv2.destroyAllWindows()
        self._save(screen_w, screen_h)

    def _save(self, screen_w: int, screen_h: int) -> None:
        """Save recorded steps to YAML."""
        if not self.steps:
            print("No steps recorded.")
            return

        flow = {
            "device": self.device_name,
            "screen_resolution": [screen_w, screen_h],
            "steps": self.steps,
        }
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(
            yaml.dump(flow, default_flow_style=False, allow_unicode=True, sort_keys=False)
        )
        print(f"\nSaved {len(self.steps)} steps to {self.output_path}")
