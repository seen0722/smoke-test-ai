# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

smoke-test-ai is an Android OS automation testing framework. It runs a 5-stage pipeline: Flash → Pre-ADB Setup (AOA2 HID) → ADB Bootstrap → Test Execution → Reporting. All UI and user-facing strings are in Chinese (中文).

## Running

```bash
# Activate venv
source .venv/bin/activate

# Full pipeline: flash + setup + test + report
smoke-test run --device product_a --suite smoke_basic --build /path/to/build/

# Tests only (device already in ADB mode)
smoke-test test --suite smoke_basic --serial <DEVICE_SERIAL>

# Factory reset → test
smoke-test reset-test --suite smoke_basic --serial <DEVICE_SERIAL> --device product_a

# List configs
smoke-test devices list
smoke-test suites list
```

## Testing

```bash
pytest                          # Run all tests
pytest tests/test_plugins.py -v # Run specific test file
pytest -k "test_charging" -v    # Run tests matching pattern
```

Coverage configured to fail under 69%. Config in `pyproject.toml [tool.pytest.ini_options]`.

## Architecture

- **cli.py** — Click CLI entry point. Commands: `run`, `test`, `reset-test`, `record`, `replay`, `devices`, `suites`.
- **smoke_test_ai/core/orchestrator.py** — 5-stage pipeline controller (~900 lines). Coordinates all drivers and plugins.
- **smoke_test_ai/core/test_runner.py** — Iterates test cases, manages retries, dependencies, and plugin dispatch.
- **smoke_test_ai/drivers/** — Hardware abstraction:
  - `adb_controller.py` — ADB shell wrapper
  - `aoa_hid.py` — AOA2 USB HID (keyboard/touch/consumer) for Pre-ADB automation
  - `usb_power.py` — USB power control via uhubctl (per-port power switching)
  - `usb_power_serial.py` — USB power control via serial hub controller (alternative backend)
  - `flash/` — Flashing drivers (fastboot, custom)
  - `screen_capture/` — Screen capture (ADB, webcam)
- **smoke_test_ai/plugins/** — Extensible test plugins (charging, suspend, camera, telephony, wifi, bluetooth, audio, network). All receive `PluginContext` with adb, usb_power, settings.
- **smoke_test_ai/runners/** — `blind_runner.py` (AOA2 YAML step playback), `recorder.py` (interactive recording)
- **smoke_test_ai/ai/** — LLM integration (Ollama/OpenAI) for screenshot analysis
- **smoke_test_ai/reporting/** — CLI, JSON, HTML, Test Plan reporters
- **config/** — YAML configs for devices, test suites, flash profiles, setup flows

## USB Power Control — Dual Backend

Two backends for controlling USB port power, selected via device config `usb_power.backend`:

### uhubctl (default)
Uses the `uhubctl` CLI tool. Requires a USB hub with per-port power switching (PPPS).
```yaml
usb_power:
  backend: "uhubctl"        # or omit (default)
  hub_location: "1-1"
  port: 3
  off_duration: 20.0
```
Driver: `smoke_test_ai/drivers/usb_power.py` → `UsbPowerController`

### Serial hub controller
Uses the `usb-port-controller` package to communicate with a serial USB hub via binary protocol.
```yaml
usb_power:
  backend: "serial"
  device_serial: "UHB-07"   # Auto-discover by device serial (recommended)
  # serial_port: "/dev/cu.usbserial-111240"  # Or explicit path
  port: 3
  off_duration: 20.0
```
Driver: `smoke_test_ai/drivers/usb_power_serial.py` → `SerialUsbPowerController`

Install: `pip install -e ".[serial-hub]"`
Source: https://github.com/seen0722/usb-port-controller

### How plugins use USB power
Both backends expose the same interface: `power_off() -> bool`, `power_on() -> bool`, `power_cycle() -> bool`. Plugins access it via `context.usb_power`. The charging and suspend plugins use it for power-cycling tests. No plugin code needs to know which backend is active.

### Backend selection logic
In `orchestrator.py:368` and `cli.py:122`:
```python
backend = usb_power_cfg.get("backend", "uhubctl")
if backend == "serial":
    from smoke_test_ai.drivers.usb_power_serial import SerialUsbPowerController
    usb_power = SerialUsbPowerController(...)
else:
    usb_power = UsbPowerController(...)
```

## Key Design Details

- Test suites and device configs are YAML-based under `config/`.
- Plugins receive `PluginContext(adb, usb_power, settings, device_capabilities)`.
- Pre-ADB automation uses AOA2 USB accessory mode with HID descriptors for keyboard, touch, and consumer controls.
- `BlindRunner` plays YAML step files for Setup Wizard automation without screen reading.
- Test types: `adb_check`, `adb_shell`, `screenshot_llm`, `apk_instrumentation`, and plugin types.
- Adaptive pipeline skips unnecessary stages based on build_type, keep_data, and skip flags.

## Dependencies

Core: click, rich, pyyaml, pyusb, opencv-python-headless, httpx, jinja2, Pillow, mobly
Optional: `[dev]` pytest, `[pdf]` weasyprint, `[serial-hub]` usb-port-controller
