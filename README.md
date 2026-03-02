# smoke-test-ai

Android OS image 等級的全自動化 smoke test 框架。從 SCM build 完成到測試報告產出，實現端到端的自動化流程，包含 Pre-ADB 階段（Setup Wizard）的自動化操作。

## 核心特色

- **Pre-ADB 自動化** — 透過 AOA2 USB HID 模擬觸控/鍵盤，搭配 Webcam + LLM Vision 自動完成 Setup Wizard，不需要額外硬體
- **5 階段 Pipeline** — Flash → Setup Wizard → ADB Bootstrap → 測試執行 → 報告產生
- **Plugin 架構** — 可擴充的 Plugin 系統，支援真實功能測試（SMS/電話、相機、WiFi/BLE 掃描、音頻、網路下載），不只是 framework 狀態檢查
- **YAML 可客製化測試** — 以 YAML 定義測試套件，支援 4 種內建 + 6 種 Plugin 測試類型，不需改程式碼
- **LLM 整合** — 支援 Ollama / OpenAI 相容 API，用於 UI 截圖判讀和測試報告生成
- **螢幕喚醒防護** — 分層策略確保 user build（ADB 關閉）下螢幕不會自動關閉

## 架構

```
Host PC (Linux/Mac/Win)
├── Orchestrator (5-stage pipeline)
│   ├── Flash Driver (fastboot / custom)
│   ├── Setup Wizard Agent (AOA2 HID + LLM Vision)
│   ├── Test Runner (6 test types)
│   │   └── Plugin System
│   │       ├── TelephonyPlugin (SMS/Call via Mobly Snippet)
│   │       ├── CameraPlugin (ADB intent + LLM Vision)
│   │       ├── WifiPlugin (WiFi scan via Mobly Snippet)
│   │       ├── BluetoothPlugin (BLE scan via Mobly Snippet)
│   │       ├── AudioPlugin (Audio playback via Mobly Snippet)
│   │       └── NetworkPlugin (HTTP download + TCP connect)
│   └── Reporter (CLI / JSON / HTML / Test Plan)
│
├── USB Hub
│   ├── DUT USB-C (AOA2 HID + ADB)
│   ├── Peer Phone USB (SMS 雙機測試, optional)
│   └── Webcam USB (螢幕擷取)
│
└── Ollama / LLM Server
```

### 每台 DUT 硬體需求

| 硬體 | 成本 | 用途 |
|------|------|------|
| USB-C 線 | ~$3 | AOA2 HID + ADB |
| USB Webcam | ~$10-15 | 螢幕擷取 (Pre-ADB 階段) |
| 固定夾具 | ~$5 | 固定 webcam 與手機位置 |
| Peer Phone + USB 線 | optional | SMS 雙機功能測試 |
| **總計/台** | **~$18-23** | (不含 Peer Phone) |

## 安裝

```bash
git clone https://github.com/seen0722/smoke-test-ai.git
cd smoke-test-ai

python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install mobly  # 功能測試 plugin 需要 (Telephony/WiFi/BLE/Audio/Network)
# Mobly Bundled Snippets APK 已內建於 apks/ 目錄，測試時自動安裝至裝置

# macOS: 安裝 libusb (AOA2 HID 需要)
brew install libusb

# Linux: 安裝 libusb
sudo apt install libusb-1.0-0-dev
```

## 快速開始

### 1. 設定裝置配置

```yaml
# config/devices/my_device.yaml
device:
  name: "My-Device"
  build_type: "user"           # user | userdebug
  screen_resolution: [1080, 2400]
  lock_pin: "0000"             # FBE unlock PIN (omit if no PIN)
  has_sim: true                # 裝置是否有 SIM 卡
  phone_number: "+886912345678"  # DUT 電話號碼 (SMS 測試用)
  peer_serial: "PEER_SERIAL"   # Peer 裝置序號 (SMS 雙機測試, optional)
  peer_phone_number: "+886900000000"
  flash:
    profile: "fastboot"
  screen_capture:
    method: "webcam"           # webcam | adb
    webcam_device: "/dev/video0"
  setup_wizard:
    method: "llm_vision"
    max_steps: 30
    timeout: 300
```

### 2. 設定 LLM 與 WiFi

```yaml
# config/settings.yaml
llm:
  provider: "ollama"
  base_url: "http://localhost:11434"
  vision_model: "llava:13b"
  text_model: "llama3:8b"

wifi:
  ssid: "TestLab-5G"
  password: "your-password"

reporting:
  formats: ["cli", "json"]
  output_dir: "results/"
```

### 3. 執行測試

```bash
# 完整流程：flash → Setup Wizard → 測試 → 報告
smoke-test run --device my_device --suite smoke_basic --build /path/to/images --serial DEVICE_SN

# 跳過刷機（裝置已刷好）
smoke-test run --device my_device --suite smoke_basic --skip-flash --serial DEVICE_SN

# 跳過 Setup Wizard（userdebug build）
smoke-test run --device my_device --suite smoke_basic --skip-flash --skip-setup

# 僅跑測試（最簡模式）
smoke-test test --suite smoke_basic --serial DEVICE_SN

# 列出可用配置
smoke-test devices list
smoke-test suites list
```

## 測試類型

### 內建類型

| 類型 | 說明 | 判定方式 |
|------|------|---------|
| `adb_check` | ADB 屬性檢查 | 輸出精確比對 `expected` |
| `adb_shell` | Shell 指令執行 | `expected_contains` / `expected_not_contains` / `expected_pattern` |
| `screenshot_llm` | 截圖 + LLM 視覺判讀 | LLM 分析截圖回傳 pass/fail |
| `apk_instrumentation` | APK instrumentation 測試 | `am instrument` 結果 |

### Plugin 類型（功能測試）

| 類型 | 說明 | 判定方式 |
|------|------|---------|
| `telephony` | SMS 簡訊收發、網路信號、撥打電話 | Mobly Snippet RPC 呼叫結果 |
| `camera` | 相機拍照、照片品質驗證 | DCIM 新檔案偵測 + 可選 LLM 驗證 |
| `wifi` | WiFi 掃描、SSID 搜尋、開關切換、連線品質、DHCP、5GHz/P2P/Aware 偵測、熱點 | Mobly Snippet WiFi API |
| `bluetooth` | BLE 掃描/廣播、Classic 掃描、開關切換、Adapter 資訊、配對列表、LE Audio | Mobly Snippet BLE/BT API |
| `audio` | 音頻播放、音量控制、麥克風靜音、裝置偵測、路由資訊 | Mobly Snippet Media/Audio API |
| `network` | HTTP 下載、TCP 連通性 | ADB curl + Mobly Snippet |

### Plugin 架構

Plugin 系統讓你可以新增需要 Android API 存取的功能測試，而不需要修改核心 framework：

```
smoke_test_ai/plugins/
├── __init__.py          # TestPlugin, PluginContext exports
├── base.py              # TestPlugin ABC + PluginContext dataclass
├── camera.py            # CameraPlugin — 直接啟動相機拍照 + LLM 驗證
├── telephony.py         # TelephonyPlugin — SMS 收發 + 撥打電話 (Mobly Snippet)
├── wifi.py              # WifiPlugin — WiFi 掃描 (Mobly Snippet)
├── bluetooth.py         # BluetoothPlugin — BLE 裝置掃描 (Mobly Snippet)
├── audio.py             # AudioPlugin — 音頻播放驗證 (Mobly Snippet)
└── network.py           # NetworkPlugin — HTTP 下載 + TCP 連通性
```

**TelephonyPlugin** 使用 Google Mobly Bundled Snippets，透過 JSON-RPC 呼叫 Android API：
- `send_sms` — DUT 發送簡訊，確認發送成功
- `receive_sms` — Peer 裝置發送簡訊給 DUT，DUT 確認收到（雙機模式）
- `check_signal` — 查詢行動網路類型（LTE/NR/etc）
- `make_call` — 撥打電話，確認通話狀態為 OFFHOOK
- `check_voice_type` — 查詢語音網路類型
- `sim_info` — 讀取 SIM 卡資訊（門號、IMSI）

**CameraPlugin** 使用 ADB 直接啟動相機，不需 Snippet：
- `capture_photo` — 啟動相機 → `KEYCODE_CAMERA` + `VOLUME_DOWN` 雙快門鍵 → `find -newer` 偵測新檔案（前鏡頭測試會先查詢鏡頭數量，單鏡頭裝置自動 SKIP）
- `capture_and_verify` — 拍照後 pull 照片，用 LLM Vision 驗證品質
- `verify_latest_photo` — 不拍照，直接驗證裝置上最新照片品質（避免重複拍照）
- 測試完畢後自動 force-stop 相機 app，避免影響後續測試

**WifiPlugin** 使用 Mobly Snippet WiFi API：
- `scan` — 掃描 WiFi AP 列表，確認找到至少一個網路
- `scan_for_ssid` — 掃描後檢查特定 SSID 是否存在
- `toggle` — WiFi 開關切換（disable → enable → 等待重新連線）
- `connection_info` — 取得連線資訊（SSID、RSSI、linkSpeed）
- `dhcp_info` — 取得 DHCP 分配資訊（IP、Gateway、DNS）
- `is_5ghz_supported` / `is_p2p_supported` / `is_aware_available` — 裝置能力檢測
- `hotspot` — WiFi 熱點開關測試

**BluetoothPlugin** 使用 Mobly Snippet BLE/BT API：
- `ble_scan` — BLE 裝置掃描（0 裝置也算 PASS，驗證掃描功能正常）
- `toggle` — 藍牙開關切換（disable → enable）
- `classic_scan` — Classic Bluetooth 掃描
- `adapter_info` — 取得 BT 名稱和 MAC 位址
- `paired_devices` — 列出已配對裝置
- `ble_advertise` — BLE 廣播測試（start → stop）
- `le_audio_supported` — LE Audio 支援偵測

**AudioPlugin** 使用 Mobly Snippet Media/Audio API：
- `play_and_check` — 播放系統音頻檔案，確認 isMusicActive() 回傳 true
- `volume_control` — 音量設定測試
- `microphone_test` — 麥克風靜音 mute/unmute 測試
- `list_devices` — 列出音訊裝置
- `audio_route` — 取得音訊路由資訊

**NetworkPlugin** 使用 ADB curl + Mobly Snippet：
- `http_download` — HTTP 下載測試，支援 WiFi/行動數據模式切換
- `tcp_connect` — TCP 連通性測試

新增 Plugin 只需：一個 Python 檔 + YAML 測試案例，無需修改 framework。

### YAML 變數替換

YAML 測試案例中可使用 `${VAR}` 變數，由 Orchestrator 在執行前自動替換：

| 變數 | 來源 | 說明 |
|------|------|------|
| `${WIFI_SSID}` | `settings.yaml` → `wifi.ssid` | WiFi SSID |
| `${WIFI_PASSWORD}` | `settings.yaml` → `wifi.password` | WiFi 密碼 |
| `${PEER_PHONE_NUMBER}` | device config → `peer_phone_number` | Peer 裝置電話號碼 |
| `${PHONE_NUMBER}` | device config → `phone_number` | DUT 電話號碼 |

## 內建測試套件 (smoke_basic — 60 項)

| 類別 | 測試數 | 測試項目 |
|------|--------|---------|
| 基礎檢查 (adb) | 27 | 開機完成、螢幕顯示(LLM)、觸控回應、WiFi 連線、網路存取、SIM 卡狀態、相機可用、音效輸出、GPS Provider/定位、藍牙啟用/Adapter/MAC、NFC、加速度計、陀螺儀、儲存、記憶體、亮度、自動旋轉、電池、充電、系統崩潰、SELinux、DNS、SurfaceFlinger、Activity Manager |
| 相機功能 | 3 | 後鏡頭拍照、前鏡頭拍照、照片品質驗證(LLM) |
| 電話/簡訊 | 7 | 行動網路類型、SMS 發送、SMS 接收、撥打電話、語音網路類型、SIM 卡資訊 × 需 SIM 卡 |
| WiFi 功能 | 9 | WiFi 掃描、SSID 搜尋、開關切換、連線品質、DHCP、5GHz 支援、P2P 支援、WiFi Aware、熱點開關 |
| 藍牙功能 | 7 | BLE 掃描、開關切換、Classic 掃描、Adapter 資訊、配對列表、BLE 廣播、LE Audio 支援 |
| 音頻功能 | 5 | 音頻播放、音量控制、麥克風靜音、裝置偵測、路由資訊 |
| 網路功能 | 3 | HTTP 下載 (WiFi)、HTTP 下載 (行動數據)、TCP 連通性 |

### 自訂測試項目

在 YAML 直接新增，不需要改任何程式碼：

```yaml
# ADB shell 測試
- id: "bluetooth_scan"
  name: "藍牙掃描"
  type: "adb_shell"
  command: "dumpsys bluetooth_manager | grep 'scanning'"
  expected_contains: "true"

# 功能測試：SMS 簡訊發送
- id: "sms_send"
  name: "SMS 簡訊發送"
  type: "telephony"
  action: "send_sms"
  params:
    to_number: "${PEER_PHONE_NUMBER}"
    body: "smoke-test-outbound-{timestamp}"
  requires:
    device_capability: "has_sim"

# 功能測試：相機拍照
- id: "camera_rear"
  name: "後鏡頭拍照"
  type: "camera"
  action: "capture_photo"
  params:
    camera: "back"
    wait_seconds: 5
```

## 5 階段 Pipeline

```
Stage 0: Flash Image
    │  fastboot / 自訂工具刷入 OS image
    ▼
Stage 1: Setup Wizard (Pre-ADB)
    │  AOA2 HID 模擬觸控 + Webcam 截圖 + LLM Vision 分析
    │  自動完成語言選擇、WiFi 設定、Google 登入跳過等步驟
    ▼
Stage 2: ADB Bootstrap + Pre-test Setup
    │  等待 ADB 連線 → FBE 解鎖 → WiFi 連線 → 螢幕常亮 → 喚醒螢幕
    │  自動安裝 Mobly Snippet APK（本地 apks/ 或從 GitHub 下載）
    │  自動授予 BT/Location/Phone/SMS/Audio runtime 權限 (Android 12+)
    │  清除上次測試資料 → 授予相機權限 → 解析 YAML 變數
    ▼
Stage 3: Test Execute
    │  依 YAML 測試套件逐項執行測試（含 Plugin 功能測試）
    │  Mobly Snippet 自動載入（telephony/wifi/bluetooth/audio/network 測試時）
    ▼
Stage 4: Report
       CLI 表格 / JSON / HTML 報告 + Test Plan 輸出
```

## 螢幕喚醒防護

user build 下 ADB 預設關閉，螢幕可能自動關閉導致測試失敗。防護策略：

| 階段 | 方式 | 說明 |
|------|------|------|
| Pre-ADB | HID 滑鼠動作 | 安全喚醒，不會意外關閉螢幕 |
| Pre-ADB | HID Power 鍵 (fallback) | 連續 2 次失敗後升級 |
| Pre-ADB | Webcam 亮度偵測 | 平均亮度 < 10 判定螢幕關閉 |
| Post-ADB | FBE 自動解鎖 | 偵測 `RUNNING_LOCKED` 狀態，自動輸入 PIN 解鎖 |
| Post-ADB | `stay_on_while_plugged_in` | USB 充電時螢幕常亮 |
| Post-ADB | `screen_off_timeout 30min` | 螢幕 timeout 設為 30 分鐘 |
| Post-ADB | `KEYCODE_WAKEUP` | 測試前立即喚醒 |

## 開發

```bash
# 安裝開發依賴
pip install -e ".[dev]"

# 執行測試 (157 個單元測試，全 Mock，不需硬體)
pytest tests/ -v

# 執行單一模組測試
pytest tests/test_adb_controller.py -v
```

## Tech Stack

| 元件 | 技術 |
|------|------|
| 語言 | Python 3.10+ |
| AOA2 HID | PyUSB + libusb |
| 螢幕擷取 | OpenCV (cv2) |
| LLM | httpx + Ollama / OpenAI-compatible API |
| ADB | subprocess + adb CLI |
| 設定檔 | PyYAML |
| CLI | Click + Rich |
| 功能測試 | Google Mobly Bundled Snippets (Telephony/WiFi/BLE/Audio/Network) |
| 報告 | Jinja2 (HTML + Test Plan) + JSON |
| 測試 | pytest + pytest-mock (157 tests) |

## License

MIT
