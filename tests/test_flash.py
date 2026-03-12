import pytest
import tempfile
import os
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
        assert mock_run.call_count >= 2
        first_call = mock_run.call_args_list[0]
        cmd = first_call[0][0] if first_call[0] else first_call[1].get("args", [])
        assert "oem" in cmd or "oem" in str(first_call)

    @patch("smoke_test_ai.drivers.flash.fastboot.os.path.isfile", return_value=False)
    def test_flash_script_not_found(self, mock_isfile):
        driver = FastbootFlashDriver(serial="FAKE")
        config = {"script": "/nonexistent/fastboot.bash"}
        with pytest.raises(FileNotFoundError, match="Flash script not found"):
            driver.flash(config)


class TestParseScript:
    def _write_script(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".bash", delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_parse_fastboot_tool_var(self):
        script = self._write_script(
            'fastboot_tool="sudo ./fastboot"\n'
            'image_dir="./"\n'
            '$fastboot_tool erase boot_a\n'
            '$fastboot_tool flash boot_a ${image_dir}boot.img\n'
        )
        try:
            cmds = FastbootFlashDriver._parse_script(script)
            assert len(cmds) == 2
            assert cmds[0] == ["erase", "boot_a"]
            assert cmds[1] == ["flash", "boot_a", "${image_dir}boot.img"]
        finally:
            os.unlink(script)

    def test_parse_skips_comments(self):
        script = self._write_script(
            '$fastboot_tool flash boot_a boot.img\n'
            '#$fastboot_tool erase persist\n'
            '#$fastboot_tool flash persist persist.img\n'
            '$fastboot_tool set_active a\n'
        )
        try:
            cmds = FastbootFlashDriver._parse_script(script)
            assert len(cmds) == 2
            assert cmds[0] == ["flash", "boot_a", "boot.img"]
            assert cmds[1] == ["set_active", "a"]
        finally:
            os.unlink(script)

    def test_parse_sudo_fastboot(self):
        script = self._write_script(
            'sudo ./fastboot flash system system.img\n'
            './fastboot reboot\n'
        )
        try:
            cmds = FastbootFlashDriver._parse_script(script)
            assert len(cmds) == 2
            assert cmds[0] == ["flash", "system", "system.img"]
            assert cmds[1] == ["reboot"]
        finally:
            os.unlink(script)

    def test_parse_skips_non_fastboot_lines(self):
        script = self._write_script(
            'fastboot_tool="sudo ./fastboot"\n'
            'image_dir="./"\n'
            'case $1 in\n'
            '  *)\n'
            '    $fastboot_tool flash boot_a boot.img\n'
            'esac\n'
        )
        try:
            cmds = FastbootFlashDriver._parse_script(script)
            assert len(cmds) == 1
            assert cmds[0] == ["flash", "boot_a", "boot.img"]
        finally:
            os.unlink(script)

    def test_parse_real_t70_style(self):
        """Simulate T70 fastboot.bash structure."""
        script = self._write_script(
            'fastboot_tool="sudo ./fastboot"\n'
            'image_dir="./"\n'
            '\n'
            'case $1 in\n'
            '\t*)\n'
            '\t\t$fastboot_tool erase userdata\n'
            '\t\t$fastboot_tool flash userdata ${image_dir}userdata.img\n'
            '\t\t$fastboot_tool erase super\n'
            '\t\t$fastboot_tool flash super ${image_dir}super.img\n'
            '\t\t$fastboot_tool erase boot_a\n'
            '\t\t$fastboot_tool erase boot_b\n'
            '\t\t$fastboot_tool flash boot_a ${image_dir}boot.img\n'
            '\t\t$fastboot_tool flash boot_b ${image_dir}boot.img\n'
            '\t\t#$fastboot_tool erase persist\n'
            '\t\t#$fastboot_tool flash persist ${image_dir}persist.img\n'
            '\t\t$fastboot_tool set_active a\n'
            '\t\t#$fastboot_tool reboot\n'
            'esac\n'
        )
        try:
            cmds = FastbootFlashDriver._parse_script(script)
            # 9 active commands (2 commented out for persist, 1 for reboot)
            assert len(cmds) == 9
            assert cmds[0] == ["erase", "userdata"]
            assert cmds[1] == ["flash", "userdata", "${image_dir}userdata.img"]
            assert cmds[-1] == ["set_active", "a"]
        finally:
            os.unlink(script)


class TestRunScript:
    @patch("smoke_test_ai.drivers.flash.fastboot.subprocess.run")
    def test_run_script_uses_system_fastboot(self, mock_run):
        """Script mode parses script and uses system fastboot."""
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        driver = FastbootFlashDriver(serial="FAKE", fastboot_path="/usr/bin/fastboot")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".bash", delete=False) as f:
            f.write('$fastboot_tool erase boot_a\n')
            f.write('$fastboot_tool flash boot_a ${image_dir}boot.img\n')
            script_path = f.name

        try:
            config = {"script": script_path}
            driver.flash(config)
            assert mock_run.call_count == 2
            # First call: erase boot_a
            first_cmd = mock_run.call_args_list[0][0][0]
            assert first_cmd[0] == "/usr/bin/fastboot"
            assert "-s" in first_cmd and "FAKE" in first_cmd
            assert "erase" in first_cmd
        finally:
            os.unlink(script_path)

    @patch("smoke_test_ai.drivers.flash.fastboot.subprocess.run")
    def test_run_script_with_pre_flash(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        driver = FastbootFlashDriver(serial="FAKE")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".bash", delete=False) as f:
            f.write('$fastboot_tool flash boot_a boot.img\n')
            script_path = f.name

        try:
            config = {
                "pre_flash": ["fastboot oem unlock Trimble-Thorpe"],
                "script": script_path,
            }
            driver.flash(config)
            # pre_flash (1) + parsed script command (1) = 2
            assert mock_run.call_count == 2
        finally:
            os.unlink(script_path)

    @patch("smoke_test_ai.drivers.flash.fastboot.subprocess.run")
    def test_run_script_failure_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="FAILED: write")
        driver = FastbootFlashDriver(serial="FAKE")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".bash", delete=False) as f:
            f.write('$fastboot_tool flash boot_a boot.img\n')
            script_path = f.name

        try:
            config = {"script": script_path}
            with pytest.raises(RuntimeError, match="Flash command failed"):
                driver.flash(config)
        finally:
            os.unlink(script_path)


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
