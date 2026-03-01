import time

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.base import TestPlugin, PluginContext


class BluetoothPlugin(TestPlugin):
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        action = test_case.get("action", "")
        if action == "ble_scan":
            return self._ble_scan(test_case, context)
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
