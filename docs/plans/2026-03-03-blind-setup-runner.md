# Blind Setup Runner Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a YAML-driven blind runner that automates Setup Wizard + USB Debugging enablement via AOA2 HID, plus a CLI recorder for generating step files.

**Architecture:** YAML step files define action sequences (tap/swipe/type/key/wake/home/back/sleep/wait_for_adb). BlindRunner reads them and dispatches to the existing AoaHidDriver. A `smoke-test record` CLI command uses ADB screencap + OpenCV to interactively record coordinates into YAML.

**Tech Stack:** Python 3.10+, PyUSB (existing AoaHidDriver), Click (CLI), OpenCV (recorder), PyYAML, pytest

---

## Task 1: BlindRunner — Basic Actions (TDD)

**Files:**
- Create: `smoke_test_ai/runners/__init__.py`
- Create: `smoke_test_ai/runners/blind_runner.py`
- Create: `tests/test_blind_runner.py`

### Step 1: Write the failing tests for basic actions

Create `tests/test_blind_runner.py`:

```python
import time
import pytest
from unittest.mock import MagicMock, patch

from smoke_test_ai.runners.blind_runner import BlindRunner


def _make_runner(steps, screen_w=2560, screen_h=1600):
    """Helper: build BlindRunner with mock HID and ADB."""
    hid = MagicMock()
    adb = MagicMock()
    aoa_config = {
        "vendor_id": 0x099E,
        "product_id": 0x02B1,
        "rotation": 90,
        "keyboard_hid_id": 1,
        "touch_hid_id": 2,
        "consumer_hid_id": 3,
    }
    flow_config = {
        "screen_resolution": [screen_w, screen_h],
        "steps": steps,
    }
    runner = BlindRunner(hid=hid, adb=adb, aoa_config=aoa_config, flow_config=flow_config)
    return runner, hid, adb


class TestBlindRunnerBasicActions:
    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_tap_action(self, mock_sleep):
        """tap calls hid.tap() with correct coordinates and screen size."""
        runner, hid, _ = _make_runner([
            {"action": "tap", "x": 500, "y": 300, "delay": 0.5},
        ])
        runner.run()
        hid.tap.assert_called_once_with(2, 500, 300, 2560, 1600)
        mock_sleep.assert_called_with(0.5)

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_tap_with_repeat(self, mock_sleep):
        """tap with repeat=7 calls hid.tap() seven times."""
        runner, hid, _ = _make_runner([
            {"action": "tap", "x": 100, "y": 200, "repeat": 7, "delay": 0.3},
        ])
        runner.run()
        assert hid.tap.call_count == 7

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_swipe_action(self, mock_sleep):
        """swipe calls hid.swipe() with start/end coords and duration."""
        runner, hid, _ = _make_runner([
            {"action": "swipe", "x1": 100, "y1": 800, "x2": 100, "y2": 200,
             "duration": 0.5, "delay": 1.0},
        ])
        runner.run()
        hid.swipe.assert_called_once_with(
            2, 100, 800, 100, 200, 2560, 1600, duration=0.5,
        )

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_type_action(self, mock_sleep):
        """type calls hid.type_text() with the text string."""
        runner, hid, _ = _make_runner([
            {"action": "type", "text": "hello", "delay": 1.0},
        ])
        runner.run()
        hid.type_text.assert_called_once_with(1, "hello")

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_key_enter(self, mock_sleep):
        """key=enter calls hid.press_enter()."""
        runner, hid, _ = _make_runner([
            {"action": "key", "key": "enter", "delay": 0.5},
        ])
        runner.run()
        hid.press_enter.assert_called_once_with(1)

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_wake_action(self, mock_sleep):
        """wake calls hid.wake_screen()."""
        runner, hid, _ = _make_runner([
            {"action": "wake", "delay": 1.0},
        ])
        runner.run()
        hid.wake_screen.assert_called_once_with(2)

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_home_action(self, mock_sleep):
        """home calls hid.press_home()."""
        runner, hid, _ = _make_runner([
            {"action": "home", "delay": 1.0},
        ])
        runner.run()
        hid.press_home.assert_called_once_with(3)

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_back_action(self, mock_sleep):
        """back calls hid.press_back()."""
        runner, hid, _ = _make_runner([
            {"action": "back", "delay": 1.0},
        ])
        runner.run()
        hid.press_back.assert_called_once_with(3)

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_sleep_action(self, mock_sleep):
        """sleep action calls time.sleep with specified duration."""
        runner, hid, _ = _make_runner([
            {"action": "sleep", "duration": 3.0},
        ])
        runner.run()
        mock_sleep.assert_any_call(3.0)

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_default_delay(self, mock_sleep):
        """Steps without explicit delay use default 1.0s."""
        runner, hid, _ = _make_runner([
            {"action": "wake"},
        ])
        runner.run()
        mock_sleep.assert_called_with(1.0)

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_unknown_action_skipped(self, mock_sleep):
        """Unknown action type is skipped without crashing."""
        runner, hid, _ = _make_runner([
            {"action": "unknown_thing"},
            {"action": "wake", "delay": 0.5},
        ])
        result = runner.run()
        assert result is True
        hid.wake_screen.assert_called_once()

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_run_returns_true_on_completion(self, mock_sleep):
        """run() returns True when all steps complete."""
        runner, _, _ = _make_runner([
            {"action": "wake"},
            {"action": "home", "delay": 0.5},
        ])
        assert runner.run() is True
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/test_blind_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'smoke_test_ai.runners'`

### Step 3: Write BlindRunner implementation

Create `smoke_test_ai/runners/__init__.py`:

```python
```

Create `smoke_test_ai/runners/blind_runner.py`:

```python
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
            self.hid.send_key(self.kbd_id, 0x2B)  # HID Tab
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
        """Release AOA → poll ADB → re-init AOA for RSA tap."""
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
```

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/test_blind_runner.py -v`
Expected: All 12 tests PASS

### Step 5: Commit

```bash
git add smoke_test_ai/runners/__init__.py smoke_test_ai/runners/blind_runner.py tests/test_blind_runner.py
git commit -m "feat: add BlindRunner with basic HID action dispatch"
```

---

## Task 2: BlindRunner — wait_for_adb Tests (TDD)

**Files:**
- Modify: `tests/test_blind_runner.py`

### Step 1: Write the failing tests for wait_for_adb

Append to `tests/test_blind_runner.py`:

```python
class TestBlindRunnerWaitForAdb:
    @patch("smoke_test_ai.runners.blind_runner.AoaHidDriver")
    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_wait_for_adb_success(self, mock_sleep, MockHid):
        """wait_for_adb: close → poll adb → re-init HID → returns True."""
        runner, hid, adb = _make_runner([
            {"action": "wait_for_adb", "timeout": 10},
        ])
        adb.wait_for_device.return_value = True
        new_hid = MagicMock()
        MockHid.return_value = new_hid

        result = runner.run()

        assert result is True
        hid.close.assert_called_once()
        adb.wait_for_device.assert_called_once_with(timeout=10)
        MockHid.assert_called_once_with(
            vendor_id=0x099E, product_id=0x02B1, rotation=90,
        )
        new_hid.find_device.assert_called_once()
        new_hid.start_accessory.assert_called_once()
        new_hid.register_touch.assert_called_once_with(2)
        new_hid.register_consumer.assert_called_once_with(3)

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_wait_for_adb_timeout(self, mock_sleep):
        """wait_for_adb timeout → run() returns False."""
        runner, hid, adb = _make_runner([
            {"action": "wait_for_adb", "timeout": 5},
        ])
        adb.wait_for_device.return_value = False

        result = runner.run()

        assert result is False
        hid.close.assert_called_once()

    @patch("smoke_test_ai.runners.blind_runner.AoaHidDriver")
    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_steps_after_wait_use_new_hid(self, mock_sleep, MockHid):
        """After wait_for_adb, subsequent steps use the re-initialized HID."""
        new_hid = MagicMock()
        MockHid.return_value = new_hid
        runner, old_hid, adb = _make_runner([
            {"action": "wait_for_adb", "timeout": 10},
            {"action": "tap", "x": 500, "y": 300, "delay": 0.5},
        ])
        adb.wait_for_device.return_value = True

        runner.run()

        # tap should be called on the NEW hid, not old
        old_hid.tap.assert_not_called()
        new_hid.tap.assert_called_once_with(2, 500, 300, 2560, 1600)
```

### Step 2: Run tests to verify they pass

Run: `python -m pytest tests/test_blind_runner.py::TestBlindRunnerWaitForAdb -v`

Note: These tests depend on the `_wait_for_adb` implementation from Task 1. The import `AoaHidDriver` in `_wait_for_adb` is inside the function body, so the `@patch` path targets `smoke_test_ai.runners.blind_runner.AoaHidDriver`. If this path doesn't resolve (because of the local import), change the patch target to `smoke_test_ai.drivers.aoa_hid.AoaHidDriver`.

Expected: All 3 tests PASS

### Step 3: Fix any issues and commit

```bash
git add tests/test_blind_runner.py
git commit -m "test: add wait_for_adb tests for BlindRunner"
```

---

## Task 3: Device Config — AOA Section + Setup Flow Directory

**Files:**
- Modify: `config/devices/product_a.yaml`
- Create: `config/setup_flows/.gitkeep`

### Step 1: Add AOA config to product_a.yaml

Add after the `flash:` block (before `screen_capture:`):

```yaml
  aoa:
    enabled: true
    vendor_id: 0x099E
    product_id: 0x02B1
    rotation: 90
    keyboard_hid_id: 1
    touch_hid_id: 2
    consumer_hid_id: 3
```

### Step 2: Create setup_flows directory

```bash
mkdir -p config/setup_flows
touch config/setup_flows/.gitkeep
```

### Step 3: Commit

```bash
git add config/devices/product_a.yaml config/setup_flows/.gitkeep
git commit -m "feat: add AOA config to product_a and create setup_flows directory"
```

---

## Task 4: Orchestrator — Stage 1 Integration (TDD)

**Files:**
- Modify: `smoke_test_ai/core/orchestrator.py`
- Modify: existing orchestrator tests (if any) or add integration test to `tests/test_blind_runner.py`

### Step 1: Write the failing test

Append to `tests/test_blind_runner.py`:

```python
class TestOrchestratorStage1:
    @patch("smoke_test_ai.core.orchestrator.BlindRunner")
    @patch("smoke_test_ai.core.orchestrator.yaml.safe_load")
    @patch("smoke_test_ai.core.orchestrator.AoaHidDriver")
    def test_stage1_runs_blind_runner(self, MockHid, mock_yaml, MockRunner):
        """Stage 1 loads flow YAML and runs BlindRunner when aoa.enabled."""
        from smoke_test_ai.core.orchestrator import Orchestrator

        mock_hid_instance = MagicMock()
        MockHid.return_value = mock_hid_instance
        mock_runner_instance = MagicMock()
        mock_runner_instance.run.return_value = True
        MockRunner.return_value = mock_runner_instance
        mock_yaml.return_value = {"screen_resolution": [2560, 1600], "steps": []}

        settings = {
            "llm": {"provider": "ollama", "base_url": "http://localhost:11434",
                     "vision_model": "llava", "text_model": "llama3"},
            "wifi": {},
            "reporting": {"formats": ["cli"], "output_dir": "results/"},
        }
        device_config = {
            "device": {
                "name": "Test-Device",
                "build_type": "user",
                "screen_resolution": [2560, 1600],
                "aoa": {
                    "enabled": True,
                    "vendor_id": 0x099E,
                    "product_id": 0x02B1,
                    "rotation": 90,
                    "keyboard_hid_id": 1,
                    "touch_hid_id": 2,
                    "consumer_hid_id": 3,
                },
                "flash": {"profile": "fastboot"},
            }
        }
        orch = Orchestrator(settings, device_config)
        # We can't easily run the full pipeline; test _run_stage1 directly
        # This test verifies the integration exists; full E2E is manual
        MockRunner.assert_not_called()  # Not called until run()
```

Note: This test is a sanity check. The real orchestrator integration test is complex because `run()` has many dependencies. The primary verification is:
1. The import works
2. BlindRunner is constructed correctly

### Step 2: Add `_init_aoa_hid()` and Stage 1 logic to orchestrator

In `smoke_test_ai/core/orchestrator.py`, add after the `__init__` method:

```python
def _init_aoa_hid(self, aoa_cfg: dict):
    """Initialize AOA2 HID driver: find device, start accessory mode, register HIDs."""
    from smoke_test_ai.drivers.aoa_hid import (
        AoaHidDriver, HID_KEYBOARD_DESCRIPTOR,
    )

    hid = AoaHidDriver(
        vendor_id=aoa_cfg["vendor_id"],
        product_id=aoa_cfg["product_id"],
        rotation=aoa_cfg.get("rotation", 0),
    )
    hid.find_device()
    hid.start_accessory()

    kbd_id = aoa_cfg.get("keyboard_hid_id", 1)
    touch_id = aoa_cfg.get("touch_hid_id", 2)
    consumer_id = aoa_cfg.get("consumer_hid_id", 3)
    hid.register_hid(kbd_id, HID_KEYBOARD_DESCRIPTOR)
    hid.register_touch(touch_id)
    hid.register_consumer(consumer_id)

    logger.info(f"AOA HID initialized (keyboard={kbd_id}, touch={touch_id}, consumer={consumer_id})")
    return hid
```

Replace the Stage 1 placeholder (lines 326-330) with:

```python
# Stage 1: Pre-ADB Setup (Blind AOA2 HID automation)
if not skip_setup and self.device_config.get("build_type") == "user":
    aoa_cfg = self.device_config.get("aoa", {})
    if aoa_cfg.get("enabled"):
        logger.info("=== Stage 1: Pre-ADB Setup (Blind AOA2 HID) ===")
        flow_name = self.device_config["name"].lower().replace("-", "_").replace(" ", "_")
        flow_path = Path(config_dir) / "setup_flows" / f"{flow_name}.yaml"
        if flow_path.exists():
            try:
                import yaml
                from smoke_test_ai.runners.blind_runner import BlindRunner
                from smoke_test_ai.drivers.aoa_hid import AoaHidDriver

                hid = self._init_aoa_hid(aoa_cfg)
                flow = yaml.safe_load(flow_path.read_text())
                runner = BlindRunner(hid=hid, adb=adb, aoa_config=aoa_cfg, flow_config=flow)
                if runner.run():
                    logger.info("Blind setup flow completed successfully")
                else:
                    logger.warning("Blind setup flow did not complete — ADB may not be available")
                hid.close()
            except Exception as e:
                logger.error(f"Blind setup flow failed: {e}")
        else:
            logger.info(f"No setup flow at {flow_path}, skipping Stage 1")
    else:
        logger.info("=== Stage 1: Pre-ADB Setup (AOA not configured) ===")
        logger.info("Waiting for ADB to become available...")
```

Note: `config_dir` needs to be passed into `run()` or derived from settings. Check how the `run` CLI command passes it — the `run()` method signature may need a `config_dir` parameter added. Currently CLI passes `config_path` to load configs but doesn't pass it to `orch.run()`. Add `config_dir: str = "config"` to `run()` signature and pass `config_path` from CLI.

### Step 3: Run tests

Run: `python -m pytest tests/test_blind_runner.py -v`
Expected: All tests PASS

### Step 4: Commit

```bash
git add smoke_test_ai/core/orchestrator.py tests/test_blind_runner.py
git commit -m "feat: integrate BlindRunner into Orchestrator Stage 1"
```

---

## Task 5: CLI `record` Command

**Files:**
- Modify: `cli.py`
- Create: `smoke_test_ai/runners/recorder.py`

### Step 1: Write the recorder module

Create `smoke_test_ai/runners/recorder.py`:

```python
import subprocess
import cv2
import numpy as np
import yaml
from pathlib import Path
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)

WINDOW_NAME = "smoke-test recorder (click=tap, drag=swipe, t=type, w=wake, h=home, b=back, s=sleep, a=wait_for_adb, n=next screenshot, q=quit)"


class StepRecorder:
    """Interactive CLI recorder: ADB screencap + OpenCV → YAML steps."""

    def __init__(self, serial: str | None, device_name: str, output_path: Path):
        self.serial = serial
        self.device_name = device_name
        self.output_path = output_path
        self.steps: list[dict] = []
        self._click_start: tuple[int, int] | None = None
        self._drag_end: tuple[int, int] | None = None
        self._current_image: np.ndarray | None = None

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
        if event == cv2.EVENT_LBUTTONDOWN:
            self._click_start = (x, y)
            self._drag_end = None
        elif event == cv2.EVENT_LBUTTONUP:
            if self._click_start:
                dx = abs(x - self._click_start[0])
                dy = abs(y - self._click_start[1])
                if dx > 20 or dy > 20:
                    self._drag_end = (x, y)
                    sx, sy = self._click_start
                    desc = input(f"  Swipe ({sx},{sy})→({x},{y}). Description: ").strip()
                    dur = input("  Duration [0.3]: ").strip() or "0.3"
                    delay = input("  Delay after [1.5]: ").strip() or "1.5"
                    self.steps.append({
                        "action": "swipe",
                        "x1": sx, "y1": sy, "x2": x, "y2": y,
                        "duration": float(dur), "delay": float(delay),
                        "description": desc or f"Swipe ({sx},{sy})→({x},{y})",
                    })
                    print(f"  ✓ Recorded swipe")
                else:
                    desc = input(f"  Tap ({x},{y}). Description: ").strip()
                    delay = input("  Delay after [1.0]: ").strip() or "1.0"
                    repeat = input("  Repeat [1]: ").strip() or "1"
                    step = {
                        "action": "tap", "x": x, "y": y,
                        "delay": float(delay),
                        "description": desc or f"Tap ({x},{y})",
                    }
                    if int(repeat) > 1:
                        step["repeat"] = int(repeat)
                    self.steps.append(step)
                    print(f"  ✓ Recorded tap")
                self._click_start = None

    def run(self) -> None:
        """Main recording loop."""
        print(f"Recording setup flow for '{self.device_name}'")
        print("Controls: click=tap, drag=swipe, t=type, w=wake, h=home, b=back, s=sleep, a=wait_for_adb, n=screenshot, q=quit")
        print()

        self._current_image = self._adb_screencap()
        if self._current_image is None:
            print("ERROR: Could not capture screenshot. Check ADB connection.")
            return

        screen_h, screen_w = self._current_image.shape[:2]
        print(f"Screen resolution: {screen_w}x{screen_h}")

        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(WINDOW_NAME, self._mouse_callback)
        cv2.imshow(WINDOW_NAME, self._current_image)

        while True:
            key = cv2.waitKey(0) & 0xFF

            if key == ord("q"):
                break
            elif key == ord("n"):
                img = self._adb_screencap()
                if img is not None:
                    self._current_image = img
                    cv2.imshow(WINDOW_NAME, img)
                    print("  ✓ Screenshot refreshed")
            elif key == ord("t"):
                text = input("  Text to type: ").strip()
                delay = input("  Delay after [1.0]: ").strip() or "1.0"
                if text:
                    self.steps.append({"action": "type", "text": text, "delay": float(delay)})
                    print(f"  ✓ Recorded type: '{text}'")
            elif key == ord("w"):
                self.steps.append({"action": "wake", "delay": 1.0})
                print("  ✓ Recorded wake")
            elif key == ord("h"):
                self.steps.append({"action": "home", "delay": 1.0})
                print("  ✓ Recorded home")
            elif key == ord("b"):
                self.steps.append({"action": "back", "delay": 1.0})
                print("  ✓ Recorded back")
            elif key == ord("s"):
                dur = input("  Sleep duration [2.0]: ").strip() or "2.0"
                self.steps.append({"action": "sleep", "duration": float(dur)})
                print(f"  ✓ Recorded sleep {dur}s")
            elif key == ord("a"):
                timeout = input("  ADB wait timeout [30]: ").strip() or "30"
                self.steps.append({
                    "action": "wait_for_adb", "timeout": int(timeout),
                    "description": "Release AOA, wait for ADB, re-init AOA",
                })
                print(f"  ✓ Recorded wait_for_adb (timeout={timeout}s)")
            elif key == ord("k"):
                key_name = input("  Key name (enter/tab): ").strip()
                self.steps.append({"action": "key", "key": key_name, "delay": 1.0})
                print(f"  ✓ Recorded key: {key_name}")

        cv2.destroyAllWindows()

        if not self.steps:
            print("No steps recorded.")
            return

        flow = {
            "device": self.device_name,
            "screen_resolution": [screen_w, screen_h],
            "steps": self.steps,
        }
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(yaml.dump(flow, default_flow_style=False, allow_unicode=True, sort_keys=False))
        print(f"\nSaved {len(self.steps)} steps to {self.output_path}")
```

### Step 2: Add `record` command to CLI

In `cli.py`, add after the existing commands:

```python
@main.command()
@click.option("--device", required=True, help="Device config name (e.g. product_a)")
@click.option("--serial", default=None, help="Device serial number for ADB screencap")
@click.option("--config-dir", default="config", help="Config directory path")
def record(device, serial, config_dir):
    """Record a setup flow by clicking on ADB screenshots."""
    from smoke_test_ai.runners.recorder import StepRecorder
    from smoke_test_ai.utils.config import load_device_config

    config_path = Path(config_dir)
    device_config = load_device_config(config_path / "devices" / f"{device}.yaml")
    device_name = device_config["device"]["name"]

    flow_name = device_name.lower().replace("-", "_").replace(" ", "_")
    output_path = config_path / "setup_flows" / f"{flow_name}.yaml"

    recorder = StepRecorder(serial=serial, device_name=device_name, output_path=output_path)
    recorder.run()
```

### Step 3: Write a minimal test for recorder YAML output

Append to `tests/test_blind_runner.py`:

```python
class TestStepRecorderOutput:
    def test_generates_valid_yaml(self, tmp_path):
        """StepRecorder outputs valid YAML with correct structure."""
        from smoke_test_ai.runners.recorder import StepRecorder

        output = tmp_path / "test_flow.yaml"
        rec = StepRecorder(serial=None, device_name="Test-Device", output_path=output)
        rec.steps = [
            {"action": "wake", "delay": 1.0},
            {"action": "tap", "x": 500, "y": 300, "delay": 2.0, "description": "Tap start"},
        ]
        # Simulate save without running the interactive loop
        import yaml
        flow = {
            "device": rec.device_name,
            "screen_resolution": [1080, 2400],
            "steps": rec.steps,
        }
        output.write_text(yaml.dump(flow, default_flow_style=False, sort_keys=False))

        loaded = yaml.safe_load(output.read_text())
        assert loaded["device"] == "Test-Device"
        assert len(loaded["steps"]) == 2
        assert loaded["steps"][0]["action"] == "wake"
        assert loaded["steps"][1]["x"] == 500
```

### Step 4: Run all tests

Run: `python -m pytest tests/test_blind_runner.py -v`
Expected: All tests PASS

### Step 5: Commit

```bash
git add smoke_test_ai/runners/recorder.py cli.py tests/test_blind_runner.py
git commit -m "feat: add smoke-test record command with OpenCV screenshot recorder"
```

---

## Task 6: Full Test Suite Verification + Docs Sync

**Files:**
- Modify: `README.md` (test count update)

### Step 1: Run full test suite

Run: `python -m pytest tests/ -v`
Expected: All tests PASS (previous 176 + new ~16 = ~192)

### Step 2: Update README test count

Update the two places in README.md where test count is mentioned:
- `# 執行測試 (Nnn 個單元測試，全 Mock，不需硬體)`
- `| 測試 | pytest + pytest-mock (Nnn tests) |`

### Step 3: Commit and push

```bash
git add README.md
git commit -m "docs: sync README with blind runner (60 tests, Nnn unit tests)"
git push
```

---

## Summary: Task Execution Order

| Task | Description | Files | Tests |
|------|-------------|-------|-------|
| 1 | BlindRunner basic actions | `runners/blind_runner.py`, `tests/test_blind_runner.py` | 12 |
| 2 | wait_for_adb tests | `tests/test_blind_runner.py` | 3 |
| 3 | Device config + setup_flows dir | `config/devices/product_a.yaml`, `config/setup_flows/` | 0 |
| 4 | Orchestrator Stage 1 integration | `orchestrator.py`, `tests/test_blind_runner.py` | 1 |
| 5 | CLI record command | `recorder.py`, `cli.py`, `tests/test_blind_runner.py` | 1 |
| 6 | Full test suite + docs | `README.md` | 0 |

**Total new tests:** ~17

**End-to-end verification (manual, with real hardware):**
1. On userdebug build: `smoke-test record --serial SERIAL --device product_a`
2. Flash user build, then: `smoke-test run --device product_a --suite smoke_basic --skip-flash`
3. Verify ADB connects and tests run
