import pytest
from unittest.mock import patch, MagicMock
from smoke_test_ai.drivers.adb_controller import AdbController


@pytest.fixture
def adb():
    return AdbController(serial="FAKE_SERIAL")


def test_adb_controller_init(adb):
    assert adb.serial == "FAKE_SERIAL"


@patch("smoke_test_ai.drivers.adb_controller.subprocess.run")
def test_shell_command(mock_run, adb):
    mock_run.return_value = MagicMock(returncode=0, stdout="userdebug", stderr="")
    result = adb.shell("getprop ro.build.type")
    assert result.stdout == "userdebug"
    cmd = mock_run.call_args[0][0]
    assert "adb" in cmd
    assert "-s" in cmd
    assert "FAKE_SERIAL" in cmd


@patch("smoke_test_ai.drivers.adb_controller.subprocess.run")
def test_shell_command_no_serial(mock_run):
    adb = AdbController()
    mock_run.return_value = MagicMock(returncode=0, stdout="1", stderr="")
    adb.shell("getprop sys.boot_completed")
    cmd = mock_run.call_args[0][0]
    assert "-s" not in cmd


@patch("smoke_test_ai.drivers.adb_controller.subprocess.run")
def test_get_prop(mock_run, adb):
    mock_run.return_value = MagicMock(returncode=0, stdout="1\n", stderr="")
    value = adb.getprop("sys.boot_completed")
    assert value == "1"


@patch("smoke_test_ai.drivers.adb_controller.subprocess.run")
def test_is_connected_true(mock_run, adb):
    mock_run.return_value = MagicMock(returncode=0, stdout="List of devices attached\nFAKE_SERIAL\tdevice\n", stderr="")
    assert adb.is_connected() is True


@patch("smoke_test_ai.drivers.adb_controller.subprocess.run")
def test_is_connected_false(mock_run, adb):
    mock_run.return_value = MagicMock(returncode=0, stdout="List of devices attached\n", stderr="")
    assert adb.is_connected() is False


@patch("smoke_test_ai.drivers.adb_controller.subprocess.run")
def test_screencap(mock_run, adb, tmp_path):
    mock_run.return_value = MagicMock(returncode=0, stdout=b"\x89PNG", stderr="")
    output = tmp_path / "screen.png"
    adb.screencap(output)
    mock_run.assert_called_once()


@patch("smoke_test_ai.drivers.adb_controller.subprocess.run")
def test_install_apk(mock_run, adb):
    mock_run.return_value = MagicMock(returncode=0, stdout="Success", stderr="")
    result = adb.install("/path/to/app.apk")
    assert result.returncode == 0
