from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.base import TestPlugin, PluginContext


class WifiPlugin(TestPlugin):
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        action = test_case.get("action", "")
        if action == "scan":
            return self._scan(test_case, context)
        if action == "scan_for_ssid":
            return self._scan_for_ssid(test_case, context)
        return TestResult(
            id=test_case["id"], name=test_case["name"],
            status=TestStatus.ERROR,
            message=f"Unknown wifi action: {action}",
        )

    def _scan(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        try:
            ctx.snippet.wifiStartScan()
            results = ctx.snippet.wifiGetScanResults()
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"WiFi scan failed: {e}")

        count = len(results) if isinstance(results, list) else 0
        if count > 0:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=f"Found {count} WiFi networks")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message="No WiFi networks found")

    def _scan_for_ssid(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        params = tc.get("params", {})
        expected_ssid = params.get("expected_ssid", "")

        try:
            ctx.snippet.wifiStartScan()
            results = ctx.snippet.wifiGetScanResults()
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"WiFi scan failed: {e}")

        ssid_list = []
        if isinstance(results, list):
            for ap in results:
                ssid = ap.get("SSID", "") if isinstance(ap, dict) else ""
                if ssid:
                    ssid_list.append(ssid)

        if expected_ssid in ssid_list:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=f"Found SSID '{expected_ssid}' among {len(ssid_list)} networks")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message=f"SSID '{expected_ssid}' not found (scanned: {ssid_list[:10]})")
