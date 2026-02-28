# smoke-test-ai Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an end-to-end Android OS smoke test automation framework that handles flash → Setup Wizard (pre-ADB) → ADB testing → reporting.

**Architecture:** Bottom-up build: project scaffold → driver layer (ADB, AOA2 HID, screen capture) → AI layer (LLM client) → core engine (test runner, orchestrator) → CLI + reporting. Each layer is independently testable.

**Tech Stack:** Python 3.10+, PyUSB + libusb (AOA2), OpenCV (screen capture), Click + Rich (CLI), Jinja2 (reports), PyYAML (config), httpx (LLM API), pytest (testing)

---

### Task 1: Project Scaffold & Dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `smoke_test_ai/__init__.py`
- Create: `smoke_test_ai/core/__init__.py`
- Create: `smoke_test_ai/drivers/__init__.py`
- Create: `smoke_test_ai/drivers/flash/__init__.py`
- Create: `smoke_test_ai/drivers/screen_capture/__init__.py`
- Create: `smoke_test_ai/ai/__init__.py`
- Create: `smoke_test_ai/reporting/__init__.py`
- Create: `smoke_test_ai/utils/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `config/settings.yaml`
- Create: `config/devices/.gitkeep`
- Create: `config/flash_profiles/.gitkeep`
- Create: `config/test_suites/.gitkeep`
- Create: `scripts/install.sh`

**Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "smoke-test-ai"
version = "0.1.0"
description = "Android OS image smoke test automation framework"
requires-python = ">=3.10"
dependencies = [
    "click>=8.1",
    "rich>=13.0",
    "pyyaml>=6.0",
    "pyusb>=1.2",
    "opencv-python-headless>=4.8",
    "httpx>=0.25",
    "jinja2>=3.1",
    "Pillow>=10.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-mock>=3.10",
]
pdf = [
    "weasyprint>=60.0",
]

[project.scripts]
smoke-test = "cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

**Step 2: Create requirements.txt**

```
click>=8.1
rich>=13.0
pyyaml>=6.0
pyusb>=1.2
opencv-python-headless>=4.8
httpx>=0.25
jinja2>=3.1
Pillow>=10.0
pytest>=7.0
pytest-mock>=3.10
```

**Step 3: Create all `__init__.py` files and directory structure**

All `__init__.py` files should be empty. Create directories:
- `smoke_test_ai/core/`
- `smoke_test_ai/drivers/flash/`
- `smoke_test_ai/drivers/screen_capture/`
- `smoke_test_ai/ai/`
- `smoke_test_ai/reporting/`
- `smoke_test_ai/utils/`
- `tests/`
- `config/devices/`
- `config/flash_profiles/`
- `config/test_suites/`
- `templates/`
- `scripts/`

**Step 4: Create config/settings.yaml**

```yaml
llm:
  provider: "ollama"
  base_url: "http://localhost:11434"
  vision_model: "llava:13b"
  text_model: "llama3:8b"
  timeout: 30
  max_retries: 3

wifi:
  ssid: "TestLab-5G"
  password: ""

reporting:
  formats: ["cli", "json"]
  output_dir: "results/"
  screenshots: true

parallel:
  max_devices: 4
  per_device_timeout: 900
```

**Step 5: Create scripts/install.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== smoke-test-ai installer ==="

# Detect OS
OS="$(uname -s)"
case "$OS" in
    Linux)
        echo "Installing libusb on Linux..."
        if command -v apt-get &>/dev/null; then
            sudo apt-get update && sudo apt-get install -y libusb-1.0-0-dev libudev-dev
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y libusb1-devel
        fi
        ;;
    Darwin)
        echo "Installing libusb on macOS..."
        brew install libusb
        ;;
    *)
        echo "Unsupported OS: $OS. Please install libusb manually."
        ;;
esac

echo "Installing Python dependencies..."
pip install -e ".[dev]"

echo "=== Installation complete ==="
```

**Step 6: Create tests/conftest.py**

```python
import pytest
from pathlib import Path


@pytest.fixture
def project_root():
    return Path(__file__).parent.parent


@pytest.fixture
def config_dir(project_root):
    return project_root / "config"


@pytest.fixture
def sample_settings():
    return {
        "llm": {
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "vision_model": "llava:13b",
            "text_model": "llama3:8b",
            "timeout": 30,
            "max_retries": 3,
        },
        "wifi": {"ssid": "TestLab-5G", "password": ""},
        "reporting": {
            "formats": ["cli", "json"],
            "output_dir": "results/",
            "screenshots": True,
        },
        "parallel": {"max_devices": 4, "per_device_timeout": 900},
    }
```

**Step 7: Create .gitignore**

```
__pycache__/
*.pyc
*.egg-info/
dist/
build/
.venv/
results/
*.log
.env
```

**Step 8: Install dependencies and verify**

Run: `pip install -e ".[dev]"`
Expected: Successful installation

**Step 9: Run pytest to verify empty test suite works**

Run: `python -m pytest tests/ -v`
Expected: "no tests ran" with exit code 5 (no tests collected, which is fine)

**Step 10: Commit**

```bash
git add -A
git commit -m "feat: project scaffold with dependencies and config structure"
```

---

### Task 2: Utils — Logger & Config Loader

**Files:**
- Create: `smoke_test_ai/utils/logger.py`
- Create: `smoke_test_ai/utils/config.py`
- Create: `tests/test_utils.py`

**Step 1: Write the failing tests**

```python
# tests/test_utils.py
import pytest
from pathlib import Path
from smoke_test_ai.utils.config import load_settings, load_device_config, load_test_suite


def test_load_settings(config_dir):
    settings = load_settings(config_dir / "settings.yaml")
    assert settings["llm"]["provider"] == "ollama"
    assert settings["parallel"]["max_devices"] == 4


def test_load_settings_missing_file():
    with pytest.raises(FileNotFoundError):
        load_settings(Path("/nonexistent/settings.yaml"))


def test_load_device_config(tmp_path):
    device_yaml = tmp_path / "device.yaml"
    device_yaml.write_text(
        "device:\n  name: TestDevice\n  build_type: user\n"
        "  screen_resolution: [1080, 2400]\n"
    )
    config = load_device_config(device_yaml)
    assert config["device"]["name"] == "TestDevice"
    assert config["device"]["build_type"] == "user"


def test_load_test_suite(tmp_path):
    suite_yaml = tmp_path / "suite.yaml"
    suite_yaml.write_text(
        "test_suite:\n  name: Basic\n  timeout: 60\n"
        "  tests:\n    - id: t1\n      name: Test1\n      type: adb_check\n"
        "      command: getprop ro.build.type\n      expected: userdebug\n"
    )
    suite = load_test_suite(suite_yaml)
    assert suite["test_suite"]["name"] == "Basic"
    assert len(suite["test_suite"]["tests"]) == 1
    assert suite["test_suite"]["tests"][0]["id"] == "t1"
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_utils.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement logger.py**

```python
# smoke_test_ai/utils/logger.py
import logging
from rich.logging import RichHandler


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = RichHandler(rich_tracebacks=True, show_path=False)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(level)
    return logger
```

**Step 4: Implement config.py**

```python
# smoke_test_ai/utils/config.py
import os
import yaml
from pathlib import Path


def _expand_env_vars(data):
    """Recursively expand ${VAR} references in string values."""
    if isinstance(data, str):
        if "${" in data:
            for key, value in os.environ.items():
                data = data.replace(f"${{{key}}}", value)
        return data
    elif isinstance(data, dict):
        return {k: _expand_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_expand_env_vars(item) for item in data]
    return data


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return _expand_env_vars(data) if data else {}


def load_settings(path: Path) -> dict:
    return _load_yaml(path)


def load_device_config(path: Path) -> dict:
    return _load_yaml(path)


def load_test_suite(path: Path) -> dict:
    return _load_yaml(path)
```

**Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_utils.py -v`
Expected: 4 passed

**Step 6: Commit**

```bash
git add smoke_test_ai/utils/logger.py smoke_test_ai/utils/config.py tests/test_utils.py
git commit -m "feat: add logger and YAML config loader with env var expansion"
```

---

### Task 3: ADB Controller Driver

**Files:**
- Create: `smoke_test_ai/drivers/adb_controller.py`
- Create: `tests/test_adb_controller.py`

**Step 1: Write the failing tests**

```python
# tests/test_adb_controller.py
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
    mock_run.return_value = MagicMock(
        returncode=0, stdout="userdebug", stderr=""
    )
    result = adb.shell("getprop ro.build.type")
    assert result.stdout == "userdebug"
    mock_run.assert_called_once()
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
    mock_run.return_value = MagicMock(
        returncode=0, stdout="1\n", stderr=""
    )
    value = adb.getprop("sys.boot_completed")
    assert value == "1"


@patch("smoke_test_ai.drivers.adb_controller.subprocess.run")
def test_is_connected_true(mock_run, adb):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="List of devices attached\nFAKE_SERIAL\tdevice\n",
        stderr="",
    )
    assert adb.is_connected() is True


@patch("smoke_test_ai.drivers.adb_controller.subprocess.run")
def test_is_connected_false(mock_run, adb):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="List of devices attached\n",
        stderr="",
    )
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
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_adb_controller.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Implement adb_controller.py**

```python
# smoke_test_ai/drivers/adb_controller.py
import subprocess
import time
from pathlib import Path
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)


class AdbController:
    def __init__(self, serial: str | None = None, adb_path: str = "adb"):
        self.serial = serial
        self.adb_path = adb_path

    def _build_cmd(self, *args: str) -> list[str]:
        cmd = [self.adb_path]
        if self.serial:
            cmd.extend(["-s", self.serial])
        cmd.extend(args)
        return cmd

    def _run(self, *args: str, timeout: int = 30, **kwargs) -> subprocess.CompletedProcess:
        cmd = self._build_cmd(*args)
        logger.debug(f"ADB: {' '.join(cmd)}")
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            **kwargs,
        )

    def shell(self, command: str, timeout: int = 30) -> subprocess.CompletedProcess:
        return self._run("shell", command, timeout=timeout)

    def getprop(self, prop: str) -> str:
        result = self.shell(f"getprop {prop}")
        return result.stdout.strip()

    def is_connected(self) -> bool:
        result = self._run("devices")
        if self.serial:
            return f"{self.serial}\tdevice" in result.stdout
        lines = result.stdout.strip().split("\n")
        return any("\tdevice" in line for line in lines[1:])

    def wait_for_device(self, timeout: int = 60) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_connected():
                logger.info(f"Device {self.serial or 'any'} connected")
                return True
            time.sleep(2)
        logger.warning(f"Timeout waiting for device {self.serial or 'any'}")
        return False

    def screencap(self, output_path: Path) -> None:
        self._run(
            "exec-out", "screencap", "-p",
            timeout=10,
        )

    def install(self, apk_path: str) -> subprocess.CompletedProcess:
        return self._run("install", "-r", apk_path, timeout=120)

    def connect_wifi(self, ssid: str, password: str) -> subprocess.CompletedProcess:
        return self.shell(
            f'cmd wifi connect-network "{ssid}" wpa2 "{password}"',
            timeout=30,
        )

    def reboot(self, mode: str = "") -> subprocess.CompletedProcess:
        if mode:
            return self._run("reboot", mode)
        return self._run("reboot")
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_adb_controller.py -v`
Expected: 8 passed

**Step 5: Commit**

```bash
git add smoke_test_ai/drivers/adb_controller.py tests/test_adb_controller.py
git commit -m "feat: add ADB controller driver with shell, getprop, screencap, wifi"
```

---

### Task 4: Screen Capture Drivers (Base + Webcam + ADB)

**Files:**
- Create: `smoke_test_ai/drivers/screen_capture/base.py`
- Create: `smoke_test_ai/drivers/screen_capture/webcam.py`
- Create: `smoke_test_ai/drivers/screen_capture/adb_screencap.py`
- Create: `tests/test_screen_capture.py`

**Step 1: Write the failing tests**

```python
# tests/test_screen_capture.py
import pytest
import numpy as np
from unittest.mock import patch, MagicMock, PropertyMock
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
        # Crop should produce (600, 800, 3) -> y:50..650, x:100..900
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
        # Create a minimal valid PNG
        fake_png = (
            b"\x89PNG\r\n\x1a\n"
            + b"\x00" * 100
        )
        mock_run.return_value = MagicMock(
            returncode=0, stdout=fake_png, stderr=b""
        )

        cap = AdbScreenCapture(serial="FAKE")
        # We patch cv2.imdecode to return a fake image
        with patch(
            "smoke_test_ai.drivers.screen_capture.adb_screencap.cv2"
        ) as mock_cv2:
            fake_img = np.zeros((1920, 1080, 3), dtype=np.uint8)
            mock_cv2.imdecode.return_value = fake_img
            image = cap.capture()
            assert image is not None
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_screen_capture.py -v`
Expected: FAIL

**Step 3: Implement base.py**

```python
# smoke_test_ai/drivers/screen_capture/base.py
from abc import ABC, abstractmethod
import numpy as np


class ScreenCapture(ABC):
    @abstractmethod
    def capture(self) -> np.ndarray | None:
        """Capture a frame. Returns BGR numpy array or None on failure."""
        ...

    def open(self) -> None:
        """Open the capture device. Override if needed."""
        pass

    def close(self) -> None:
        """Release the capture device. Override if needed."""
        pass

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()
```

**Step 4: Implement webcam.py**

```python
# smoke_test_ai/drivers/screen_capture/webcam.py
import cv2
import numpy as np
from smoke_test_ai.drivers.screen_capture.base import ScreenCapture
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)


class WebcamCapture(ScreenCapture):
    def __init__(
        self,
        device_index: int | str = 0,
        crop: tuple[int, int, int, int] | None = None,
    ):
        self.device_index = device_index
        self.crop = crop  # (x, y, width, height)
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
```

**Step 5: Implement adb_screencap.py**

```python
# smoke_test_ai/drivers/screen_capture/adb_screencap.py
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
            result = subprocess.run(
                cmd, capture_output=True, timeout=10
            )
            if result.returncode != 0:
                logger.warning(f"screencap failed: {result.stderr}")
                return None
            img_array = np.frombuffer(result.stdout, dtype=np.uint8)
            image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            return image
        except subprocess.TimeoutExpired:
            logger.warning("screencap timed out")
            return None
```

**Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_screen_capture.py -v`
Expected: 5 passed

**Step 7: Commit**

```bash
git add smoke_test_ai/drivers/screen_capture/ tests/test_screen_capture.py
git commit -m "feat: add screen capture drivers (base, webcam, adb screencap)"
```

---

### Task 5: AOA2 HID Driver

**Files:**
- Create: `smoke_test_ai/drivers/aoa_hid.py`
- Create: `tests/test_aoa_hid.py`

**Step 1: Write the failing tests**

```python
# tests/test_aoa_hid.py
import pytest
from unittest.mock import patch, MagicMock
from smoke_test_ai.drivers.aoa_hid import AoaHidDriver, HID_KEYBOARD_DESCRIPTOR


@pytest.fixture
def mock_usb_device():
    device = MagicMock()
    device.idVendor = 0x18D1  # Google
    device.idProduct = 0x4EE2
    return device


class TestAoaHidDriver:
    def test_hid_keyboard_descriptor_exists(self):
        assert len(HID_KEYBOARD_DESCRIPTOR) > 0

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_find_device(self, mock_find, mock_usb_device):
        mock_find.return_value = mock_usb_device
        driver = AoaHidDriver(vendor_id=0x18D1, product_id=0x4EE2)
        driver.find_device()
        assert driver._device is not None

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_find_device_not_found(self, mock_find):
        mock_find.return_value = None
        driver = AoaHidDriver(vendor_id=0x18D1, product_id=0x4EE2)
        with pytest.raises(RuntimeError, match="Android device not found"):
            driver.find_device()

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_register_hid(self, mock_find, mock_usb_device):
        mock_find.return_value = mock_usb_device
        driver = AoaHidDriver(vendor_id=0x18D1, product_id=0x4EE2)
        driver.find_device()
        driver.register_hid(hid_id=1, descriptor=HID_KEYBOARD_DESCRIPTOR)
        assert mock_usb_device.ctrl_transfer.call_count == 2  # register + set descriptor

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_send_key_event(self, mock_find, mock_usb_device):
        mock_find.return_value = mock_usb_device
        driver = AoaHidDriver(vendor_id=0x18D1, product_id=0x4EE2)
        driver.find_device()
        driver.register_hid(hid_id=1, descriptor=HID_KEYBOARD_DESCRIPTOR)
        driver.send_key(hid_id=1, key_code=0x28)  # Enter key
        # 2 calls: key down + key up
        assert mock_usb_device.ctrl_transfer.call_count == 2 + 2

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_unregister_hid(self, mock_find, mock_usb_device):
        mock_find.return_value = mock_usb_device
        driver = AoaHidDriver(vendor_id=0x18D1, product_id=0x4EE2)
        driver.find_device()
        driver.register_hid(hid_id=1, descriptor=HID_KEYBOARD_DESCRIPTOR)
        driver.unregister_hid(hid_id=1)
        # register(1) + set_desc(1) + unregister(1) = 3
        assert mock_usb_device.ctrl_transfer.call_count == 3

    @patch("smoke_test_ai.drivers.aoa_hid.usb.core.find")
    def test_tap(self, mock_find, mock_usb_device):
        mock_find.return_value = mock_usb_device
        driver = AoaHidDriver(vendor_id=0x18D1, product_id=0x4EE2)
        driver.find_device()
        driver.register_mouse(hid_id=2)
        driver.tap(hid_id=2, x=540, y=960, screen_w=1080, screen_h=2400)
        # register + set_desc + at least 2 events (press + release)
        assert mock_usb_device.ctrl_transfer.call_count >= 4
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_aoa_hid.py -v`
Expected: FAIL

**Step 3: Implement aoa_hid.py**

```python
# smoke_test_ai/drivers/aoa_hid.py
import struct
import time
import usb.core
import usb.util
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)

# AOA2 control request codes
ACCESSORY_REGISTER_HID = 54
ACCESSORY_UNREGISTER_HID = 55
ACCESSORY_SET_HID_REPORT_DESC = 56
ACCESSORY_SEND_HID_EVENT = 57

# USB HID keyboard report descriptor
HID_KEYBOARD_DESCRIPTOR = bytes([
    0x05, 0x01,  # Usage Page (Generic Desktop)
    0x09, 0x06,  # Usage (Keyboard)
    0xA1, 0x01,  # Collection (Application)
    0x05, 0x07,  # Usage Page (Key Codes)
    0x19, 0xE0,  # Usage Minimum (224)
    0x29, 0xE7,  # Usage Maximum (231)
    0x15, 0x00,  # Logical Minimum (0)
    0x25, 0x01,  # Logical Maximum (1)
    0x75, 0x01,  # Report Size (1)
    0x95, 0x08,  # Report Count (8)
    0x81, 0x02,  # Input (Data, Variable, Absolute) - Modifier keys
    0x95, 0x01,  # Report Count (1)
    0x75, 0x08,  # Report Size (8)
    0x81, 0x01,  # Input (Constant) - Reserved byte
    0x95, 0x06,  # Report Count (6)
    0x75, 0x08,  # Report Size (8)
    0x15, 0x00,  # Logical Minimum (0)
    0x25, 0x65,  # Logical Maximum (101)
    0x05, 0x07,  # Usage Page (Key Codes)
    0x19, 0x00,  # Usage Minimum (0)
    0x29, 0x65,  # Usage Maximum (101)
    0x81, 0x00,  # Input (Data, Array)
    0xC0,        # End Collection
])

# USB HID mouse (absolute positioning) report descriptor
HID_MOUSE_DESCRIPTOR = bytes([
    0x05, 0x01,  # Usage Page (Generic Desktop)
    0x09, 0x02,  # Usage (Mouse)
    0xA1, 0x01,  # Collection (Application)
    0x09, 0x01,  # Usage (Pointer)
    0xA1, 0x00,  # Collection (Physical)
    0x05, 0x09,  # Usage Page (Buttons)
    0x19, 0x01,  # Usage Minimum (1)
    0x29, 0x03,  # Usage Maximum (3)
    0x15, 0x00,  # Logical Minimum (0)
    0x25, 0x01,  # Logical Maximum (1)
    0x95, 0x03,  # Report Count (3)
    0x75, 0x01,  # Report Size (1)
    0x81, 0x02,  # Input (Variable)
    0x95, 0x01,  # Report Count (1)
    0x75, 0x05,  # Report Size (5)
    0x81, 0x01,  # Input (Constant) - Padding
    0x05, 0x01,  # Usage Page (Generic Desktop)
    0x09, 0x30,  # Usage (X)
    0x09, 0x31,  # Usage (Y)
    0x16, 0x00, 0x00,  # Logical Minimum (0)
    0x26, 0x10, 0x27,  # Logical Maximum (10000)
    0x36, 0x00, 0x00,  # Physical Minimum (0)
    0x46, 0x10, 0x27,  # Physical Maximum (10000)
    0x75, 0x10,  # Report Size (16)
    0x95, 0x02,  # Report Count (2)
    0x81, 0x02,  # Input (Variable, Absolute)
    0xC0,        # End Collection (Physical)
    0xC0,        # End Collection (Application)
])


class AoaHidDriver:
    def __init__(self, vendor_id: int, product_id: int):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self._device = None

    def find_device(self) -> None:
        self._device = usb.core.find(
            idVendor=self.vendor_id, idProduct=self.product_id
        )
        if self._device is None:
            raise RuntimeError(
                f"Android device not found "
                f"(VID=0x{self.vendor_id:04X}, PID=0x{self.product_id:04X})"
            )
        logger.info(f"Found device: VID=0x{self.vendor_id:04X} PID=0x{self.product_id:04X}")

    def register_hid(self, hid_id: int, descriptor: bytes) -> None:
        if self._device is None:
            raise RuntimeError("Device not found. Call find_device() first.")
        # ACCESSORY_REGISTER_HID
        self._device.ctrl_transfer(
            0x40,  # USB_DIR_OUT | USB_TYPE_VENDOR
            ACCESSORY_REGISTER_HID,
            hid_id,
            len(descriptor),
        )
        # ACCESSORY_SET_HID_REPORT_DESC
        self._device.ctrl_transfer(
            0x40,
            ACCESSORY_SET_HID_REPORT_DESC,
            hid_id,
            0,
            descriptor,
        )
        logger.info(f"Registered HID device {hid_id}, descriptor size={len(descriptor)}")

    def unregister_hid(self, hid_id: int) -> None:
        if self._device is None:
            return
        self._device.ctrl_transfer(
            0x40,
            ACCESSORY_UNREGISTER_HID,
            hid_id,
            0,
        )
        logger.info(f"Unregistered HID device {hid_id}")

    def send_hid_event(self, hid_id: int, data: bytes) -> None:
        if self._device is None:
            raise RuntimeError("Device not found.")
        self._device.ctrl_transfer(
            0x40,
            ACCESSORY_SEND_HID_EVENT,
            hid_id,
            0,
            data,
        )

    def register_mouse(self, hid_id: int) -> None:
        self.register_hid(hid_id, HID_MOUSE_DESCRIPTOR)

    def send_key(self, hid_id: int, key_code: int, modifiers: int = 0) -> None:
        # Key down: [modifiers, reserved, key_code, 0, 0, 0, 0, 0]
        report = struct.pack("BBBBBBBB", modifiers, 0, key_code, 0, 0, 0, 0, 0)
        self.send_hid_event(hid_id, report)
        time.sleep(0.05)
        # Key up: all zeros
        report = struct.pack("BBBBBBBB", 0, 0, 0, 0, 0, 0, 0, 0)
        self.send_hid_event(hid_id, report)

    def tap(
        self,
        hid_id: int,
        x: int,
        y: int,
        screen_w: int = 1080,
        screen_h: int = 2400,
    ) -> None:
        # Convert screen coordinates to 0-10000 range
        abs_x = int((x / screen_w) * 10000)
        abs_y = int((y / screen_h) * 10000)
        # Mouse press: button1=1, x, y
        report = struct.pack("<BHH", 0x01, abs_x, abs_y)
        self.send_hid_event(hid_id, report)
        time.sleep(0.1)
        # Mouse release: button=0, x, y
        report = struct.pack("<BHH", 0x00, abs_x, abs_y)
        self.send_hid_event(hid_id, report)

    def swipe(
        self,
        hid_id: int,
        x1: int, y1: int,
        x2: int, y2: int,
        screen_w: int = 1080,
        screen_h: int = 2400,
        steps: int = 10,
        duration: float = 0.3,
    ) -> None:
        delay = duration / steps
        for i in range(steps + 1):
            t = i / steps
            cx = int(x1 + (x2 - x1) * t)
            cy = int(y1 + (y2 - y1) * t)
            abs_x = int((cx / screen_w) * 10000)
            abs_y = int((cy / screen_h) * 10000)
            button = 0x01  # held down
            report = struct.pack("<BHH", button, abs_x, abs_y)
            self.send_hid_event(hid_id, report)
            time.sleep(delay)
        # Release
        report = struct.pack("<BHH", 0x00, abs_x, abs_y)
        self.send_hid_event(hid_id, report)

    def close(self) -> None:
        self._device = None
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_aoa_hid.py -v`
Expected: 7 passed

**Step 5: Commit**

```bash
git add smoke_test_ai/drivers/aoa_hid.py tests/test_aoa_hid.py
git commit -m "feat: add AOA2 HID driver with keyboard, mouse tap, and swipe support"
```

---

### Task 6: Flash Controller Drivers

**Files:**
- Create: `smoke_test_ai/drivers/flash/base.py`
- Create: `smoke_test_ai/drivers/flash/fastboot.py`
- Create: `smoke_test_ai/drivers/flash/custom.py`
- Create: `tests/test_flash.py`

**Step 1: Write the failing tests**

```python
# tests/test_flash.py
import pytest
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
        config = {
            "images": [{"partition": "system", "file": "/path/system.img"}],
        }
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
        assert mock_run.call_count >= 2  # flash + reboot


class TestCustomFlashDriver:
    @patch("smoke_test_ai.drivers.flash.custom.subprocess.run")
    def test_custom_commands(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        driver = CustomFlashDriver()
        config = {
            "commands": [
                "tool flash --image /path/system.img",
                "tool reboot",
            ],
        }
        driver.flash(config)
        assert mock_run.call_count == 2
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_flash.py -v`
Expected: FAIL

**Step 3: Implement base.py**

```python
# smoke_test_ai/drivers/flash/base.py
from abc import ABC, abstractmethod


class FlashDriver(ABC):
    @abstractmethod
    def flash(self, config: dict) -> None:
        """Flash images to device based on config."""
        ...
```

**Step 4: Implement fastboot.py**

```python
# smoke_test_ai/drivers/flash/fastboot.py
import subprocess
from smoke_test_ai.drivers.flash.base import FlashDriver
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)


class FastbootFlashDriver(FlashDriver):
    def __init__(self, serial: str | None = None, fastboot_path: str = "fastboot"):
        self.serial = serial
        self.fastboot_path = fastboot_path

    def _run(self, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
        cmd = [self.fastboot_path]
        if self.serial:
            cmd.extend(["-s", self.serial])
        cmd.extend(args)
        logger.info(f"Fastboot: {' '.join(cmd)}")
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def flash(self, config: dict) -> None:
        for pre_cmd in config.get("pre_flash", []):
            logger.info(f"Pre-flash: {pre_cmd}")
            subprocess.run(pre_cmd.split(), capture_output=True, text=True, timeout=60)

        for image in config.get("images", []):
            partition = image["partition"]
            file_path = image["file"]
            logger.info(f"Flashing {partition}: {file_path}")
            result = self._run("flash", partition, file_path)
            if result.returncode != 0:
                raise RuntimeError(
                    f"Flash failed for {partition}: {result.stderr}"
                )

        for post_cmd in config.get("post_flash", []):
            logger.info(f"Post-flash: {post_cmd}")
            subprocess.run(post_cmd.split(), capture_output=True, text=True, timeout=60)
```

**Step 5: Implement custom.py**

```python
# smoke_test_ai/drivers/flash/custom.py
import subprocess
from smoke_test_ai.drivers.flash.base import FlashDriver
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)


class CustomFlashDriver(FlashDriver):
    def flash(self, config: dict) -> None:
        for cmd_str in config.get("commands", []):
            logger.info(f"Custom flash: {cmd_str}")
            result = subprocess.run(
                cmd_str, shell=True, capture_output=True, text=True, timeout=600
            )
            if result.returncode != 0:
                raise RuntimeError(f"Custom flash failed: {cmd_str}\n{result.stderr}")
```

**Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_flash.py -v`
Expected: 4 passed

**Step 7: Commit**

```bash
git add smoke_test_ai/drivers/flash/ tests/test_flash.py
git commit -m "feat: add flash drivers (base, fastboot, custom command)"
```

---

### Task 7: LLM Client & Visual Analyzer

**Files:**
- Create: `smoke_test_ai/ai/llm_client.py`
- Create: `smoke_test_ai/ai/visual_analyzer.py`
- Create: `tests/test_ai.py`

**Step 1: Write the failing tests**

```python
# tests/test_ai.py
import pytest
import json
import numpy as np
from unittest.mock import patch, MagicMock, AsyncMock
from smoke_test_ai.ai.llm_client import LlmClient
from smoke_test_ai.ai.visual_analyzer import VisualAnalyzer


class TestLlmClient:
    def test_init_ollama(self):
        client = LlmClient(
            provider="ollama",
            base_url="http://localhost:11434",
            vision_model="llava:13b",
            text_model="llama3:8b",
        )
        assert client.provider == "ollama"

    @patch("smoke_test_ai.ai.llm_client.httpx.Client")
    def test_chat_text(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Hello world"}
        }
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = LlmClient(
            provider="ollama",
            base_url="http://localhost:11434",
            text_model="llama3:8b",
        )
        result = client.chat("Say hello")
        assert result == "Hello world"

    @patch("smoke_test_ai.ai.llm_client.httpx.Client")
    def test_chat_vision(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": '{"screen_state": "home", "completed": true}'}
        }
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        client = LlmClient(
            provider="ollama",
            base_url="http://localhost:11434",
            vision_model="llava:13b",
        )
        fake_image = np.zeros((100, 100, 3), dtype=np.uint8)
        result = client.chat_vision("What do you see?", fake_image)
        assert "completed" in result


class TestVisualAnalyzer:
    @patch("smoke_test_ai.ai.llm_client.httpx.Client")
    def test_analyze_setup_wizard(self, mock_client_cls):
        response_json = {
            "screen_state": "language_selection",
            "completed": False,
            "action": {"type": "tap", "x": 540, "y": 1200},
            "confidence": 0.95,
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": json.dumps(response_json)}
        }
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        llm = LlmClient(
            provider="ollama",
            base_url="http://localhost:11434",
            vision_model="llava:13b",
        )
        analyzer = VisualAnalyzer(llm)
        fake_image = np.zeros((1920, 1080, 3), dtype=np.uint8)
        result = analyzer.analyze_setup_wizard(fake_image)

        assert result["screen_state"] == "language_selection"
        assert result["completed"] is False
        assert result["action"]["type"] == "tap"

    @patch("smoke_test_ai.ai.llm_client.httpx.Client")
    def test_analyze_test_screenshot(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": '{"pass": true, "reason": "Screen looks normal"}'}
        }
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        llm = LlmClient(
            provider="ollama",
            base_url="http://localhost:11434",
            vision_model="llava:13b",
        )
        analyzer = VisualAnalyzer(llm)
        fake_image = np.zeros((1920, 1080, 3), dtype=np.uint8)
        result = analyzer.analyze_test_screenshot(
            fake_image, "Is the screen normal?"
        )
        assert result["pass"] is True
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ai.py -v`
Expected: FAIL

**Step 3: Implement llm_client.py**

```python
# smoke_test_ai/ai/llm_client.py
import base64
import httpx
import cv2
import numpy as np
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)


class LlmClient:
    def __init__(
        self,
        provider: str = "ollama",
        base_url: str = "http://localhost:11434",
        vision_model: str | None = None,
        text_model: str | None = None,
        api_key: str | None = None,
        timeout: int = 30,
    ):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.vision_model = vision_model
        self.text_model = text_model
        self.api_key = api_key
        self.timeout = timeout

    def _get_client(self) -> httpx.Client:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
        )

    def _image_to_base64(self, image: np.ndarray) -> str:
        _, buffer = cv2.imencode(".jpg", image)
        return base64.b64encode(buffer).decode("utf-8")

    def chat(self, prompt: str, model: str | None = None) -> str:
        model = model or self.text_model
        if not model:
            raise ValueError("No text model configured")

        if self.provider == "ollama":
            return self._ollama_chat(prompt, model)
        else:
            return self._openai_compatible_chat(prompt, model)

    def chat_vision(
        self, prompt: str, image: np.ndarray, model: str | None = None
    ) -> str:
        model = model or self.vision_model
        if not model:
            raise ValueError("No vision model configured")

        image_b64 = self._image_to_base64(image)

        if self.provider == "ollama":
            return self._ollama_chat_vision(prompt, image_b64, model)
        else:
            return self._openai_compatible_chat_vision(prompt, image_b64, model)

    def _ollama_chat(self, prompt: str, model: str) -> str:
        with self._get_client() as client:
            response = client.post(
                "/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
            )
            response.raise_for_status()
            return response.json()["message"]["content"]

    def _ollama_chat_vision(
        self, prompt: str, image_b64: str, model: str
    ) -> str:
        with self._get_client() as client:
            response = client.post(
                "/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [image_b64],
                        }
                    ],
                    "stream": False,
                },
            )
            response.raise_for_status()
            return response.json()["message"]["content"]

    def _openai_compatible_chat(self, prompt: str, model: str) -> str:
        with self._get_client() as client:
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    def _openai_compatible_chat_vision(
        self, prompt: str, image_b64: str, model: str
    ) -> str:
        with self._get_client() as client:
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_b64}"
                                    },
                                },
                            ],
                        }
                    ],
                },
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
```

**Step 4: Implement visual_analyzer.py**

```python
# smoke_test_ai/ai/visual_analyzer.py
import json
import numpy as np
from smoke_test_ai.ai.llm_client import LlmClient
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)

SETUP_WIZARD_PROMPT = """You are an Android Setup Wizard automation assistant.
Analyze this screenshot and determine:
1. What step of the Setup Wizard is currently displayed?
2. What action should be taken? (tap coordinates, swipe direction, type text, or wait)
3. Is the Setup Wizard complete (home screen / launcher visible)?

Return ONLY valid JSON:
{
  "screen_state": "language_selection | wifi_setup | google_login | terms | pin_setup | home | unknown",
  "completed": false,
  "action": {
    "type": "tap | swipe | type | wait",
    "x": 540,
    "y": 1200,
    "text": "",
    "direction": "up | down | left | right",
    "wait_seconds": 0
  },
  "confidence": 0.95
}"""

TEST_SCREENSHOT_PROMPT = """Analyze this Android device screenshot for testing.
Question: {question}

Return ONLY valid JSON:
{{
  "pass": true,
  "reason": "explanation"
}}"""


class VisualAnalyzer:
    def __init__(self, llm: LlmClient):
        self.llm = llm

    def analyze_setup_wizard(self, image: np.ndarray) -> dict:
        response = self.llm.chat_vision(SETUP_WIZARD_PROMPT, image)
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response: {response}")
            return {
                "screen_state": "unknown",
                "completed": False,
                "action": {"type": "wait", "wait_seconds": 3},
                "confidence": 0.0,
            }

    def analyze_test_screenshot(self, image: np.ndarray, question: str) -> dict:
        prompt = TEST_SCREENSHOT_PROMPT.format(question=question)
        response = self.llm.chat_vision(prompt, image)
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response: {response}")
            return {"pass": False, "reason": f"LLM parse error: {response}"}

    def generate_report_summary(self, results_json: str) -> str:
        prompt = (
            "Summarize the following Android smoke test results. "
            "Highlight failures and provide recommendations.\n\n"
            f"{results_json}"
        )
        return self.llm.chat(prompt)
```

**Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_ai.py -v`
Expected: 5 passed

**Step 6: Commit**

```bash
git add smoke_test_ai/ai/ tests/test_ai.py
git commit -m "feat: add LLM client (Ollama + OpenAI-compatible) and visual analyzer"
```

---

### Task 8: Test Runner Engine

**Files:**
- Create: `smoke_test_ai/core/test_runner.py`
- Create: `tests/test_runner.py`

**Step 1: Write the failing tests**

```python
# tests/test_runner.py
import pytest
from unittest.mock import patch, MagicMock
from smoke_test_ai.core.test_runner import TestRunner, TestResult, TestStatus


@pytest.fixture
def mock_adb():
    adb = MagicMock()
    adb.serial = "FAKE"
    return adb


@pytest.fixture
def runner(mock_adb):
    return TestRunner(adb=mock_adb)


class TestTestResult:
    def test_pass_result(self):
        r = TestResult(id="t1", name="Test1", status=TestStatus.PASS)
        assert r.passed

    def test_fail_result(self):
        r = TestResult(
            id="t1", name="Test1", status=TestStatus.FAIL, message="oops"
        )
        assert not r.passed
        assert r.message == "oops"


class TestTestRunner:
    def test_run_adb_check_pass(self, runner, mock_adb):
        mock_adb.shell.return_value = MagicMock(
            returncode=0, stdout="1\n", stderr=""
        )
        test_case = {
            "id": "boot",
            "name": "Boot check",
            "type": "adb_check",
            "command": "getprop sys.boot_completed",
            "expected": "1",
        }
        result = runner.run_test(test_case)
        assert result.status == TestStatus.PASS

    def test_run_adb_check_fail(self, runner, mock_adb):
        mock_adb.shell.return_value = MagicMock(
            returncode=0, stdout="0\n", stderr=""
        )
        test_case = {
            "id": "boot",
            "name": "Boot check",
            "type": "adb_check",
            "command": "getprop sys.boot_completed",
            "expected": "1",
        }
        result = runner.run_test(test_case)
        assert result.status == TestStatus.FAIL

    def test_run_adb_shell_expected_contains(self, runner, mock_adb):
        mock_adb.shell.return_value = MagicMock(
            returncode=0, stdout="Wi-Fi is enabled\n", stderr=""
        )
        test_case = {
            "id": "wifi",
            "name": "WiFi check",
            "type": "adb_shell",
            "command": "dumpsys wifi | grep 'Wi-Fi is'",
            "expected_contains": "enabled",
        }
        result = runner.run_test(test_case)
        assert result.status == TestStatus.PASS

    def test_run_adb_shell_expected_not_contains(self, runner, mock_adb):
        mock_adb.shell.return_value = MagicMock(
            returncode=0, stdout="STATE_IN_SERVICE\n", stderr=""
        )
        test_case = {
            "id": "sim",
            "name": "SIM check",
            "type": "adb_shell",
            "command": "dumpsys telephony.registry",
            "expected_not_contains": "OUT_OF_SERVICE",
        }
        result = runner.run_test(test_case)
        assert result.status == TestStatus.PASS

    def test_run_suite(self, runner, mock_adb):
        mock_adb.shell.return_value = MagicMock(
            returncode=0, stdout="1\n", stderr=""
        )
        suite = {
            "test_suite": {
                "name": "Basic",
                "timeout": 60,
                "tests": [
                    {
                        "id": "t1",
                        "name": "Test1",
                        "type": "adb_check",
                        "command": "getprop sys.boot_completed",
                        "expected": "1",
                    },
                    {
                        "id": "t2",
                        "name": "Test2",
                        "type": "adb_check",
                        "command": "getprop ro.build.type",
                        "expected": "1",
                    },
                ],
            }
        }
        results = runner.run_suite(suite)
        assert len(results) == 2

    def test_unknown_test_type_errors(self, runner):
        test_case = {"id": "bad", "name": "Bad", "type": "nonexistent"}
        result = runner.run_test(test_case)
        assert result.status == TestStatus.ERROR
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_runner.py -v`
Expected: FAIL

**Step 3: Implement test_runner.py**

```python
# smoke_test_ai/core/test_runner.py
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from smoke_test_ai.drivers.adb_controller import AdbController
from smoke_test_ai.ai.visual_analyzer import VisualAnalyzer
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)


class TestStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


@dataclass
class TestResult:
    id: str
    name: str
    status: TestStatus
    message: str = ""
    duration: float = 0.0
    screenshot_path: str | None = None

    @property
    def passed(self) -> bool:
        return self.status == TestStatus.PASS

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "duration": self.duration,
            "screenshot_path": self.screenshot_path,
        }


class TestRunner:
    def __init__(
        self,
        adb: AdbController,
        visual_analyzer: VisualAnalyzer | None = None,
        screen_capture=None,
    ):
        self.adb = adb
        self.visual_analyzer = visual_analyzer
        self.screen_capture = screen_capture

    def run_suite(self, suite_config: dict) -> list[TestResult]:
        suite = suite_config["test_suite"]
        logger.info(f"Running test suite: {suite['name']}")
        results = []
        for test_case in suite["tests"]:
            result = self.run_test(test_case)
            results.append(result)
            status_icon = "PASS" if result.passed else result.status.value
            logger.info(f"  [{status_icon}] {result.name}: {result.message}")
        return results

    def run_test(self, test_case: dict) -> TestResult:
        test_id = test_case["id"]
        test_name = test_case["name"]
        test_type = test_case["type"]
        start_time = time.time()

        try:
            if test_type == "adb_check":
                result = self._run_adb_check(test_case)
            elif test_type == "adb_shell":
                result = self._run_adb_shell(test_case)
            elif test_type == "screenshot_llm":
                result = self._run_screenshot_llm(test_case)
            elif test_type == "apk_instrumentation":
                result = self._run_apk_instrumentation(test_case)
            else:
                result = TestResult(
                    id=test_id,
                    name=test_name,
                    status=TestStatus.ERROR,
                    message=f"Unknown test type: {test_type}",
                )
        except Exception as e:
            result = TestResult(
                id=test_id,
                name=test_name,
                status=TestStatus.ERROR,
                message=str(e),
            )

        result.duration = time.time() - start_time
        return result

    def _run_adb_check(self, tc: dict) -> TestResult:
        proc = self.adb.shell(tc["command"])
        actual = proc.stdout.strip()
        expected = tc["expected"]
        if actual == expected:
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS)
        return TestResult(
            id=tc["id"],
            name=tc["name"],
            status=TestStatus.FAIL,
            message=f"Expected '{expected}', got '{actual}'",
        )

    def _run_adb_shell(self, tc: dict) -> TestResult:
        proc = self.adb.shell(tc["command"])
        output = proc.stdout.strip()

        if "expected_contains" in tc:
            if tc["expected_contains"] in output:
                return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS)
            return TestResult(
                id=tc["id"],
                name=tc["name"],
                status=TestStatus.FAIL,
                message=f"Output does not contain '{tc['expected_contains']}'",
            )

        if "expected_not_contains" in tc:
            if tc["expected_not_contains"] not in output:
                return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS)
            return TestResult(
                id=tc["id"],
                name=tc["name"],
                status=TestStatus.FAIL,
                message=f"Output contains '{tc['expected_not_contains']}'",
            )

        if "expected_pattern" in tc:
            if re.search(tc["expected_pattern"], output):
                return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS)
            return TestResult(
                id=tc["id"],
                name=tc["name"],
                status=TestStatus.FAIL,
                message=f"Output does not match pattern '{tc['expected_pattern']}'",
            )

        # No assertion — just check return code
        if proc.returncode == 0:
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS)
        return TestResult(
            id=tc["id"],
            name=tc["name"],
            status=TestStatus.FAIL,
            message=f"Command failed with exit code {proc.returncode}",
        )

    def _run_screenshot_llm(self, tc: dict) -> TestResult:
        if not self.visual_analyzer or not self.screen_capture:
            return TestResult(
                id=tc["id"],
                name=tc["name"],
                status=TestStatus.SKIP,
                message="Visual analyzer or screen capture not configured",
            )
        image = self.screen_capture.capture()
        if image is None:
            return TestResult(
                id=tc["id"],
                name=tc["name"],
                status=TestStatus.ERROR,
                message="Failed to capture screen",
            )
        result = self.visual_analyzer.analyze_test_screenshot(image, tc["prompt"])
        if result.get("pass", False):
            return TestResult(
                id=tc["id"],
                name=tc["name"],
                status=TestStatus.PASS,
                message=result.get("reason", ""),
            )
        return TestResult(
            id=tc["id"],
            name=tc["name"],
            status=TestStatus.FAIL,
            message=result.get("reason", "LLM judged as fail"),
        )

    def _run_apk_instrumentation(self, tc: dict) -> TestResult:
        package = tc["package"]
        runner = tc.get("runner", "androidx.test.runner.AndroidJUnitRunner")
        timeout = tc.get("timeout", 120)
        proc = self.adb.shell(
            f"am instrument -w {package}/{runner}",
            timeout=timeout,
        )
        if "OK (" in proc.stdout:
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS)
        return TestResult(
            id=tc["id"],
            name=tc["name"],
            status=TestStatus.FAIL,
            message=proc.stdout[:500],
        )
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_runner.py -v`
Expected: 7 passed

**Step 5: Commit**

```bash
git add smoke_test_ai/core/test_runner.py tests/test_runner.py
git commit -m "feat: add test runner engine with adb_check, adb_shell, screenshot_llm, apk_instrumentation"
```

---

### Task 9: Reporting (CLI + JSON + HTML)

**Files:**
- Create: `smoke_test_ai/reporting/cli_reporter.py`
- Create: `smoke_test_ai/reporting/json_reporter.py`
- Create: `smoke_test_ai/reporting/html_reporter.py`
- Create: `templates/report.html`
- Create: `tests/test_reporting.py`

**Step 1: Write the failing tests**

```python
# tests/test_reporting.py
import json
import pytest
from pathlib import Path
from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.reporting.json_reporter import JsonReporter
from smoke_test_ai.reporting.html_reporter import HtmlReporter


@pytest.fixture
def sample_results():
    return [
        TestResult(id="t1", name="Boot check", status=TestStatus.PASS, duration=0.5),
        TestResult(
            id="t2",
            name="WiFi check",
            status=TestStatus.FAIL,
            message="Not connected",
            duration=1.2,
        ),
        TestResult(id="t3", name="SIM check", status=TestStatus.PASS, duration=0.3),
    ]


class TestJsonReporter:
    def test_generate(self, sample_results, tmp_path):
        output = tmp_path / "results.json"
        reporter = JsonReporter()
        reporter.generate(
            results=sample_results,
            suite_name="Basic Smoke",
            device_name="Product-A",
            output_path=output,
        )
        assert output.exists()
        data = json.loads(output.read_text())
        assert data["suite_name"] == "Basic Smoke"
        assert data["device_name"] == "Product-A"
        assert len(data["tests"]) == 3
        assert data["summary"]["total"] == 3
        assert data["summary"]["passed"] == 2
        assert data["summary"]["failed"] == 1


class TestHtmlReporter:
    def test_generate(self, sample_results, tmp_path):
        output = tmp_path / "report.html"
        reporter = HtmlReporter(
            template_dir=Path(__file__).parent.parent / "templates"
        )
        reporter.generate(
            results=sample_results,
            suite_name="Basic Smoke",
            device_name="Product-A",
            output_path=output,
        )
        assert output.exists()
        html = output.read_text()
        assert "Basic Smoke" in html
        assert "Product-A" in html
        assert "PASS" in html
        assert "FAIL" in html
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_reporting.py -v`
Expected: FAIL

**Step 3: Implement cli_reporter.py**

```python
# smoke_test_ai/reporting/cli_reporter.py
from rich.console import Console
from rich.table import Table
from smoke_test_ai.core.test_runner import TestResult, TestStatus

console = Console()


class CliReporter:
    def print_results(
        self, results: list[TestResult], suite_name: str, device_name: str
    ) -> None:
        table = Table(title=f"Smoke Test Results: {suite_name} @ {device_name}")
        table.add_column("ID", style="dim")
        table.add_column("Test Name")
        table.add_column("Status")
        table.add_column("Duration", justify="right")
        table.add_column("Message")

        for r in results:
            status_style = {
                TestStatus.PASS: "[bold green]PASS[/]",
                TestStatus.FAIL: "[bold red]FAIL[/]",
                TestStatus.SKIP: "[bold yellow]SKIP[/]",
                TestStatus.ERROR: "[bold red]ERROR[/]",
            }.get(r.status, r.status.value)

            table.add_row(
                r.id, r.name, status_style, f"{r.duration:.2f}s", r.message
            )

        console.print(table)

        passed = sum(1 for r in results if r.passed)
        total = len(results)
        console.print(
            f"\n[bold]Summary:[/] {passed}/{total} passed "
            f"({'[green]ALL PASS[/]' if passed == total else '[red]HAS FAILURES[/]'})"
        )
```

**Step 4: Implement json_reporter.py**

```python
# smoke_test_ai/reporting/json_reporter.py
import json
from datetime import datetime
from pathlib import Path
from smoke_test_ai.core.test_runner import TestResult


class JsonReporter:
    def generate(
        self,
        results: list[TestResult],
        suite_name: str,
        device_name: str,
        output_path: Path,
    ) -> None:
        passed = sum(1 for r in results if r.passed)
        data = {
            "suite_name": suite_name,
            "device_name": device_name,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": len(results) - passed,
            },
            "tests": [r.to_dict() for r in results],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
```

**Step 5: Implement html_reporter.py**

```python
# smoke_test_ai/reporting/html_reporter.py
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from smoke_test_ai.core.test_runner import TestResult


class HtmlReporter:
    def __init__(self, template_dir: Path | None = None):
        if template_dir is None:
            template_dir = Path(__file__).parent.parent.parent / "templates"
        self.env = Environment(loader=FileSystemLoader(str(template_dir)))

    def generate(
        self,
        results: list[TestResult],
        suite_name: str,
        device_name: str,
        output_path: Path,
    ) -> None:
        passed = sum(1 for r in results if r.passed)
        template = self.env.get_template("report.html")
        html = template.render(
            suite_name=suite_name,
            device_name=device_name,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
            results=[r.to_dict() for r in results],
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html)
```

**Step 6: Create templates/report.html**

```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>Smoke Test Report - {{ suite_name }}</title>
<style>
  body { font-family: -apple-system, sans-serif; margin: 40px; background: #f5f5f5; }
  h1 { color: #333; }
  .summary { display: flex; gap: 20px; margin: 20px 0; }
  .card { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
  .card.pass { border-left: 4px solid #4caf50; }
  .card.fail { border-left: 4px solid #f44336; }
  .card h3 { margin: 0 0 8px 0; color: #666; font-size: 14px; }
  .card .value { font-size: 32px; font-weight: bold; }
  table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
  th { background: #333; color: white; padding: 12px; text-align: left; }
  td { padding: 10px 12px; border-bottom: 1px solid #eee; }
  .status-PASS { color: #4caf50; font-weight: bold; }
  .status-FAIL { color: #f44336; font-weight: bold; }
  .status-SKIP { color: #ff9800; font-weight: bold; }
  .status-ERROR { color: #f44336; font-weight: bold; }
  .meta { color: #999; font-size: 14px; margin-bottom: 20px; }
</style>
</head>
<body>
<h1>Smoke Test Report</h1>
<p class="meta">Suite: {{ suite_name }} | Device: {{ device_name }} | {{ timestamp }}</p>
<div class="summary">
  <div class="card"><h3>Total</h3><div class="value">{{ total }}</div></div>
  <div class="card pass"><h3>Passed</h3><div class="value" style="color:#4caf50">{{ passed }}</div></div>
  <div class="card fail"><h3>Failed</h3><div class="value" style="color:#f44336">{{ failed }}</div></div>
</div>
<table>
  <tr><th>ID</th><th>Test Name</th><th>Status</th><th>Duration</th><th>Message</th></tr>
  {% for r in results %}
  <tr>
    <td>{{ r.id }}</td>
    <td>{{ r.name }}</td>
    <td class="status-{{ r.status }}">{{ r.status }}</td>
    <td>{{ "%.2f"|format(r.duration) }}s</td>
    <td>{{ r.message }}</td>
  </tr>
  {% endfor %}
</table>
</body>
</html>
```

**Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_reporting.py -v`
Expected: 2 passed

**Step 8: Commit**

```bash
git add smoke_test_ai/reporting/ templates/report.html tests/test_reporting.py
git commit -m "feat: add reporters (CLI with Rich, JSON, HTML with Jinja2 template)"
```

---

### Task 10: Orchestrator & CLI

**Files:**
- Create: `smoke_test_ai/core/orchestrator.py`
- Create: `smoke_test_ai/ai/setup_wizard_agent.py`
- Create: `cli.py`
- Create: `config/devices/product_a.yaml`
- Create: `config/test_suites/smoke_basic.yaml`
- Create: `tests/test_orchestrator.py`

**Step 1: Write the failing tests**

```python
# tests/test_orchestrator.py
import pytest
from unittest.mock import patch, MagicMock
from smoke_test_ai.core.orchestrator import Orchestrator


@pytest.fixture
def settings():
    return {
        "llm": {
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "vision_model": "llava:13b",
            "text_model": "llama3:8b",
            "timeout": 30,
        },
        "wifi": {"ssid": "TestLab", "password": "pass123"},
        "reporting": {
            "formats": ["cli", "json"],
            "output_dir": "results/",
            "screenshots": True,
        },
        "parallel": {"max_devices": 4, "per_device_timeout": 900},
    }


@pytest.fixture
def device_config():
    return {
        "device": {
            "name": "Product-A",
            "build_type": "user",
            "screen_resolution": [1080, 2400],
            "flash": {"profile": "fastboot"},
            "screen_capture": {"method": "adb"},
            "setup_wizard": {"method": "llm_vision", "max_steps": 30, "timeout": 300},
        }
    }


class TestOrchestrator:
    def test_init(self, settings, device_config):
        orch = Orchestrator(settings=settings, device_config=device_config)
        assert orch.device_name == "Product-A"

    def test_select_flash_driver(self, settings, device_config):
        orch = Orchestrator(settings=settings, device_config=device_config)
        driver = orch._get_flash_driver(serial="FAKE")
        assert driver is not None

    def test_select_screen_capture_adb(self, settings, device_config):
        orch = Orchestrator(settings=settings, device_config=device_config)
        cap = orch._get_screen_capture(serial="FAKE")
        assert cap is not None
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL

**Step 3: Implement setup_wizard_agent.py**

```python
# smoke_test_ai/ai/setup_wizard_agent.py
import time
from smoke_test_ai.drivers.aoa_hid import AoaHidDriver
from smoke_test_ai.drivers.screen_capture.base import ScreenCapture
from smoke_test_ai.ai.visual_analyzer import VisualAnalyzer
from smoke_test_ai.drivers.adb_controller import AdbController
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)


class SetupWizardAgent:
    def __init__(
        self,
        hid: AoaHidDriver,
        screen_capture: ScreenCapture,
        analyzer: VisualAnalyzer,
        adb: AdbController,
        screen_w: int = 1080,
        screen_h: int = 2400,
        hid_id: int = 2,
        max_steps: int = 30,
        timeout: int = 300,
    ):
        self.hid = hid
        self.screen_capture = screen_capture
        self.analyzer = analyzer
        self.adb = adb
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.hid_id = hid_id
        self.max_steps = max_steps
        self.timeout = timeout

    def run(self) -> bool:
        logger.info("Starting Setup Wizard automation...")
        deadline = time.time() + self.timeout

        for step in range(self.max_steps):
            if time.time() > deadline:
                logger.warning("Setup Wizard timeout")
                return False

            if self.adb.is_connected():
                boot = self.adb.getprop("sys.boot_completed")
                if boot == "1":
                    logger.info("ADB connected and boot completed — Setup Wizard done")
                    return True

            image = self.screen_capture.capture()
            if image is None:
                logger.warning(f"Step {step}: Failed to capture screen, waiting...")
                time.sleep(3)
                continue

            analysis = self.analyzer.analyze_setup_wizard(image)
            logger.info(
                f"Step {step}: state={analysis['screen_state']} "
                f"confidence={analysis.get('confidence', 0):.2f}"
            )

            if analysis.get("completed", False):
                logger.info("LLM reports Setup Wizard completed")
                return True

            action = analysis.get("action", {})
            self._execute_action(action)
            time.sleep(1)

        logger.warning(f"Setup Wizard did not complete within {self.max_steps} steps")
        return False

    def _execute_action(self, action: dict) -> None:
        action_type = action.get("type", "wait")

        if action_type == "tap":
            x, y = action.get("x", 540), action.get("y", 960)
            logger.info(f"  Action: tap ({x}, {y})")
            self.hid.tap(self.hid_id, x, y, self.screen_w, self.screen_h)

        elif action_type == "swipe":
            direction = action.get("direction", "up")
            cx, cy = self.screen_w // 2, self.screen_h // 2
            offsets = {
                "up": (cx, cy + 400, cx, cy - 400),
                "down": (cx, cy - 400, cx, cy + 400),
                "left": (cx + 400, cy, cx - 400, cy),
                "right": (cx - 400, cy, cx + 400, cy),
            }
            x1, y1, x2, y2 = offsets.get(direction, offsets["up"])
            logger.info(f"  Action: swipe {direction}")
            self.hid.swipe(self.hid_id, x1, y1, x2, y2, self.screen_w, self.screen_h)

        elif action_type == "type":
            text = action.get("text", "")
            logger.info(f"  Action: type '{text}'")
            # Type via ADB if available, otherwise skip
            if self.adb.is_connected():
                self.adb.shell(f"input text '{text}'")

        elif action_type == "wait":
            wait_sec = action.get("wait_seconds", 3)
            logger.info(f"  Action: wait {wait_sec}s")
            time.sleep(wait_sec)
```

**Step 4: Implement orchestrator.py**

```python
# smoke_test_ai/core/orchestrator.py
import time
from pathlib import Path
from smoke_test_ai.drivers.adb_controller import AdbController
from smoke_test_ai.drivers.flash.base import FlashDriver
from smoke_test_ai.drivers.flash.fastboot import FastbootFlashDriver
from smoke_test_ai.drivers.flash.custom import CustomFlashDriver
from smoke_test_ai.drivers.screen_capture.base import ScreenCapture
from smoke_test_ai.drivers.screen_capture.webcam import WebcamCapture
from smoke_test_ai.drivers.screen_capture.adb_screencap import AdbScreenCapture
from smoke_test_ai.ai.llm_client import LlmClient
from smoke_test_ai.ai.visual_analyzer import VisualAnalyzer
from smoke_test_ai.ai.setup_wizard_agent import SetupWizardAgent
from smoke_test_ai.core.test_runner import TestRunner, TestResult
from smoke_test_ai.reporting.cli_reporter import CliReporter
from smoke_test_ai.reporting.json_reporter import JsonReporter
from smoke_test_ai.reporting.html_reporter import HtmlReporter
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)


class Orchestrator:
    def __init__(self, settings: dict, device_config: dict):
        self.settings = settings
        self.device_config = device_config["device"]
        self.device_name = self.device_config["name"]

    def _get_flash_driver(self, serial: str | None = None) -> FlashDriver:
        profile = self.device_config["flash"]["profile"]
        if profile == "fastboot":
            return FastbootFlashDriver(serial=serial)
        elif profile == "custom":
            return CustomFlashDriver()
        raise ValueError(f"Unknown flash profile: {profile}")

    def _get_screen_capture(self, serial: str | None = None) -> ScreenCapture:
        method = self.device_config.get("screen_capture", {}).get("method", "adb")
        if method == "adb":
            return AdbScreenCapture(serial=serial)
        elif method == "webcam":
            sc = self.device_config["screen_capture"]
            return WebcamCapture(
                device_index=sc.get("webcam_device", 0),
                crop=tuple(sc["webcam_crop"]) if "webcam_crop" in sc else None,
            )
        raise ValueError(f"Unknown screen capture method: {method}")

    def _get_llm_client(self) -> LlmClient:
        llm_cfg = self.settings["llm"]
        return LlmClient(
            provider=llm_cfg["provider"],
            base_url=llm_cfg["base_url"],
            vision_model=llm_cfg.get("vision_model"),
            text_model=llm_cfg.get("text_model"),
            api_key=llm_cfg.get("api_key"),
            timeout=llm_cfg.get("timeout", 30),
        )

    def run(
        self,
        serial: str | None = None,
        suite_config: dict | None = None,
        build_dir: str | None = None,
        skip_flash: bool = False,
        skip_setup: bool = False,
    ) -> list[TestResult]:
        adb = AdbController(serial=serial)

        # Stage 0: Flash
        if not skip_flash and build_dir:
            logger.info("=== Stage 0: Flash Image ===")
            flash_driver = self._get_flash_driver(serial=serial)
            flash_config = self.device_config["flash"]
            flash_driver.flash(flash_config)
            logger.info("Flash complete. Waiting for device boot...")
            time.sleep(10)

        # Stage 1: Pre-ADB Setup
        if not skip_setup and self.device_config.get("build_type") == "user":
            logger.info("=== Stage 1: Pre-ADB Setup (Setup Wizard) ===")
            screen_capture = self._get_screen_capture(serial=serial)
            llm = self._get_llm_client()
            analyzer = VisualAnalyzer(llm)
            resolution = self.device_config.get("screen_resolution", [1080, 2400])
            sw_config = self.device_config.get("setup_wizard", {})

            # AOA2 HID would be initialized here with actual device VID/PID
            # For now, log that it would be used
            logger.info("Setup Wizard automation would use AOA2 HID + LLM Vision")
            logger.info("Skipping actual AOA2 in this run — waiting for ADB...")

        # Stage 2: ADB Bootstrap
        logger.info("=== Stage 2: ADB Bootstrap ===")
        if not adb.wait_for_device(timeout=120):
            logger.error("Device not found via ADB")
            return []

        wifi_cfg = self.settings.get("wifi", {})
        if wifi_cfg.get("ssid"):
            adb.connect_wifi(wifi_cfg["ssid"], wifi_cfg.get("password", ""))

        adb.shell("settings put global stay_on_while_plugged_in 3")

        # Stage 3: Test Execute
        if suite_config:
            logger.info("=== Stage 3: Test Execute ===")
            screen_capture = self._get_screen_capture(serial=serial)
            llm = self._get_llm_client()
            analyzer = VisualAnalyzer(llm)
            runner = TestRunner(
                adb=adb,
                visual_analyzer=analyzer,
                screen_capture=screen_capture,
            )
            results = runner.run_suite(suite_config)
        else:
            results = []

        # Stage 4: Report
        logger.info("=== Stage 4: Report ===")
        self._generate_reports(results)

        return results

    def _generate_reports(self, results: list[TestResult]) -> None:
        report_cfg = self.settings.get("reporting", {})
        formats = report_cfg.get("formats", ["cli"])
        output_dir = Path(report_cfg.get("output_dir", "results/"))

        if "cli" in formats:
            CliReporter().print_results(results, "Smoke Test", self.device_name)

        if "json" in formats:
            json_path = output_dir / f"{self.device_name}_results.json"
            JsonReporter().generate(results, "Smoke Test", self.device_name, json_path)
            logger.info(f"JSON report: {json_path}")

        if "html" in formats:
            html_path = output_dir / f"{self.device_name}_report.html"
            HtmlReporter().generate(results, "Smoke Test", self.device_name, html_path)
            logger.info(f"HTML report: {html_path}")
```

**Step 5: Implement cli.py**

```python
# cli.py
import click
from pathlib import Path
from rich.console import Console
from smoke_test_ai.utils.config import load_settings, load_device_config, load_test_suite

console = Console()


@click.group()
def main():
    """smoke-test-ai: Android OS smoke test automation"""
    pass


@main.command()
@click.option("--device", required=True, help="Device config name (e.g. product_a)")
@click.option("--suite", required=True, help="Test suite name (e.g. smoke_basic)")
@click.option("--build", default=None, help="Build directory with images")
@click.option("--serial", default=None, help="Device serial number")
@click.option("--skip-flash", is_flag=True, help="Skip flashing stage")
@click.option("--skip-setup", is_flag=True, help="Skip Setup Wizard stage")
@click.option("--config-dir", default="config", help="Config directory path")
def run(device, suite, build, serial, skip_flash, skip_setup, config_dir):
    """Run full smoke test pipeline."""
    from smoke_test_ai.core.orchestrator import Orchestrator

    config_path = Path(config_dir)
    settings = load_settings(config_path / "settings.yaml")
    device_config = load_device_config(config_path / "devices" / f"{device}.yaml")
    suite_config = load_test_suite(config_path / "test_suites" / f"{suite}.yaml")

    orch = Orchestrator(settings=settings, device_config=device_config)
    results = orch.run(
        serial=serial,
        suite_config=suite_config,
        build_dir=build,
        skip_flash=skip_flash,
        skip_setup=skip_setup,
    )

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    if passed == total and total > 0:
        console.print(f"\n[bold green]ALL {total} TESTS PASSED[/]")
    else:
        console.print(f"\n[bold red]{total - passed}/{total} TESTS FAILED[/]")
        raise SystemExit(1)


@main.command()
@click.option("--suite", required=True, help="Test suite name")
@click.option("--serial", default=None, help="Device serial number")
@click.option("--config-dir", default="config", help="Config directory path")
def test(suite, serial, config_dir):
    """Run tests only (assumes ADB is available)."""
    from smoke_test_ai.core.orchestrator import Orchestrator

    config_path = Path(config_dir)
    settings = load_settings(config_path / "settings.yaml")
    # Minimal device config for test-only mode
    device_config = {"device": {"name": "direct", "screen_capture": {"method": "adb"}}}
    suite_config = load_test_suite(config_path / "test_suites" / f"{suite}.yaml")

    orch = Orchestrator(settings=settings, device_config=device_config)
    results = orch.run(
        serial=serial,
        suite_config=suite_config,
        skip_flash=True,
        skip_setup=True,
    )

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    raise SystemExit(0 if passed == total and total > 0 else 1)


@main.group()
def devices():
    """Manage device configurations."""
    pass


@devices.command("list")
@click.option("--config-dir", default="config", help="Config directory path")
def devices_list(config_dir):
    """List available device configs."""
    config_path = Path(config_dir) / "devices"
    if not config_path.exists():
        console.print("[yellow]No device configs found[/]")
        return
    for f in sorted(config_path.glob("*.yaml")):
        config = load_device_config(f)
        name = config.get("device", {}).get("name", f.stem)
        build_type = config.get("device", {}).get("build_type", "unknown")
        console.print(f"  {f.stem}: {name} ({build_type})")


@main.group()
def suites():
    """Manage test suites."""
    pass


@suites.command("list")
@click.option("--config-dir", default="config", help="Config directory path")
def suites_list(config_dir):
    """List available test suites."""
    config_path = Path(config_dir) / "test_suites"
    if not config_path.exists():
        console.print("[yellow]No test suites found[/]")
        return
    for f in sorted(config_path.glob("*.yaml")):
        config = load_test_suite(f)
        name = config.get("test_suite", {}).get("name", f.stem)
        count = len(config.get("test_suite", {}).get("tests", []))
        console.print(f"  {f.stem}: {name} ({count} tests)")


if __name__ == "__main__":
    main()
```

**Step 6: Create sample config files**

Create `config/devices/product_a.yaml`:
```yaml
device:
  name: "Product-A"
  build_type: "user"
  screen_resolution: [1080, 2400]
  has_sim: true
  has_dp_output: false

  flash:
    profile: "fastboot"
    images:
      - partition: "system"
        file: "${BUILD_DIR}/system.img"
      - partition: "vendor"
        file: "${BUILD_DIR}/vendor.img"
      - partition: "boot"
        file: "${BUILD_DIR}/boot.img"
    post_flash:
      - "fastboot reboot"

  screen_capture:
    method: "webcam"
    webcam_device: "/dev/video0"
    webcam_crop: [100, 50, 1080, 1920]

  setup_wizard:
    method: "llm_vision"
    max_steps: 30
    timeout: 300
```

Create `config/test_suites/smoke_basic.yaml`:
```yaml
test_suite:
  name: "Basic Smoke Test"
  timeout: 600

  tests:
    - id: "boot_complete"
      name: "開機完成驗證"
      type: "adb_check"
      command: "getprop sys.boot_completed"
      expected: "1"

    - id: "display_normal"
      name: "螢幕顯示正常"
      type: "screenshot_llm"
      prompt: "螢幕是否正常顯示？是否有異常色塊或花屏？"
      pass_criteria: "normal"

    - id: "touch_responsive"
      name: "觸控回應"
      type: "adb_shell"
      command: "input tap 540 960 && dumpsys window | grep mCurrentFocus"
      expected_contains: "Launcher"

    - id: "wifi_connected"
      name: "WiFi 連線"
      type: "adb_shell"
      command: "dumpsys wifi | grep 'Wi-Fi is'"
      expected_contains: "enabled"

    - id: "internet_access"
      name: "網路存取"
      type: "adb_shell"
      command: "ping -c 3 8.8.8.8"
      expected_contains: "3 received"

    - id: "sim_status"
      name: "SIM 卡狀態"
      type: "adb_shell"
      command: "dumpsys telephony.registry | grep mServiceState"
      expected_not_contains: "OUT_OF_SERVICE"

    - id: "camera_available"
      name: "相機可用"
      type: "adb_shell"
      command: "dumpsys media.camera | grep 'Device version'"
      expected_pattern: "Device version:.*"

    - id: "audio_output"
      name: "音效輸出"
      type: "adb_shell"
      command: "dumpsys audio | grep 'stream_MUSIC'"
      expected_contains: "stream_MUSIC"
```

**Step 7: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests pass

**Step 8: Verify CLI works**

Run: `python cli.py --help`
Expected: Shows help with run, test, devices, suites commands

Run: `python cli.py suites list`
Expected: Lists smoke_basic suite

**Step 9: Commit**

```bash
git add smoke_test_ai/core/orchestrator.py smoke_test_ai/ai/setup_wizard_agent.py cli.py config/ tests/test_orchestrator.py
git commit -m "feat: add orchestrator, setup wizard agent, CLI, and sample configs"
```

---

## Task Dependency Graph

```
Task 1 (Scaffold)
  ├── Task 2 (Utils)
  │     ├── Task 3 (ADB Controller)
  │     ├── Task 4 (Screen Capture)
  │     ├── Task 5 (AOA2 HID)
  │     └── Task 6 (Flash Drivers)
  │
  ├── Task 7 (LLM Client + Visual Analyzer)
  │     └── depends on Task 2
  │
  ├── Task 8 (Test Runner)
  │     └── depends on Tasks 3, 4, 7
  │
  ├── Task 9 (Reporting)
  │     └── depends on Task 8
  │
  └── Task 10 (Orchestrator + CLI)
        └── depends on all above
```

## Notes for Implementer

- Tasks 3-6 are independent of each other and can be parallelized
- Task 7 depends only on Task 2
- Task 8 integrates Tasks 3, 4, and 7
- Task 10 is the final integration task
- All tests use mocks — no actual hardware or Ollama needed to run the test suite
- AOA2 HID driver uses PyUSB which requires libusb installed on the host
- The `screen_capture` drivers abstract away the capture method so tests can mock them
