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
