import time

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.base import TestPlugin, PluginContext


class BluetoothPlugin(TestPlugin):
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        action = test_case.get("action", "")
        if action == "ble_scan":
            return self._ble_scan(test_case, context)
        if action == "toggle":
            return self._toggle(test_case, context)
        if action == "classic_scan":
            return self._classic_scan(test_case, context)
        if action == "adapter_info":
            return self._adapter_info(test_case, context)
        if action == "paired_devices":
            return self._paired_devices(test_case, context)
        if action == "ble_advertise":
            return self._ble_advertise(test_case, context)
        if action == "le_audio_supported":
            return self._le_audio_supported(test_case, context)
        return TestResult(
            id=test_case["id"], name=test_case["name"],
            status=TestStatus.ERROR,
            message=f"Unknown bluetooth action: {action}",
        )

    def _ble_scan(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        params = tc.get("params", {})
        scan_duration = params.get("scan_duration", 5)

        # bleStartScan is @AsyncRpc — Mobly handles the callbackId internally.
        # Required args: scanFilters (JSONArray), scanSettings (JSONObject).
        # Pass empty values for a generic scan.
        handler = None
        try:
            handler = ctx.snippet.bleStartScan([], {})
            time.sleep(scan_duration)
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"BLE scan failed: {e}")
        finally:
            try:
                # bleStopScan is @Rpc, takes callbackId as parameter
                callback_id = handler.callback_id if handler else None
                if callback_id:
                    ctx.snippet.bleStopScan(callback_id)
            except Exception:
                pass

        # Collect scan result events that arrived during scan_duration
        devices = []
        if handler:
            try:
                while True:
                    event = handler.waitAndGet("onScanResult", timeout=0.5)
                    devices.append(event.data)
            except Exception:
                pass  # Timeout or no more events

        count = len(devices)
        if count > 0:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=f"Found {count} BLE devices")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message="No BLE devices found")

    def _toggle(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        try:
            ctx.snippet.btDisable()
            time.sleep(3)
            ctx.snippet.btEnable()
            time.sleep(3)
            enabled = ctx.snippet.btIsEnabled()
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"BT toggle failed: {e}")

        if enabled:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message="Bluetooth toggle OK (disable→enable)")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message="Bluetooth not re-enabled after toggle")

    def _classic_scan(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        try:
            results = ctx.snippet.btDiscoverAndGetResults()
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Classic BT scan failed: {e}")

        count = len(results) if isinstance(results, list) else 0
        return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                          message=f"Classic BT discovery completed, found {count} devices")

    def _adapter_info(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        try:
            name = ctx.snippet.btGetName()
            address = ctx.snippet.btGetAddress()
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Adapter info failed: {e}")

        if name and address:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=f"BT adapter: {name} ({address})")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message=f"Incomplete adapter info: name={name}, address={address}")

    def _paired_devices(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        try:
            devices = ctx.snippet.btGetPairedDevices()
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"btGetPairedDevices failed: {e}")

        count = len(devices) if isinstance(devices, list) else 0
        return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                          message=f"Found {count} paired BT devices")

    def _ble_advertise(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        params = tc.get("params", {})
        duration = params.get("duration", 3)

        handler = None
        try:
            handler = ctx.snippet.bleStartAdvertising({}, {}, None)
            time.sleep(duration)
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"BLE advertise failed: {e}")
        finally:
            try:
                if handler:
                    callback_id = handler.callback_id if hasattr(handler, "callback_id") else None
                    if callback_id:
                        ctx.snippet.bleStopAdvertising(callback_id)
            except Exception:
                pass

        return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                          message="BLE advertising started and stopped successfully")

    def _le_audio_supported(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        try:
            supported = ctx.snippet.btIsLeAudioSupported()
        except Exception as e:
            if "Unknown RPC" in str(e):
                return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                                  message="btIsLeAudioSupported not in installed Snippet APK")
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"btIsLeAudioSupported failed: {e}")

        return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                          message=f"LE Audio {'supported' if supported else 'not supported'}")
