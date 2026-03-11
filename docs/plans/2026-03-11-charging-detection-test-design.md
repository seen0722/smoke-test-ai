# 充電偵測測試設計

## 目標

透過 USB 斷電/上電（uhubctl），驗證裝置正確偵測充電狀態變化。利用現有 `UsbPowerController` 實現自動化充電偵測測試。

## 測試流程

```
1. 記錄初始狀態（確認 USB powered: true）
2. USB power off（斷電）
3. 等待 off_duration 秒（預設 5s，可設定）
4. USB power on（上電）
5. 等待 ADB 重連 + settle_time 秒
6. 檢查斷電期間狀態：AC powered: false + USB powered: false + status: 3 (discharging)
7. 檢查上電後狀態：任一 powered: true + status: 2 (charging)
```

注意：斷電期間 ADB 會斷線，無法即時查詢 battery status。實際做法是：
- 斷電前記錄初始狀態（應為充電中）
- 上電後 ADB 重連，查詢當前狀態（應恢復充電）
- 為了驗證斷電期間確實停止充電，在上電+ADB重連後先**短暫查詢**（此時 status 應已恢復為 charging）
- 實際驗證斷電效果：比較斷電前後狀態變化，確認系統能正確切換

修正流程：
```
1. 確認初始狀態：任一 powered: true + status: 2 (charging)
2. USB power off
3. 等待 off_duration 秒（預設 5s）
4. USB power on
5. 等待 ADB 重連（wait_for_device）
6. 等待 settle_time 秒（預設 5s）讓充電狀態穩定
7. 確認恢復狀態：任一 powered: true + status: 2 (charging)
```

若初始狀態不是充電中，測試直接 FAIL（前置條件不滿足）。

## 實作方式

新增 `charging` plugin，從 `PluginContext` 取得 `usb_power` controller。

### YAML 測試定義

```yaml
- id: "charging_detection"
  name: "充電偵測測試"
  type: "charging"
  action: "detect"
  params:
    off_duration: 5        # 斷電秒數
    settle_time: 5         # 上電後等待秒數
  depends_on: "charging_connected"
  requires:
    device_capability: "usb_power"
```

### 判定邏輯

- 初始狀態：任一 `powered: true` AND `status: 2` → 前置條件通過
- 上電恢復後：任一 `powered: true` AND `status: 2` → 測試通過
- 無 `usb_power` controller → SKIP
- 任一條件不符 → FAIL，附帶 `dumpsys battery` 完整輸出

### Battery Status 值對照

| 值 | 意義 |
|----|------|
| 1 | BATTERY_STATUS_UNKNOWN |
| 2 | BATTERY_STATUS_CHARGING |
| 3 | BATTERY_STATUS_DISCHARGING |
| 4 | BATTERY_STATUS_NOT_CHARGING |
| 5 | BATTERY_STATUS_FULL |

## 影響檔案

| 檔案 | 動作 |
|------|------|
| `smoke_test_ai/plugins/charging.py` | **新建** — ChargingPlugin |
| `smoke_test_ai/plugins/__init__.py` | 註冊 charging type |
| `smoke_test_ai/core/test_runner.py` | PluginContext 傳入 usb_power |
| `config/test_suites/smoke_basic.yaml` | 新增 charging_detection 測試項 |
| `tests/test_plugins.py` | 新增 ~4 個測試 |

## PluginContext 擴充

`PluginContext` 需要新增 `usb_power` 欄位：

```python
@dataclass
class PluginContext:
    adb: AdbController
    settings: dict
    device_capabilities: dict
    visual_analyzer: Any = None
    snippet: Any = None
    usb_power: Any = None        # 新增
```

`test_runner.py` 建立 PluginContext 時傳入 `usb_power`。
`orchestrator.py` 將 `usb_power` 傳給 TestRunner。

## 測試策略

1. `test_charging_detect_pass` — 正常流程：初始充電 → 斷電 → 上電 → 恢復充電
2. `test_charging_detect_no_usb_power` — 無 usb_power controller → SKIP
3. `test_charging_detect_initial_not_charging` — 初始非充電狀態 → FAIL
4. `test_charging_detect_not_recovered` — 上電後未恢復充電 → FAIL

全部 mock `usb_power` 和 `adb.shell`，不需實際硬體。
