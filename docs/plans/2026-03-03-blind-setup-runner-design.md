# Blind Setup Runner — Pre-ADB 自動化設計

**日期**: 2026-03-03
**狀態**: Approved

## 背景

全新 Android 15 user build 裝置沒有 ADB，需要透過 AOA2 HID 盲操作完成 Setup Wizard、啟用 USB Debugging，才能讓 smoke-test-ai 接管測試。

Google ATS (OmniLab) 用 WebAOA + AoaTargetPreparer 實現相同功能：錄製固定命令序列，盲操作回放。我們參考此架構，用 YAML + Python CLI 實現。

## 約束

- 目標裝置：固定單一產品（Android 15 landscape tablet）
- 無 webcam — 純盲操作
- 有 SIM 卡、不需連 WiFi（Setup Wizard 走最短路徑）
- RSA Allow 需要：釋放 AOA → ADB 連線 → 重新 AOA → 點 Allow
- 成功驗證：`adb devices` 輪詢確認裝置出現

## 架構

```
smoke-test CLI
├── record 命令（錄製）     ── ADB screencap + OpenCV UI → 輸出 YAML
├── run 命令 (Stage 1)     ── 載入 YAML → BlindRunner 逐步執行
└── AOA HID Driver（已有）  ── tap/swipe/type/key/wake/home/back
```

三個新元件：
1. **YAML step file** — `config/setup_flows/{device}.yaml`
2. **BlindRunner** — `smoke_test_ai/runners/blind_runner.py`
3. **`smoke-test record`** — CLI 錄製命令

## YAML Step File 格式

```yaml
# config/setup_flows/product_a.yaml
device: "Product-A"
screen_resolution: [2560, 1600]
orientation: landscape

steps:
  - action: wake
    description: "Wake screen"

  - action: tap
    x: 1850
    y: 1420
    delay: 2.0
    description: "Tap Start button"

  - action: swipe
    x1: 1280
    y1: 800
    x2: 1280
    y2: 200
    duration: 0.3
    delay: 1.5
    description: "Scroll down"

  - action: type
    text: "0000"
    delay: 1.0
    description: "Enter PIN"

  - action: key
    key: enter
    delay: 1.0

  - action: home
    delay: 1.0

  - action: back
    delay: 1.0

  - action: sleep
    duration: 2.0

  - action: tap
    x: 1280
    y: 900
    repeat: 7
    delay: 0.3
    description: "Tap Build number 7 times"

  - action: wait_for_adb
    timeout: 30
    description: "Release AOA, wait for ADB, re-init AOA for RSA"

  - action: tap
    x: 1500
    y: 900
    delay: 2.0
    description: "Tap Allow on RSA dialog"
```

### 支援的 Action 類型

| Action | 參數 | HID 方法 | 說明 |
|--------|------|----------|------|
| `tap` | x, y, repeat?, delay? | `hid.tap()` | 點擊，repeat 可重複 |
| `swipe` | x1, y1, x2, y2, duration?, delay? | `hid.swipe()` | 滑動手勢 |
| `type` | text, delay? | `hid.type_text()` | 鍵盤輸入文字 |
| `key` | key, delay? | `hid.send_key()` / `hid.press_enter()` | 特殊按鍵 |
| `wake` | delay? | `hid.wake_screen()` | 喚醒螢幕 |
| `home` | delay? | `hid.press_home()` | Home 鍵 |
| `back` | delay? | `hid.press_back()` | Back 鍵 |
| `sleep` | duration | `time.sleep()` | 純等待 |
| `wait_for_adb` | timeout? | 特殊流程 | 釋放 AOA → 等 ADB → 重新 AOA |

## BlindRunner

**檔案**: `smoke_test_ai/runners/blind_runner.py`

```python
class BlindRunner:
    def __init__(self, hid, adb, aoa_config, flow_config): ...
    def run(self) -> bool: ...
    def _execute_step(self, step): ...
    def _do_wait_for_adb(self, timeout): ...
```

### run() 邏輯

1. 遍歷 `steps` 列表
2. 每步 dispatch 到對應 action handler
3. 每步執行後 `time.sleep(step.get('delay', 1.0))`
4. `tap` 有 `repeat` 時，執行 N 次，每次之間 sleep `delay`
5. 全部執行完 → 回傳 True

### wait_for_adb 內部邏輯

1. `hid.close()` — 釋放 AOA，USB 裝置回到普通模式
2. 等待 USB 重新列舉（sleep 2s）
3. 輪詢 `adb devices` 直到裝置出現或 timeout
4. 重新 `_init_aoa_hid()` — 此時 PID=0x2D01（Accessory+ADB）
5. 繼續執行後續步驟（點 RSA Allow）

### 錯誤處理

- 盲操作無法偵測個別步驟成敗
- 最終驗證靠 `wait_for_adb`：ADB 連上 = 成功
- ADB timeout → `run()` 回傳 False → Orchestrator 報錯

## CLI 錄製器

**命令**: `smoke-test record --serial DEVICE_SN --device product_a`

### 流程

1. ADB 連接裝置，截取螢幕截圖
2. OpenCV `imshow` 顯示截圖
3. 使用者在圖上點擊 → 記錄 (x, y)
4. 終端互動選擇 action 類型、輸入描述
5. 按 `n` 截取下一張截圖
6. 按 `q` 結束
7. 輸出 YAML 到 `config/setup_flows/{device}.yaml`

### 支援的錄製動作

- 滑鼠左鍵點擊 → tap
- 滑鼠左鍵拖曳 → swipe（記錄起點+終點）
- 鍵盤 `t` → type（終端輸入文字）
- 鍵盤 `w` → wake
- 鍵盤 `h` → home
- 鍵盤 `b` → back
- 鍵盤 `s` → sleep（輸入秒數）
- 鍵盤 `a` → wait_for_adb
- 鍵盤 `n` → 重新截圖
- 鍵盤 `q` → 儲存並結束

## Orchestrator 整合

Stage 1 修改（`smoke_test_ai/core/orchestrator.py`）：

```python
# Stage 1: Pre-ADB Setup
if build_type == "user" and aoa_cfg.get("enabled"):
    flow_path = config_dir / "setup_flows" / f"{device_name}.yaml"
    if flow_path.exists():
        hid = self._init_aoa_hid(aoa_cfg)
        flow = yaml.safe_load(flow_path.read_text())
        runner = BlindRunner(hid, adb, aoa_cfg, flow)
        success = runner.run()
        if not success:
            logger.warning("Blind setup flow did not complete")
    else:
        logger.info("No setup flow found, skipping Stage 1")
```

## 完整執行流程（端到端）

```
1. Flash image (Stage 0)
2. AOA init → HID registered (keyboard + touch + consumer)
3. BlindRunner 執行 YAML steps:
   a. Wake screen
   b. Setup Wizard: tap/swipe 按固定座標走完
   c. Navigate to Settings → About → tap Build number ×7
   d. Developer Options → toggle USB Debugging → confirm OK
   e. wait_for_adb:
      i.   close AOA
      ii.  adb devices 輪詢 → 裝置出現 (unauthorized)
      iii. re-init AOA (PID 0x2D01)
      iv.  tap "Allow" on RSA dialog
   f. sleep → 等 ADB 穩定
4. Stage 2: ADB Bootstrap (FBE unlock, WiFi, Mobly snippet)
5. Stage 3: Test Execute
6. Stage 4: Report
```

## 與 Google ATS 的比較

| 面向 | Google ATS | smoke-test-ai |
|------|-----------|---------------|
| 錄製工具 | WebAOA（瀏覽器 WebUSB） | CLI + OpenCV（ADB screencap） |
| 命令格式 | 純文字 `"click 500 800"` | YAML 結構化 |
| 執行引擎 | AoaTargetPreparer (Java) | BlindRunner (Python) |
| HID 驅動 | aoa-helper (Java, javax.usb) | AoaHidDriver (Python, PyUSB) |
| 座標系統 | 固定 360×640 正規化 | 實際像素 + HID 0-10000 正規化 |
| RSA 處理 | Tradefed 框架處理 | wait_for_adb step 自行處理 |
| 錯誤恢復 | 無 | wait_for_adb timeout 檢測 |
| Vision/LLM | 無 | 無（此場景不用） |

## 檔案清單

| 檔案 | 動作 |
|------|------|
| `smoke_test_ai/runners/__init__.py` | 新建 |
| `smoke_test_ai/runners/blind_runner.py` | 新建 — BlindRunner |
| `cli.py` | 新增 `record` 命令 |
| `smoke_test_ai/core/orchestrator.py` | Stage 1 整合 BlindRunner |
| `config/setup_flows/` | 新建目錄 |
| `tests/test_blind_runner.py` | 新建 — 單元測試 |

## 測試計畫

### 單元測試（test_blind_runner.py）

- `test_tap_action` — tap 正確呼叫 hid.tap()
- `test_tap_with_repeat` — repeat=7 呼叫 7 次 tap
- `test_swipe_action` — swipe 正確呼叫 hid.swipe()
- `test_type_action` — type 正確呼叫 hid.type_text()
- `test_key_enter` — key=enter 呼叫 press_enter
- `test_wake_action` — wake 呼叫 wake_screen
- `test_home_action` — home 呼叫 press_home
- `test_back_action` — back 呼叫 press_back
- `test_sleep_action` — sleep 呼叫 time.sleep
- `test_wait_for_adb_success` — 成功流程：close → poll → re-init
- `test_wait_for_adb_timeout` — timeout 回傳 False
- `test_run_full_flow` — 多步驟序列全部執行
- `test_delay_between_steps` — 驗證 delay 參數生效
- `test_unknown_action_skipped` — 未知 action 跳過不中斷

### 端到端驗證

1. 在 userdebug build 上用 `smoke-test record` 錄製流程
2. 刷 user build 後用 `smoke-test run` 執行 Stage 1
3. 確認 ADB 連上、USB debugging 已啟用
