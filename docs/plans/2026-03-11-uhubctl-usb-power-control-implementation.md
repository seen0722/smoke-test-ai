# uhubctl USB 電源控制整合 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 整合 uhubctl USB 電源控制，讓 smoke test 流程能自動 power cycle DUT 的 USB port，取代手動拔插。

**Architecture:** 新增 `UsbPowerController` driver 封裝 uhubctl CLI。在 device YAML 中設定 hub location + port。Orchestrator 建立實例並傳入 BlindRunner，在 flash 後、factory reset 後、USB 偵測超時時自動觸發 power cycle。

**Tech Stack:** uhubctl CLI, subprocess, YAML config

---

## Task 1: UsbPowerController driver — 核心類別

**Files:**
- Create: `smoke_test_ai/drivers/usb_power.py`
- Create: `tests/test_usb_power.py`

**Step 1: Write the failing tests**

```python
# tests/test_usb_power.py
import subprocess
from unittest.mock import patch, MagicMock, call
from smoke_test_ai.drivers.usb_power import UsbPowerController


class TestUsbPowerController:
    def _make_ctrl(self):
        return UsbPowerController(hub_location="1-1", port=1, off_duration=2.0)

    @patch("smoke_test_ai.drivers.usb_power.subprocess.run")
    def test_power_off_calls_uhubctl(self, mock_run):
        """power_off() calls uhubctl with correct args."""
        mock_run.return_value = MagicMock(returncode=0, stdout="Port 1: 0000 off")
        ctrl = self._make_ctrl()
        assert ctrl.power_off() is True
        mock_run.assert_called_once_with(
            ["uhubctl", "-l", "1-1", "-p", "1", "-a", "off"],
            capture_output=True, text=True, timeout=10,
        )

    @patch("smoke_test_ai.drivers.usb_power.subprocess.run")
    def test_power_on_calls_uhubctl(self, mock_run):
        """power_on() calls uhubctl with -a on."""
        mock_run.return_value = MagicMock(returncode=0, stdout="Port 1: 0100 power")
        ctrl = self._make_ctrl()
        assert ctrl.power_on() is True
        mock_run.assert_called_once_with(
            ["uhubctl", "-l", "1-1", "-p", "1", "-a", "on"],
            capture_output=True, text=True, timeout=10,
        )

    @patch("smoke_test_ai.drivers.usb_power.time.sleep")
    @patch("smoke_test_ai.drivers.usb_power.subprocess.run")
    def test_power_cycle_sequence(self, mock_run, mock_sleep):
        """power_cycle() calls off → sleep → on in correct order."""
        mock_run.return_value = MagicMock(returncode=0, stdout="ok")
        ctrl = self._make_ctrl()
        assert ctrl.power_cycle() is True
        assert mock_run.call_count == 2
        # First call: off
        assert mock_run.call_args_list[0][0][0][5] == "off"
        # Sleep with off_duration
        mock_sleep.assert_called_once_with(2.0)
        # Second call: on
        assert mock_run.call_args_list[1][0][0][5] == "on"

    @patch("smoke_test_ai.drivers.usb_power.subprocess.run")
    def test_power_off_failure_returns_false(self, mock_run):
        """uhubctl non-zero exit → returns False."""
        mock_run.return_value = MagicMock(returncode=1, stdout="error")
        ctrl = self._make_ctrl()
        assert ctrl.power_off() is False

    @patch("smoke_test_ai.drivers.usb_power.time.sleep")
    @patch("smoke_test_ai.drivers.usb_power.subprocess.run")
    def test_power_cycle_custom_duration(self, mock_run, mock_sleep):
        """power_cycle(off_duration=5.0) overrides default."""
        mock_run.return_value = MagicMock(returncode=0, stdout="ok")
        ctrl = self._make_ctrl()
        ctrl.power_cycle(off_duration=5.0)
        mock_sleep.assert_called_once_with(5.0)
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_usb_power.py -v`
Expected: FAIL (ImportError — module not found)

**Step 3: Write implementation**

```python
# smoke_test_ai/drivers/usb_power.py
import subprocess
import time
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)


class UsbPowerController:
    """Control USB port power via uhubctl."""

    def __init__(self, hub_location: str, port: int, off_duration: float = 3.0):
        self.hub_location = hub_location
        self.port = port
        self.off_duration = off_duration

    def _run_uhubctl(self, action: str) -> bool:
        cmd = ["uhubctl", "-l", self.hub_location, "-p", str(self.port), "-a", action]
        logger.info(f"USB power {action}: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                logger.warning(f"uhubctl failed (rc={result.returncode}): {result.stdout}")
                return False
            logger.info(f"USB power {action} OK")
            return True
        except FileNotFoundError:
            logger.warning("uhubctl not found. Install with: brew install uhubctl (macOS) or apt install uhubctl (Ubuntu)")
            return False
        except subprocess.TimeoutExpired:
            logger.warning("uhubctl timed out")
            return False

    def power_off(self) -> bool:
        return self._run_uhubctl("off")

    def power_on(self) -> bool:
        return self._run_uhubctl("on")

    def power_cycle(self, off_duration: float | None = None) -> bool:
        duration = off_duration if off_duration is not None else self.off_duration
        if not self.power_off():
            return False
        time.sleep(duration)
        return self.power_on()
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_usb_power.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add smoke_test_ai/drivers/usb_power.py tests/test_usb_power.py
git commit -m "feat: add UsbPowerController driver for uhubctl integration"
```

---

## Task 2: Device YAML 新增 usb_power 設定

**Files:**
- Modify: `config/devices/product_a.yaml`

**Step 1: Add usb_power section**

在 `config/devices/product_a.yaml` 的 `screen_capture` 區塊之後、`setup_wizard` 之前加入：

```yaml
  usb_power:
    hub_location: "1-1"
    port: 1
    off_duration: 3.0
```

**Step 2: Verify YAML is valid**

Run: `python -c "import yaml; print(yaml.safe_load(open('config/devices/product_a.yaml'))['device']['usb_power'])"`
Expected: `{'hub_location': '1-1', 'port': 1, 'off_duration': 3.0}`

**Step 3: Commit**

```bash
git add config/devices/product_a.yaml
git commit -m "config: add usb_power settings for Product-A"
```

---

## Task 3: Orchestrator 初始化 + Flash 後 power cycle

**Files:**
- Modify: `smoke_test_ai/core/orchestrator.py:1-6` (imports), `:331-349` (run method)
- Test: `tests/test_orchestrator.py`

**Step 1: Write the failing tests**

```python
# tests/test_orchestrator.py — add to TestOrchestratorRun class

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_flash_triggers_power_cycle(self, MockAdb, mock_sleep, settings, device_config):
        """After flash, power_cycle is called if usb_power configured."""
        device_config["device"]["usb_power"] = {
            "hub_location": "1-1", "port": 1, "off_duration": 2.0,
        }
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb_inst = self._mock_adb()
        MockAdb.return_value = mock_adb_inst

        mock_flash_driver = MagicMock()
        with patch.object(orch, "_get_flash_driver", return_value=mock_flash_driver), \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"), \
             patch("smoke_test_ai.core.orchestrator.UsbPowerController") as MockPower:
            mock_power = MagicMock()
            mock_power.power_cycle.return_value = True
            MockPower.return_value = mock_power
            orch.run(serial="FAKE", build_dir="/some/build")
            mock_power.power_cycle.assert_called_once()

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_flash_no_power_cycle_when_unconfigured(self, MockAdb, mock_sleep, settings, device_config):
        """Without usb_power config, no power cycle after flash."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb_inst = self._mock_adb()
        MockAdb.return_value = mock_adb_inst

        mock_flash_driver = MagicMock()
        with patch.object(orch, "_get_flash_driver", return_value=mock_flash_driver), \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            orch.run(serial="FAKE", build_dir="/some/build")
            # No crash, no power cycle call
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_orchestrator.py -k "power_cycle" -v`
Expected: FAIL (ImportError or AttributeError)

**Step 3: Write implementation**

Add import at top of `orchestrator.py`:

```python
from smoke_test_ai.drivers.usb_power import UsbPowerController
```

Modify `run()` method — after `adb = AdbController(serial=serial)` (line 340), add UsbPowerController init:

```python
        adb = AdbController(serial=serial)

        # Initialize USB power controller if configured
        usb_power_cfg = self.device_config.get("usb_power")
        usb_power = UsbPowerController(
            hub_location=usb_power_cfg["hub_location"],
            port=usb_power_cfg["port"],
            off_duration=usb_power_cfg.get("off_duration", 3.0),
        ) if usb_power_cfg else None
```

After flash (line 349 `time.sleep(10)`), add power cycle:

```python
            time.sleep(10)
            if usb_power:
                logger.info("USB power cycle after flash...")
                usb_power.power_cycle()
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add smoke_test_ai/core/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: orchestrator power cycle after flash"
```

---

## Task 4: BlindRunner 整合 — power_cycle action + 超時恢復

**Files:**
- Modify: `smoke_test_ai/runners/blind_runner.py:12` (__init__), `:43-53` (handler map), `:133-181` (_wait_for_adb)
- Test: `tests/test_blind_runner.py`

**Step 1: Write the failing tests**

```python
# tests/test_blind_runner.py — add new class

class TestBlindRunnerPowerCycle:
    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_power_cycle_action(self, mock_sleep):
        """power_cycle action in setup flow triggers usb_power.power_cycle()."""
        runner, hid, adb = _make_runner([
            {"action": "power_cycle", "delay": 1.0, "description": "USB power reset"},
        ])
        mock_power = MagicMock()
        mock_power.power_cycle.return_value = True
        runner.usb_power = mock_power

        result = runner.run()

        assert result is True
        mock_power.power_cycle.assert_called_once()

    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    def test_power_cycle_action_no_controller(self, mock_sleep):
        """power_cycle action without usb_power configured → skip, return True."""
        runner, hid, adb = _make_runner([
            {"action": "power_cycle", "delay": 1.0},
        ])
        # usb_power is None by default

        result = runner.run()

        assert result is True

    @patch("smoke_test_ai.runners.blind_runner.usb.core.find")
    @patch("smoke_test_ai.runners.blind_runner.time.sleep")
    @patch("smoke_test_ai.runners.blind_runner.time.time")
    def test_wait_for_adb_power_cycle_on_timeout(self, mock_time, mock_sleep, mock_usb_find):
        """USB detection timeout triggers power_cycle before returning False."""
        runner, hid, adb = _make_runner([
            {"action": "wait_for_adb", "timeout": 5},
        ])
        mock_power = MagicMock()
        mock_power.power_cycle.return_value = True
        runner.usb_power = mock_power

        # Simulate time passing beyond timeout — no device found
        mock_time.side_effect = [0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        mock_usb_find.return_value = []
        adb.is_connected.return_value = False

        result = runner.run()

        assert result is False
        mock_power.power_cycle.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_blind_runner.py -k "power_cycle" -v`
Expected: FAIL

**Step 3: Write implementation**

Modify `BlindRunner.__init__` (line 12) to accept `usb_power`:

```python
    def __init__(self, hid, adb, aoa_config: dict, flow_config: dict, usb_power=None):
        self.hid = hid
        self.adb = adb
        self.aoa_config = aoa_config
        self.flow_config = flow_config
        self.usb_power = usb_power
```

Add `power_cycle` to handler map (line 43-53):

```python
        handler = {
            "tap": self._do_tap,
            "swipe": self._do_swipe,
            "type": self._do_type,
            "key": self._do_key,
            "wake": self._do_wake,
            "home": self._do_home,
            "back": self._do_back,
            "sleep": self._do_sleep,
            "wait_for_adb": self._do_wait_for_adb,
            "power_cycle": self._do_power_cycle,
        }.get(action)
```

Add `_do_power_cycle` method (after `_do_sleep`):

```python
    def _do_power_cycle(self, step: dict) -> bool:
        if self.usb_power is None:
            logger.warning("power_cycle action skipped: usb_power not configured")
            return True
        duration = step.get("off_duration")
        return self.usb_power.power_cycle(off_duration=duration)
```

In `_wait_for_adb()`, after the first timeout check (line 179-181), add power cycle attempt:

```python
        if not found_mode:
            # Try USB power cycle as last resort
            if self.usb_power:
                logger.info("USB detection timeout — trying power cycle...")
                self.usb_power.power_cycle()
            logger.error(f"Device not found after USB re-enumeration (timeout={timeout}s)")
            return False
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_blind_runner.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add smoke_test_ai/runners/blind_runner.py tests/test_blind_runner.py
git commit -m "feat: BlindRunner power_cycle action and timeout recovery"
```

---

## Task 5: Orchestrator 傳遞 usb_power 到 BlindRunner + Factory Reset 整合

**Files:**
- Modify: `smoke_test_ai/core/orchestrator.py:365` (BlindRunner construction)
- Modify: `cli.py:96-117` (reset-test command)

**Step 1: Pass usb_power to BlindRunner**

In `orchestrator.py`, where BlindRunner is constructed (line 365):

```python
                        runner = BlindRunner(hid=hid, adb=adb, aoa_config=aoa_cfg, flow_config=flow, usb_power=usb_power)
```

**Step 2: Update CLI reset-test command**

In `cli.py`, replace the manual unplug prompt (lines 106-110) with automated power cycle:

```python
    # USB power cycle to avoid offline charging mode
    usb_power_cfg = device_config.get("device", {}).get("usb_power")
    if usb_power_cfg:
        from smoke_test_ai.drivers.usb_power import UsbPowerController
        usb_power = UsbPowerController(
            hub_location=usb_power_cfg["hub_location"],
            port=usb_power_cfg["port"],
            off_duration=usb_power_cfg.get("off_duration", 3.0),
        )
        console.print("[cyan]USB power cycle to prevent offline charging...[/]")
        usb_power.power_cycle()
    else:
        console.print("\n[bold cyan]>>> Please UNPLUG the USB cable now <<<[/]")
        console.print("Wait for the device to fully boot into the home screen,")
        console.print("then plug the USB cable back in.")
        click.pause("Press any key after USB is reconnected...")
```

**Step 3: Verify all tests pass**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add smoke_test_ai/core/orchestrator.py cli.py
git commit -m "feat: pass usb_power to BlindRunner, automate factory reset power cycle"
```

---

## Task 6: 全部測試驗證 + 收尾

**Step 1: Run all tests**

```bash
python -m pytest tests/ -v --tb=short
```
Expected: ALL PASS

**Step 2: Run coverage**

```bash
python -m pytest tests/ --cov=smoke_test_ai --cov-report=term-missing
```
Expected: Coverage ≥ 69% (should increase due to new driver + integration code)

**Step 3: Verify uhubctl integration end-to-end**

```bash
uhubctl -l 1-1 -p 1 -a off && sleep 3 && uhubctl -l 1-1 -p 1 -a on
```
Expected: DUT disconnects then reconnects

---

## 關鍵檔案

| 檔案 | 動作 |
|------|------|
| `smoke_test_ai/drivers/usb_power.py` | **新建** — UsbPowerController (~40 行) |
| `tests/test_usb_power.py` | **新建** — 5 個測試 |
| `config/devices/product_a.yaml` | 新增 `usb_power` 區塊 |
| `smoke_test_ai/core/orchestrator.py` | import + 初始化 + flash 後 power cycle + 傳遞到 BlindRunner |
| `smoke_test_ai/runners/blind_runner.py` | `__init__` 加 usb_power 參數 + power_cycle action + 超時恢復 |
| `cli.py` | reset-test 自動 power cycle 取代手動拔插 |
| `tests/test_orchestrator.py` | 新增 2 個測試 |
| `tests/test_blind_runner.py` | 新增 3 個測試 |

## 驗證

1. `python -m pytest tests/ -v` — 全部測試通過
2. `python -m pytest tests/ --cov=smoke_test_ai` — Coverage ≥ 69%
3. `uhubctl -l 1-1 -p 1 -a off && sleep 3 && uhubctl -l 1-1 -p 1 -a on` — DUT 斷電再恢復
4. 接上 DUT，`smoke-test reset-test --device product_a --suite smoke_basic --serial <serial>` — 自動 power cycle 無需手動拔插
