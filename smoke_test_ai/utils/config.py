import os
import yaml
from pathlib import Path

def _expand_env_vars(data):
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
