import pytest
from unittest.mock import patch, MagicMock
from smoke_test_ai.drivers.flash.base import FlashDriver
from smoke_test_ai.drivers.flash.fastboot import FastbootFlashDriver
from smoke_test_ai.drivers.flash.custom import CustomFlashDriver

def test_base_is_abstract():
    with pytest.raises(TypeError):
        FlashDriver()

class TestFastbootFlashDriver:
    @patch("smoke_test_ai.drivers.flash.fastboot.subprocess.run")
    def test_flash_single_partition(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        driver = FastbootFlashDriver(serial="FAKE")
        config = {"images": [{"partition": "system", "file": "/path/system.img"}]}
        driver.flash(config)
        assert mock_run.called

    @patch("smoke_test_ai.drivers.flash.fastboot.subprocess.run")
    def test_flash_with_reboot(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        driver = FastbootFlashDriver(serial="FAKE")
        config = {
            "images": [{"partition": "boot", "file": "/path/boot.img"}],
            "post_flash": ["fastboot reboot"],
        }
        driver.flash(config)
        assert mock_run.call_count >= 2

    @patch("smoke_test_ai.drivers.flash.fastboot.subprocess.run")
    def test_pre_flash_oem_unlock(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        driver = FastbootFlashDriver(serial="FAKE")
        config = {
            "pre_flash": ["fastboot oem unlock Trimble-Thorpe"],
            "images": [{"partition": "boot", "file": "/path/boot.img"}],
        }
        driver.flash(config)
        # pre_flash (via _run) + flash partition
        assert mock_run.call_count >= 2
        first_call = mock_run.call_args_list[0]
        cmd = first_call[0][0] if first_call[0] else first_call[1].get("args", [])
        assert "oem" in cmd or "oem" in str(first_call)

    @patch("smoke_test_ai.drivers.flash.fastboot.os.path.isfile", return_value=True)
    @patch("smoke_test_ai.drivers.flash.fastboot.subprocess.run")
    def test_flash_script_mode(self, mock_run, mock_isfile):
        mock_run.return_value = MagicMock(returncode=0, stdout="Flashing...\nDone", stderr="")
        driver = FastbootFlashDriver(serial="FAKE")
        config = {"script": "/path/to/fastboot.bash", "script_timeout": 300}
        driver.flash(config)
        # script run via subprocess
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["bash", "/path/to/fastboot.bash"]
        assert call_args[1]["env"]["ANDROID_SERIAL"] == "FAKE"

    @patch("smoke_test_ai.drivers.flash.fastboot.os.path.isfile", return_value=True)
    @patch("smoke_test_ai.drivers.flash.fastboot.subprocess.run")
    def test_flash_script_with_pre_flash(self, mock_run, mock_isfile):
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        driver = FastbootFlashDriver(serial="FAKE")
        config = {
            "pre_flash": ["fastboot oem unlock Trimble-Thorpe"],
            "script": "/path/to/fastboot.bash",
        }
        driver.flash(config)
        # pre_flash + script = 2 calls
        assert mock_run.call_count == 2

    @patch("smoke_test_ai.drivers.flash.fastboot.os.path.isfile", return_value=False)
    def test_flash_script_not_found(self, mock_isfile):
        driver = FastbootFlashDriver(serial="FAKE")
        config = {"script": "/nonexistent/fastboot.bash"}
        with pytest.raises(FileNotFoundError, match="Flash script not found"):
            driver.flash(config)

    @patch("smoke_test_ai.drivers.flash.fastboot.os.path.isfile", return_value=True)
    @patch("smoke_test_ai.drivers.flash.fastboot.subprocess.run")
    def test_flash_script_failure(self, mock_run, mock_isfile):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="FAILED: write error")
        driver = FastbootFlashDriver(serial="FAKE")
        config = {"script": "/path/to/fastboot.bash"}
        with pytest.raises(RuntimeError, match="Flash script failed"):
            driver.flash(config)

class TestCustomFlashDriver:
    @patch("smoke_test_ai.drivers.flash.custom.subprocess.run")
    def test_custom_commands(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        driver = CustomFlashDriver()
        config = {"commands": ["tool flash --image /path/system.img", "tool reboot"]}
        driver.flash(config)
        assert mock_run.call_count == 2


class TestResolveFlashConfig:
    def test_resolve_build_dir_in_script(self):
        from smoke_test_ai.core.orchestrator import Orchestrator
        config = {
            "profile": "fastboot",
            "pre_flash": ["fastboot oem unlock Trimble-Thorpe"],
            "script": "${BUILD_DIR}/fastboot.bash",
        }
        resolved = Orchestrator._resolve_flash_config(config, "/images/T70")
        assert resolved["script"] == "/images/T70/fastboot.bash"
        assert resolved["pre_flash"] == ["fastboot oem unlock Trimble-Thorpe"]

    def test_resolve_build_dir_in_images(self):
        from smoke_test_ai.core.orchestrator import Orchestrator
        config = {
            "images": [
                {"partition": "system", "file": "${BUILD_DIR}/system.img"},
                {"partition": "boot", "file": "${BUILD_DIR}/boot.img"},
            ]
        }
        resolved = Orchestrator._resolve_flash_config(config, "/builds/v2")
        assert resolved["images"][0]["file"] == "/builds/v2/system.img"
        assert resolved["images"][1]["file"] == "/builds/v2/boot.img"
