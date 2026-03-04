import pytest
import usb.core
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
        hid.tap.assert_called_once_with(2, 500, 300, 2560, 1600, press_duration=0.05)
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


class TestBlindRunnerWaitForAdb:
    @patch("smoke_test_ai.drivers.aoa_hid.AoaHidDriver")
    @patch("smoke_test_ai.runners.blind_runner.usb.core.find")
    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_wait_for_adb_success(self, mock_sleep, mock_usb_find, MockHid):
        """wait_for_adb: close → poll USB → re-init HID → returns True."""
        runner, hid, adb = _make_runner([
            {"action": "wait_for_adb", "timeout": 10},
        ])
        new_hid = MagicMock()
        MockHid.return_value = new_hid
        # Simulate device found in normal mode
        fake_dev = MagicMock()
        fake_dev.idVendor = 0x099E
        fake_dev.idProduct = 0x02B1
        mock_usb_find.return_value = [fake_dev]

        result = runner.run()

        assert result is True
        hid.close.assert_called_once()
        MockHid.assert_called_once_with(
            vendor_id=0x099E, product_id=0x02B1, rotation=90,
        )
        new_hid.find_device.assert_called_once()
        new_hid.start_accessory.assert_called_once()
        new_hid.register_touch.assert_called_once_with(2)
        new_hid.register_consumer.assert_called_once_with(3)

    @patch("smoke_test_ai.runners.blind_runner.usb.core.find")
    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    @patch("smoke_test_ai.runners.blind_runner.time.time")
    def test_wait_for_adb_timeout(self, mock_time, mock_sleep, mock_usb_find):
        """wait_for_adb timeout → run() returns False."""
        runner, hid, adb = _make_runner([
            {"action": "wait_for_adb", "timeout": 5},
        ])
        # Simulate time passing beyond timeout
        mock_time.side_effect = [0, 0, 1, 2, 3, 4, 5, 6]
        mock_usb_find.return_value = []  # No device found
        adb.is_connected.return_value = False  # ADB fallback also fails

        result = runner.run()

        assert result is False
        hid.close.assert_called_once()

    @patch("smoke_test_ai.drivers.aoa_hid.AoaHidDriver")
    @patch("smoke_test_ai.runners.blind_runner.usb.core.find")
    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_steps_after_wait_use_new_hid(self, mock_sleep, mock_usb_find, MockHid):
        """After wait_for_adb, subsequent steps use the re-initialized HID."""
        new_hid = MagicMock()
        MockHid.return_value = new_hid
        runner, old_hid, adb = _make_runner([
            {"action": "wait_for_adb", "timeout": 10},
            {"action": "tap", "x": 500, "y": 300, "delay": 0.5},
        ])
        # Simulate device found in Accessory+ADB mode
        fake_dev = MagicMock()
        fake_dev.idVendor = 0x18D1
        fake_dev.idProduct = 0x2D01
        mock_usb_find.return_value = [fake_dev]

        runner.run()

        old_hid.tap.assert_not_called()
        new_hid.tap.assert_called_once_with(2, 500, 300, 2560, 1600, press_duration=0.05)


class TestBlindRunnerKeyTab:
    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_key_tab(self, mock_sleep):
        """key=tab calls hid.send_key() with HID tab code 0x2B."""
        runner, hid, _ = _make_runner([
            {"action": "key", "key": "tab", "delay": 0.5},
        ])
        runner.run()
        hid.send_key.assert_called_once_with(1, 0x2B)


class TestBlindRunnerUSBError:
    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_usb_error_triggers_reconnect(self, mock_sleep):
        """USBError during step triggers _reconnect_aoa and continues (returns True)."""
        runner, hid, adb = _make_runner([
            {"action": "wake", "delay": 0.5},
        ])
        hid.wake_screen.side_effect = usb.core.USBError("device disconnected")
        runner._reconnect_aoa = MagicMock(return_value=True)

        result = runner.run()

        assert result is True
        runner._reconnect_aoa.assert_called_once()

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_usb_error_reconnect_fails(self, mock_sleep):
        """USBError + reconnect failure -> run returns False."""
        runner, hid, adb = _make_runner([
            {"action": "wake", "delay": 0.5},
        ])
        hid.wake_screen.side_effect = usb.core.USBError("device disconnected")
        runner._reconnect_aoa = MagicMock(return_value=False)

        result = runner.run()

        assert result is False
        runner._reconnect_aoa.assert_called_once()

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_reconnect_aoa_delegates_to_wait_for_adb(self, mock_sleep):
        """_reconnect_aoa calls _wait_for_adb(timeout=30)."""
        runner, hid, adb = _make_runner([
            {"action": "wake"},
        ])
        runner._wait_for_adb = MagicMock(return_value=True)

        result = runner._reconnect_aoa()

        assert result is True
        runner._wait_for_adb.assert_called_once_with(timeout=30)


class TestBlindRunnerAdbFallback:
    @patch("smoke_test_ai.drivers.aoa_hid.AoaHidDriver")
    @patch("smoke_test_ai.runners.blind_runner.usb.core.find")
    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_wait_for_adb_adb_fallback(self, mock_sleep, mock_usb_find, MockHid):
        """USB scan finds nothing, ADB fallback detects device, returns True."""
        runner, hid, adb = _make_runner([
            {"action": "wait_for_adb", "timeout": 10},
        ])
        new_hid = MagicMock()
        MockHid.return_value = new_hid

        # USB scan returns no matching devices
        mock_usb_find.return_value = []
        # ADB fallback detects the device
        adb.is_connected.return_value = True

        result = runner.run()

        assert result is True
        adb.is_connected.assert_called_with(allow_unauthorized=True)

    @patch("smoke_test_ai.drivers.aoa_hid.AoaHidDriver")
    @patch("smoke_test_ai.runners.blind_runner.usb.util.dispose_resources")
    @patch("smoke_test_ai.runners.blind_runner.usb.core.find")
    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_wait_for_adb_dispose_resources_called(
        self, mock_sleep, mock_usb_find, mock_dispose, MockHid
    ):
        """usb.util.dispose_resources is called during AOA re-init."""
        runner, hid, adb = _make_runner([
            {"action": "wait_for_adb", "timeout": 10},
        ])
        new_hid = MagicMock()
        MockHid.return_value = new_hid

        fake_dev = MagicMock()
        fake_dev.idVendor = 0x099E
        fake_dev.idProduct = 0x02B1
        mock_usb_find.return_value = [fake_dev]

        result = runner.run()

        assert result is True
        mock_dispose.assert_called()

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_tap_custom_press_duration(self, mock_sleep):
        """YAML step with press_duration: 0.2 forwards correctly to hid.tap()."""
        runner, hid, _ = _make_runner([
            {"action": "tap", "x": 500, "y": 300, "press_duration": 0.2, "delay": 0.5},
        ])
        runner.run()
        hid.tap.assert_called_once_with(
            2, 500, 300, 2560, 1600, press_duration=0.2,
        )

    @patch("smoke_test_ai.runners.blind_runner.usb.core.find")
    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    @patch("smoke_test_ai.runners.blind_runner.time.time")
    def test_wait_for_adb_both_fail(self, mock_time, mock_sleep, mock_usb_find):
        """Both USB scan and ADB fallback fail -> timeout returns False."""
        runner, hid, adb = _make_runner([
            {"action": "wait_for_adb", "timeout": 5},
        ])
        # Simulate time passing beyond timeout
        mock_time.side_effect = [0, 0, 1, 2, 3, 4, 5, 6]
        mock_usb_find.return_value = []
        adb.is_connected.return_value = False

        result = runner.run()

        assert result is False
        adb.is_connected.assert_called_with(allow_unauthorized=True)


class TestStepRecorderOutput:
    def test_save_generates_valid_yaml(self, tmp_path):
        """StepRecorder._save() outputs valid YAML with correct structure."""
        from smoke_test_ai.runners.recorder import StepRecorder

        output = tmp_path / "test_flow.yaml"
        rec = StepRecorder(serial=None, device_name="Test-Device", output_path=output)
        rec.steps = [
            {"action": "wake", "delay": 1.0},
            {"action": "tap", "x": 500, "y": 300, "delay": 2.0, "description": "Tap start"},
        ]
        rec._save(screen_w=1080, screen_h=2400)

        import yaml
        loaded = yaml.safe_load(output.read_text())
        assert loaded["device"] == "Test-Device"
        assert loaded["screen_resolution"] == [1080, 2400]
        assert len(loaded["steps"]) == 2
        assert loaded["steps"][0]["action"] == "wake"
        assert loaded["steps"][1]["x"] == 500

    def test_save_empty_steps_skips(self, tmp_path):
        """StepRecorder._save() with no steps does not create file."""
        from smoke_test_ai.runners.recorder import StepRecorder

        output = tmp_path / "test_flow.yaml"
        rec = StepRecorder(serial=None, device_name="Test-Device", output_path=output)
        rec.steps = []
        rec._save(screen_w=1080, screen_h=2400)

        assert not output.exists()


class TestStepRecorderActions:
    @patch("smoke_test_ai.runners.recorder.subprocess.run")
    def test_adb_tap_sends_correct_command(self, mock_run):
        """_adb_tap(500, 300) with serial='ABC123' sends correct adb command."""
        from smoke_test_ai.runners.recorder import StepRecorder
        from pathlib import Path

        rec = StepRecorder(serial="ABC123", device_name="Dev", output_path=Path("/tmp/t.yaml"))
        rec._adb_tap(500, 300)

        mock_run.assert_called_once_with(
            ["adb", "-s", "ABC123", "shell", "input", "tap", "500", "300"],
            capture_output=True, timeout=5,
        )

    @patch("smoke_test_ai.runners.recorder.subprocess.run")
    def test_adb_tap_no_serial(self, mock_run):
        """_adb_tap(100, 200) without serial omits -s flag."""
        from smoke_test_ai.runners.recorder import StepRecorder
        from pathlib import Path

        rec = StepRecorder(serial=None, device_name="Dev", output_path=Path("/tmp/t.yaml"))
        rec._adb_tap(100, 200)

        mock_run.assert_called_once_with(
            ["adb", "shell", "input", "tap", "100", "200"],
            capture_output=True, timeout=5,
        )

    @patch("smoke_test_ai.runners.recorder.subprocess.run")
    def test_adb_swipe_sends_correct_command(self, mock_run):
        """_adb_swipe(100, 200, 300, 400, 500) sends correct adb command."""
        from smoke_test_ai.runners.recorder import StepRecorder
        from pathlib import Path

        rec = StepRecorder(serial="ABC123", device_name="Dev", output_path=Path("/tmp/t.yaml"))
        rec._adb_swipe(100, 200, 300, 400, 500)

        mock_run.assert_called_once_with(
            ["adb", "-s", "ABC123", "shell", "input", "swipe", "100", "200", "300", "400", "500"],
            capture_output=True, timeout=5,
        )

    def test_mouse_callback_tap_detection(self):
        """Mouse down at (100,200) then up at (105,205) → tap (within 20px threshold)."""
        import cv2
        from smoke_test_ai.runners.recorder import StepRecorder
        from pathlib import Path

        rec = StepRecorder(serial=None, device_name="Dev", output_path=Path("/tmp/t.yaml"))
        rec._mouse_callback(cv2.EVENT_LBUTTONDOWN, 100, 200, 0, None)
        rec._mouse_callback(cv2.EVENT_LBUTTONUP, 105, 205, 0, None)

        assert rec._pending_tap == (105, 205)
        assert rec._pending_swipe is None

    def test_mouse_callback_swipe_detection(self):
        """Mouse down at (100,200) then up at (100,300) → swipe (beyond 20px threshold)."""
        import cv2
        from smoke_test_ai.runners.recorder import StepRecorder
        from pathlib import Path

        rec = StepRecorder(serial=None, device_name="Dev", output_path=Path("/tmp/t.yaml"))
        rec._mouse_callback(cv2.EVENT_LBUTTONDOWN, 100, 200, 0, None)
        rec._mouse_callback(cv2.EVENT_LBUTTONUP, 100, 300, 0, None)

        assert rec._pending_swipe == (100, 200, 100, 300)
        assert rec._pending_tap is None
