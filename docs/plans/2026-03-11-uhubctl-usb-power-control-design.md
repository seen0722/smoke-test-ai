# uhubctl USB 電源控制整合設計

## 背景

使用支援 per-port power switching (PPPS) 的 USB hub + `uhubctl` 工具，實現程式化控制 DUT 的 USB 電源。解決 4 個場景：

1. Factory reset 後防止離線充電模式
2. Flash 後重開機確保乾淨的 USB re-enumeration
3. Blind Runner USB 偵測超時時自動恢復
4. Setup flow YAML 中可手動觸發 power cycle

## 硬體資訊

### 目前使用

- **Hub:** RSHTECH RSH-ST07C（7 port USB 3.0）
- **晶片:** VIA Labs VL822（VID:PID `2109:2822`）
- **Hub location:** `1-1`，DUT port: `1`
- **限制:** 7 port hub 內部由兩顆 4-port 晶片串接（4+4-1=7），僅 4 port 可透過 uhubctl 控制
- **驗證:** `uhubctl -l 1-1 -p 1 -a off/on` 已確認可控制 DUT 電源

### USB Hub 選購建議

選擇支援 uhubctl 的 hub 時，**必須確認支援 per-port power switching (PPPS)**。並非所有 USB hub 都支援，即使標示 "individually powered" 也不代表支援軟體控制。

**推薦晶片組（依可靠度排序）：**

| 晶片廠商 | VID:PID 範圍 | 說明 |
|----------|-------------|------|
| VIA Labs (VL81x/VL82x) | `2109:xxxx` | 最常見，社群驗證最多 |
| Realtek (RTL5411) | `0bda:0411` | 高 port 數 hub 常用 |
| Genesys Logic (GL850G/GL3510) | `05E3:0608/0610` | D-Link、BenQ 常見 |
| Texas Instruments (TUSB) | `0451:xxxx` | TI 評估板、LG 螢幕 |

**推薦型號：**

| 型號 | Port 數 | USB | VID:PID | 備註 |
|------|---------|-----|---------|------|
| **RSHTECH RSH-ST07C** | 7 (4 可控) | 3.0 | `2109:2822` | 目前使用中，價格實惠 |
| **RSHTECH RSH-A37S** | 7 | 3.0 | `2109:2822` | 同晶片，無已知限制 |
| **Plugable USB3-HUB7BC** | 7 | 3.0 | `2109:0813` | uhubctl 社群推薦 |
| **AmazonBasics HU9002V1** | 7 | 3.1 | `2109:2817` | 容易取得 |
| **Sipolar A-173** | 7 | 3.0 | `0bda:0411` | 工業級，適合測試實驗室 |

**多 DUT 場景選擇：**

| 型號 | Port 數 | VID:PID | 備註 |
|------|---------|---------|------|
| **RSHTECH RSH-A10** | 10 | `0bda:0411` | 3 顆 4-port 晶片串接 |
| **RSHTECH RSH-A16** | 16 | `0bda:0411` | 大規模測試用 |

### 重要注意事項

1. **USB 3.0 雙虛擬 hub：** USB 3.0 hub 連接 USB 3 port 時，系統會看到兩個獨立 hub（USB2 + USB3）。uhubctl 會自動處理兩者，除非使用 `-e` 參數
2. **VBUS 不一定斷電：** 部分 hub 只切斷資料連接但不切斷 VBUS 電源。購買後務必用 USB 風扇/燈泡實測確認
3. **7/10 port hub 內部串接：** 7 port = 兩顆 4-port 晶片，10 port = 三顆。部分 port 用於內部串接，不可控制
4. **Raspberry Pi 限制：** 所有 RPi 型號僅支援 ganged（全部 port 同時切換），不支援 per-port。需外接 hub
5. **Windows 不支援：** uhubctl 不支援 Windows 的 USB 電源切換

### 跨平台安裝

| | macOS | Ubuntu |
|--|-------|--------|
| 安裝 | `brew install uhubctl` | `sudo apt install uhubctl` |
| 權限 | 不需要 sudo | 需 sudo 或 udev rule |
| macOS 26+ | 需 `brew install libusb --head`（等待 libusb 1.0.30） | N/A |
| Linux 6.0+ | N/A | 使用 kernel sysfs 介面，更穩定 |

**Ubuntu udev rule（免 sudo）：**

```bash
# /etc/udev/rules.d/52-usb-hub-power.rules
SUBSYSTEM=="usb", ATTR{idVendor}=="2109", MODE="0666"
```

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### 資料來源

- [uhubctl GitHub — 支援裝置列表](https://github.com/mvp/uhubctl)
- [RSHTECH RSH-ST07C 4-port 限制說明](https://tinyurl.com/4pjnujrn)
- 實機驗證：macOS Darwin 25.3.0 + RSH-ST07C + uhubctl 2.6.0

---

## 設計

### 1. UsbPowerController Driver

**檔案：** `smoke_test_ai/drivers/usb_power.py`

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
    off_duration: 20.0       # 斷電持續時間（秒）
    reset_delay: 3           # factory reset 後等待裝置關機再斷電（秒）
```

若 `usb_power` 區塊不存在，所有電源控制呼叫自動 skip。

### 2. 整合點

#### 2a. Factory Reset（orchestrator + cli）

```
factory_reset() → 等 reset_delay 秒 → power_cycle(off_duration=20) → wait_for_boot()
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

### 4. WiFi 子系統就緒等待

Factory reset 後 WiFi adapter 需要較長時間初始化，`connect_wifi()` 支援 `wifi_timeout` 參數：

- Factory reset 場景（`skip_setup=False`）：`wifi_timeout=45`
- 一般場景（`skip_setup=True`）：`wifi_timeout=15`（預設）

流程：`_wait_wifi_subsystem(timeout)` → `enable_wifi(timeout)` → `connect_wifi()`

### 5. 測試策略

**`tests/test_usb_power.py`（5 個測試）：**
- test_power_off_calls_uhubctl
- test_power_on_calls_uhubctl
- test_power_cycle_sequence
- test_power_off_failure_returns_false
- test_power_cycle_custom_duration

**整合測試（5 個測試，加到現有檔案）：**
- test_flash_triggers_power_cycle (test_orchestrator.py)
- test_flash_no_power_cycle_when_unconfigured (test_orchestrator.py)
- test_wait_for_adb_power_cycle_on_timeout (test_blind_runner.py)
- test_power_cycle_action (test_blind_runner.py)
- test_power_cycle_action_no_controller (test_blind_runner.py)

**WiFi 子系統測試（2 個，test_adb_controller.py）：**
- test_wait_wifi_subsystem_ready
- test_wait_wifi_subsystem_timeout

共 12 個測試，全部 mock subprocess.run。

## 影響檔案

| 檔案 | 動作 |
|------|------|
| `smoke_test_ai/drivers/usb_power.py` | **新建** — UsbPowerController |
| `smoke_test_ai/core/orchestrator.py` | 初始化 + flash/reset 整合 + WiFi timeout |
| `smoke_test_ai/runners/blind_runner.py` | _wait_for_adb + power_cycle action |
| `smoke_test_ai/drivers/adb_controller.py` | _wait_wifi_subsystem + wifi_timeout |
| `config/devices/product_a.yaml` | 新增 usb_power 區塊 |
| `cli.py` | reset-test 自動化 USB power cycle + --reset-delay |
| `tests/test_usb_power.py` | **新建** — 5 個測試 |
| `tests/test_orchestrator.py` | 新增 2 個測試 |
| `tests/test_blind_runner.py` | 新增 3 個測試 |
| `tests/test_adb_controller.py` | 新增 2 個測試 |
