#!/usr/bin/env python3
"""
Quick DUT test script for new plugins (WiFi, BLE, Audio, Network).
Usage: .venv/bin/python scripts/test_new_plugins_on_dut.py [serial]
"""
import sys
import time

SERIAL = sys.argv[1] if len(sys.argv) > 1 else None


def main():
    from mobly.controllers.android_device import AndroidDevice

    print(f"=== Connecting to device {SERIAL or '(auto-detect)'}... ===")
    ad = AndroidDevice(SERIAL) if SERIAL else AndroidDevice(None)
    ad.load_snippet("mbs", "com.google.android.mobly.snippet.bundled")
    snippet = ad.mbs
    print(f"Snippet loaded on {ad.serial}\n")

    results = []

    # --- Test 1: WiFi Scan ---
    print("--- [1/6] WiFi Scan ---")
    try:
        scan_results = snippet.wifiScanAndGetResults()
        count = len(scan_results) if isinstance(scan_results, list) else 0
        if count > 0:
            ssids = [r.get("SSID", "?") for r in scan_results[:5]]
            print(f"  PASS: Found {count} networks. Top SSIDs: {ssids}")
            results.append(("WiFi Scan", "PASS"))
        else:
            print(f"  FAIL: No WiFi networks found")
            results.append(("WiFi Scan", "FAIL"))
    except Exception as e:
        print(f"  ERROR: {e}")
        results.append(("WiFi Scan", f"ERROR: {e}"))

    # --- Test 2: BLE Scan ---
    print("\n--- [2/6] BLE Scan ---")
    try:
        # bleStartScan is @AsyncRpc — Mobly handles callbackId internally
        # Required args: scanFilters (JSONArray), scanSettings (JSONObject)
        handler = snippet.bleStartScan([], {})
        time.sleep(5)
        snippet.bleStopScan(handler.callback_id)
        # Collect events
        devices = []
        try:
            while True:
                event = handler.waitAndGet("onScanResult", timeout=0.5)
                devices.append(event.data)
        except Exception:
            pass
        count = len(devices)
        if count > 0:
            print(f"  PASS: Found {count} BLE devices")
            results.append(("BLE Scan", "PASS"))
        else:
            print(f"  FAIL: No BLE devices found")
            results.append(("BLE Scan", "FAIL"))
    except Exception as e:
        print(f"  ERROR: {e}")
        results.append(("BLE Scan", f"ERROR: {e}"))

    # --- Test 3: Audio Playback ---
    print("\n--- [3/6] Audio Playback ---")
    try:
        import subprocess
        # Find a valid system audio file on device
        audio_path = None
        candidates = [
            "/system/media/audio/ringtones/Ring_Synth_04.ogg",
            "/system/media/audio/notifications/OnTheHunt.ogg",
            "/system/media/audio/ui/camera_click.ogg",
            "/system/media/audio/alarms/Alarm_Classic.ogg",
            "/product/media/audio/alarms/Alarm_Classic.ogg",
            "/product/media/audio/ringtones/Ring_Synth_04.ogg",
            "/product/media/audio/notifications/OnTheHunt.ogg",
        ]
        for path in candidates:
            proc = subprocess.run(
                ["adb", "-s", ad.serial, "shell", f"[ -f '{path}' ] && echo exists"],
                capture_output=True, text=True, timeout=5,
            )
            if "exists" in proc.stdout:
                audio_path = path
                break

        if not audio_path:
            # Fallback: find any .ogg file on system
            proc = subprocess.run(
                ["adb", "-s", ad.serial, "shell", "find /system/media/audio -name '*.ogg' | head -1"],
                capture_output=True, text=True, timeout=10,
            )
            audio_path = proc.stdout.strip()

        if not audio_path:
            print(f"  SKIP: No audio file found on device")
            results.append(("Audio Playback", "SKIP"))
        else:
            print(f"  Using audio file: {audio_path}")
            snippet.mediaPlayAudioFile(audio_path)
            time.sleep(2)
            is_playing = snippet.isMusicActive()
            snippet.mediaStop()
            if is_playing:
                print(f"  PASS: Audio is playing")
                results.append(("Audio Playback", "PASS"))
            else:
                print(f"  FAIL: Audio not playing (isMusicActive=False)")
                results.append(("Audio Playback", "FAIL"))
    except Exception as e:
        print(f"  ERROR: {e}")
        results.append(("Audio Playback", f"ERROR: {e}"))
        try:
            snippet.mediaStop()
        except Exception:
            pass

    # --- Test 4: HTTP Download (WiFi) ---
    print("\n--- [4/6] HTTP Download (WiFi) ---")
    try:
        import subprocess
        proc = subprocess.run(
            ["adb", "-s", ad.serial, "shell",
             "curl -o /dev/null -s -w '%{http_code} %{speed_download}' 'https://www.google.com/generate_204'"],
            capture_output=True, text=True, timeout=30,
        )
        output = proc.stdout.strip()
        parts = output.split()
        http_code = parts[0] if parts else "?"
        speed = parts[1] if len(parts) > 1 else "0"
        if http_code.startswith("2"):
            print(f"  PASS: HTTP {http_code}, speed: {speed} bytes/s")
            results.append(("HTTP Download", "PASS"))
        else:
            print(f"  FAIL: HTTP {http_code}")
            results.append(("HTTP Download", f"FAIL: HTTP {http_code}"))
    except Exception as e:
        print(f"  ERROR: {e}")
        results.append(("HTTP Download", f"ERROR: {e}"))

    # --- Test 5: TCP Connect ---
    print("\n--- [5/6] TCP Connect (8.8.8.8:443) ---")
    try:
        connectable = snippet.networkIsTcpConnectable("8.8.8.8", 443)
        if connectable:
            print(f"  PASS: TCP connection to 8.8.8.8:443 succeeded")
            results.append(("TCP Connect", "PASS"))
        else:
            print(f"  FAIL: TCP connection failed")
            results.append(("TCP Connect", "FAIL"))
    except Exception as e:
        print(f"  ERROR: {e}")
        results.append(("TCP Connect", f"ERROR: {e}"))

    # --- Test 6: Telephony check_signal ---
    print("\n--- [6/6] Telephony Signal Check ---")
    try:
        net_type = snippet.getDataNetworkType()
        NETWORK_TYPE_NAMES = {
            0: "UNKNOWN", 1: "GPRS", 2: "EDGE", 3: "UMTS", 4: "CDMA",
            5: "EVDO_0", 6: "EVDO_A", 7: "1xRTT", 8: "HSDPA", 9: "HSUPA",
            10: "HSPA", 11: "IDEN", 12: "EVDO_B", 13: "LTE", 14: "EHRPD",
            15: "HSPAP", 16: "GSM", 17: "TD_SCDMA", 18: "IWLAN", 19: "LTE_CA",
            20: "NR",
        }
        name = NETWORK_TYPE_NAMES.get(net_type, f"UNKNOWN({net_type})")
        print(f"  INFO: Network type = {name} (code={net_type})")
        results.append(("Signal Check", f"PASS: {name}"))
    except Exception as e:
        print(f"  ERROR: {e}")
        results.append(("Signal Check", f"ERROR: {e}"))

    # --- Summary ---
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    pass_count = sum(1 for _, s in results if s.startswith("PASS"))
    for test_name, status in results:
        icon = "+" if status.startswith("PASS") else ("-" if status.startswith("FAIL") else "!")
        print(f"  [{icon}] {test_name}: {status}")
    print(f"\nTotal: {pass_count}/{len(results)} passed")

    # Cleanup
    try:
        ad.unload_snippet("mbs")
    except Exception:
        pass

    return 0 if pass_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
