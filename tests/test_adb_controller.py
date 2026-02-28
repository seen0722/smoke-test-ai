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


@patch("smoke_test_ai.drivers.adb_controller.subprocess.run")
def test_get_user_state_unlocked(mock_run, adb):
    mock_run.return_value = MagicMock(returncode=0, stdout="    State: RUNNING_UNLOCKED\n", stderr="")
    assert adb.get_user_state() == "RUNNING_UNLOCKED"


@patch("smoke_test_ai.drivers.adb_controller.subprocess.run")
def test_get_user_state_locked(mock_run, adb):
    mock_run.return_value = MagicMock(returncode=0, stdout="    State: RUNNING_LOCKED\n", stderr="")
    assert adb.get_user_state() == "RUNNING_LOCKED"


@patch("smoke_test_ai.drivers.adb_controller.time.sleep")
@patch("smoke_test_ai.drivers.adb_controller.subprocess.run")
def test_unlock_keyguard_with_pin(mock_run, mock_sleep, adb):
    # First calls: wakeup, swipe, input text, enter. Last call: get_user_state
    mock_run.return_value = MagicMock(returncode=0, stdout="    State: RUNNING_UNLOCKED\n", stderr="")
    result = adb.unlock_keyguard(pin="0000")
    assert result is True


@patch("smoke_test_ai.drivers.adb_controller.time.sleep")
@patch("smoke_test_ai.drivers.adb_controller.subprocess.run")
def test_unlock_keyguard_no_pin(mock_run, mock_sleep, adb):
    mock_run.return_value = MagicMock(returncode=0, stdout="    State: RUNNING_UNLOCKED\n", stderr="")
    result = adb.unlock_keyguard(pin=None)
    assert result is True


@patch("smoke_test_ai.drivers.adb_controller.time.sleep")
@patch("smoke_test_ai.drivers.adb_controller.subprocess.run")
def test_unlock_keyguard_fail(mock_run, mock_sleep, adb):
    mock_run.return_value = MagicMock(returncode=0, stdout="    State: RUNNING_LOCKED\n", stderr="")
    result = adb.unlock_keyguard(pin="9999")
    assert result is False


@patch("smoke_test_ai.drivers.adb_controller.time.sleep")
@patch("smoke_test_ai.drivers.adb_controller.subprocess.run")
def test_enable_wifi_already_enabled(mock_run, mock_sleep, adb):
    mock_run.return_value = MagicMock(returncode=0, stdout="Wi-Fi is enabled\n", stderr="")
    assert adb.enable_wifi() is True


@patch("smoke_test_ai.drivers.adb_controller.time.sleep")
@patch("smoke_test_ai.drivers.adb_controller.subprocess.run")
def test_enable_wifi_needs_enabling(mock_run, mock_sleep, adb):
    # First call: WiFi is disabled; second call: svc wifi enable; third call: WiFi is enabled
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="Wi-Fi is disabled\n", stderr=""),  # check state
        MagicMock(returncode=0, stdout="", stderr=""),  # svc wifi enable
        MagicMock(returncode=0, stdout="Wi-Fi is enabled\n", stderr=""),  # check again
    ]
    assert adb.enable_wifi() is True


@patch("smoke_test_ai.drivers.adb_controller.time.sleep")
@patch("smoke_test_ai.drivers.adb_controller.subprocess.run")
def test_connect_wifi_enables_first(mock_run, mock_sleep, adb):
    """Verify connect_wifi calls enable_wifi before connecting."""
    mock_run.side_effect = [
        # enable_wifi: check → already enabled
        MagicMock(returncode=0, stdout="Wi-Fi is enabled\n", stderr=""),
        # connect-network command
        MagicMock(returncode=0, stdout="", stderr=""),
        # is_wifi_connected: dumpsys wifi
        MagicMock(returncode=0, stdout="Wi-Fi is enabled\n", stderr=""),
        # is_wifi_connected: ip route
        MagicMock(returncode=0, stdout="default via 192.168.1.1 dev wlan0\n", stderr=""),
    ]
    assert adb.connect_wifi("TestSSID", "pass123") is True
