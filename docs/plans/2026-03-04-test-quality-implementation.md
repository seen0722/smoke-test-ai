# Test Quality Improvement — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add ~35 new tests covering BlindRunner new features, Plugin execute() paths, Orchestrator.run(), SetupWizardAgent, and Recorder, plus coverage infrastructure with a 70% threshold.

**Architecture:** Layer-by-layer approach — coverage infra first, then tests ordered by dependency depth (drivers → plugins → orchestrator → agents). Each task is independently committable.

**Tech Stack:** pytest, pytest-cov, unittest.mock

---

## Task 1: Add pytest-cov to dev dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add pytest-cov dependency and coverage config**

In `pyproject.toml`, add `"pytest-cov>=4.0"` to dev dependencies and add coverage config sections:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-mock>=3.10",
    "pytest-cov>=4.0",
]

[tool.coverage.run]
source = ["smoke_test_ai"]
omit = ["*/tests/*"]

[tool.coverage.report]
show_missing = true
```

**Step 2: Install the new dependency**

Run: `pip install -e ".[dev]"`

**Step 3: Verify coverage works**

Run: `pytest tests/ --cov --cov-report=term-missing -q 2>&1 | tail -30`
Expected: Coverage report with percentage per module, all existing tests pass.

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add pytest-cov and coverage config"
```

---

## Task 2: BlindRunner — USBError reconnect tests

**Files:**
- Modify: `tests/test_blind_runner.py`

**Step 1: Write the failing tests**

Add a new class `TestBlindRunnerUSBError` after `TestBlindRunnerWaitForAdb`:

```python
class TestBlindRunnerUSBError:
    """Tests for USBError auto-reconnect in _execute_step."""

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_usb_error_triggers_reconnect(self, mock_sleep):
        """USBError during step triggers _reconnect_aoa and continues."""
        runner, hid, _ = _make_runner([
            {"action": "tap", "x": 100, "y": 200, "delay": 0.5},
        ])
        hid.tap.side_effect = usb.core.USBError("Device disconnected")
        with patch.object(runner, "_reconnect_aoa", return_value=True) as mock_reconnect:
            result = runner.run()
        assert result is True
        mock_reconnect.assert_called_once()

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_usb_error_reconnect_fails(self, mock_sleep):
        """USBError + reconnect failure → run returns False."""
        runner, hid, _ = _make_runner([
            {"action": "tap", "x": 100, "y": 200, "delay": 0.5},
        ])
        hid.tap.side_effect = usb.core.USBError("Device disconnected")
        with patch.object(runner, "_reconnect_aoa", return_value=False):
            result = runner.run()
        assert result is False

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_reconnect_aoa_delegates_to_wait_for_adb(self, mock_sleep):
        """_reconnect_aoa calls _wait_for_adb(timeout=30)."""
        runner, hid, _ = _make_runner([])
        with patch.object(runner, "_wait_for_adb", return_value=True) as mock_wait:
            result = runner._reconnect_aoa()
        assert result is True
        mock_wait.assert_called_once_with(timeout=30)
```

Also add `import usb.core` at the top of the test file.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_blind_runner.py::TestBlindRunnerUSBError -v`
Expected: FAIL (tests should fail because... actually they should pass since we're testing existing code with mocks)

Run: `pytest tests/test_blind_runner.py::TestBlindRunnerUSBError -v`
Expected: 3 passed

**Step 3: Commit**

```bash
git add tests/test_blind_runner.py
git commit -m "test: add BlindRunner USBError reconnect tests"
```

---

## Task 3: BlindRunner — ADB fallback and press_duration tests

**Files:**
- Modify: `tests/test_blind_runner.py`

**Step 1: Write the tests**

Add a new class `TestBlindRunnerAdbFallback`:

```python
class TestBlindRunnerAdbFallback:
    """Tests for ADB fallback detection and press_duration forwarding."""

    @patch("smoke_test_ai.drivers.aoa_hid.AoaHidDriver")
    @patch("smoke_test_ai.runners.blind_runner.usb.core.find")
    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_wait_for_adb_adb_fallback(self, mock_sleep, mock_usb_find, MockHid):
        """When USB scan finds nothing, ADB fallback detects device."""
        runner, hid, adb = _make_runner([
            {"action": "wait_for_adb", "timeout": 10},
        ])
        new_hid = MagicMock()
        MockHid.return_value = new_hid
        # USB scan returns empty — no device found via PyUSB
        mock_usb_find.return_value = []
        # ADB fallback succeeds
        adb.is_connected.return_value = True

        result = runner.run()

        assert result is True
        adb.is_connected.assert_called_with(allow_unauthorized=True)
        new_hid.find_device.assert_called_once()

    @patch("smoke_test_ai.drivers.aoa_hid.AoaHidDriver")
    @patch("smoke_test_ai.runners.blind_runner.usb.core.find")
    @patch("smoke_test_ai.runners.blind_runner.usb.util.dispose_resources")
    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_wait_for_adb_dispose_resources_called(self, mock_sleep, mock_dispose, mock_usb_find, MockHid):
        """dispose_resources is called during AOA re-init to clear libusb cache."""
        runner, hid, adb = _make_runner([
            {"action": "wait_for_adb", "timeout": 10},
        ])
        new_hid = MagicMock()
        MockHid.return_value = new_hid
        fake_dev = MagicMock()
        fake_dev.idVendor = 0x099E
        fake_dev.idProduct = 0x02B1
        mock_usb_find.return_value = [fake_dev]

        runner.run()

        mock_dispose.assert_called()

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_tap_custom_press_duration(self, mock_sleep):
        """YAML press_duration value is forwarded to hid.tap()."""
        runner, hid, _ = _make_runner([
            {"action": "tap", "x": 300, "y": 400, "delay": 0.5, "press_duration": 0.2},
        ])
        runner.run()
        hid.tap.assert_called_once_with(2, 300, 400, 2560, 1600, press_duration=0.2)
```

**Step 2: Run tests**

Run: `pytest tests/test_blind_runner.py::TestBlindRunnerAdbFallback -v`
Expected: All pass. Note: `dispose_resources` test may need adjustment — the code calls `usb.util.dispose_resources` inside `_wait_for_adb` in a loop over `usb.core.find()` results, so we need to ensure the mock path is correct.

**Step 3: Commit**

```bash
git add tests/test_blind_runner.py
git commit -m "test: add BlindRunner ADB fallback and press_duration tests"
```

---

## Task 4: BlindRunner — wait_for_adb both-fail test

**Files:**
- Modify: `tests/test_blind_runner.py`

**Step 1: Write the test**

Add to `TestBlindRunnerAdbFallback`:

```python
    @patch("smoke_test_ai.runners.blind_runner.usb.core.find")
    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    @patch("smoke_test_ai.runners.blind_runner.time.time")
    def test_wait_for_adb_both_fail(self, mock_time, mock_sleep, mock_usb_find):
        """Both USB scan and ADB fallback fail → returns False."""
        runner, hid, adb = _make_runner([
            {"action": "wait_for_adb", "timeout": 5},
        ])
        mock_time.side_effect = [0, 0, 1, 2, 3, 4, 5, 6]
        mock_usb_find.return_value = []
        adb.is_connected.return_value = False

        result = runner.run()

        assert result is False
        adb.is_connected.assert_called_with(allow_unauthorized=True)
```

**Step 2: Run test**

Run: `pytest tests/test_blind_runner.py::TestBlindRunnerAdbFallback::test_wait_for_adb_both_fail -v`
Expected: PASS

**Step 3: Run all BlindRunner tests**

Run: `pytest tests/test_blind_runner.py -v`
Expected: All pass (existing + new)

**Step 4: Commit**

```bash
git add tests/test_blind_runner.py
git commit -m "test: add BlindRunner wait_for_adb both-fail test"
```

---

## Task 5: Plugin execute() dispatch tests — Camera & Telephony

**Files:**
- Modify: `tests/test_plugins.py`

**Step 1: Write the tests**

The Camera plugin already has `test_unknown_action_errors` and `test_capture_photo_pass` which test the `execute()` entry point. So Camera is already covered.

For Telephony, add to `TestTelephonyPlugin`:

```python
    def test_execute_dispatches_send_sms(self, plugin_context):
        """execute() routes action='send_sms' to _send_sms."""
        plugin = TelephonyPlugin()
        plugin_context.snippet = MagicMock()
        plugin_context.snippet.smsSendTextMessage.return_value = None
        tc = {
            "id": "tel1", "name": "SMS", "type": "telephony",
            "action": "send_sms",
            "params": {"to": "+886900000000", "message": "test"},
        }
        with patch("smoke_test_ai.plugins.telephony.time.sleep"):
            result = plugin.execute(tc, plugin_context)
        assert result.status in (TestStatus.PASS, TestStatus.FAIL)

    def test_execute_unknown_action_errors(self, plugin_context):
        """execute() with unknown action returns ERROR."""
        plugin = TelephonyPlugin()
        tc = {
            "id": "tel1", "name": "Unknown", "type": "telephony",
            "action": "nonexistent",
        }
        result = plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.ERROR
        assert "Unknown" in result.message
```

**Step 2: Run tests**

Run: `pytest tests/test_plugins.py::TestTelephonyPlugin::test_execute_dispatches_send_sms tests/test_plugins.py::TestTelephonyPlugin::test_execute_unknown_action_errors -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_plugins.py
git commit -m "test: add Telephony execute() dispatch tests"
```

---

## Task 6: Plugin execute() dispatch tests — Wifi & Bluetooth

**Files:**
- Modify: `tests/test_plugins.py`

**Step 1: Write the tests**

Add to `TestWifiPlugin`:

```python
    def test_execute_dispatches_scan(self, plugin_context):
        """execute() routes action='scan' correctly."""
        plugin = WifiPlugin()
        plugin_context.snippet = MagicMock()
        plugin_context.snippet.wifiScannerGetScanResults.return_value = []
        tc = {
            "id": "w1", "name": "WiFi Scan", "type": "wifi",
            "action": "scan", "params": {},
        }
        result = plugin.execute(tc, plugin_context)
        assert result.status in (TestStatus.PASS, TestStatus.SKIP)

    def test_execute_unknown_action_errors(self, plugin_context):
        """execute() with unknown action returns ERROR."""
        plugin = WifiPlugin()
        tc = {"id": "w1", "name": "Unknown", "type": "wifi", "action": "nonexistent"}
        result = plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.ERROR
```

Add to `TestBluetoothPlugin`:

```python
    def test_execute_dispatches_ble_scan(self, plugin_context):
        """execute() routes action='ble_scan' correctly."""
        plugin = BluetoothPlugin()
        plugin_context.snippet = MagicMock()
        plugin_context.snippet.bleStartScan.return_value = None
        plugin_context.snippet.bleGetScanResults.return_value = [{"name": "device1"}]
        plugin_context.snippet.bleStopScan.return_value = None
        tc = {
            "id": "bt1", "name": "BLE Scan", "type": "bluetooth",
            "action": "ble_scan", "params": {},
        }
        with patch("smoke_test_ai.plugins.bluetooth.time.sleep"):
            result = plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.PASS

    def test_execute_unknown_action_errors(self, plugin_context):
        """execute() with unknown action returns ERROR."""
        plugin = BluetoothPlugin()
        tc = {"id": "bt1", "name": "Unknown", "type": "bluetooth", "action": "nonexistent"}
        result = plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.ERROR
```

**Step 2: Run tests**

Run: `pytest tests/test_plugins.py::TestWifiPlugin::test_execute_dispatches_scan tests/test_plugins.py::TestWifiPlugin::test_execute_unknown_action_errors tests/test_plugins.py::TestBluetoothPlugin::test_execute_dispatches_ble_scan tests/test_plugins.py::TestBluetoothPlugin::test_execute_unknown_action_errors -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_plugins.py
git commit -m "test: add WiFi and Bluetooth execute() dispatch tests"
```

---

## Task 7: Plugin execute() dispatch tests — Audio & Network

**Files:**
- Modify: `tests/test_plugins.py`

**Step 1: Write the tests**

Add to `TestAudioPlugin`:

```python
    def test_execute_dispatches_play_and_check(self, plugin_context):
        """execute() routes action='play_and_check' correctly."""
        plugin = AudioPlugin()
        plugin_context.snippet = MagicMock()
        plugin_context.snippet.mediaIsPlaying.return_value = True
        tc = {
            "id": "a1", "name": "Audio Play", "type": "audio",
            "action": "play_and_check", "params": {},
        }
        plugin_context.adb.shell.return_value = MagicMock(stdout="", returncode=0)
        with patch("smoke_test_ai.plugins.audio.time.sleep"):
            result = plugin.execute(tc, plugin_context)
        assert result.status in (TestStatus.PASS, TestStatus.FAIL, TestStatus.SKIP)

    def test_execute_unknown_action_errors(self, plugin_context):
        """execute() with unknown action returns ERROR."""
        plugin = AudioPlugin()
        tc = {"id": "a1", "name": "Unknown", "type": "audio", "action": "nonexistent"}
        result = plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.ERROR
```

Add to `TestNetworkPlugin`:

```python
    def test_execute_dispatches_http_download(self, plugin_context):
        """execute() routes action='http_download' correctly."""
        plugin = NetworkPlugin()
        plugin_context.snippet = MagicMock()
        plugin_context.snippet.wifiGetConnectionInfo.return_value = {}
        plugin_context.adb.shell.return_value = MagicMock(
            stdout="HTTP/1.1 204 No Content\n\n", returncode=0
        )
        tc = {
            "id": "n1", "name": "HTTP", "type": "network",
            "action": "http_download",
            "params": {"url": "https://www.google.com/generate_204"},
        }
        with patch("smoke_test_ai.plugins.network.time.sleep"):
            result = plugin.execute(tc, plugin_context)
        assert result.status in (TestStatus.PASS, TestStatus.FAIL)

    def test_execute_unknown_action_errors(self, plugin_context):
        """execute() with unknown action returns ERROR."""
        plugin = NetworkPlugin()
        tc = {"id": "n1", "name": "Unknown", "type": "network", "action": "nonexistent"}
        result = plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.ERROR
```

**Step 2: Run tests**

Run: `pytest tests/test_plugins.py::TestAudioPlugin::test_execute_dispatches_play_and_check tests/test_plugins.py::TestAudioPlugin::test_execute_unknown_action_errors tests/test_plugins.py::TestNetworkPlugin::test_execute_dispatches_http_download tests/test_plugins.py::TestNetworkPlugin::test_execute_unknown_action_errors -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_plugins.py
git commit -m "test: add Audio and Network execute() dispatch tests"
```

---

## Task 8: Orchestrator.run() — skip_flash and report generation tests

**Files:**
- Modify: `tests/test_orchestrator.py`

**Step 1: Write the tests**

Add a new class `TestOrchestratorRun`:

```python
class TestOrchestratorRun:
    """Tests for Orchestrator.run() pipeline stages."""

    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_run_skips_flash_when_no_build_dir(self, MockAdb, settings, device_config):
        """run() without build_dir skips Stage 0 entirely."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        adb = MockAdb.return_value
        adb.wait_for_device.return_value = True
        adb.get_user_state.return_value = "RUNNING_UNLOCKED"
        adb.is_wifi_connected.return_value = True
        adb.shell.return_value = _make_shell_result("")
        adb.get_device_info.return_value = {}

        with patch.object(orch, "_get_flash_driver") as mock_flash, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            orch.run(serial="FAKE", skip_setup=True)
        mock_flash.assert_not_called()

    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_run_calls_flash_with_build_dir(self, MockAdb, settings, device_config):
        """run() with build_dir triggers Stage 0 flash."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        adb = MockAdb.return_value
        adb.wait_for_device.return_value = True
        adb.get_user_state.return_value = "RUNNING_UNLOCKED"
        adb.is_wifi_connected.return_value = True
        adb.shell.return_value = _make_shell_result("")
        adb.get_device_info.return_value = {}

        mock_driver = MagicMock()
        with patch.object(orch, "_get_flash_driver", return_value=mock_driver) as mock_gfd, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"), \
             patch("smoke_test_ai.core.orchestrator.time.sleep"):
            orch.run(serial="FAKE", build_dir="/tmp/build", skip_setup=True)
        mock_gfd.assert_called_once()
        mock_driver.flash.assert_called_once()

    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_run_generates_reports(self, MockAdb, settings, device_config):
        """run() calls _generate_reports at the end."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        adb = MockAdb.return_value
        adb.wait_for_device.return_value = True
        adb.get_user_state.return_value = "RUNNING_UNLOCKED"
        adb.is_wifi_connected.return_value = True
        adb.shell.return_value = _make_shell_result("")
        adb.get_device_info.return_value = {"model": "Test"}

        with patch.object(orch, "_generate_reports") as mock_report, \
             patch.object(orch, "_pre_test_setup"):
            orch.run(serial="FAKE", skip_setup=True)
        mock_report.assert_called_once()

    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_run_returns_empty_when_adb_timeout(self, MockAdb, settings, device_config):
        """run() returns [] when ADB device not found."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        adb = MockAdb.return_value
        adb.wait_for_device.return_value = False

        result = orch.run(serial="FAKE", skip_setup=True)
        assert result == []
```

**Step 2: Run tests**

Run: `pytest tests/test_orchestrator.py::TestOrchestratorRun -v`
Expected: All pass

**Step 3: Commit**

```bash
git add tests/test_orchestrator.py
git commit -m "test: add Orchestrator.run() pipeline tests"
```

---

## Task 9: Orchestrator.run() — blind setup and WiFi tests

**Files:**
- Modify: `tests/test_orchestrator.py`

**Step 1: Write the tests**

Add to `TestOrchestratorRun`:

```python
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_run_blind_setup_when_user_build(self, MockAdb, settings, device_config, tmp_path):
        """run() triggers BlindRunner for user build with AOA config."""
        device_config["device"]["aoa"] = {
            "enabled": True,
            "vendor_id": 0x099E, "product_id": 0x02B1,
            "rotation": 90,
            "keyboard_hid_id": 1, "touch_hid_id": 2, "consumer_hid_id": 3,
        }
        orch = Orchestrator(settings=settings, device_config=device_config)
        adb = MockAdb.return_value
        adb.wait_for_device.return_value = True
        adb.get_user_state.return_value = "RUNNING_UNLOCKED"
        adb.is_wifi_connected.return_value = True
        adb.shell.return_value = _make_shell_result("")
        adb.get_device_info.return_value = {}

        # Create a minimal flow YAML
        flow_dir = tmp_path / "setup_flows"
        flow_dir.mkdir()
        flow_file = flow_dir / "product_a.yaml"
        flow_file.write_text("device: Product-A\nscreen_resolution: [1080, 2400]\nsteps:\n- action: wake\n  delay: 1.0\n")

        mock_hid = MagicMock()
        with patch.object(orch, "_init_aoa_hid", return_value=mock_hid) as mock_init_aoa, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            orch.run(serial="FAKE", config_dir=str(tmp_path))
        mock_init_aoa.assert_called_once()
        mock_hid.close.assert_called_once()

    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_run_unlocks_fbe_when_locked(self, MockAdb, settings, device_config):
        """run() calls unlock_keyguard when user storage is locked."""
        device_config["device"]["lock_pin"] = "0000"
        orch = Orchestrator(settings=settings, device_config=device_config)
        adb = MockAdb.return_value
        adb.wait_for_device.return_value = True
        adb.get_user_state.return_value = "RUNNING_LOCKED"
        adb.unlock_keyguard.return_value = True
        adb.is_wifi_connected.return_value = True
        adb.shell.return_value = _make_shell_result("")
        adb.get_device_info.return_value = {}

        with patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            orch.run(serial="FAKE", skip_flash=True)
        adb.unlock_keyguard.assert_called_once_with(pin="0000")
```

**Step 2: Run tests**

Run: `pytest tests/test_orchestrator.py::TestOrchestratorRun -v`
Expected: All pass

**Step 3: Commit**

```bash
git add tests/test_orchestrator.py
git commit -m "test: add Orchestrator blind setup and FBE unlock tests"
```

---

## Task 10: SetupWizardAgent tests

**Files:**
- Create: `tests/test_setup_wizard.py`

**Step 1: Write the tests**

```python
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from smoke_test_ai.ai.setup_wizard_agent import SetupWizardAgent


def _make_agent(max_steps=30, timeout=300):
    """Helper: build SetupWizardAgent with all-mock dependencies."""
    hid = MagicMock()
    screen_capture = MagicMock()
    analyzer = MagicMock()
    adb = MagicMock()
    agent = SetupWizardAgent(
        hid=hid,
        screen_capture=screen_capture,
        analyzer=analyzer,
        adb=adb,
        screen_w=1080,
        screen_h=2400,
        hid_id=2,
        keyboard_hid_id=1,
        max_steps=max_steps,
        timeout=timeout,
    )
    return agent, hid, screen_capture, analyzer, adb


class TestSetupWizardAgent:
    @patch("smoke_test_ai.ai.setup_wizard_agent.time.sleep")
    @patch("smoke_test_ai.ai.setup_wizard_agent.time.time")
    def test_run_completes_when_adb_boot_done(self, mock_time, mock_sleep):
        """run() returns True when ADB reports boot_completed=1."""
        agent, hid, sc, analyzer, adb = _make_agent(max_steps=5)
        mock_time.side_effect = [0, 1, 2, 3, 4, 5]  # well within timeout
        adb.is_connected.return_value = True
        adb.getprop.return_value = "1"  # sys.boot_completed

        result = agent.run()

        assert result is True
        # Screen capture and analyzer never called because ADB check passes first
        sc.capture.assert_not_called()

    @patch("smoke_test_ai.ai.setup_wizard_agent.time.sleep")
    @patch("smoke_test_ai.ai.setup_wizard_agent.time.time")
    def test_run_executes_tap_action(self, mock_time, mock_sleep):
        """run() calls hid.tap when LLM suggests tap action."""
        agent, hid, sc, analyzer, adb = _make_agent(max_steps=2)
        mock_time.side_effect = [0, 1, 2, 3, 4]
        adb.is_connected.return_value = False

        bright_image = np.ones((100, 100, 3), dtype=np.uint8) * 128
        sc.capture.return_value = bright_image

        # First call: LLM says tap, second call: completed
        analyzer.analyze_setup_wizard.side_effect = [
            {
                "screen_state": "setup_wizard",
                "confidence": 0.9,
                "completed": False,
                "action": {"type": "tap", "x": 540, "y": 1200},
            },
            {
                "screen_state": "home_screen",
                "confidence": 0.95,
                "completed": True,
                "action": {},
            },
        ]

        result = agent.run()

        assert result is True
        hid.tap.assert_called_once_with(2, 540, 1200, 1080, 2400)

    @patch("smoke_test_ai.ai.setup_wizard_agent.time.sleep")
    @patch("smoke_test_ai.ai.setup_wizard_agent.time.time")
    def test_run_max_steps_exceeded(self, mock_time, mock_sleep):
        """run() returns False when max_steps reached without completion."""
        agent, hid, sc, analyzer, adb = _make_agent(max_steps=2)
        mock_time.side_effect = [0] + list(range(20))  # never timeout
        adb.is_connected.return_value = False

        bright_image = np.ones((100, 100, 3), dtype=np.uint8) * 128
        sc.capture.return_value = bright_image
        analyzer.analyze_setup_wizard.return_value = {
            "screen_state": "setup_wizard",
            "confidence": 0.8,
            "completed": False,
            "action": {"type": "wait"},
        }

        result = agent.run()

        assert result is False

    @patch("smoke_test_ai.ai.setup_wizard_agent.time.sleep")
    @patch("smoke_test_ai.ai.setup_wizard_agent.time.time")
    def test_run_screenshot_failure_continues(self, mock_time, mock_sleep):
        """run() continues when screen capture returns None."""
        agent, hid, sc, analyzer, adb = _make_agent(max_steps=3)
        mock_time.side_effect = [0] + list(range(20))
        adb.is_connected.return_value = False

        # First capture fails, second succeeds with completed
        bright_image = np.ones((100, 100, 3), dtype=np.uint8) * 128
        sc.capture.side_effect = [None, bright_image, bright_image]
        analyzer.analyze_setup_wizard.return_value = {
            "screen_state": "home",
            "confidence": 0.9,
            "completed": True,
            "action": {},
        }

        result = agent.run()

        assert result is True
        # Analyzer only called for non-None captures
        assert analyzer.analyze_setup_wizard.call_count >= 1

    @patch("smoke_test_ai.ai.setup_wizard_agent.time.sleep")
    @patch("smoke_test_ai.ai.setup_wizard_agent.time.time")
    def test_run_swipe_action(self, mock_time, mock_sleep):
        """run() calls hid.swipe when LLM suggests swipe action."""
        agent, hid, sc, analyzer, adb = _make_agent(max_steps=2)
        mock_time.side_effect = [0, 1, 2, 3, 4]
        adb.is_connected.return_value = False

        bright_image = np.ones((100, 100, 3), dtype=np.uint8) * 128
        sc.capture.return_value = bright_image
        analyzer.analyze_setup_wizard.side_effect = [
            {
                "screen_state": "setup_wizard",
                "confidence": 0.9,
                "completed": False,
                "action": {"type": "swipe", "direction": "up"},
            },
            {
                "screen_state": "home",
                "confidence": 0.9,
                "completed": True,
                "action": {},
            },
        ]

        result = agent.run()

        assert result is True
        hid.swipe.assert_called_once()
        # Verify swipe is "up" direction: y1 > y2
        call_args = hid.swipe.call_args[0]
        assert call_args[2] > call_args[4]  # y1 > y2 for upward swipe
```

**Step 2: Run tests**

Run: `pytest tests/test_setup_wizard.py -v`
Expected: 5 passed

**Step 3: Commit**

```bash
git add tests/test_setup_wizard.py
git commit -m "test: add SetupWizardAgent unit tests"
```

---

## Task 11: Recorder tests

**Files:**
- Modify: `tests/test_blind_runner.py` (StepRecorder tests are already here)

**Step 1: Write the tests**

Add a new class `TestStepRecorderActions` after `TestStepRecorderOutput`:

```python
class TestStepRecorderActions:
    """Tests for StepRecorder helper methods."""

    def test_adb_tap_sends_correct_command(self):
        """_adb_tap calls subprocess with correct adb input tap args."""
        from smoke_test_ai.runners.recorder import StepRecorder
        rec = StepRecorder(serial="ABC123", device_name="Test", output_path=Path("/tmp/test.yaml"))
        with patch("smoke_test_ai.runners.recorder.subprocess.run") as mock_run:
            rec._adb_tap(500, 300)
        mock_run.assert_called_once_with(
            ["adb", "-s", "ABC123", "shell", "input", "tap", "500", "300"],
            capture_output=True, timeout=5,
        )

    def test_adb_tap_no_serial(self):
        """_adb_tap without serial omits -s flag."""
        from smoke_test_ai.runners.recorder import StepRecorder
        rec = StepRecorder(serial=None, device_name="Test", output_path=Path("/tmp/test.yaml"))
        with patch("smoke_test_ai.runners.recorder.subprocess.run") as mock_run:
            rec._adb_tap(100, 200)
        mock_run.assert_called_once_with(
            ["adb", "shell", "input", "tap", "100", "200"],
            capture_output=True, timeout=5,
        )

    def test_adb_swipe_sends_correct_command(self):
        """_adb_swipe calls subprocess with correct swipe args."""
        from smoke_test_ai.runners.recorder import StepRecorder
        rec = StepRecorder(serial=None, device_name="Test", output_path=Path("/tmp/test.yaml"))
        with patch("smoke_test_ai.runners.recorder.subprocess.run") as mock_run:
            rec._adb_swipe(100, 200, 300, 400, 500)
        mock_run.assert_called_once_with(
            ["adb", "shell", "input", "swipe", "100", "200", "300", "400", "500"],
            capture_output=True, timeout=5,
        )

    def test_mouse_callback_tap_detection(self):
        """Mouse down+up within 20px threshold registers as tap."""
        from smoke_test_ai.runners.recorder import StepRecorder
        import cv2
        rec = StepRecorder(serial=None, device_name="Test", output_path=Path("/tmp/test.yaml"))
        # Simulate mouse down
        rec._mouse_callback(cv2.EVENT_LBUTTONDOWN, 100, 200, 0, None)
        assert rec._mouse_down == (100, 200)
        # Simulate mouse up at same position
        rec._mouse_callback(cv2.EVENT_LBUTTONUP, 105, 205, 0, None)
        assert rec._pending_tap == (105, 205)
        assert rec._pending_swipe is None

    def test_mouse_callback_swipe_detection(self):
        """Mouse down+up beyond 20px threshold registers as swipe."""
        from smoke_test_ai.runners.recorder import StepRecorder
        import cv2
        rec = StepRecorder(serial=None, device_name="Test", output_path=Path("/tmp/test.yaml"))
        rec._mouse_callback(cv2.EVENT_LBUTTONDOWN, 100, 200, 0, None)
        rec._mouse_callback(cv2.EVENT_LBUTTONUP, 100, 300, 0, None)
        assert rec._pending_swipe == (100, 200, 100, 300)
        assert rec._pending_tap is None
```

Add `from pathlib import Path` at the top if not already present.

**Step 2: Run tests**

Run: `pytest tests/test_blind_runner.py::TestStepRecorderActions -v`
Expected: 5 passed

**Step 3: Run all tests**

Run: `pytest tests/ -v --tb=short`
Expected: All pass

**Step 4: Commit**

```bash
git add tests/test_blind_runner.py
git commit -m "test: add StepRecorder action and mouse callback tests"
```

---

## Task 12: Set coverage threshold and verify

**Files:**
- Modify: `pyproject.toml`

**Step 1: Run coverage to check current percentage**

Run: `pytest tests/ --cov --cov-report=term-missing -q 2>&1 | tail -30`
Expected: Coverage report. Note the total percentage.

**Step 2: Set fail_under threshold**

If total coverage ≥ 70%, add to `pyproject.toml`:

```toml
[tool.coverage.report]
show_missing = true
fail_under = 70
```

If total coverage is between 60-70%, set `fail_under` to 5% below current value (to account for new code additions).

**Step 3: Verify threshold works**

Run: `pytest tests/ --cov --cov-fail-under=70 -q`
Expected: All tests pass, coverage check passes.

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: set coverage threshold to 70%"
```

---

## Task 13: Final verification

**Step 1: Run full test suite with coverage**

Run: `pytest tests/ --cov --cov-report=term-missing -v`
Expected: All tests pass, coverage ≥ 70%.

**Step 2: Count new tests**

Run: `pytest tests/ --co -q 2>/dev/null | tail -5`
Expected: ~229+ tests collected (was 194).

**Step 3: Final commit if any adjustments needed**

Only commit if fixes were needed in previous steps.
