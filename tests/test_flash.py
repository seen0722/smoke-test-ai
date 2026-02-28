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

class TestCustomFlashDriver:
    @patch("smoke_test_ai.drivers.flash.custom.subprocess.run")
    def test_custom_commands(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        driver = CustomFlashDriver()
        config = {"commands": ["tool flash --image /path/system.img", "tool reboot"]}
        driver.flash(config)
        assert mock_run.call_count == 2
