# Functional Test Plugin Architecture — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Plugin architecture so new functional test types (telephony SMS, camera capture) can be added without modifying the core test runner.

**Architecture:** A `TestPlugin` ABC with a `PluginContext` dataclass lives in `smoke_test_ai/plugins/`. The existing `TestRunner` gains a `plugins` dict; unknown test types are dispatched to the matching plugin. Two concrete plugins ship first: `TelephonyPlugin` (Mobly Snippet RPC for SMS) and `CameraPlugin` (ADB intent + DCIM check). Orchestrator handles Mobly snippet lifecycle and plugin loading.

**Tech Stack:** Python 3.10+, Mobly (`pip install mobly`), existing ADB/LLM infrastructure

---

### Task 1: Plugin base classes (`base.py` + `__init__.py`)

**Files:**
- Create: `smoke_test_ai/plugins/__init__.py`
- Create: `smoke_test_ai/plugins/base.py`
- Create: `tests/test_plugins.py`

**Step 1: Write the failing tests**

In `tests/test_plugins.py`:

```python
import pytest
from unittest.mock import MagicMock
from smoke_test_ai.plugins.base import TestPlugin, PluginContext
from smoke_test_ai.core.test_runner import TestResult, TestStatus


class DummyPlugin(TestPlugin):
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        return TestResult(
            id=test_case["id"],
            name=test_case["name"],
            status=TestStatus.PASS,
            message="dummy",
        )


@pytest.fixture
def plugin_context():
    return PluginContext(
        adb=MagicMock(),
        settings={},
        device_capabilities={},
    )


class TestPluginBase:
    def test_plugin_context_defaults(self):
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={})
        assert ctx.snippet is None
        assert ctx.peer_snippet is None
        assert ctx.visual_analyzer is None

    def test_dummy_plugin_executes(self, plugin_context):
        plugin = DummyPlugin()
        tc = {"id": "t1", "name": "Test", "type": "dummy"}
        result = plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.PASS
        assert result.message == "dummy"

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            TestPlugin()
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_plugins.py -v`
Expected: `ModuleNotFoundError: No module named 'smoke_test_ai.plugins'`

**Step 3: Write the implementation**

`smoke_test_ai/plugins/__init__.py`:

```python
from smoke_test_ai.plugins.base import TestPlugin, PluginContext

__all__ = ["TestPlugin", "PluginContext"]
```

`smoke_test_ai/plugins/base.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from smoke_test_ai.core.test_runner import TestResult
from smoke_test_ai.drivers.adb_controller import AdbController


@dataclass
class PluginContext:
    adb: AdbController
    settings: dict
    device_capabilities: dict
    snippet: object | None = None
    peer_snippet: object | None = None
    visual_analyzer: object | None = None


class TestPlugin(ABC):
    @abstractmethod
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        """Execute a functional test, return result."""
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_plugins.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add smoke_test_ai/plugins/__init__.py smoke_test_ai/plugins/base.py tests/test_plugins.py
git commit -m "feat: add TestPlugin ABC and PluginContext base classes"
```

---

### Task 2: TestRunner plugin dispatch

**Files:**
- Modify: `smoke_test_ai/core/test_runner.py` (lines 32-33, 80-90)
- Modify: `tests/test_runner.py`

**Step 1: Write the failing test**

Append to `tests/test_runner.py`:

```python
class TestPluginDispatch:
    def test_plugin_type_dispatched(self, mock_adb):
        from smoke_test_ai.plugins.base import TestPlugin, PluginContext

        class FakePlugin(TestPlugin):
            def execute(self, test_case, context):
                return TestResult(
                    id=test_case["id"], name=test_case["name"],
                    status=TestStatus.PASS, message="from plugin",
                )

        runner = TestRunner(adb=mock_adb, plugins={"custom": FakePlugin()})
        tc = {"id": "c1", "name": "Custom", "type": "custom"}
        result = runner.run_test(tc)
        assert result.status == TestStatus.PASS
        assert result.message == "from plugin"

    def test_plugin_receives_context(self, mock_adb):
        from smoke_test_ai.plugins.base import TestPlugin, PluginContext

        received = {}

        class SpyPlugin(TestPlugin):
            def execute(self, test_case, context):
                received["adb"] = context.adb
                received["caps"] = context.device_capabilities
                return TestResult(
                    id=test_case["id"], name=test_case["name"],
                    status=TestStatus.PASS,
                )

        runner = TestRunner(
            adb=mock_adb,
            device_capabilities={"has_sim": True},
            plugins={"spy": SpyPlugin()},
        )
        tc = {"id": "s1", "name": "Spy", "type": "spy"}
        runner.run_test(tc)
        assert received["adb"] is mock_adb
        assert received["caps"] == {"has_sim": True}

    def test_unknown_type_still_errors(self, mock_adb):
        runner = TestRunner(adb=mock_adb, plugins={})
        tc = {"id": "bad", "name": "Bad", "type": "nonexistent"}
        result = runner.run_test(tc)
        assert result.status == TestStatus.ERROR

    def test_plugin_exception_caught(self, mock_adb):
        from smoke_test_ai.plugins.base import TestPlugin, PluginContext

        class BrokenPlugin(TestPlugin):
            def execute(self, test_case, context):
                raise RuntimeError("boom")

        runner = TestRunner(adb=mock_adb, plugins={"broken": BrokenPlugin()})
        tc = {"id": "b1", "name": "Broken", "type": "broken"}
        result = runner.run_test(tc)
        assert result.status == TestStatus.ERROR
        assert "boom" in result.message
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runner.py::TestPluginDispatch -v`
Expected: `TypeError: TestRunner.__init__() got an unexpected keyword argument 'plugins'`

**Step 3: Modify TestRunner**

In `smoke_test_ai/core/test_runner.py`:

Change the `__init__` signature (line 33) to accept `plugins`:

```python
class TestRunner:
    def __init__(self, adb: AdbController, visual_analyzer=None, screen_capture=None, webcam_capture=None, device_capabilities: dict | None = None, plugins: dict | None = None):
        self.adb = adb
        self.visual_analyzer = visual_analyzer
        self.screen_capture = screen_capture
        self.webcam_capture = webcam_capture
        self.device_capabilities = device_capabilities or {}
        self._plugins = plugins or {}
```

Add a `_plugin_context` property and modify the dispatch block inside `run_test` (around lines 80-90). Replace the `else` (unknown type) branch with plugin lookup:

```python
                elif test_type in self._plugins:
                    from smoke_test_ai.plugins.base import PluginContext
                    ctx = PluginContext(
                        adb=self.adb,
                        settings={},
                        device_capabilities=self.device_capabilities,
                    )
                    result = self._plugins[test_type].execute(test_case, ctx)
                else:
                    result = TestResult(id=test_id, name=test_name, status=TestStatus.ERROR, message=f"Unknown test type: {test_type}")
```

The full dispatch block (lines 80-92) should read:

```python
            try:
                if test_type == "adb_check":
                    result = self._run_adb_check(test_case)
                elif test_type == "adb_shell":
                    result = self._run_adb_shell(test_case)
                elif test_type == "screenshot_llm":
                    result = self._run_screenshot_llm(test_case)
                elif test_type == "apk_instrumentation":
                    result = self._run_apk_instrumentation(test_case)
                elif test_type in self._plugins:
                    from smoke_test_ai.plugins.base import PluginContext
                    ctx = PluginContext(
                        adb=self.adb,
                        settings={},
                        device_capabilities=self.device_capabilities,
                    )
                    result = self._plugins[test_type].execute(test_case, ctx)
                else:
                    result = TestResult(id=test_id, name=test_name, status=TestStatus.ERROR, message=f"Unknown test type: {test_type}")
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_runner.py -v`
Expected: All existing tests + 4 new tests pass

**Step 5: Commit**

```bash
git add smoke_test_ai/core/test_runner.py tests/test_runner.py
git commit -m "feat: add plugin dispatch to TestRunner"
```

---

### Task 3: CameraPlugin

**Files:**
- Create: `smoke_test_ai/plugins/camera.py`
- Modify: `tests/test_plugins.py`

**Step 1: Write the failing tests**

Append to `tests/test_plugins.py`:

```python
from smoke_test_ai.plugins.camera import CameraPlugin


class TestCameraPlugin:
    @pytest.fixture
    def camera_plugin(self):
        return CameraPlugin()

    def test_capture_photo_pass(self, camera_plugin, plugin_context):
        adb = plugin_context.adb
        # ls before: one old file
        # ls after: a new file
        adb.shell.side_effect = [
            MagicMock(stdout="IMG_20260101.jpg\n", returncode=0),  # baseline ls
            MagicMock(stdout="", returncode=0),                     # am start
            MagicMock(stdout="", returncode=0),                     # keyevent
            MagicMock(stdout="IMG_20260301.jpg\n", returncode=0),  # after ls
            MagicMock(stdout="1234567\n", returncode=0),           # stat size
        ]
        tc = {
            "id": "cam1", "name": "Camera", "type": "camera",
            "action": "capture_photo",
            "params": {"camera": "back", "wait_seconds": 0},
        }
        result = camera_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.PASS

    def test_capture_photo_no_new_file(self, camera_plugin, plugin_context):
        adb = plugin_context.adb
        adb.shell.side_effect = [
            MagicMock(stdout="IMG_20260101.jpg\n", returncode=0),  # baseline
            MagicMock(stdout="", returncode=0),                     # am start
            MagicMock(stdout="", returncode=0),                     # keyevent
            MagicMock(stdout="IMG_20260101.jpg\n", returncode=0),  # same file
        ]
        tc = {
            "id": "cam1", "name": "Camera", "type": "camera",
            "action": "capture_photo",
            "params": {"camera": "back", "wait_seconds": 0},
        }
        result = camera_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.FAIL

    def test_unknown_action_errors(self, camera_plugin, plugin_context):
        tc = {
            "id": "cam1", "name": "Camera", "type": "camera",
            "action": "unknown_action", "params": {},
        }
        result = camera_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.ERROR
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_plugins.py::TestCameraPlugin -v`
Expected: `ModuleNotFoundError: No module named 'smoke_test_ai.plugins.camera'`

**Step 3: Write the implementation**

`smoke_test_ai/plugins/camera.py`:

```python
import time

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.base import TestPlugin, PluginContext

DCIM_PATH = "/sdcard/DCIM/Camera"


class CameraPlugin(TestPlugin):
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        action = test_case.get("action", "")
        if action == "capture_photo":
            return self._capture_photo(test_case, context)
        if action == "capture_and_verify":
            return self._capture_and_verify(test_case, context)
        return TestResult(
            id=test_case["id"], name=test_case["name"],
            status=TestStatus.ERROR,
            message=f"Unknown camera action: {action}",
        )

    def _capture_photo(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        params = tc.get("params", {})
        camera = params.get("camera", "back")
        wait_seconds = params.get("wait_seconds", 5)
        adb = ctx.adb

        # 1. Record baseline: newest file in DCIM
        baseline = adb.shell(f"ls -t {DCIM_PATH}/ | head -1").stdout.strip()

        # 2. Launch camera
        camera_id = 0 if camera == "back" else 1
        adb.shell(
            f"am start -a android.media.action.IMAGE_CAPTURE "
            f"--ei android.intent.extras.CAMERA_FACING {camera_id}"
        )
        time.sleep(2)

        # 3. Trigger shutter
        adb.shell("input keyevent KEYCODE_CAMERA")
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        # 4. Check for new file
        newest = adb.shell(f"ls -t {DCIM_PATH}/ | head -1").stdout.strip()
        if not newest or newest == baseline:
            return TestResult(
                id=tid, name=tname, status=TestStatus.FAIL,
                message=f"No new photo in {DCIM_PATH}/ (newest: {newest})",
            )

        # 5. Check file size > 0
        size_out = adb.shell(f"stat -c %s {DCIM_PATH}/{newest}").stdout.strip()
        try:
            size = int(size_out)
        except ValueError:
            size = 0
        if size == 0:
            return TestResult(
                id=tid, name=tname, status=TestStatus.FAIL,
                message=f"Photo {newest} has zero bytes",
            )

        return TestResult(
            id=tid, name=tname, status=TestStatus.PASS,
            message=f"Captured {newest} ({size} bytes, {camera} camera)",
        )

    def _capture_and_verify(self, tc: dict, ctx: PluginContext) -> TestResult:
        # First, take the photo
        result = self._capture_photo(tc, ctx)
        if result.status != TestStatus.PASS:
            return result

        # Then verify with LLM if available
        if not ctx.visual_analyzer:
            return result  # no LLM, just return capture result

        prompt = tc.get("params", {}).get(
            "verify_prompt", "Is the photo clear, not black, not white?"
        )
        newest = result.message.split()[1]  # extract filename from message
        adb = ctx.adb

        # Pull photo to temp path
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            local_path = Path(tmp) / newest
            adb.shell(f"cat {DCIM_PATH}/{newest}", timeout=30)
            # Use screen capture as fallback for LLM analysis
            image = None
            if hasattr(adb, "pull"):
                adb.pull(f"{DCIM_PATH}/{newest}", str(local_path))
                import cv2
                image = cv2.imread(str(local_path))

        if image is None:
            return result  # can't pull, return capture-only result

        analysis = ctx.visual_analyzer.analyze_test_screenshot(image, prompt)
        if analysis.get("pass", False):
            return TestResult(
                id=tc["id"], name=tc["name"], status=TestStatus.PASS,
                message=f"Verified: {analysis.get('reason', '')}",
            )
        return TestResult(
            id=tc["id"], name=tc["name"], status=TestStatus.FAIL,
            message=f"LLM rejected: {analysis.get('reason', '')}",
        )
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_plugins.py::TestCameraPlugin -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add smoke_test_ai/plugins/camera.py tests/test_plugins.py
git commit -m "feat: add CameraPlugin for photo capture testing"
```

---

### Task 4: TelephonyPlugin

**Files:**
- Create: `smoke_test_ai/plugins/telephony.py`
- Modify: `tests/test_plugins.py`

**Step 1: Write the failing tests**

Append to `tests/test_plugins.py`:

```python
from smoke_test_ai.plugins.telephony import TelephonyPlugin


class TestTelephonyPlugin:
    @pytest.fixture
    def telephony_plugin(self):
        return TelephonyPlugin()

    def test_send_sms_pass(self, telephony_plugin):
        snippet = MagicMock()
        snippet.sendSms.return_value = None  # no error = success
        ctx = PluginContext(
            adb=MagicMock(), settings={}, device_capabilities={},
            snippet=snippet,
        )
        tc = {
            "id": "sms1", "name": "SMS Send", "type": "telephony",
            "action": "send_sms",
            "params": {"to_number": "+886900000000", "body": "test msg"},
        }
        result = telephony_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        snippet.sendSms.assert_called_once_with("+886900000000", "test msg")

    def test_send_sms_no_snippet(self, telephony_plugin, plugin_context):
        tc = {
            "id": "sms1", "name": "SMS Send", "type": "telephony",
            "action": "send_sms",
            "params": {"to_number": "+886900000000", "body": "test"},
        }
        result = telephony_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.SKIP
        assert "snippet" in result.message.lower()

    def test_receive_sms_pass(self, telephony_plugin):
        dut_snippet = MagicMock()
        dut_snippet.waitForSms.return_value = {
            "OriginatingAddress": "+886900000000",
            "MessageBody": "smoke-test-inbound-123",
        }
        peer_snippet = MagicMock()
        ctx = PluginContext(
            adb=MagicMock(), settings={},
            device_capabilities={},
            snippet=dut_snippet, peer_snippet=peer_snippet,
        )
        ctx.adb.serial = "DUT_SERIAL"
        ctx.settings = {"device": {"phone_number": "+886912345678"}}
        tc = {
            "id": "sms2", "name": "SMS Receive", "type": "telephony",
            "action": "receive_sms",
            "params": {"body": "smoke-test-inbound", "timeout": 10},
        }
        result = telephony_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        peer_snippet.sendSms.assert_called_once()
        dut_snippet.waitForSms.assert_called_once_with(10000)

    def test_receive_sms_no_peer(self, telephony_plugin):
        ctx = PluginContext(
            adb=MagicMock(), settings={}, device_capabilities={},
            snippet=MagicMock(), peer_snippet=None,
        )
        tc = {
            "id": "sms2", "name": "SMS Receive", "type": "telephony",
            "action": "receive_sms",
            "params": {"body": "test", "timeout": 10},
        }
        result = telephony_plugin.execute(tc, ctx)
        assert result.status == TestStatus.SKIP
        assert "peer" in result.message.lower()

    def test_check_signal_pass(self, telephony_plugin):
        snippet = MagicMock()
        snippet.getDataNetworkType.return_value = 13  # LTE
        ctx = PluginContext(
            adb=MagicMock(), settings={}, device_capabilities={},
            snippet=snippet,
        )
        tc = {
            "id": "sig1", "name": "Signal", "type": "telephony",
            "action": "check_signal",
            "params": {"expected_data_type": "LTE|NR"},
        }
        result = telephony_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS

    def test_unknown_action_errors(self, telephony_plugin, plugin_context):
        tc = {
            "id": "t1", "name": "Bad", "type": "telephony",
            "action": "bad_action", "params": {},
        }
        result = telephony_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.ERROR
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_plugins.py::TestTelephonyPlugin -v`
Expected: `ModuleNotFoundError: No module named 'smoke_test_ai.plugins.telephony'`

**Step 3: Write the implementation**

`smoke_test_ai/plugins/telephony.py`:

```python
import re
import time

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.base import TestPlugin, PluginContext

# Android data network type constants (TelephonyManager.NETWORK_TYPE_*)
NETWORK_TYPE_NAMES = {
    0: "UNKNOWN", 1: "GPRS", 2: "EDGE", 3: "UMTS", 4: "CDMA",
    5: "EVDO_0", 6: "EVDO_A", 7: "1xRTT", 8: "HSDPA", 9: "HSUPA",
    10: "HSPA", 11: "IDEN", 12: "EVDO_B", 13: "LTE", 14: "EHRPD",
    15: "HSPAP", 16: "GSM", 17: "TD_SCDMA", 18: "IWLAN", 19: "LTE_CA",
    20: "NR",
}


class TelephonyPlugin(TestPlugin):
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        action = test_case.get("action", "")
        if action == "send_sms":
            return self._send_sms(test_case, context)
        if action == "receive_sms":
            return self._receive_sms(test_case, context)
        if action == "check_signal":
            return self._check_signal(test_case, context)
        return TestResult(
            id=test_case["id"], name=test_case["name"],
            status=TestStatus.ERROR,
            message=f"Unknown telephony action: {action}",
        )

    def _send_sms(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available on DUT")
        params = tc.get("params", {})
        to_number = params.get("to_number", "")
        body = self._render_body(params.get("body", "smoke-test"))

        try:
            ctx.snippet.sendSms(to_number, body)
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"sendSms failed: {e}")

        return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                          message=f"SMS sent to {to_number}")

    def _receive_sms(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available on DUT")
        if not ctx.peer_snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Peer device snippet not available")

        params = tc.get("params", {})
        body = self._render_body(params.get("body", "smoke-test"))
        timeout = params.get("timeout", 30)
        dut_number = ctx.settings.get("device", {}).get("phone_number", "")

        try:
            # DUT starts listening (non-blocking)
            ctx.snippet.asyncWaitForSms("sms_receive_cb")
            # Peer sends SMS to DUT
            ctx.peer_snippet.sendSms(dut_number, body)
            # DUT waits for receipt
            received = ctx.snippet.waitForSms(timeout * 1000)
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"SMS receive failed: {e}")

        msg_body = received.get("MessageBody", "")
        if body in msg_body:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=f"Received SMS: {msg_body[:80]}")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message=f"Expected '{body}' in message, got: {msg_body[:80]}")

    def _check_signal(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available on DUT")
        params = tc.get("params", {})
        expected_pattern = params.get("expected_data_type", ".*")

        try:
            net_type_int = ctx.snippet.getDataNetworkType()
            net_type_name = NETWORK_TYPE_NAMES.get(net_type_int, f"UNKNOWN({net_type_int})")
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"getDataNetworkType failed: {e}")

        if re.search(expected_pattern, net_type_name):
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=f"Network type: {net_type_name}")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message=f"Network type {net_type_name} does not match /{expected_pattern}/")

    @staticmethod
    def _render_body(template: str) -> str:
        return template.replace("{timestamp}", str(int(time.time())))
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_plugins.py::TestTelephonyPlugin -v`
Expected: 6 passed

**Step 5: Commit**

```bash
git add smoke_test_ai/plugins/telephony.py tests/test_plugins.py
git commit -m "feat: add TelephonyPlugin for SMS send/receive/signal tests"
```

---

### Task 5: TestPlanReporter — handle new types

**Files:**
- Modify: `smoke_test_ai/reporting/test_plan_reporter.py` (lines 46-72)
- Modify: `tests/test_reporting.py`

**Step 1: Write the failing tests**

Append to `tests/test_reporting.py`, at the end of the file, a new fixture and test class:

```python
@pytest.fixture
def suite_config_with_plugins():
    return {
        "test_suite": {
            "name": "Functional Smoke Test",
            "timeout": 600,
            "tests": [
                {
                    "id": "sms_send",
                    "name": "SMS Send",
                    "type": "telephony",
                    "action": "send_sms",
                    "params": {"to_number": "+886900000000", "body": "test"},
                },
                {
                    "id": "sms_receive",
                    "name": "SMS Receive",
                    "type": "telephony",
                    "action": "receive_sms",
                    "params": {"body": "test", "timeout": 30},
                },
                {
                    "id": "signal_check",
                    "name": "Signal Check",
                    "type": "telephony",
                    "action": "check_signal",
                    "params": {"expected_data_type": "LTE|NR"},
                },
                {
                    "id": "cam_back",
                    "name": "Rear Camera",
                    "type": "camera",
                    "action": "capture_photo",
                    "params": {"camera": "back"},
                },
                {
                    "id": "cam_verify",
                    "name": "Photo Verify",
                    "type": "camera",
                    "action": "capture_and_verify",
                    "params": {"camera": "back", "verify_prompt": "Is photo clear?"},
                },
            ],
        }
    }


class TestTestPlanReporterPluginTypes:
    def test_telephony_send_criteria(self, suite_config_with_plugins, tmp_path):
        output = tmp_path / "plan.html"
        reporter = TestPlanReporter(
            template_dir=Path(__file__).parent.parent / "templates"
        )
        reporter.generate(suite_config=suite_config_with_plugins, output_path=output)
        html = output.read_text()
        assert "SMS sent to" in html
        assert "+886900000000" in html

    def test_telephony_receive_criteria(self, suite_config_with_plugins, tmp_path):
        output = tmp_path / "plan.html"
        reporter = TestPlanReporter(
            template_dir=Path(__file__).parent.parent / "templates"
        )
        reporter.generate(suite_config=suite_config_with_plugins, output_path=output)
        html = output.read_text()
        assert "SMS received within" in html

    def test_telephony_signal_criteria(self, suite_config_with_plugins, tmp_path):
        output = tmp_path / "plan.html"
        reporter = TestPlanReporter(
            template_dir=Path(__file__).parent.parent / "templates"
        )
        reporter.generate(suite_config=suite_config_with_plugins, output_path=output)
        html = output.read_text()
        assert "Network type matches" in html
        assert "LTE|NR" in html

    def test_camera_capture_criteria(self, suite_config_with_plugins, tmp_path):
        output = tmp_path / "plan.html"
        reporter = TestPlanReporter(
            template_dir=Path(__file__).parent.parent / "templates"
        )
        reporter.generate(suite_config=suite_config_with_plugins, output_path=output)
        html = output.read_text()
        assert "New photo file created in DCIM" in html
        assert "back" in html

    def test_camera_verify_criteria(self, suite_config_with_plugins, tmp_path):
        output = tmp_path / "plan.html"
        reporter = TestPlanReporter(
            template_dir=Path(__file__).parent.parent / "templates"
        )
        reporter.generate(suite_config=suite_config_with_plugins, output_path=output)
        html = output.read_text()
        assert "LLM verified" in html
        assert "Is photo clear?" in html
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_reporting.py::TestTestPlanReporterPluginTypes -v`
Expected: FAIL — criteria text like "SMS sent to" will not appear (currently returns "Unknown test type")

**Step 3: Modify `_build_pass_criteria` and `generate`**

In `smoke_test_ai/reporting/test_plan_reporter.py`:

Add telephony and camera handling at the end of `_build_pass_criteria` (before `return "Unknown test type"`):

```python
        if t == "telephony":
            action = tc.get("action", "")
            params = tc.get("params", {})
            if action == "send_sms":
                return f"SMS sent to {params.get('to_number', 'peer')} without error"
            if action == "receive_sms":
                return f"SMS received within {params.get('timeout', 30)}s"
            if action == "check_signal":
                return f"Network type matches /{params.get('expected_data_type', '.*')}/"
            return f"Telephony action: {action}"

        if t == "camera":
            action = tc.get("action", "")
            params = tc.get("params", {})
            if action == "capture_photo":
                return f"New photo file created in DCIM ({params.get('camera', 'back')} camera)"
            if action == "capture_and_verify":
                return f"Photo captured and LLM verified: {params.get('verify_prompt', '')}"
            return f"Camera action: {action}"
```

Also update the `generate` method's `"command"` field extraction to handle plugin test types that use `params` instead of `command`/`prompt`:

Change line 24 from:

```python
                "command": tc.get("command") or tc.get("prompt", ""),
```

to:

```python
                "command": tc.get("command") or tc.get("prompt") or tc.get("action", ""),
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_reporting.py -v`
Expected: All tests pass (existing + 5 new)

**Step 5: Commit**

```bash
git add smoke_test_ai/reporting/test_plan_reporter.py tests/test_reporting.py
git commit -m "feat: add telephony and camera pass criteria to test plan reporter"
```

---

### Task 6: Orchestrator integration

**Files:**
- Modify: `smoke_test_ai/core/orchestrator.py`
- Modify: `pyproject.toml`

**Step 1: Add mobly dependency**

In `pyproject.toml`, add `"mobly>=1.12"` to the `dependencies` list:

```toml
dependencies = [
    "click>=8.1",
    "rich>=13.0",
    "pyyaml>=6.0",
    "pyusb>=1.2",
    "opencv-python-headless>=4.8",
    "httpx>=0.25",
    "jinja2>=3.1",
    "Pillow>=10.0",
    "python-dotenv>=1.0",
    "mobly>=1.12",
]
```

**Step 2: Modify orchestrator**

In `smoke_test_ai/core/orchestrator.py`:

Add imports at top:

```python
from smoke_test_ai.plugins.base import PluginContext
from smoke_test_ai.plugins.camera import CameraPlugin
from smoke_test_ai.plugins.telephony import TelephonyPlugin
```

Add `_has_snippet_tests` helper and `_init_plugins` method to `Orchestrator`:

```python
    @staticmethod
    def _has_snippet_tests(suite_config: dict) -> bool:
        """Check if any test in the suite requires Mobly snippet."""
        tests = suite_config.get("test_suite", {}).get("tests", [])
        return any(t.get("type") == "telephony" for t in tests)

    def _init_plugins(self, adb, analyzer, serial, suite_config):
        """Initialize plugins and optionally Mobly snippet connections."""
        snippet = None
        peer_snippet = None

        if self._has_snippet_tests(suite_config):
            try:
                from mobly.controllers.android_device import AndroidDevice
                mobly_dut = AndroidDevice(serial or adb.serial)
                mobly_dut.load_snippet('mbs', 'com.google.android.mobly.snippet.bundled')
                snippet = mobly_dut.mbs
                self._mobly_dut = mobly_dut
                logger.info("Mobly snippet loaded on DUT")

                peer_serial = self.device_config.get("peer_serial")
                if peer_serial:
                    mobly_peer = AndroidDevice(peer_serial)
                    mobly_peer.load_snippet('mbs', 'com.google.android.mobly.snippet.bundled')
                    peer_snippet = mobly_peer.mbs
                    self._mobly_peer = mobly_peer
                    logger.info(f"Mobly snippet loaded on peer ({peer_serial})")
            except Exception as e:
                logger.warning(f"Failed to load Mobly snippets: {e}")

        plugins = {
            "telephony": TelephonyPlugin(),
            "camera": CameraPlugin(),
        }

        return plugins, snippet, peer_snippet
```

Modify the Stage 3 block in `run()` to call `_init_plugins` and pass `plugins` to `TestRunner`. Replace lines 147-163 with:

```python
        # Stage 3: Test Execute
        if suite_config:
            logger.info("=== Stage 3: Test Execute ===")
            screen_capture = self._get_screen_capture(serial=serial)
            webcam_capture = self._get_webcam_capture()
            llm = self._get_llm_client()
            analyzer = VisualAnalyzer(llm)
            device_capabilities = {
                k: v for k, v in self.device_config.items()
                if isinstance(v, bool)
            }

            plugins, snippet, peer_snippet = self._init_plugins(
                adb, analyzer, serial, suite_config
            )

            runner = TestRunner(
                adb=adb,
                visual_analyzer=analyzer,
                screen_capture=screen_capture,
                webcam_capture=webcam_capture,
                device_capabilities=device_capabilities,
                plugins=plugins,
            )
            # Inject snippet handles into runner's plugin context
            runner._snippet = snippet
            runner._peer_snippet = peer_snippet
            runner._visual_analyzer = analyzer
            runner._settings = self.settings

            results = runner.run_suite(suite_config)
            if webcam_capture:
                webcam_capture.close()
            # Cleanup Mobly devices
            if hasattr(self, '_mobly_dut'):
                try:
                    self._mobly_dut.unload_snippet('mbs')
                except Exception:
                    pass
            if hasattr(self, '_mobly_peer'):
                try:
                    self._mobly_peer.unload_snippet('mbs')
                except Exception:
                    pass
```

Then update the plugin dispatch in `test_runner.py` to pass these extra fields through `PluginContext`. Change the plugin dispatch block in `run_test()` to:

```python
                elif test_type in self._plugins:
                    from smoke_test_ai.plugins.base import PluginContext
                    ctx = PluginContext(
                        adb=self.adb,
                        settings=getattr(self, '_settings', {}),
                        device_capabilities=self.device_capabilities,
                        snippet=getattr(self, '_snippet', None),
                        peer_snippet=getattr(self, '_peer_snippet', None),
                        visual_analyzer=self.visual_analyzer,
                    )
                    result = self._plugins[test_type].execute(test_case, ctx)
```

**Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add pyproject.toml smoke_test_ai/core/orchestrator.py smoke_test_ai/core/test_runner.py
git commit -m "feat: integrate plugins into orchestrator with Mobly snippet lifecycle"
```

---

### Task 7: Full test run + cleanup

**Step 1: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests pass (existing + new)

**Step 2: Verify test plan HTML generation with new types**

```bash
python -c "
from pathlib import Path
from smoke_test_ai.reporting.test_plan_reporter import TestPlanReporter
import yaml
with open('config/test_suites/smoke_basic.yaml') as f:
    suite = yaml.safe_load(f)
TestPlanReporter().generate(suite, Path('results/Product-A_test_plan.html'))
print('Generated successfully')
"
```

**Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "chore: final cleanup for plugin architecture"
```

---

Plan complete and saved to `docs/plans/2026-03-01-functional-test-plugin-implementation.md`.

**Two execution options:**

**1. Subagent-Driven (this session)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** — Open new session with `executing-plans`, batch execution with checkpoints

Which approach?