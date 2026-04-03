import pytest
from unittest.mock import patch, MagicMock


class TestSerialUsbPowerController:
    @pytest.fixture
    def controller(self):
        with patch("smoke_test_ai.drivers.usb_power_serial.UsbPortController") as MockCtrl:
            mock_instance = MockCtrl.return_value
            mock_instance.is_connected = True
            MockCtrl.find.return_value = mock_instance
            from smoke_test_ai.drivers.usb_power_serial import SerialUsbPowerController
            ctrl = SerialUsbPowerController(
                port=3, off_duration=2.0, serial_port="/dev/ttyUSB0"
            )
            yield ctrl, mock_instance, MockCtrl

    @pytest.fixture
    def controller_by_serial(self):
        with patch("smoke_test_ai.drivers.usb_power_serial.UsbPortController") as MockCtrl:
            mock_instance = MockCtrl.find.return_value
            mock_instance.is_connected = True
            from smoke_test_ai.drivers.usb_power_serial import SerialUsbPowerController
            ctrl = SerialUsbPowerController(
                port=3, off_duration=2.0, device_serial="UHB-07"
            )
            yield ctrl, mock_instance, MockCtrl

    def test_power_off(self, controller):
        ctrl, mock, _ = controller
        assert ctrl.power_off() is True
        mock.connect.assert_called_once()
        mock.port_off.assert_called_once_with(3)

    def test_power_on(self, controller):
        ctrl, mock, _ = controller
        assert ctrl.power_on() is True
        mock.connect.assert_called_once()
        mock.port_on.assert_called_once_with(3)

    @patch("smoke_test_ai.drivers.usb_power_serial.time")
    def test_power_cycle(self, mock_time, controller):
        ctrl, mock, _ = controller
        assert ctrl.power_cycle() is True
        mock.port_off.assert_called_once_with(3)
        mock_time.sleep.assert_called_once_with(2.0)
        mock.port_on.assert_called_once_with(3)

    @patch("smoke_test_ai.drivers.usb_power_serial.time")
    def test_power_cycle_custom_duration(self, mock_time, controller):
        ctrl, mock, _ = controller
        assert ctrl.power_cycle(off_duration=10.0) is True
        mock_time.sleep.assert_called_once_with(10.0)

    def test_power_off_handles_error(self, controller):
        ctrl, mock, _ = controller
        mock.port_off.side_effect = Exception("device disconnected")
        assert ctrl.power_off() is False

    def test_close(self, controller):
        ctrl, mock, _ = controller
        ctrl._ensure_connected()
        ctrl.close()
        mock.disconnect.assert_called_once()

    def test_lazy_connect(self, controller):
        ctrl, mock, _ = controller
        mock.is_connected = False
        ctrl.power_on()
        assert mock.connect.call_count >= 1

    def test_find_by_device_serial(self, controller_by_serial):
        ctrl, mock, MockCtrl = controller_by_serial
        assert ctrl.power_on() is True
        MockCtrl.find.assert_called_once_with(serial="UHB-07")
        mock.port_on.assert_called_once_with(3)
