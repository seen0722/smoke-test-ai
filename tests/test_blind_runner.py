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


class TestBlindRunnerWaitForAdb:
    @patch("smoke_test_ai.drivers.aoa_hid.AoaHidDriver")
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

    @patch("smoke_test_ai.drivers.aoa_hid.AoaHidDriver")
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

        old_hid.tap.assert_not_called()
        new_hid.tap.assert_called_once_with(2, 500, 300, 2560, 1600)


class TestBlindRunnerKeyTab:
    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_key_tab(self, mock_sleep):
        """key=tab calls hid.send_key() with HID tab code 0x2B."""
        runner, hid, _ = _make_runner([
            {"action": "key", "key": "tab", "delay": 0.5},
        ])
        runner.run()
        hid.send_key.assert_called_once_with(1, 0x2B)
