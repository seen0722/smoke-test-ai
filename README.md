# smoke-test-ai

Android OS image 等級的全自動化 smoke test 框架。從 SCM build 完成到測試報告產出，實現端到端的自動化流程，包含 Pre-ADB 階段（Setup Wizard）的自動化操作。

## 核心特色

- **Pre-ADB 自動化** — 透過 AOA2 USB HID 模擬觸控/鍵盤，以 Blind Runner 播放預錄的 YAML 步驟檔完成 Setup Wizard（開發者選項、USB debugging 啟用等），不需要 Webcam 或 LLM
- **自適應 5 階段 Pipeline** — 根據 `--build-type`（user/userdebug）和 `--keep-data` 自動調整流程：AOA 盲操作、Setup Wizard、userdata 燒錄過濾
- **Plugin 架構** — 可擴充的 Plugin 系統，支援真實功能測試（SMS/電話、相機、WiFi/BLE 掃描、音頻、網路下載），不只是 framework 狀態檢查
- **YAML 可客製化測試** — 以 YAML 定義測試套件，支援 4 種內建 + 9 種 Plugin 測試類型，不需改程式碼
- **LLM 整合** — 支援 Ollama / OpenAI 相容 API，用於 UI 截圖判讀和測試報告生成
- **螢幕喚醒防護** — 分層策略確保 user build（ADB 關閉）下螢幕不會自動關閉

## 架構

```
Host PC (Linux/Mac/Win)
├── Orchestrator (5-stage pipeline)
│   ├── Flash Driver (fastboot / custom)
│   ├── Setup Wizard (Pre-ADB)
│   │   ├── Blind Runner (YAML 預錄步驟播放)
│   │   └── Step Recorder (OpenCV 互動錄製器)
│   ├── Test Runner (6 test types)
│   │   ├── Plugin System
│   │   │   ├── TelephonyPlugin (SMS/Call via Mobly Snippet)
│   │   │   ├── CameraPlugin (ADB intent + LLM Vision)
│   │   │   ├── WifiPlugin (WiFi scan via Mobly Snippet)
│   │   │   ├── BluetoothPlugin (BLE scan via Mobly Snippet)
│   │   │   ├── AudioPlugin (Audio playback via Mobly Snippet)
│   │   │   └── NetworkPlugin (HTTP download + TCP connect)
│   │   └── Mobly Bundled Snippets APK (apks/ — 自動安裝至 DUT)
│   └── Reporter (CLI / JSON / HTML / Test Plan)
│
├── USB Hub (uhubctl per-port power switching)
│   ├── DUT USB-C (AOA2 HID + ADB + 電源控制)
│   └── Peer Phone USB (SMS 雙機測試, optional)
│
└── Ollama / LLM Server (測試報告 + screenshot_llm 測試用)
```

### 每台 DUT 硬體需求

| 硬體 | 成本 | 用途 |
|------|------|------|
| USB Hub (uhubctl 相容) | ~$30 | USB 電源控制 + 連接 DUT |
| USB-C 線 | ~$3 | AOA2 HID + ADB |
| Peer Phone + USB 線 | optional | SMS 雙機功能測試 |
| **總計/台** | **~$33** | (不含 Peer Phone) |

## 安裝

```bash
git clone https://github.com/seen0722/smoke-test-ai.git
cd smoke-test-ai

python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install mobly  # 功能測試 plugin 需要 (Telephony/WiFi/BLE/Audio/Network)
# Mobly Bundled Snippets APK 已內建於 apks/ 目錄，測試時自動安裝至裝置

# macOS: 安裝 libusb + uhubctl
brew install libusb uhubctl

# Linux: 安裝 libusb + uhubctl
sudo apt install libusb-1.0-0-dev uhubctl
```

### USB Hub 電源控制設定（uhubctl）

使用支援 per-port power switching (PPPS) 的 USB hub，可實現程式化控制 DUT 電源。用於 factory reset 後防止離線充電模式、flash 後乾淨重開機、USB 偵測超時自動恢復。

**推薦 USB Hub：**

> ⚠️ **重要：** 許多 USB hub 雖然支援 uhubctl per-port power switching (PPPS)，但只切斷 **data 信號線**，不切斷 **VBUS 5V 電源**。若需要真正斷電（充電測試、deep sleep 測試），必須選擇經驗證可切 VBUS 的 hub。

| 型號 | Port 數 | VBUS 切斷 | 備註 |
|------|---------|-----------|------|
| **AmazonBasics HU9002V1** | 10 | ✅ 確認 ([#229](https://github.com/mvp/uhubctl/issues/229)) | USB 3.1，用戶確認手機停充 |
| **Yepkit YKUSH3** | 3 | ✅ 保證 | 專為 VBUS 切換設計，需用 `ykushcmd` |
| **Yepkit YKUSH XS** | 1 | ✅ 保證 | 單 port，可串接現有 hub |
| RSHTECH RSH-ST07C | 7 | ❌ 只切 data | VIA VL822，VBUS 不斷，實體開關可切 |
| Plugable USB3-HUB7BC | 7 | ❓ 未驗證 | VIA VL813，需自行測試 |

> 完整選購指南見 [docs/plans/2026-03-11-uhubctl-usb-power-control-design.md](docs/plans/2026-03-11-uhubctl-usb-power-control-design.md)
>
> 驗證 VBUS 是否可切：插上手機/USB 燈，執行 `uhubctl -l <location> -p <port> -a off`，確認手機停充或 USB 燈熄滅

**驗證 hub 是否支援：**

```bash
uhubctl
# 應顯示 hub 的 port 狀態和 "power" 資訊
# 確認 DUT 所在的 hub location 和 port 編號
```

**Linux 免 sudo 設定（udev rule）：**

```bash
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="2109", MODE="0666"' | \
  sudo tee /etc/udev/rules.d/52-usb-hub-power.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
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
    pre_flash:                     # OEM unlock (user build 需要)
      - "fastboot oem unlock Trimble-Thorpe"
    script: "${BUILD_DIR}/fastboot.bash"  # 原廠燒錄腳本（自動解析）
    script_timeout: 600
  screen_capture:
    method: "webcam"           # webcam | adb
    webcam_device: "/dev/video0"
  usb_power:                   # USB 電源控制 (optional, 需 uhubctl)
    hub_location: "1-1"        # uhubctl hub location
    port: 1                    # DUT 所在 port
    off_duration: 20.0         # 斷電持續秒數
    reset_delay: 3             # factory reset 後等待裝置關機再斷電（秒）
  setup_wizard:
    method: "blind"            # blind (預錄 YAML 步驟播放)
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

# 指定 build type（覆蓋 YAML 設定）
smoke-test run --device my_device --suite smoke_basic --build /path/to/images \
  --build-type user --serial DEVICE_SN

# 保留 userdata 燒錄（跳過 userdata erase/flash，保留既有設定）
smoke-test run --device my_device --suite smoke_basic --build /path/to/images \
  --keep-data --serial DEVICE_SN

# 跳過刷機（裝置已刷好）
smoke-test run --device my_device --suite smoke_basic --skip-flash --serial DEVICE_SN

# 跳過 Setup Wizard（userdebug build）
smoke-test run --device my_device --suite smoke_basic --skip-flash --skip-setup

# Factory Reset → Setup → 測試（自動 USB power cycle）
smoke-test reset-test --device my_device --suite smoke_basic --serial DEVICE_SN

# Factory Reset，指定 build type（user build 自動觸發 AOA）
smoke-test reset-test --device my_device --suite smoke_basic \
  --build-type user --serial DEVICE_SN

# 僅跑測試（最簡模式）
smoke-test test --suite smoke_basic --serial DEVICE_SN

# 錄製 Setup Flow（互動式 OpenCV 錄製器）
smoke-test record --device product_a --serial DEVICE_SN

# ADB 模式重播 Setup Flow（測試用）
smoke-test replay --device product_a --serial DEVICE_SN

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
| `camera` | 相機拍照、錄影、照片品質驗證 | DCIM 新檔案偵測 + 可選 LLM 驗證 |
| `wifi` | WiFi 掃描、SSID 搜尋、開關切換、連線品質、DHCP、5GHz/P2P/Aware 偵測、熱點 | Mobly Snippet WiFi API |
| `bluetooth` | BLE 掃描/廣播、Classic 掃描、開關切換、Adapter 資訊、配對列表、LE Audio | Mobly Snippet BLE/BT API |
| `audio` | 音頻播放、音量控制、麥克風靜音、裝置偵測、路由資訊 | Mobly Snippet Media/Audio API |
| `network` | HTTP 下載、TCP 連通性 | ADB curl + Mobly Snippet |
| `charging` | 充電偵測（USB 斷電/上電驗證充電恢復）| uhubctl + `dumpsys battery` |
| `suspend` | Suspend/Resume + Deep Sleep 驗證、ADB Reboot | uhubctl + `soc_sleep/stats` |

### Google Mobly Bundled Snippets

功能測試（Telephony / WiFi / Bluetooth / Audio / Network）透過 [Google Mobly Bundled Snippets](https://github.com/nicecyj/mobly-bundled-snippets) 實現。

**運作原理：**

```
Host PC                              DUT (Android)
┌──────────────┐    ADB + TCP    ┌──────────────────────┐
│  Plugin      │◄──────────────►│  Mobly Snippets APK   │
│  (Python)    │   JSON-RPC     │  (Android Service)    │
│              │                │                       │
│  snippet.    │  ──request──►  │  TelephonyManager     │
│  smsSendText │                │  WifiManager          │
│  (to, body)  │  ◄──result──   │  BluetoothAdapter     │
│              │                │  AudioManager         │
└──────────────┘                └──────────────────────┘
```

1. **安裝** — Orchestrator Stage 2 自動將 `apks/mobly-bundled-snippets.apk` 安裝至 DUT
2. **啟動** — Plugin 透過 ADB 啟動 Snippet Server（`am instrument`），建立 TCP 連線
3. **呼叫** — Host 端 Python 發送 JSON-RPC 請求，Snippet APK 呼叫 Android API 並回傳結果
4. **優勢** — 直接存取 Android Framework API（TelephonyManager、WifiManager 等），不依賴 shell 指令解析

APK 已內建於 `apks/` 目錄，不需額外下載。

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
├── network.py           # NetworkPlugin — HTTP 下載 + TCP 連通性
├── charging.py          # ChargingPlugin — USB 斷電/上電充電偵測 (uhubctl)
└── suspend.py           # SuspendPlugin — Suspend/Resume + Deep Sleep 驗證 + ADB Reboot
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

**ChargingPlugin** 使用 uhubctl USB 電源控制 + `dumpsys battery`：
- `detect` — 充電偵測測試：確認初始充電中 → USB 斷電 → 等待 → USB 上電 → ADB 重連 → 確認充電恢復
- 需要 `usb_power` 設定，未設定時自動 SKIP
- 測試後自動重連 Mobly Snippet（USB power cycle 會中斷 RPC 連線）

**SuspendPlugin** 使用 uhubctl USB 電源控制 + `soc_sleep/stats`：
- `deep_sleep` — Suspend/Resume + Deep Sleep 驗證：讀取 soc_sleep stats → 開飛航模式 → 螢幕關閉 → USB 斷電 120s → USB 上電 → ADB 重連 → 喚醒螢幕 → 確認 aosd/cxsd/ddr 計數增加
- `reboot` — ADB Reboot 驗證：`adb reboot` → 等待裝置重啟 → 確認 `sys.boot_completed=1`
- 需要能切 VBUS 的 USB hub（deep_sleep 測試），未設定時自動 SKIP
- 支援 Qualcomm soc_sleep/stats 多行格式解析

新增 Plugin 只需：一個 Python 檔 + YAML 測試案例，無需修改 framework。

### Blind Runner（Pre-ADB Setup Flow）

透過 AOA2 USB HID 播放預錄的 YAML 步驟檔，在無 ADB 的情況下自動完成裝置設定（開啟開發者選項、啟用 USB debugging 等）。

**錄製 → 播放流程：**

```bash
# 1. 錄製：OpenCV 互動錄製器（點擊/滑動/輸入）
smoke-test record --device product_a --serial DEVICE_SN

# 2. AOA 播放：透過 USB HID 在 DUT 上重播步驟
#    （程式碼整合於 Orchestrator Stage 1）

# 3. ADB 測試播放：快速驗證步驟正確性
smoke-test replay --device product_a --serial DEVICE_SN
```

**YAML 步驟格式：**

```yaml
# config/setup_flows/product_a.yaml
device: Product-A
screen_resolution: [2160, 1080]
steps:
- action: tap
  x: 672
  y: 890
  delay: 5.0
  press_duration: 0.05    # 按壓時間（預設 50ms，長按可設 1.0）
  description: Tap Developer options

- action: swipe
  x1: 888
  y1: 803
  x2: 922
  y2: 291
  duration: 0.3
  delay: 2.5
  description: Swipe in Developer options

- action: tap
  x: 2014
  y: 644
  delay: 3.0
  description: Enable USB debugging
  repeat: 1                # 重複點擊次數（預設 1）

- action: wait_for_adb
  timeout: 30
  description: Wait for USB re-enumeration after debugging toggle

- action: back
  delay: 1.0
  description: Go back
```

**支援的 action 類型：**

| Action | 說明 | 參數 |
|--------|------|------|
| `tap` | 觸控點擊 | `x`, `y`, `delay`, `press_duration`, `repeat` |
| `swipe` | 滑動 | `x1`, `y1`, `x2`, `y2`, `duration`, `delay` |
| `type` | 輸入文字（HID 鍵盤） | `text`, `delay` |
| `key` | 按鍵 | `key` (enter/tab/etc), `delay` |
| `wake` | 喚醒螢幕 | `delay` |
| `home` | Home 鍵 | `delay` |
| `back` | 返回鍵（Consumer Control） | `delay` |
| `sleep` | 等待 | `duration` |
| `wait_for_adb` | 等待 USB 重新列舉並重連 AOA | `timeout` |
| `power_cycle` | USB 電源重置（需配置 usb_power） | `off_duration` |

**AOA 穩定性特性：**
- **VID-only matching** — USB debugging 啟用後 PID 會改變（如 0x02B1→0x02B5），自動適應
- **USBError 自動重連** — 操作中 USB 斷開時自動觸發 `wait_for_adb` 重連
- **ADB fallback 偵測** — macOS 上 PyUSB/libusb 有時無法列舉裝置，改用 ADB 偵測
- **三模式 USB 偵測** — 支援 Normal / Accessory / Accessory+ADB 三種 USB 模式

### YAML 變數替換

YAML 測試案例中可使用 `${VAR}` 變數，由 Orchestrator 在執行前自動替換：

| 變數 | 來源 | 說明 |
|------|------|------|
| `${WIFI_SSID}` | `settings.yaml` → `wifi.ssid` | WiFi SSID |
| `${WIFI_PASSWORD}` | `settings.yaml` → `wifi.password` | WiFi 密碼 |
| `${PEER_PHONE_NUMBER}` | device config → `peer_phone_number` | Peer 裝置電話號碼 |
| `${PHONE_NUMBER}` | device config → `phone_number` | DUT 電話號碼 |

## 內建測試套件 (smoke_basic — 65 項，按 BSP 子系統分類)

| 子系統 | 測試數 | 測試項目 |
|--------|--------|---------|
| **Boot** | 8 | 開機完成、SKU ID、Build Number、Android Version、Kernel 版本、SELinux Enforcing、Partition 完整性、ADB Reboot |
| **Display** | 3 | 螢幕顯示(LLM)、亮度寫入驗證、自動旋轉 |
| **Touchscreen** | 1 | 觸控裝置存在 |
| **Sensor** | 6 | 加速度計(存在+數據)、陀螺儀(存在+數據)、光線感測器、磁力計 |
| **Camera** | 5 | 相機裝置、後鏡頭拍照、前鏡頭拍照、照片品質(LLM)、錄影 |
| **Audio** | 5 | 播放、音量、麥克風、裝置偵測、路由 |
| **WiFi** | 8 | 連線、掃描、SSID、開關、連線品質、DHCP、5GHz、熱點 |
| **Bluetooth** | 6 | 啟用、BLE 掃描、開關、Classic 掃描、Adapter、配對列表 |
| **NFC** | 1 | NFC 啟用 |
| **GPS** | 2 | GPS 開啟、衛星訊號 |
| **Telephony** | 7 | SIM、網路類型、SMS 發送/接收、撥打電話、語音網路、SIM 資訊 |
| **Network** | 4 | ping、DNS、HTTP WiFi/行動數據 |
| **Storage** | 2 | 內部儲存、記憶體 |
| **Power** | 5 | 電池、充電、充電偵測、Thermal Driver、Suspend/Deep Sleep |
| **USB** | 1 | USB Gadget 模式 |
| **System** | 1 | 無系統崩潰 |

> 進階測試已移至獨立套件：`wifi_advanced.yaml`（P2P、Aware）、`bluetooth_advanced.yaml`（BLE 廣播、LE Audio）

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
    │  OEM unlock (user build) → 解析原廠 fastboot.bash → 系統 fastboot 逐一執行
    │  支援 A/B slot 全量燒錄（30+ partitions）、跨平台（macOS/Linux）
    │  --keep-data 時自動過濾 userdata erase/flash 指令
    │  USB power cycle 確保乾淨重開機（若配置 usb_power）
    ▼
Stage 1: Setup Wizard (Pre-ADB)  ← 條件觸發
    │  僅在 need_aoa 時執行（user build + 全量燒錄/factory reset）
    │  Blind Runner — 透過 AOA2 HID 播放預錄的 YAML 步驟檔
    │  自動完成開發者選項開啟、USB debugging 啟用等設定
    │  userdebug build 或 --keep-data 時跳過此階段
    ▼
Stage 2: ADB Bootstrap + Pre-test Setup
    │  等待 ADB 連線 → FBE 解鎖（僅 fresh_state）→ WiFi 連線
    │  螢幕常亮 + 解鎖 Keyguard → 喚醒螢幕
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

### Factory Reset Pipeline（reset-test）

```
Factory Reset → USB Power Cycle → [user: 延遲 ADB 等待] → Stage 1-4
```

`reset-test` 命令執行 factory reset 後自動進行 USB power cycle（防止離線充電模式），然後重新走完整 pipeline：

```bash
smoke-test reset-test --device product_a --suite smoke_basic --serial DEVICE_SN
# 可選：--reset-delay 5（factory reset 後等待秒數，預設從 YAML 或 3 秒）
# 可選：--build-type user（user build 時 ADB 等待延遲到 AOA 之後）
```

若未配置 `usb_power`，會提示手動拔插 USB。

### 自適應 Pipeline 決策矩陣

Pipeline 根據 `--build-type` 和 `--keep-data` 自動決定各階段行為：

```
                    keep-data=false           keep-data=true
                    (全量燒錄)                (保留 userdata)
  ┌──────────────┬───────────────────────┬──────────────────────┐
  │ user         │ Flash → AOA 盲操作   │ Flash (跳過 userdata)│
  │              │ (Setup Wizard +      │ → ADB Bootstrap      │
  │              │  USB Debug 啟用)     │ (ADB 已開啟,         │
  │              │ → ADB Bootstrap      │  無 Setup Wizard)    │
  ├──────────────┼───────────────────────┼──────────────────────┤
  │ userdebug    │ Flash → ADB Bootstrap│ Flash (跳過 userdata)│
  │              │ (ADB 預設開啟,       │ → ADB Bootstrap      │
  │              │  pm disable 跳過)    │ (同上)               │
  └──────────────┴───────────────────────┴──────────────────────┘
```

**僅 `user + 全量燒錄/factory reset` 需要 AOA 盲操作。**

## 螢幕喚醒防護

user build 下 ADB 預設關閉，螢幕可能自動關閉導致測試失敗。防護策略：

| 階段 | 方式 | 說明 |
|------|------|------|
| Pre-ADB | HID 滑鼠動作 | 安全喚醒，不會意外關閉螢幕 |
| Pre-ADB | HID Power 鍵 (fallback) | 連續 2 次失敗後升級 |
| Post-ADB | FBE 自動解鎖 | 偵測 `RUNNING_LOCKED` 狀態，自動輸入 PIN 解鎖 |
| Post-ADB | `stay_on_while_plugged_in` | USB 充電時螢幕常亮 |
| Post-ADB | `screen_off_timeout max` | 螢幕 timeout 設為最大值（永不關閉） |
| Post-ADB | `KEYCODE_WAKEUP` | 測試前立即喚醒 |
| Post-ADB | `wm dismiss-keyguard` | 解除 Keyguard 鎖定螢幕 |
| 相機測試前 | `CLOSE_SYSTEM_DIALOGS` | 關閉殘留的系統對話框 |

## 開發

```bash
# 安裝開發依賴
pip install -e ".[dev]"

# 執行測試 (285 個單元測試，全 Mock，不需硬體)
pytest tests/ -v

# 執行單一模組測試
pytest tests/test_adb_controller.py -v
```

## Tech Stack

| 元件 | 技術 |
|------|------|
| 語言 | Python 3.10+ |
| AOA2 HID | PyUSB + libusb |
| 螢幕擷取 / 錄製器 | OpenCV (cv2) |
| LLM | httpx + Ollama / OpenAI-compatible API |
| ADB | subprocess + adb CLI |
| 設定檔 | PyYAML |
| CLI | Click + Rich |
| USB 電源控制 | uhubctl (per-port power switching) |
| 功能測試 | Google Mobly Bundled Snippets (Telephony/WiFi/BLE/Audio/Network) |
| 報告 | Jinja2 (HTML + Test Plan) + JSON |
| 測試 | pytest + pytest-mock (285 tests) |

## License

MIT
