import subprocess
import time
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)


class UsbPowerController:
    """Control USB port power via uhubctl."""

    def __init__(self, hub_location: str, port: int, off_duration: float = 3.0):
        self.hub_location = hub_location
        self.port = port
        self.off_duration = off_duration

    def _run_uhubctl(self, action: str) -> bool:
        cmd = ["uhubctl", "-l", self.hub_location, "-p", str(self.port), "-a", action]
        logger.info(f"USB power {action}: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                logger.warning(f"uhubctl failed (rc={result.returncode}): {result.stdout}")
                return False
            logger.info(f"USB power {action} OK")
            return True
        except FileNotFoundError:
            logger.warning("uhubctl not found. Install with: brew install uhubctl (macOS) or apt install uhubctl (Ubuntu)")
            return False
        except subprocess.TimeoutExpired:
            logger.warning("uhubctl timed out")
            return False

    def power_off(self) -> bool:
        return self._run_uhubctl("off")

    def power_on(self) -> bool:
        return self._run_uhubctl("on")

    def power_cycle(self, off_duration: float | None = None) -> bool:
        duration = off_duration if off_duration is not None else self.off_duration
        if not self.power_off():
            return False
        time.sleep(duration)
        return self.power_on()
