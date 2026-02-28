import pytest
from pathlib import Path
from smoke_test_ai.utils.config import load_settings, load_device_config, load_test_suite

def test_load_settings(config_dir):
    settings = load_settings(config_dir / "settings.yaml")
    assert settings["llm"]["provider"] in ("ollama", "openai")
    assert settings["parallel"]["max_devices"] == 4

def test_load_settings_missing_file():
    with pytest.raises(FileNotFoundError):
        load_settings(Path("/nonexistent/settings.yaml"))

def test_load_device_config(tmp_path):
    device_yaml = tmp_path / "device.yaml"
    device_yaml.write_text("device:\n  name: TestDevice\n  build_type: user\n  screen_resolution: [1080, 2400]\n")
    config = load_device_config(device_yaml)
    assert config["device"]["name"] == "TestDevice"
    assert config["device"]["build_type"] == "user"

def test_load_test_suite(tmp_path):
    suite_yaml = tmp_path / "suite.yaml"
    suite_yaml.write_text("test_suite:\n  name: Basic\n  timeout: 60\n  tests:\n    - id: t1\n      name: Test1\n      type: adb_check\n      command: getprop ro.build.type\n      expected: userdebug\n")
    suite = load_test_suite(suite_yaml)
    assert suite["test_suite"]["name"] == "Basic"
    assert len(suite["test_suite"]["tests"]) == 1
    assert suite["test_suite"]["tests"][0]["id"] == "t1"
