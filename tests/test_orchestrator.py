import pytest
import subprocess
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
