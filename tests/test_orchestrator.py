import pytest
import subprocess
import yaml
from unittest.mock import patch, MagicMock, call
from pathlib import Path
from smoke_test_ai.core.orchestrator import Orchestrator


@pytest.fixture
def settings():
    return {
        "llm": {
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "vision_model": "llava:13b",
            "text_model": "llama3:8b",
            "timeout": 30,
        },
        "wifi": {"ssid": "TestLab", "password": "pass123"},
        "reporting": {
            "formats": ["cli", "json"],
            "output_dir": "results/",
            "screenshots": True,
        },
        "parallel": {"max_devices": 4, "per_device_timeout": 900},
    }


@pytest.fixture
def device_config():
    return {
        "device": {
            "name": "Product-A",
            "build_type": "user",
            "screen_resolution": [1080, 2400],
            "flash": {"profile": "fastboot"},
            "screen_capture": {"method": "adb"},
            "setup_wizard": {"method": "llm_vision", "max_steps": 30, "timeout": 300},
        }
    }


def _make_shell_result(stdout="", returncode=0):
    """Helper to create a mock subprocess result."""
    r = MagicMock(spec=subprocess.CompletedProcess)
    r.stdout = stdout
    r.stderr = ""
    r.returncode = returncode
    return r


class TestOrchestrator:
    def test_init(self, settings, device_config):
        orch = Orchestrator(settings=settings, device_config=device_config)
        assert orch.device_name == "Product-A"

    def test_select_flash_driver(self, settings, device_config):
        orch = Orchestrator(settings=settings, device_config=device_config)
        driver = orch._get_flash_driver(serial="FAKE")
        assert driver is not None

    def test_select_screen_capture_adb(self, settings, device_config):
        orch = Orchestrator(settings=settings, device_config=device_config)
        cap = orch._get_screen_capture(serial="FAKE")
        assert cap is not None


class TestEnsureMoblySnippet:
    """Tests for _ensure_mobly_snippet APK installation flow."""

    def test_already_installed(self, settings, device_config):
        """If snippet is already installed for user 0, return True immediately."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        adb = MagicMock()
        pkg = Orchestrator._SNIPPET_PKG
        adb.shell.return_value = _make_shell_result(f"package:{pkg}")
        assert orch._ensure_mobly_snippet(adb) is True
        # Only one shell call (the check)
        adb.shell.assert_called_once_with(f"pm list packages --user 0 {pkg}")

    def test_install_existing_for_user(self, settings, device_config):
        """If package exists globally but not for user 0, use install-existing."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        adb = MagicMock()
        pkg = Orchestrator._SNIPPET_PKG

        def shell_side_effect(cmd):
            if "install-existing" in cmd:
                return _make_shell_result("Success")
            if "pm list packages --user 0" in cmd:
                return _make_shell_result("")  # Not found for user 0
            if "pm list packages" in cmd:
                return _make_shell_result(f"package:{pkg}")  # Found globally
            return _make_shell_result("")

        adb.shell.side_effect = shell_side_effect
        assert orch._ensure_mobly_snippet(adb) is True

    def test_install_from_local_apk(self, settings, device_config, tmp_path):
        """If APK found locally, install it and verify."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        adb = MagicMock()
        pkg = Orchestrator._SNIPPET_PKG

        # Create a fake APK file
        apk_file = tmp_path / "mobly-bundled-snippets.apk"
        apk_file.write_bytes(b"fake_apk")

        call_count = [0]

        def shell_side_effect(cmd):
            if "pm list packages --user 0" in cmd:
                call_count[0] += 1
                if call_count[0] <= 1:
                    return _make_shell_result("")  # Not found first check
                return _make_shell_result(f"package:{pkg}")  # Found after install
            if "pm list packages" in cmd:
                return _make_shell_result("")  # Not found globally either
            if cmd == "id":
                return _make_shell_result("uid=2000(shell)")
            return _make_shell_result("")

        adb.shell.side_effect = shell_side_effect
        adb.install.return_value = _make_shell_result("Success", returncode=0)

        with patch.object(orch, "_find_snippet_apk", return_value=apk_file):
            assert orch._ensure_mobly_snippet(adb) is True
        adb.install.assert_called_once_with(str(apk_file))

    def test_install_fails_returns_false(self, settings, device_config, tmp_path):
        """If adb install fails, return False with error details."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        adb = MagicMock()

        def shell_side_effect(cmd):
            if "pm list packages" in cmd:
                return _make_shell_result("")  # Not found
            if cmd == "id":
                return _make_shell_result("uid=2000(shell)")
            return _make_shell_result("")

        adb.shell.side_effect = shell_side_effect
        adb.install.return_value = _make_shell_result(
            "Failure [INSTALL_FAILED_OLDER_SDK]", returncode=1
        )

        apk_file = tmp_path / "mobly-bundled-snippets.apk"
        apk_file.write_bytes(b"fake_apk")
        with patch.object(orch, "_find_snippet_apk", return_value=apk_file):
            assert orch._ensure_mobly_snippet(adb) is False

    def test_no_apk_and_download_fails(self, settings, device_config):
        """If no local APK and download fails, return False."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        adb = MagicMock()

        def shell_side_effect(cmd):
            if "pm list packages" in cmd:
                return _make_shell_result("")
            if cmd == "id":
                return _make_shell_result("uid=2000(shell)")
            return _make_shell_result("")

        adb.shell.side_effect = shell_side_effect

        with patch.object(orch, "_find_snippet_apk", return_value=None), \
             patch.object(orch, "_download_snippet_apk", return_value=None):
            assert orch._ensure_mobly_snippet(adb) is False

    def test_download_and_install(self, settings, device_config, tmp_path):
        """If no local APK, download it and install successfully."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        adb = MagicMock()
        pkg = Orchestrator._SNIPPET_PKG

        apk_file = tmp_path / "mobly-bundled-snippets.apk"
        apk_file.write_bytes(b"fake_apk")

        call_count = [0]

        def shell_side_effect(cmd):
            if "pm list packages --user 0" in cmd:
                call_count[0] += 1
                if call_count[0] <= 1:
                    return _make_shell_result("")
                return _make_shell_result(f"package:{pkg}")
            if "pm list packages" in cmd:
                return _make_shell_result("")
            if cmd == "id":
                return _make_shell_result("uid=2000(shell)")
            return _make_shell_result("")

        adb.shell.side_effect = shell_side_effect
        adb.install.return_value = _make_shell_result("Success", returncode=0)

        with patch.object(orch, "_find_snippet_apk", return_value=None), \
             patch.object(orch, "_download_snippet_apk", return_value=apk_file):
            assert orch._ensure_mobly_snippet(adb) is True
        adb.install.assert_called_once_with(str(apk_file))


class TestOrchestratorRun:
    """Tests for Orchestrator.run() pipeline stages."""

    def _mock_adb(self, wait_for_device=True, user_state="RUNNING_UNLOCKED", wifi_connected=True):
        """Create a mock AdbController with sensible defaults."""
        adb = MagicMock()
        adb.wait_for_device.return_value = wait_for_device
        adb.get_user_state.return_value = user_state
        adb.is_wifi_connected.return_value = wifi_connected
        adb.is_connected.return_value = True
        # Return boot_completed=1 for preflight, empty for others
        def _shell_side_effect(cmd):
            if "sys.boot_completed" in cmd:
                return _make_shell_result("1")
            if "pm list packages" in cmd:
                return _make_shell_result("package:com.google.android.mobly.snippet.bundled")
            return _make_shell_result("")
        adb.shell.side_effect = _shell_side_effect
        adb.get_device_info.return_value = {"model": "Test", "sdk": "33"}
        adb.skip_setup_wizard.return_value = True
        adb.unlock_keyguard.return_value = True
        return adb

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_run_skips_flash_when_no_build_dir(self, MockAdb, mock_sleep, settings, device_config):
        """run() without build_dir skips Stage 0 — _get_flash_driver never called."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb_inst = self._mock_adb()
        MockAdb.return_value = mock_adb_inst

        with patch.object(orch, "_get_flash_driver") as mock_flash, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            orch.run(serial="FAKE", build_dir=None)
            mock_flash.assert_not_called()

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_run_calls_flash_with_build_dir(self, MockAdb, mock_sleep, settings, device_config):
        """run() with build_dir triggers Stage 0 — flash driver's flash() called."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb_inst = self._mock_adb()
        MockAdb.return_value = mock_adb_inst

        mock_flash_driver = MagicMock()
        with patch.object(orch, "_get_flash_driver", return_value=mock_flash_driver) as mock_get_flash, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            orch.run(serial="FAKE", build_dir="/some/build")
            mock_get_flash.assert_called_once_with(serial="FAKE")
            mock_flash_driver.flash.assert_called_once()

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_run_generates_reports(self, MockAdb, mock_sleep, settings, device_config):
        """run() calls _generate_reports at end exactly once."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb_inst = self._mock_adb()
        MockAdb.return_value = mock_adb_inst

        with patch.object(orch, "_generate_reports") as mock_reports, \
             patch.object(orch, "_pre_test_setup"):
            orch.run(serial="FAKE")
            mock_reports.assert_called_once()

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_run_returns_empty_when_adb_timeout(self, MockAdb, mock_sleep, settings, device_config):
        """ADB wait_for_device returns False -> run() returns []."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb_inst = self._mock_adb(wait_for_device=False)
        MockAdb.return_value = mock_adb_inst

        with patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            result = orch.run(serial="FAKE")
            assert result == []

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_run_blind_setup_when_user_build(self, MockAdb, mock_sleep, settings, device_config, tmp_path):
        """For user build with AOA config, triggers BlindRunner with setup flow YAML."""
        # Add AOA config to device_config
        device_config["device"]["aoa"] = {
            "enabled": True,
            "vendor_id": 0x18D1,
            "product_id": 0x4EE2,
        }
        device_config["device"]["build_type"] = "user"

        # Create minimal flow YAML
        flow_dir = tmp_path / "setup_flows"
        flow_dir.mkdir()
        flow_yaml = flow_dir / "product_a.yaml"
        flow_yaml.write_text(yaml.dump({"steps": [{"action": "tap", "x": 100, "y": 200}]}))

        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb_inst = self._mock_adb()
        MockAdb.return_value = mock_adb_inst

        mock_hid = MagicMock()
        mock_blind_runner = MagicMock()
        mock_blind_runner.run.return_value = True

        with patch.object(orch, "_init_aoa_hid", return_value=mock_hid) as mock_init_hid, \
             patch("smoke_test_ai.runners.blind_runner.BlindRunner", return_value=mock_blind_runner) as MockBlindRunner, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            orch.run(serial="FAKE", config_dir=str(tmp_path), is_factory_reset=True)
            mock_init_hid.assert_called_once()
            MockBlindRunner.assert_called_once()
            mock_hid.close.assert_called_once()

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_flash_triggers_power_cycle(self, MockAdb, mock_sleep, settings, device_config):
        """After flash, power_cycle is called if usb_power configured."""
        device_config["device"]["usb_power"] = {
            "hub_location": "1-1", "port": 1, "off_duration": 2.0,
        }
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb_inst = self._mock_adb()
        MockAdb.return_value = mock_adb_inst

        mock_flash_driver = MagicMock()
        with patch.object(orch, "_get_flash_driver", return_value=mock_flash_driver), \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"), \
             patch("smoke_test_ai.core.orchestrator.UsbPowerController") as MockPower:
            mock_power = MagicMock()
            mock_power.power_cycle.return_value = True
            MockPower.return_value = mock_power
            orch.run(serial="FAKE", build_dir="/some/build")
            mock_power.power_cycle.assert_called_once()

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_flash_no_power_cycle_when_unconfigured(self, MockAdb, mock_sleep, settings, device_config):
        """Without usb_power config, no power cycle after flash."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb_inst = self._mock_adb()
        MockAdb.return_value = mock_adb_inst

        mock_flash_driver = MagicMock()
        with patch.object(orch, "_get_flash_driver", return_value=mock_flash_driver), \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            orch.run(serial="FAKE", build_dir="/some/build")
            # No crash, no power cycle call — just ensure it doesn't crash

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_run_unlocks_fbe_when_locked(self, MockAdb, mock_sleep, settings, device_config):
        """get_user_state returns 'RUNNING_LOCKED' -> unlock_keyguard called with pin."""
        device_config["device"]["lock_pin"] = "0000"
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb_inst = self._mock_adb(user_state="RUNNING_LOCKED")
        MockAdb.return_value = mock_adb_inst

        with patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            orch.run(serial="FAKE", is_factory_reset=True)
            mock_adb_inst.unlock_keyguard.assert_called_once_with(pin="0000")


class TestAdaptivePipeline:
    """Tests for build_type / keep_data / is_factory_reset decision logic."""

    def _setup_orch(self, settings, device_config, MockAdb, with_aoa=True):
        if with_aoa:
            device_config["device"]["aoa"] = {"enabled": True, "vendor_id": 0x18D1, "product_id": 0x4EE2}
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb = MagicMock()
        mock_adb.wait_for_device.return_value = True
        mock_adb.is_wifi_connected.return_value = True
        mock_adb.is_connected.return_value = True
        mock_adb.get_user_state.return_value = "RUNNING_UNLOCKED"
        mock_adb.get_device_info.return_value = {"model": "T", "sdk": "33"}
        def _shell(cmd):
            if "sys.boot_completed" in cmd:
                return _make_shell_result("1")
            if "pm list packages" in cmd:
                return _make_shell_result("package:com.google.android.mobly.snippet.bundled")
            return _make_shell_result("")
        mock_adb.shell.side_effect = _shell
        MockAdb.return_value = mock_adb
        return orch, mock_adb

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_user_full_flash_triggers_aoa(self, MockAdb, mock_sleep, settings, device_config):
        """user build + full flash → need_aoa=True."""
        orch, mock_adb = self._setup_orch(settings, device_config, MockAdb)
        with patch.object(orch, "_get_flash_driver") as mock_gfd, \
             patch.object(orch, "_init_aoa_hid") as mock_aoa, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            mock_gfd.return_value = MagicMock()
            orch.run(serial="S", build_dir="/b", build_type="user", keep_data=False)
            mock_aoa.assert_called_once()

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_user_keep_data_skips_aoa(self, MockAdb, mock_sleep, settings, device_config):
        """user build + keep_data=True → no AOA."""
        orch, mock_adb = self._setup_orch(settings, device_config, MockAdb)
        with patch.object(orch, "_get_flash_driver") as mock_gfd, \
             patch.object(orch, "_init_aoa_hid") as mock_aoa, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            mock_gfd.return_value = MagicMock()
            orch.run(serial="S", build_dir="/b", build_type="user", keep_data=True)
            mock_aoa.assert_not_called()

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_userdebug_never_aoa(self, MockAdb, mock_sleep, settings, device_config):
        """userdebug build → no AOA."""
        orch, mock_adb = self._setup_orch(settings, device_config, MockAdb)
        with patch.object(orch, "_get_flash_driver") as mock_gfd, \
             patch.object(orch, "_init_aoa_hid") as mock_aoa, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            mock_gfd.return_value = MagicMock()
            orch.run(serial="S", build_dir="/b", build_type="userdebug")
            mock_aoa.assert_not_called()

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_keep_data_injected_to_flash_config(self, MockAdb, mock_sleep, settings, device_config):
        """keep_data=True is injected into flash_config."""
        orch, mock_adb = self._setup_orch(settings, device_config, MockAdb, with_aoa=False)
        mock_fd = MagicMock()
        with patch.object(orch, "_get_flash_driver", return_value=mock_fd), \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            orch.run(serial="S", build_dir="/b", keep_data=True)
            flash_cfg = mock_fd.flash.call_args[0][0]
            assert flash_cfg.get("keep_data") is True

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_factory_reset_user_triggers_aoa(self, MockAdb, mock_sleep, settings, device_config):
        """is_factory_reset=True + user build → AOA."""
        orch, mock_adb = self._setup_orch(settings, device_config, MockAdb)
        with patch.object(orch, "_init_aoa_hid") as mock_aoa, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            orch.run(serial="S", build_type="user", is_factory_reset=True)
            mock_aoa.assert_called_once()

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_cli_build_type_overrides_yaml(self, MockAdb, mock_sleep, settings, device_config):
        """CLI build_type=userdebug overrides YAML user → no AOA."""
        orch, mock_adb = self._setup_orch(settings, device_config, MockAdb)
        with patch.object(orch, "_get_flash_driver") as mock_gfd, \
             patch.object(orch, "_init_aoa_hid") as mock_aoa, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            mock_gfd.return_value = MagicMock()
            orch.run(serial="S", build_dir="/b", build_type="userdebug")
            mock_aoa.assert_not_called()

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_fresh_state_longer_wifi_timeout(self, MockAdb, mock_sleep, settings, device_config):
        """fresh_state=True → 45s WiFi timeout."""
        orch, mock_adb = self._setup_orch(settings, device_config, MockAdb, with_aoa=False)
        mock_adb.is_wifi_connected.return_value = False
        with patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            orch.run(serial="S", is_factory_reset=True)
            mock_adb.connect_wifi.assert_called_once()
            assert mock_adb.connect_wifi.call_args.kwargs.get("wifi_timeout") == 45

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_keep_data_shorter_wifi_timeout(self, MockAdb, mock_sleep, settings, device_config):
        """keep_data=True (fresh_state=False) → 15s WiFi timeout."""
        orch, mock_adb = self._setup_orch(settings, device_config, MockAdb, with_aoa=False)
        mock_adb.is_wifi_connected.return_value = False
        with patch.object(orch, "_get_flash_driver") as mock_gfd, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            mock_gfd.return_value = MagicMock()
            orch.run(serial="S", build_dir="/b", keep_data=True)
            mock_adb.connect_wifi.assert_called_once()
            assert mock_adb.connect_wifi.call_args.kwargs.get("wifi_timeout") == 15
