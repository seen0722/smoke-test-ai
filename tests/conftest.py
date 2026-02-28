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
