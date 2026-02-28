import cv2
import numpy as np
from smoke_test_ai.drivers.screen_capture.base import ScreenCapture
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)

class WebcamCapture(ScreenCapture):
    def __init__(self, device_index: int | str = 0, crop: tuple[int, int, int, int] | None = None):
        self.device_index = device_index
        self.crop = crop
        self._cap = None

    def open(self) -> None:
        self._cap = cv2.VideoCapture(self.device_index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open webcam: {self.device_index}")
        logger.info(f"Webcam opened: {self.device_index}")

    def capture(self) -> np.ndarray | None:
        if self._cap is None:
            return None
        ret, frame = self._cap.read()
        if not ret or frame is None:
            logger.warning("Failed to capture frame from webcam")
            return None
        if self.crop:
            x, y, w, h = self.crop
            frame = frame[y : y + h, x : x + w]
        return frame

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info("Webcam released")
