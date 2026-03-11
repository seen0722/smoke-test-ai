import subprocess
from unittest.mock import patch, MagicMock, call
from smoke_test_ai.drivers.usb_power import UsbPowerController


class TestUsbPowerController:
    def _make_ctrl(self):
        return UsbPowerController(hub_location="1-1", port=1, off_duration=2.0)

    @patch("smoke_test_ai.drivers.usb_power.subprocess.run")
    def test_power_off_calls_uhubctl(self, mock_run):
        """power_off() calls uhubctl with correct args."""
        mock_run.return_value = MagicMock(returncode=0, stdout="Port 1: 0000 off")
        ctrl = self._make_ctrl()
        assert ctrl.power_off() is True
        mock_run.assert_called_once_with(
            ["uhubctl", "-l", "1-1", "-p", "1", "-a", "off"],
            capture_output=True, text=True, timeout=10,
        )

    @patch("smoke_test_ai.drivers.usb_power.subprocess.run")
    def test_power_on_calls_uhubctl(self, mock_run):
        """power_on() calls uhubctl with -a on."""
        mock_run.return_value = MagicMock(returncode=0, stdout="Port 1: 0100 power")
        ctrl = self._make_ctrl()
        assert ctrl.power_on() is True
        mock_run.assert_called_once_with(
            ["uhubctl", "-l", "1-1", "-p", "1", "-a", "on"],
            capture_output=True, text=True, timeout=10,
        )

    @patch("smoke_test_ai.drivers.usb_power.time.sleep")
    @patch("smoke_test_ai.drivers.usb_power.subprocess.run")
    def test_power_cycle_sequence(self, mock_run, mock_sleep):
        """power_cycle() calls off -> sleep -> on in correct order."""
        mock_run.return_value = MagicMock(returncode=0, stdout="ok")
        ctrl = self._make_ctrl()
        assert ctrl.power_cycle() is True
        assert mock_run.call_count == 2
        # First call: off
        assert mock_run.call_args_list[0][0][0][6] == "off"
        # Sleep with off_duration
        mock_sleep.assert_called_once_with(2.0)
        # Second call: on
        assert mock_run.call_args_list[1][0][0][6] == "on"

    @patch("smoke_test_ai.drivers.usb_power.subprocess.run")
    def test_power_off_failure_returns_false(self, mock_run):
        """uhubctl non-zero exit -> returns False."""
        mock_run.return_value = MagicMock(returncode=1, stdout="error")
        ctrl = self._make_ctrl()
        assert ctrl.power_off() is False

    @patch("smoke_test_ai.drivers.usb_power.time.sleep")
    @patch("smoke_test_ai.drivers.usb_power.subprocess.run")
    def test_power_cycle_custom_duration(self, mock_run, mock_sleep):
        """power_cycle(off_duration=5.0) overrides default."""
        mock_run.return_value = MagicMock(returncode=0, stdout="ok")
        ctrl = self._make_ctrl()
        ctrl.power_cycle(off_duration=5.0)
        mock_sleep.assert_called_once_with(5.0)
