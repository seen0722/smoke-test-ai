# uhubctl USB 電源控制整合設計

## 背景

使用 RSHTECH RSH-ST07C USB hub + `uhubctl` 工具，實現程式化控制 DUT 的 USB 電源。解決 4 個場景：

1. Factory reset 後防止離線充電模式
2. Flash 後重開機確保乾淨的 USB re-enumeration
3. Blind Runner USB 偵測超時時自動恢復
4. Setup flow YAML 中可手動觸發 power cycle

## 硬體資訊

- Hub: RSHTECH RSH-ST07C（內部使用 VIA Labs 2109:2822）
- Hub location: `1-1`，DUT port: `1`
- 不需要 sudo（macOS），Ubuntu 上需設定 udev rule
- `uhubctl -l 1-1 -p 1 -a off/on` 已驗證可用

## 設計

### 1. UsbPowerController Driver

**新檔案：** `smoke_test_ai/drivers/usb_power.py`

```python
class UsbPowerController:
    def __init__(self, hub_location: str, port: int, off_duration: float = 3.0):
        self.hub_location = hub_location
        self.port = port
        self.off_duration = off_duration

    def power_off(self) -> bool: ...
    def power_on(self) -> bool: ...
    def power_cycle(self, off_duration: float | None = None) -> bool:
        """power off → sleep → power on → return success"""
```

- 內部呼叫 `subprocess.run(["uhubctl", "-l", loc, "-p", str(port), "-a", action])`
- 檢查 returncode + stdout 確認操作成功
- 失敗時 log warning，不拋 exception

**Device YAML 設定：**

```yaml
device:
  usb_power:
    hub_location: "1-1"
    port: 1
    off_duration: 3.0  # 可選，預設 3 秒
```

若 `usb_power` 區塊不存在，所有電源控制呼叫自動 skip。

### 2. 整合點

#### 2a. Factory Reset（orchestrator）

```
factory_reset() → 等 ADB 斷線 → power_cycle() → wait_for_boot()
```

#### 2b. Flash 後重開機（orchestrator）

```
flash 完成 → post_flash 指令 → power_cycle() → wait_for_boot()
```

#### 2c. Blind Runner 恢復（blind_runner）

```
_wait_for_adb() USB 偵測超時 → power_cycle() → 重試偵測
```

#### 2d. Setup Flow Action（blind_runner）

```yaml
- action: power_cycle
  description: "USB 電源重置"
```

**共同原則：**
- UsbPowerController 為 None 時自動 skip
- power_cycle 失敗只 log warning，不中斷流程

### 3. 初始化與傳遞

```
Orchestrator (建立 UsbPowerController)
  ├── self.usb_power          → flash 後、factory reset 直接使用
  ├── BlindRunner(usb_power=) → _wait_for_adb() 恢復、power_cycle action
  └── AdbController           → 不傳入，由 orchestrator 層呼叫
```

- BlindRunner.__init__ 新增 `usb_power: UsbPowerController | None = None`
- CLI `reset-test` 命令也建立 UsbPowerController，取代手動拔插提示

### 4. 測試策略

**新檔案 `tests/test_usb_power.py`（5 個測試）：**
- test_power_off_calls_uhubctl
- test_power_on_calls_uhubctl
- test_power_cycle_sequence
- test_power_off_failure_returns_false
- test_power_cycle_skip_when_none

**整合測試（4 個測試，加到現有檔案）：**
- test_flash_triggers_power_cycle (test_orchestrator.py)
- test_flash_no_power_cycle_when_unconfigured (test_orchestrator.py)
- test_wait_for_adb_power_cycle_on_timeout (test_blind_runner.py)
- test_power_cycle_action (test_blind_runner.py)

共 9 個測試，全部 mock subprocess.run。

## 跨平台

| | macOS | Ubuntu |
|--|-------|--------|
| 安裝 | `brew install uhubctl` | `sudo apt install uhubctl` |
| 權限 | 不需要 sudo | 需 sudo 或 udev rule |
| 程式碼 | 相同 | 相同 |

## 影響檔案

| 檔案 | 動作 |
|------|------|
| `smoke_test_ai/drivers/usb_power.py` | **新建** — UsbPowerController |
| `smoke_test_ai/core/orchestrator.py` | 初始化 + flash/reset 整合 |
| `smoke_test_ai/runners/blind_runner.py` | _wait_for_adb + power_cycle action |
| `config/devices/product_a.yaml` | 新增 usb_power 區塊 |
| `tests/test_usb_power.py` | **新建** — 5 個測試 |
| `tests/test_orchestrator.py` | 新增 2 個測試 |
| `tests/test_blind_runner.py` | 新增 2 個測試 |
