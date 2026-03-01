# 擴展 Mobly Snippet 測試設計

**日期**: 2026-03-01
**狀態**: Draft — 待團隊討論

---

## 背景

Mobly Bundled Snippets 提供 118 個 RPC 方法，目前專案只使用 13 個（11%）。
本文件列出可加入的新測試，分為三個優先級，供團隊評估。

### 現有 Snippet 使用率

| Snippet 類別 | 可用方法 | 已使用 | 使用率 |
|-------------|---------|--------|--------|
| WiFi | 21 | 3 | 14% |
| BT Adapter | 17 | 0 | 0% |
| BLE Scanner | 2 | 2 | 100% |
| BLE Advertiser | 2 | 0 | 0% |
| BLE GATT Client | 6 | 0 | 0% |
| BLE GATT Server | 5 | 0 | 0% |
| BT Profiles (A2DP/HFP/HA/LEA) | 17 | 0 | 0% |
| Telephony | 5 | 1 | 20% |
| SMS | 3 | 3 | 100% |
| Audio | 20 | 1 | 5% |
| Media | 5 | 2 | 40% |
| Networking | 2 | 1 | 50% |
| Storage | 2 | 0 | 0% |
| File | 2 | 0 | 0% |
| Account | 5 | 0 | 0% |
| Others | 4 | 0 | 0% |
| **合計** | **118** | **13** | **11%** |

---

## 已知 Bug

### `telephonyStartCall` / `telephonyEndCall` 不存在

`telephony.py` 呼叫的 `telephonyStartCall()` 和 `telephonyEndCall()` **不是** Mobly Bundled Snippets 的方法。`TelephonySnippet` 只提供查詢方法（`getTelephonyCallState`, `getDataNetworkType` 等）。

**建議修正**：改用 ADB intent 撥打/掛斷：
```python
# 撥打
ctx.adb.shell(f"am start -a android.intent.action.CALL -d tel:{number}")
# 掛斷
ctx.adb.shell("input keyevent KEYCODE_ENDCALL")
# 查詢狀態（仍用 snippet）
state = ctx.snippet.getTelephonyCallState()  # 0=IDLE, 1=RINGING, 2=OFFHOOK
```

**優先級**: 高 — 目前 phone_call 測試在有 SIM 的裝置上會 crash。

---

## Tier 1：高價值、低成本（建議優先加入）

### 1.1 WiFi 開關切換 (`wifi_toggle`)

**Plugin**: WifiPlugin
**Action**: `toggle`
**Snippet 方法**: `wifiDisable()` → sleep 3s → `wifiEnable()` → `wifiIsEnabled()`
**驗證**: WiFi 恢復為 enabled 狀態
**風險**: 無，toggle 後恢復原狀

```yaml
- id: "wifi_toggle"
  name: "WiFi 開關切換"
  type: "wifi"
  action: "toggle"
  depends_on: "wifi_connected"
```

### 1.2 WiFi 連線資訊 (`wifi_connection_info`)

**Plugin**: WifiPlugin
**Action**: `connection_info`
**Snippet 方法**: `wifiGetConnectionInfo()`
**驗證**: 回傳包含 SSID、BSSID、linkSpeed、RSSI（且 RSSI > -80 dBm）
**價值**: 比 `cmd wifi status` 更結構化，可檢測信號品質

```yaml
- id: "wifi_connection_info"
  name: "WiFi 連線品質"
  type: "wifi"
  action: "connection_info"
  params:
    min_rssi: -80
  depends_on: "wifi_connected"
```

### 1.3 WiFi DHCP 資訊 (`wifi_dhcp`)

**Plugin**: WifiPlugin
**Action**: `dhcp_info`
**Snippet 方法**: `wifiGetDhcpInfo()`
**驗證**: IP、gateway、DNS 皆非 0.0.0.0
**價值**: 驗證網路堆疊完整性（IP 分配 → 路由 → DNS）

```yaml
- id: "wifi_dhcp"
  name: "WiFi DHCP 分配"
  type: "wifi"
  action: "dhcp_info"
  depends_on: "wifi_connected"
```

### 1.4 藍牙開關切換 (`bt_toggle`)

**Plugin**: BluetoothPlugin
**Action**: `toggle`
**Snippet 方法**: `btDisable()` → sleep 3s → `btEnable()` → `btIsEnabled()`
**驗證**: 藍牙恢復為 enabled

```yaml
- id: "bt_toggle"
  name: "藍牙開關切換"
  type: "bluetooth"
  action: "toggle"
  depends_on: "bluetooth_enabled"
```

### 1.5 Classic BT 掃描 (`bt_discovery`)

**Plugin**: BluetoothPlugin
**Action**: `classic_scan`
**Snippet 方法**: `btDiscoverAndGetResults()`
**驗證**: 不 crash 即可（附近不一定有 Classic BT 裝置）
**價值**: 目前只有 BLE 掃描，缺 Classic BT 測試

```yaml
- id: "bt_discovery"
  name: "Classic BT 掃描"
  type: "bluetooth"
  action: "classic_scan"
  depends_on: "bluetooth_enabled"
```

### 1.6 音量控制 (`audio_volume`)

**Plugin**: AudioPlugin
**Action**: `volume_control`
**Snippet 方法**: `getMusicMaxVolume()` → `setMusicVolume(max/2)` → `getMusicVolume()` → 恢復原值
**驗證**: 讀回的音量等於設定值

```yaml
- id: "audio_volume"
  name: "音量控制"
  type: "audio"
  action: "volume_control"
```

### 1.7 麥克風控制 (`audio_microphone`)

**Plugin**: AudioPlugin
**Action**: `microphone_test`
**Snippet 方法**: `setMicrophoneMute(true)` → `isMicrophoneMute()` → `setMicrophoneMute(false)`
**驗證**: mute 狀態正確切換

```yaml
- id: "audio_microphone"
  name: "麥克風靜音控制"
  type: "audio"
  action: "microphone_test"
```

### 1.8 音訊裝置列表 (`audio_devices`)

**Plugin**: AudioPlugin
**Action**: `list_devices`
**Snippet 方法**: `getAudioDeviceTypes()`
**驗證**: 回傳至少包含 speaker 或 earpiece

```yaml
- id: "audio_devices"
  name: "音訊裝置偵測"
  type: "audio"
  action: "list_devices"
```

### 1.9 音訊路由 (`audio_route`)

**Plugin**: AudioPlugin
**Action**: `audio_route`
**Snippet 方法**: `mediaGetLiveAudioRouteType()` + `mediaGetLiveAudioRouteName()`
**驗證**: 路由資訊非空

```yaml
- id: "audio_route"
  name: "音訊路由資訊"
  type: "audio"
  action: "audio_route"
```

### 1.10 語音網路類型 (`voice_network_type`)

**Plugin**: TelephonyPlugin
**Action**: `check_voice_type`
**Snippet 方法**: `getVoiceNetworkType()`
**驗證**: 回傳值非 0（UNKNOWN）
**前提**: requires has_sim

```yaml
- id: "voice_network_type"
  name: "語音網路類型"
  type: "telephony"
  action: "check_voice_type"
  requires:
    device_capability: "has_sim"
  depends_on: "sim_status"
```

---

## Tier 2：中等價值（需特定硬體或配置）

| ID | 測試名稱 | Snippet 方法 | 條件 |
|----|---------|-------------|------|
| `wifi_5ghz` | WiFi 5GHz 支援 | `wifiIs5GHzBandSupported()` | — |
| `wifi_p2p` | WiFi P2P 支援 | `wifiIsP2pSupported()` | — |
| `wifi_hotspot` | WiFi 熱點開關 | `wifiEnableSoftAp()` → `wifiIsApEnabled()` → `wifiDisableSoftAp()` | root or system app |
| `ble_advertise` | BLE 廣播 | `bleStartAdvertising()` → `bleStopAdvertising()` | — |
| `bt_le_audio` | LE Audio 支援 | `btIsLeAudioSupported()` | Android 13+ |
| `bt_paired` | 已配對裝置列表 | `btGetPairedDevices()` | — |
| `file_integrity` | 檔案完整性 | push → `fileMd5Hash()` → `fileDeleteContent()` | — |
| `sim_info` | SIM 卡資訊 | `getLine1Number()` + `getSubscriberId()` | requires has_sim |
| `wifi_aware` | WiFi Aware | `wifiAwareIsAvailable()` | Android 8+ |

---

## Tier 3：ADB 擴展（不需 Snippet）

| ID | 測試名稱 | 指令 | 說明 |
|----|---------|------|------|
| `sensor_proximity` | 近接感測器 | `dumpsys sensorservice \| grep proximity` | 補充現有 accel+gyro |
| `sensor_light` | 光源感測器 | `dumpsys sensorservice \| grep light` | |
| `sensor_magnetometer` | 磁力計 | `dumpsys sensorservice \| grep magnetic` | |
| `battery_health` | 電池健康度 | `dumpsys battery \| grep health` | health: 2 = GOOD |
| `battery_temperature` | 電池溫度 | `dumpsys battery \| grep temperature` | 應 < 450 (45°C) |
| `battery_level` | 電池電量 | `dumpsys battery \| grep level` | 應 > 10 |
| `screen_resolution` | 螢幕解析度 | `wm size` | 驗證符合 spec |
| `screen_density` | 螢幕密度 | `wm density` | 驗證符合 spec |
| `system_uptime` | 系統運行時間 | `cat /proc/uptime` | 確認非剛重開機 |
| `usb_mode` | USB 模式 | `dumpsys usb \| grep mCurrentFunctions` | |
| `thermal_status` | Thermal 狀態 | `dumpsys thermalservice` | 無過熱 throttling |

---

## 實作影響估算

| 項目 | Tier 1 | Tier 2 | Tier 3 |
|------|--------|--------|--------|
| 新測試數量 | 10 | 9 | 11 |
| 需修改的 Plugin | wifi, bluetooth, audio, telephony | wifi, bluetooth, network, telephony | 無（全部 adb_shell） |
| 新增 Plugin | 無 | 無 | 無 |
| 預估工時 | 半天 | 半天 | 1~2 小時 |
| Snippet 方法新增使用 | +15 | +11 | 0 |
| 使用率提升 | 11% → 24% | 24% → 33% | 不影響 |

**合計**: 若全部加入，測試從 41 → 71 個，Snippet 使用率從 11% → 33%。

---

## 待決定事項

1. **Tier 1 全部加入還是部分選擇？**
2. **phone_call bug 是否先修？** （目前 has_sim 裝置會 crash）
3. **Tier 3 的 adb_shell 測試是否直接加到 YAML 即可？** （不需改程式碼）
4. **WiFi toggle / BT toggle 是否有風險？** （測試環境中開關 radio 可能影響後續測試）
5. **裝置 spec 驗證（解析度/密度）要寫死在 device config 中嗎？**

---

## 參考資料

- [google/mobly-bundled-snippets](https://github.com/google/mobly-bundled-snippets) — 完整 RPC 方法列表
- [google/mobly](https://github.com/google/mobly) — Mobly 框架
- [Android dumpsys reference](https://developer.android.com/tools/dumpsys)
