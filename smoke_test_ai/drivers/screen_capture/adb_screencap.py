import subprocess
import cv2
import numpy as np
from smoke_test_ai.drivers.screen_capture.base import ScreenCapture
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)

class AdbScreenCapture(ScreenCapture):
    def __init__(self, serial: str | None = None, adb_path: str = "adb"):
        self.serial = serial
        self.adb_path = adb_path

    def capture(self) -> np.ndarray | None:
        cmd = [self.adb_path]
        if self.serial:
            cmd.extend(["-s", self.serial])
        cmd.extend(["exec-out", "screencap", "-p"])
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            if result.returncode != 0:
                logger.warning(f"screencap failed: {result.stderr}")
                return None
            img_array = np.frombuffer(result.stdout, dtype=np.uint8)
            image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            return image
        except subprocess.TimeoutExpired:
            logger.warning("screencap timed out")
            return None
