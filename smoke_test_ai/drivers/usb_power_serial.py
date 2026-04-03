import time
from usb_port_controller import UsbPortController
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)


class SerialUsbPowerController:
    """USB power control via serial hub controller.

    Same interface as UsbPowerController (uhubctl) so plugins work unchanged.
    """

    def __init__(
        self,
        port: int,
        off_duration: float = 3.0,
        serial_port: str | None = None,
        device_serial: str | None = None,
    ):
        self.serial_port = serial_port
        self.device_serial = device_serial
        self.port = port
        self.off_duration = off_duration
        self._ctrl: UsbPortController | None = None

    def _ensure_connected(self) -> UsbPortController:
        if self._ctrl is None or not self._ctrl.is_connected:
            if self.device_serial:
                self._ctrl = UsbPortController.find(serial=self.device_serial)
            elif self.serial_port:
                self._ctrl = UsbPortController(self.serial_port)
                self._ctrl.connect()
            else:
                self._ctrl = UsbPortController.find()
        return self._ctrl

    def power_off(self) -> bool:
        try:
            self._ensure_connected().port_off(self.port)
            logger.info(f"Serial USB port {self.port} OFF")
            return True
        except Exception as e:
            logger.warning(f"Serial USB power_off failed: {e}")
            return False

    def power_on(self) -> bool:
        try:
            self._ensure_connected().port_on(self.port)
            logger.info(f"Serial USB port {self.port} ON")
            return True
        except Exception as e:
            logger.warning(f"Serial USB power_on failed: {e}")
            return False

    def power_cycle(self, off_duration: float | None = None) -> bool:
        duration = off_duration if off_duration is not None else self.off_duration
        if not self.power_off():
            return False
        time.sleep(duration)
        return self.power_on()

    def close(self):
        if self._ctrl:
            self._ctrl.disconnect()
            self._ctrl = None
