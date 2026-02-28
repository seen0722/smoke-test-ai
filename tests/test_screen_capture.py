import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from smoke_test_ai.drivers.screen_capture.base import ScreenCapture
from smoke_test_ai.drivers.screen_capture.webcam import WebcamCapture
from smoke_test_ai.drivers.screen_capture.adb_screencap import AdbScreenCapture

def test_base_is_abstract():
    with pytest.raises(TypeError):
        ScreenCapture()

class TestWebcamCapture:
    @patch("smoke_test_ai.drivers.screen_capture.webcam.cv2")
    def test_capture_returns_image(self, mock_cv2):
        fake_frame = np.zeros((1920, 1080, 3), dtype=np.uint8)
        mock_cap = MagicMock()
        mock_cap.read.return_value = (True, fake_frame)
        mock_cap.isOpened.return_value = True
        mock_cv2.VideoCapture.return_value = mock_cap
        webcam = WebcamCapture(device_index=0)
        webcam.open()
        image = webcam.capture()
        assert image is not None
        assert image.shape == (1920, 1080, 3)

    @patch("smoke_test_ai.drivers.screen_capture.webcam.cv2")
    def test_capture_with_crop(self, mock_cv2):
        fake_frame = np.zeros((1920, 1080, 3), dtype=np.uint8)
        mock_cap = MagicMock()
        mock_cap.read.return_value = (True, fake_frame)
        mock_cap.isOpened.return_value = True
        mock_cv2.VideoCapture.return_value = mock_cap
        webcam = WebcamCapture(device_index=0, crop=(100, 50, 800, 600))
        webcam.open()
        image = webcam.capture()
        assert image is not None
        assert image.shape == (600, 800, 3)

    @patch("smoke_test_ai.drivers.screen_capture.webcam.cv2")
    def test_capture_failure(self, mock_cv2):
        mock_cap = MagicMock()
        mock_cap.read.return_value = (False, None)
        mock_cap.isOpened.return_value = True
        mock_cv2.VideoCapture.return_value = mock_cap
        webcam = WebcamCapture(device_index=0)
        webcam.open()
        image = webcam.capture()
        assert image is None

class TestAdbScreenCapture:
    @patch("smoke_test_ai.drivers.screen_capture.adb_screencap.subprocess.run")
    def test_capture_returns_image(self, mock_run):
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_png, stderr=b"")
        cap = AdbScreenCapture(serial="FAKE")
        with patch("smoke_test_ai.drivers.screen_capture.adb_screencap.cv2") as mock_cv2:
            fake_img = np.zeros((1920, 1080, 3), dtype=np.uint8)
            mock_cv2.imdecode.return_value = fake_img
            mock_cv2.IMREAD_COLOR = 1
            image = cap.capture()
            assert image is not None
