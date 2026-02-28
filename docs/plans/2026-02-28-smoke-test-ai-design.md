# smoke-test-ai Design Document

## Overview

Android OS image 等級的全自動化 smoke test 框架。從 SCM build 完成到測試報告產出，實現端到端的自動化流程，包含 Pre-ADB 階段（Setup Wizard）的自動化操作。

## Problem Statement

- SCM build 產出 Android image 後，需要 flash 至實體裝置進行 smoke test
- User build 預設 ADB 關閉，需通過 Setup Wizard 後才能啟用
- 目前採用人工 ADB + APK 混合測試，耗時且不可重複
- 不同產品線的測試項目需要可客製化
- 需支援多台裝置並行測試

## Design Decisions

### 1. Pre-ADB 輸入控制：AOA2 (Android Open Accessory v2)

**選擇理由**：
- 純軟體方案，不需要額外硬體模組（vs CH9329、Teensy）
- 只需一條 USB 線連接 Host 與 DUT
- Android 4.1+ 原生支援
- 透過 USB control requests 發送 HID 事件（鍵盤/滑鼠/觸控）
- 使用 PyUSB + libusb 實作

**AOA2 HID 控制流程**：
1. `ACCESSORY_REGISTER_HID` (code 54) — 註冊虛擬 HID 裝置
2. `ACCESSORY_SET_HID_REPORT_DESC` (code 56) — 設定 HID report descriptor
3. `ACCESSORY_SEND_HID_EVENT` (code 57) — 發送觸控/鍵盤事件
4. `ACCESSORY_UNREGISTER_HID` (code 55) — 取消註冊

**考慮但排除的方案**：
- CH9329 模組：需額外硬體 + 3 條線
- Teensy：需額外硬體 + 韌體開發
- Raspberry Pi Gadget Mode：每台 DUT 需一台 Pi
- Image 預處理（skip Setup Wizard）：修改 image 影響測試有效性

### 2. 螢幕擷取：分層策略

AOA2 與 USB-C DP Alt Mode 無法同時運作（角色衝突：AOA 要求手機為 USB Device，DP 輸出要求手機為 USB Host）。採用分層策略：

| 優先序 | 方式 | 條件 | 成本/台 |
|--------|------|------|---------|
| 1 | `adb screencap` | ADB 已開啟 | $0 |
| 2 | HDMI Capture Card | 裝置有 HDMI/DP 輸出 + 不用 AOA 時 | ~$10 |
| 3 | USB Webcam | 通用方案，所有裝置適用 | ~$10-15 |
| 4 | 盲操作腳本 | 固定流程產品 | $0 |

**推薦通用方案**：Webcam + AOA2，零衝突，所有裝置都能覆蓋。

### 3. LLM 整合：Ollama / 企業內部 LLM

應用場景：
1. **Setup Wizard 導航** — 多模態 Vision 模型分析螢幕截圖，決定操作
2. **測試結果判讀** — Vision 模型判斷 UI 截圖是否正常
3. **測試報告摘要** — 文字模型生成人類可讀摘要
4. **測試用例建議** — 文字模型根據產品規格建議測試項目

### 4. 測試項目客製化：YAML 設定

測試套件以 YAML 定義，支援多種測試類型：
- `adb_check` — ADB 指令 + 預期值比對
- `adb_shell` — ADB shell 指令執行
- `screenshot_llm` — 截圖 + LLM 判讀
- `apk_instrumentation` — APK instrumentation test

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Host PC (Linux/Mac/Win)                │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                  Orchestrator (Python)                 │  │
│  │                                                       │  │
│  │  ┌─────────┐  ┌──────────┐  ┌────────┐  ┌──────────┐ │  │
│  │  │ Device  │  │ Test     │  │ LLM    │  │ Report   │ │  │
│  │  │ Manager │  │ Runner   │  │ Client │  │ Generator│ │  │
│  │  └────┬────┘  └────┬─────┘  └───┬────┘  └────┬─────┘ │  │
│  └───────┼────────────┼────────────┼────────────┼────────┘  │
│          │            │            │            │           │
│  ┌───────┴────────────┴────────────┴────────────┘           │
│  │                                                          │
│  │  ┌──────────┐  ┌───────────┐  ┌────────────┐            │
│  │  │ AOA2 HID │  │ ADB       │  │ Flash      │            │
│  │  │ Driver   │  │ Controller│  │ Controller │            │
│  │  │ (PyUSB)  │  │           │  │            │            │
│  │  └────┬─────┘  └─────┬─────┘  └─────┬──────┘            │
│  │       │              │              │                    │
│  │  USB Hub                                                 │
│  │  ├── DUT USB-C (AOA2 + ADB)                              │
│  │  └── Webcam USB (螢幕擷取)                                │
│  └──────────────────────────────────────────────────────────┘
│                                                             │
│  ┌──────────────┐                                           │
│  │ Ollama / LLM │                                           │
│  └──────────────┘                                           │
└─────────────────────────────────────────────────────────────┘
```

### 每台 DUT 硬體需求

| 硬體 | 成本 | 用途 |
|------|------|------|
| USB-C 線 | ~$3 | AOA2 HID + ADB |
| USB Webcam | ~$10-15 | 螢幕擷取 (Pre-ADB 階段) |
| 固定夾具 | ~$5 | 固定 webcam 與手機位置 |
| **總計/台** | **~$18-23** | |

---

## Test Pipeline

### Stage 0: Flash Image

透過可插拔的 flash driver 支援多種刷機方式：
- fastboot (標準 Android)
- SP Flash Tool (MediaTek)
- QFIL (Qualcomm)
- Odin (Samsung)
- Custom (自訂指令)

### Stage 1: Pre-ADB Setup (Setup Wizard 自動化)

核心創新。循環執行：
1. Webcam 擷取螢幕畫面
2. LLM Vision 分析當前 Setup Wizard 步驟
3. AOA2 HID 發送對應的觸控/鍵盤事件
4. 重複直到 LLM 辨識到 Launcher 桌面或 ADB 連線成功

LLM 回傳格式：
```json
{
  "screen_state": "language_selection",
  "completed": false,
  "action": {
    "type": "tap",
    "x": 540,
    "y": 1200
  },
  "confidence": 0.95
}
```

### Stage 2: ADB Bootstrap

ADB 開啟後的初始設定：
- WiFi 連線 (`adb shell cmd wifi connect-network`)
- 螢幕常亮 (`settings put global stay_on_while_plugged_in 3`)
- 安裝測試 APK（如有需要）

### Stage 3: Test Execute

從 YAML 設定載入測試套件，依序或並行執行測試項目。
支援的測試類型：
- `adb_check` — 屬性/狀態檢查
- `adb_shell` — Shell 指令執行
- `screenshot_llm` — 截圖 + LLM 視覺判讀
- `apk_instrumentation` — APK 測試框架

### Stage 4: Report Generate

輸出格式：
- CLI 即時輸出 (PASS/FAIL 顏色標示)
- JSON 結構化日誌
- HTML 報告 (含截圖，Jinja2 模板)
- PDF 報告 (WeasyPrint)
- API 回傳 (整合內部系統)

---

## Project Structure

```
smoke-test-ai/
├── cli.py                          # CLI 進入點
├── config/
│   ├── devices/                    # 裝置定義
│   ├── flash_profiles/             # 刷機設定
│   ├── test_suites/                # 測試套件 (可客製化)
│   └── settings.yaml               # 全域設定
│
├── smoke_test_ai/
│   ├── core/
│   │   ├── orchestrator.py         # 主流程控制
│   │   ├── device_manager.py       # 多裝置管理 & 並行
│   │   └── test_runner.py          # 測試執行引擎
│   │
│   ├── drivers/
│   │   ├── aoa_hid.py              # AOA2 HID 驅動 (PyUSB)
│   │   ├── adb_controller.py       # ADB 控制封裝
│   │   ├── flash/                  # 可插拔 flash drivers
│   │   │   ├── base.py
│   │   │   ├── fastboot.py
│   │   │   ├── sp_flash_tool.py
│   │   │   └── custom.py
│   │   └── screen_capture/         # 可插拔螢幕擷取
│   │       ├── base.py
│   │       ├── webcam.py           # OpenCV
│   │       ├── hdmi_capture.py
│   │       └── adb_screencap.py
│   │
│   ├── ai/
│   │   ├── llm_client.py           # LLM 抽象層
│   │   ├── setup_wizard_agent.py   # Setup Wizard Agent
│   │   ├── visual_analyzer.py      # 視覺分析
│   │   └── test_result_analyzer.py # 結果分析
│   │
│   ├── reporting/
│   │   ├── cli_reporter.py
│   │   ├── html_reporter.py
│   │   ├── json_reporter.py
│   │   └── api_reporter.py
│   │
│   └── utils/
│       ├── usb_utils.py
│       └── logger.py
│
├── scripts/
│   ├── install.sh
│   └── setup_udev_rules.sh
│
├── templates/
│   └── report.html
│
├── tests/
├── requirements.txt
└── pyproject.toml
```

---

## Tech Stack

| 元件 | 技術 | 理由 |
|------|------|------|
| 語言 | Python 3.10+ | 團隊熟悉，生態豐富 |
| AOA2 HID | PyUSB + libusb | 跨平台，純 Python |
| 螢幕擷取 | OpenCV (cv2) | Webcam/HDMI 通用 |
| LLM | Ollama API / OpenAI-compatible API | 支援 Ollama 和企業 LLM |
| ADB | subprocess + adb CLI | 最穩定 |
| 設定檔 | YAML (PyYAML) | 人類可讀，容易客製化 |
| CLI | Click + Rich | 美觀的終端輸出 |
| 報告 | Jinja2 (HTML) + WeasyPrint (PDF) | 模板化 |
| 並行 | asyncio + ThreadPoolExecutor | 多裝置並行 |

---

## Configuration Examples

### Device Config

```yaml
# config/devices/product_a.yaml
device:
  name: "Product-A"
  build_type: "user"              # user | userdebug
  screen_resolution: [1080, 2400]
  has_sim: true
  has_dp_output: false

  flash:
    profile: "fastboot"

  screen_capture:
    method: "webcam"              # webcam | hdmi_capture | adb
    webcam_device: "/dev/video0"  # Linux
    webcam_crop: [100, 50, 1080, 1920]

  setup_wizard:
    method: "llm_vision"          # llm_vision | blind_script
    max_steps: 30
    timeout: 300
```

### Global Settings

```yaml
# config/settings.yaml
llm:
  provider: "ollama"
  base_url: "http://localhost:11434"
  vision_model: "llava:13b"
  text_model: "llama3:8b"
  timeout: 30

wifi:
  ssid: "TestLab-5G"
  password: "${WIFI_PASSWORD}"

reporting:
  formats: ["cli", "html", "json"]
  output_dir: "results/"
  screenshots: true
  api_endpoint: "https://internal-system.company.com/api/test-results"

parallel:
  max_devices: 8
  per_device_timeout: 900
```

### Test Suite

```yaml
# config/test_suites/smoke_basic.yaml
test_suite:
  name: "Basic Smoke Test"
  timeout: 600

  tests:
    - id: "boot_complete"
      name: "開機完成驗證"
      type: "adb_check"
      command: "getprop sys.boot_completed"
      expected: "1"

    - id: "display_normal"
      name: "螢幕顯示正常"
      type: "screenshot_llm"
      prompt: "螢幕是否正常顯示？是否有異常色塊或花屏？"
      pass_criteria: "normal"

    - id: "touch_responsive"
      name: "觸控回應"
      type: "adb_shell"
      command: "input tap 540 960 && dumpsys window | grep mCurrentFocus"
      expected_contains: "Launcher"

    - id: "wifi_connected"
      name: "WiFi 連線"
      type: "adb_shell"
      command: "dumpsys wifi | grep 'Wi-Fi is'"
      expected_contains: "enabled"

    - id: "internet_access"
      name: "網路存取"
      type: "adb_shell"
      command: "ping -c 3 8.8.8.8"
      expected_contains: "3 received"

    - id: "sim_status"
      name: "SIM 卡狀態"
      type: "adb_shell"
      command: "dumpsys telephony.registry | grep mServiceState"
      expected_not_contains: "OUT_OF_SERVICE"

    - id: "camera_available"
      name: "相機可用"
      type: "adb_shell"
      command: "dumpsys media.camera | grep 'Device version'"
      expected_pattern: "Device version:.*"

    - id: "audio_output"
      name: "音效輸出"
      type: "adb_shell"
      command: "dumpsys audio | grep 'stream_MUSIC'"
      expected_contains: "stream_MUSIC"
```

---

## CLI Usage

```bash
# 完整 smoke test
smoke-test run --device product_a --suite smoke_basic --build /path/to/images/

# 僅刷機
smoke-test flash --device product_a --build /path/to/images/

# 僅 Setup Wizard 自動化
smoke-test setup --device product_a

# 僅執行測試
smoke-test test --suite smoke_basic --serial DEVICE_SERIAL

# 多裝置並行
smoke-test run --device product_a --suite smoke_basic \
  --serials DEV001,DEV002,DEV003 --parallel

# 產出報告
smoke-test report --input results/2026-02-28/ --format html,pdf

# 列出可用裝置/測試套件
smoke-test devices list
smoke-test suites list
```

---

## Competitive Positioning

市場上無任何現成產品同時整合：
1. AOA2 USB HID — Pre-ADB 階段的輸入控制（零額外硬體）
2. Webcam/HDMI + LLM Vision — Pre-ADB 階段的螢幕理解
3. ADB 自動化測試框架 — Post-ADB 階段的完整測試

最接近的組合是 PiKVM（硬體能力）+ DroidRun（AI 能力），但無人整合成 smoke test 流程。
