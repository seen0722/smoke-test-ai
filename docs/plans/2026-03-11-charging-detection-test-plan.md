# Charging Detection Test Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 新增充電偵測測試 — 透過 USB 斷電/上電驗證裝置正確偵測充電狀態變化。

**Architecture:** 新增 `ChargingPlugin`，透過 `PluginContext.usb_power` 控制 USB 電源。需擴充 `PluginContext` 加入 `usb_power` 欄位，並讓 orchestrator/test_runner 傳入。在 `smoke_basic.yaml` 新增一個 charging_detection 測試項。

**Tech Stack:** uhubctl (UsbPowerController), `dumpsys battery`, existing plugin architecture

---

## Context

現有程式碼關鍵介面：

- `PluginContext` (`smoke_test_ai/plugins/base.py:8-15`) — 沒有 `usb_power` 欄位，需新增
- `_init_plugins()` (`orchestrator.py:297-330`) — 建立 plugin dict，需加入 `ChargingPlugin`
- `test_runner.py:90-100` — 建立 `PluginContext` 傳給 plugin，需加入 `usb_power`
- `orchestrator.py:463-474` — 建立 TestRunner 並注入 snippet/settings，需注入 `usb_power`
- `usb_power` 已在 `orchestrator.py:344` 建立，變數名 `usb_power`

## Task 1: PluginContext 加入 usb_power 欄位

**Files:**
- Modify: `smoke_test_ai/plugins/base.py:8-15`

**Step 1: Add usb_power field**

```python
# smoke_test_ai/plugins/base.py — PluginContext dataclass
@dataclass
class PluginContext:
    adb: AdbController
    settings: dict
    device_capabilities: dict
    snippet: object | None = None
    peer_snippet: object | None = None
    visual_analyzer: object | None = None
    usb_power: object | None = None
```

**Step 2: Run tests to verify nothing broke**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ALL PASS (新增 optional 欄位不影響現有程式碼)

**Step 3: Commit**

```bash
git add smoke_test_ai/plugins/base.py
git commit -m "feat: add usb_power field to PluginContext"
```

---

## Task 2: TestRunner 和 Orchestrator 傳入 usb_power

**Files:**
- Modify: `smoke_test_ai/core/test_runner.py:90-99`
- Modify: `smoke_test_ai/core/orchestrator.py:459-474`

**Step 1: TestRunner — 把 usb_power 傳入 PluginContext**

`test_runner.py:90-99` 的 PluginContext 建立處，加入 `usb_power`：

```python
# test_runner.py — run_test() 方法中建立 PluginContext 的區塊
ctx = PluginContext(
    adb=self.adb,
    settings=getattr(self, '_settings', {}),
    device_capabilities=self.device_capabilities,
    snippet=getattr(self, '_snippet', None),
    peer_snippet=getattr(self, '_peer_snippet', None),
    visual_analyzer=self.visual_analyzer,
    usb_power=getattr(self, '_usb_power', None),
)
```

**Step 2: Orchestrator — 注入 usb_power 到 runner**

`orchestrator.py` 在 `runner._settings = self.settings` 之後加：

```python
runner._usb_power = usb_power
```

（`usb_power` 變數已在 `orchestrator.py:344-350` 建立）

**Step 3: Run tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add smoke_test_ai/core/test_runner.py smoke_test_ai/core/orchestrator.py
git commit -m "feat: pass usb_power through TestRunner to PluginContext"
```

---

## Task 3: 建立 ChargingPlugin

**Files:**
- Create: `smoke_test_ai/plugins/charging.py`
- Test: `tests/test_plugins.py`

**Step 1: Write the failing tests**

在 `tests/test_plugins.py` 最後新增：

```python
class TestChargingPlugin:
    @pytest.fixture
    def charging_plugin(self):
        from smoke_test_ai.plugins.charging import ChargingPlugin
        return ChargingPlugin()

    def test_charging_detect_pass(self, charging_plugin):
        """Full flow: initial charging → power off → power on → still charging."""
        adb = MagicMock()
        usb_power = MagicMock()
        usb_power.power_off.return_value = True
        usb_power.power_on.return_value = True
        # dumpsys battery outputs: initial (charging) → after recovery (charging)
        adb.shell.side_effect = [
            MagicMock(stdout="  AC powered: false\n  USB powered: true\n  status: 2\n"),  # initial
            MagicMock(stdout="  AC powered: false\n  USB powered: true\n  status: 2\n"),  # after recovery
        ]
        adb.wait_for_device.return_value = True
        ctx = PluginContext(adb=adb, settings={}, device_capabilities={}, usb_power=usb_power)
        tc = {"id": "chg1", "name": "Charging", "type": "charging", "action": "detect",
              "params": {"off_duration": 1, "settle_time": 0}}
        with patch("smoke_test_ai.plugins.charging.time.sleep"):
            result = charging_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        usb_power.power_off.assert_called_once()
        usb_power.power_on.assert_called_once()

    def test_charging_detect_no_usb_power(self, charging_plugin):
        """No usb_power controller → SKIP."""
        adb = MagicMock()
        ctx = PluginContext(adb=adb, settings={}, device_capabilities={}, usb_power=None)
        tc = {"id": "chg2", "name": "Charging", "type": "charging", "action": "detect", "params": {}}
        result = charging_plugin.execute(tc, ctx)
        assert result.status == TestStatus.SKIP

    def test_charging_detect_initial_not_charging(self, charging_plugin):
        """Initial state not charging → FAIL."""
        adb = MagicMock()
        usb_power = MagicMock()
        adb.shell.return_value = MagicMock(
            stdout="  AC powered: false\n  USB powered: false\n  status: 3\n"
        )
        ctx = PluginContext(adb=adb, settings={}, device_capabilities={}, usb_power=usb_power)
        tc = {"id": "chg3", "name": "Charging", "type": "charging", "action": "detect", "params": {}}
        result = charging_plugin.execute(tc, ctx)
        assert result.status == TestStatus.FAIL
        assert "not charging" in result.message.lower() or "初始" in result.message

    def test_charging_detect_not_recovered(self, charging_plugin):
        """Power on but charging not recovered → FAIL."""
        adb = MagicMock()
        usb_power = MagicMock()
        usb_power.power_off.return_value = True
        usb_power.power_on.return_value = True
        adb.shell.side_effect = [
            MagicMock(stdout="  AC powered: false\n  USB powered: true\n  status: 2\n"),  # initial OK
            MagicMock(stdout="  AC powered: false\n  USB powered: false\n  status: 3\n"),  # not recovered
        ]
        adb.wait_for_device.return_value = True
        ctx = PluginContext(adb=adb, settings={}, device_capabilities={}, usb_power=usb_power)
        tc = {"id": "chg4", "name": "Charging", "type": "charging", "action": "detect",
              "params": {"off_duration": 1, "settle_time": 0}}
        with patch("smoke_test_ai.plugins.charging.time.sleep"):
            result = charging_plugin.execute(tc, ctx)
        assert result.status == TestStatus.FAIL
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_plugins.py::TestChargingPlugin -v`
Expected: FAIL (ModuleNotFoundError)

**Step 3: Write implementation**

```python
# smoke_test_ai/plugins/charging.py
import re
import time

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.base import TestPlugin, PluginContext


class ChargingPlugin(TestPlugin):
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        action = test_case.get("action", "")
        if action == "detect":
            return self._detect(test_case, context)
        return TestResult(
            id=test_case["id"], name=test_case["name"],
            status=TestStatus.ERROR,
            message=f"Unknown charging action: {action}",
        )

    def _detect(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        params = tc.get("params", {})
        off_duration = params.get("off_duration", 5)
        settle_time = params.get("settle_time", 5)

        if ctx.usb_power is None:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="usb_power not configured, skipping charging test")

        adb = ctx.adb

        # 1. Check initial state — must be charging
        initial = self._get_battery_info(adb)
        if not initial["powered"]:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Initial state not charging: {initial['raw']}")

        # 2. Power off → wait → power on
        ctx.usb_power.power_off()
        time.sleep(off_duration)
        ctx.usb_power.power_on()

        # 3. Wait for ADB reconnection + settle
        adb.wait_for_device(timeout=60)
        time.sleep(settle_time)

        # 4. Check recovered state
        recovered = self._get_battery_info(adb)
        if not recovered["powered"] or recovered["status"] != 2:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Charging not recovered after power on: "
                                      f"powered={recovered['powered']}, "
                                      f"status={recovered['status']}")

        return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                          message="Charging detection OK "
                                  "(power off → power on → charging recovered)")

    def _get_battery_info(self, adb) -> dict:
        result = adb.shell("dumpsys battery")
        stdout = result.stdout if hasattr(result, "stdout") else str(result)
        ac = bool(re.search(r"AC powered:\s*true", stdout))
        usb = bool(re.search(r"USB powered:\s*true", stdout))
        status_m = re.search(r"status:\s*(\d+)", stdout)
        status = int(status_m.group(1)) if status_m else 0
        return {
            "powered": ac or usb,
            "ac": ac,
            "usb": usb,
            "status": status,
            "raw": stdout.strip()[:200],
        }
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_plugins.py::TestChargingPlugin -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add smoke_test_ai/plugins/charging.py tests/test_plugins.py
git commit -m "feat: add ChargingPlugin with detect action"
```

---

## Task 4: 註冊 ChargingPlugin + YAML 測試項

**Files:**
- Modify: `smoke_test_ai/plugins/__init__.py`
- Modify: `smoke_test_ai/core/orchestrator.py:321-328`
- Modify: `config/test_suites/smoke_basic.yaml`

**Step 1: Register plugin**

`smoke_test_ai/plugins/__init__.py` — 新增 import 和 export：

```python
from smoke_test_ai.plugins.charging import ChargingPlugin

__all__ = [
    # ... existing ...
    "ChargingPlugin",
]
```

`orchestrator.py:321-328` — plugins dict 新增：

```python
plugins = {
    "telephony": TelephonyPlugin(),
    "camera": CameraPlugin(),
    "wifi": WifiPlugin(),
    "bluetooth": BluetoothPlugin(),
    "audio": AudioPlugin(),
    "network": NetworkPlugin(),
    "charging": ChargingPlugin(),
}
```

orchestrator.py 頂部 import 區新增：

```python
from smoke_test_ai.plugins.charging import ChargingPlugin
```

**Step 2: Add YAML test entry**

在 `config/test_suites/smoke_basic.yaml` 的 `charging_connected` 測試項之後加入：

```yaml
    - id: "charging_detection"
      name: "充電偵測測試"
      type: "charging"
      action: "detect"
      params:
        off_duration: 5
        settle_time: 5
      depends_on: "charging_connected"
      requires:
        device_capability: "usb_power"
```

**Step 3: Verify YAML valid**

Run: `python -c "import yaml; yaml.safe_load(open('config/test_suites/smoke_basic.yaml'))"`
Expected: No error

**Step 4: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add smoke_test_ai/plugins/__init__.py smoke_test_ai/core/orchestrator.py config/test_suites/smoke_basic.yaml
git commit -m "feat: register ChargingPlugin and add charging_detection test entry"
```

---

## Task 5: device_capabilities 加入 usb_power flag

**Files:**
- Modify: `smoke_test_ai/core/orchestrator.py:450-457`

YAML 測試用 `requires: device_capability: "usb_power"` 來判斷是否跳過。需要在 device_capabilities 中加入 `usb_power: True/False`。

**Step 1: Add usb_power to device_capabilities**

`orchestrator.py:450-457` 目前的 device_capabilities 建構：

```python
device_capabilities = {
    k: v for k, v in self.device_config.items()
    if isinstance(v, bool)
}
```

在這之後加一行：

```python
device_capabilities["usb_power"] = usb_power is not None
```

**Step 2: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add smoke_test_ai/core/orchestrator.py
git commit -m "feat: add usb_power flag to device_capabilities"
```

---

## 關鍵檔案

| 檔案 | 動作 |
|------|------|
| `smoke_test_ai/plugins/base.py:15` | 新增 `usb_power` 欄位 |
| `smoke_test_ai/plugins/charging.py` | **新建** — ChargingPlugin |
| `smoke_test_ai/plugins/__init__.py` | 註冊 ChargingPlugin |
| `smoke_test_ai/core/test_runner.py:92-99` | PluginContext 加入 usb_power |
| `smoke_test_ai/core/orchestrator.py` | 傳入 usb_power + device_capabilities + plugin 註冊 |
| `config/test_suites/smoke_basic.yaml` | 新增 charging_detection 測試項 |
| `tests/test_plugins.py` | 新增 4 個 ChargingPlugin 測試 |

## 驗證

1. `python -m pytest tests/ -v` — 全部測試通過
2. 接上 DUT + USB hub，執行 `smoke-test run --device product_a --suite smoke_basic --serial DEVICE_SN` 確認 charging_detection 測試通過
3. 移除 device YAML 的 usb_power 區塊，確認 charging_detection 被 SKIP
