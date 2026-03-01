# Functional Test Plugin Architecture Design

Date: 2026-03-01

## Problem

Current smoke tests are mostly Android framework state checks (`dumpsys`, `getprop`). They verify that services exist but don't validate real functionality. For example:

- "Camera available" only checks `dumpsys media.camera` device count — never actually takes a photo
- "SIM status" only checks `mServiceState` — never sends or receives SMS
- "Audio output" only checks `dumpsys audio` has a speaker — never plays sound

## Decision

Adopt a **Plugin architecture** with **Google Mobly Bundled Snippets** for functional tests that require Android API access beyond what ADB shell provides.

### Why Mobly Snippet (not Twilio / not full Mobly framework)

- **vs Twilio**: Offline-capable, free, bidirectional SMS (send + receive), access to full Android API
- **vs Full Mobly**: We keep our existing framework (flash pipeline, AOA2 HID, LLM Vision, YAML config, reporting). We only use Mobly's Python library as a Snippet RPC client — not its test runner.

### SMS: Dual-device Snippet mode

Two phones connected via USB, both with Mobly Bundled Snippets APK installed. Phone B sends SMS to DUT, DUT's Snippet `waitForSms()` verifies receipt. Vice versa for send testing.

### Camera: ADB intent approach (no Snippet needed)

Launch camera via `am start` intent → trigger shutter via `keyevent` → verify new photo in DCIM → optionally pull photo and use LLM Vision to verify image quality.

---

## Architecture

### Plugin System

```
smoke_test_ai/
  plugins/
    __init__.py              # load_plugins(settings, adb, snippet) -> dict[str, TestPlugin]
    base.py                  # TestPlugin ABC + PluginContext dataclass
    telephony.py             # TelephonyPlugin — SMS send/receive via Snippet
    camera.py                # CameraPlugin — ADB intent + DCIM check + optional LLM
```

### TestPlugin Interface

```python
# smoke_test_ai/plugins/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from smoke_test_ai.core.test_runner import TestResult
from smoke_test_ai.drivers.adb_controller import AdbController

@dataclass
class PluginContext:
    adb: AdbController
    settings: dict
    device_capabilities: dict
    snippet: object | None = None       # Mobly snippet handle (ad.mbs)
    peer_snippet: object | None = None  # Second device snippet (for dual-device tests)
    visual_analyzer: object | None = None

class TestPlugin(ABC):
    @abstractmethod
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        """Execute a functional test, return result."""
```

### Plugin Dispatch in TestRunner

```python
# test_runner.py — modified
BUILTIN_TYPES = {"adb_check", "adb_shell", "screenshot_llm", "apk_instrumentation"}

class TestRunner:
    def __init__(self, ..., plugins: dict[str, TestPlugin] | None = None):
        self._plugins = plugins or {}

    def run_test(self, test_case):
        test_type = test_case["type"]
        if test_type in BUILTIN_TYPES:
            # existing logic unchanged
            ...
        elif test_type in self._plugins:
            return self._plugins[test_type].execute(test_case, self._context)
        else:
            return TestResult(status=TestStatus.ERROR, message=f"Unknown type: {test_type}")
```

---

## Mobly Snippet Integration

### Lifecycle (in Orchestrator)

```python
# orchestrator.py — Stage 2 Bootstrap (after ADB ready)
if self._has_snippet_tests(suite_config):
    from mobly.controllers.android_device import AndroidDevice

    # DUT snippet
    self._mobly_dut = AndroidDevice(serial)
    self._mobly_dut.load_snippet('mbs', 'com.google.android.mobly.snippet.bundled')

    # Peer device (optional, for dual-device tests like SMS receive)
    peer_serial = self.device_config.get("peer_serial")
    if peer_serial:
        self._mobly_peer = AndroidDevice(peer_serial)
        self._mobly_peer.load_snippet('mbs', 'com.google.android.mobly.snippet.bundled')
```

### Device Config Addition

```yaml
# config/devices/product_a.yaml
device:
  name: "Product-A"
  phone_number: "+886912345678"    # DUT SIM number
  peer_serial: "PEER_SERIAL_123"   # Second phone serial (optional)
  peer_phone_number: "+886900000000"
  has_sim: true
```

### Snippet APK Prerequisite

The Mobly Bundled Snippets APK must be pre-installed on both DUT and peer device:
```bash
adb -s DUT_SERIAL install -r mobly-bundled-snippets.apk
adb -s PEER_SERIAL install -r mobly-bundled-snippets.apk
```

This can be automated in the orchestrator bootstrap stage, with the APK stored in the project's `assets/` directory.

---

## Plugin Implementations

### TelephonyPlugin

Handles test type: `"telephony"`

#### Actions

| action | Description | Requires |
|--------|-------------|----------|
| `send_sms` | DUT sends SMS, verify send confirmation | DUT snippet + has_sim |
| `receive_sms` | Peer sends SMS to DUT, DUT verifies receipt | Both snippets + has_sim |
| `check_signal` | Query network type and call state | DUT snippet + has_sim |

#### YAML Examples

```yaml
- id: "sms_send"
  name: "SMS 簡訊發送"
  type: "telephony"
  action: "send_sms"
  params:
    to_number: "${PEER_PHONE_NUMBER}"
    body: "smoke-test-outbound-{timestamp}"
  requires:
    device_capability: "has_sim"

- id: "sms_receive"
  name: "SMS 簡訊接收"
  type: "telephony"
  action: "receive_sms"
  params:
    body: "smoke-test-inbound-{timestamp}"
    timeout: 30
  requires:
    device_capability: "has_sim"
  depends_on: "sms_send"

- id: "network_type"
  name: "行動網路類型"
  type: "telephony"
  action: "check_signal"
  params:
    expected_data_type: "LTE|NR"    # regex match
  requires:
    device_capability: "has_sim"
```

#### Logic: `receive_sms`

```
1. DUT: mbs.asyncWaitForSms('sms_cb')          # non-blocking listen
2. Peer: mbs.sendSms(dut_number, body)          # send SMS
3. DUT: result = mbs.waitForSms(timeout * 1000) # blocking wait
4. Verify: result["MessageBody"] contains expected body → PASS
```

### CameraPlugin

Handles test type: `"camera"`

No Snippet needed — uses ADB shell commands + optional LLM Vision.

#### Actions

| action | Description | Requires |
|--------|-------------|----------|
| `capture_photo` | Take a photo, verify file created | ADB |
| `capture_and_verify` | Take a photo, pull it, LLM checks image quality | ADB + LLM |

#### YAML Examples

```yaml
- id: "camera_rear_capture"
  name: "後鏡頭拍照"
  type: "camera"
  action: "capture_photo"
  params:
    camera: "back"
    wait_seconds: 5
  pass_criteria: "DCIM 中出現新照片檔案"

- id: "camera_front_capture"
  name: "前鏡頭拍照"
  type: "camera"
  action: "capture_photo"
  params:
    camera: "front"
    wait_seconds: 5

- id: "camera_image_quality"
  name: "照片品質驗證"
  type: "camera"
  action: "capture_and_verify"
  params:
    camera: "back"
    verify_prompt: "照片是否清晰、非全黑、非全白、無明顯色偏？"
  depends_on: "camera_rear_capture"
```

#### Logic: `capture_photo`

```
1. adb shell ls -t /sdcard/DCIM/Camera/ | head -1   → record baseline
2. adb shell am start -a android.media.action.IMAGE_CAPTURE
3. sleep(2)
4. adb shell input keyevent KEYCODE_CAMERA           → trigger shutter
5. sleep(wait_seconds)
6. adb shell ls -t /sdcard/DCIM/Camera/ | head -1   → check for new file
7. New file exists and size > 0 → PASS
```

#### Logic: `capture_and_verify`

```
1-7. Same as capture_photo
8. adb pull new_photo /tmp/
9. LLM Vision analyze(photo, verify_prompt) → pass/fail
```

---

## Test Plan Reporter Update

`test_plan_reporter.py` needs to handle the new test types when building
human-readable pass criteria:

```python
if t == "telephony":
    action = tc.get("action", "")
    if action == "send_sms":
        return f"SMS sent to {tc['params'].get('to_number', 'peer')} without error"
    if action == "receive_sms":
        return f"SMS received within {tc['params'].get('timeout', 30)}s"
    if action == "check_signal":
        return f"Network type matches /{tc['params'].get('expected_data_type', '.*')}/"

if t == "camera":
    action = tc.get("action", "")
    if action == "capture_photo":
        return f"New photo file created in DCIM ({tc['params'].get('camera', 'back')} camera)"
    if action == "capture_and_verify":
        return f"Photo captured and LLM verified: {tc['params'].get('verify_prompt', '')}"
```

---

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `smoke_test_ai/plugins/__init__.py` | New | `load_plugins()` factory |
| `smoke_test_ai/plugins/base.py` | New | `TestPlugin` ABC + `PluginContext` |
| `smoke_test_ai/plugins/telephony.py` | New | `TelephonyPlugin` |
| `smoke_test_ai/plugins/camera.py` | New | `CameraPlugin` |
| `smoke_test_ai/core/test_runner.py` | Modify | Add `plugins` param + dispatch |
| `smoke_test_ai/core/orchestrator.py` | Modify | Snippet lifecycle + plugin init |
| `smoke_test_ai/reporting/test_plan_reporter.py` | Modify | Handle new types |
| `config/devices/product_a.yaml` | Modify | Add phone_number, peer_serial |
| `config/test_suites/smoke_basic.yaml` | Modify | Add functional tests |
| `requirements.txt` or `pyproject.toml` | Modify | Add `mobly` dependency |
| `tests/test_plugins.py` | New | Unit tests for plugins |

## Dependencies

- `mobly` Python package (`pip install mobly`)
- Mobly Bundled Snippets APK (pre-installed on DUT + peer)

## Future Extensions

New plugins can be added for:
- **AudioPlugin**: `mediaPlayAudioFile()` + `isMusicActive()` verification
- **BluetoothPlugin**: BLE scan/advertise between DUT and peer
- **NetworkPlugin**: `networkIsTcpConnectable()` + `networkHttpDownload()` real tests
- **Custom Snippet**: Write project-specific Java snippets for GPS mock, sensor read, etc.

Each new plugin is one Python file + YAML test cases. No framework changes needed.
