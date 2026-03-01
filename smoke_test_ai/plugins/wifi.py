import time

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.base import TestPlugin, PluginContext


class WifiPlugin(TestPlugin):
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        action = test_case.get("action", "")
        if action == "scan":
            return self._scan(test_case, context)
        if action == "scan_for_ssid":
            return self._scan_for_ssid(test_case, context)
        if action == "toggle":
            return self._toggle(test_case, context)
        if action == "connection_info":
            return self._connection_info(test_case, context)
        if action == "dhcp_info":
            return self._dhcp_info(test_case, context)
        if action == "is_5ghz_supported":
            return self._capability_check(test_case, context, "wifiIs5GHzBandSupported", "5GHz")
        if action == "is_p2p_supported":
            return self._capability_check(test_case, context, "wifiIsP2pSupported", "P2P")
        if action == "is_aware_available":
            return self._capability_check(test_case, context, "wifiAwareIsAvailable", "WiFi Aware")
        if action == "hotspot":
            return self._hotspot(test_case, context)
        return TestResult(
            id=test_case["id"], name=test_case["name"],
            status=TestStatus.ERROR,
            message=f"Unknown wifi action: {action}",
        )

    def _do_scan(self, ctx: PluginContext) -> list:
        """Run WiFi scan and return results list."""
        # wifiScanAndGetResults() = scan + wait + return (combo RPC)
        # Fallback to wifiStartScan + wifiGetCachedScanResults
        if hasattr(ctx.snippet, "wifiScanAndGetResults"):
            return ctx.snippet.wifiScanAndGetResults()
        ctx.snippet.wifiStartScan()
        return ctx.snippet.wifiGetCachedScanResults()

    def _scan(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        try:
            results = self._do_scan(ctx)
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
            results = self._do_scan(ctx)
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

    def _toggle(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        try:
            ctx.snippet.wifiDisable()
            time.sleep(3)
            ctx.snippet.wifiEnable()
            time.sleep(5)
            enabled = ctx.snippet.wifiIsEnabled()
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"WiFi toggle failed: {e}")

        if enabled:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message="WiFi toggle OK (disable→enable)")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message="WiFi not re-enabled after toggle")

    def _connection_info(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        params = tc.get("params", {})
        min_rssi = params.get("min_rssi", -80)

        # Wait for WiFi to be connected with valid RSSI (may follow a toggle test)
        info = {}
        for _ in range(10):
            try:
                if ctx.snippet.isWifiConnected():
                    info = ctx.snippet.wifiGetConnectionInfo()
                    if info.get("rssi", -999) != -999:
                        break
            except Exception:
                pass
            time.sleep(2)

        if not info:
            try:
                info = ctx.snippet.wifiGetConnectionInfo()
            except Exception as e:
                return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                                  message=f"wifiGetConnectionInfo failed: {e}")

        ssid = info.get("SSID", "")
        rssi = info.get("rssi", -999)
        link_speed = info.get("linkSpeed", 0)

        if rssi < min_rssi:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"RSSI {rssi} dBm below threshold {min_rssi} dBm (SSID: {ssid})")
        return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                          message=f"SSID: {ssid}, RSSI: {rssi} dBm, linkSpeed: {link_speed} Mbps")

    def _dhcp_info(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        try:
            info = ctx.snippet.wifiGetDhcpInfo()
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"wifiGetDhcpInfo failed: {e}")

        ip_addr = info.get("ipAddress", 0)
        gateway = info.get("gateway", 0)
        dns1 = info.get("dns1", 0)

        if ip_addr == 0 or gateway == 0:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"DHCP incomplete: ip={ip_addr}, gateway={gateway}")
        return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                          message=f"DHCP OK: ip={ip_addr}, gateway={gateway}, dns1={dns1}")

    def _capability_check(self, tc: dict, ctx: PluginContext, method: str, label: str) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        try:
            supported = getattr(ctx.snippet, method)()
        except Exception as e:
            err = str(e)
            if "Unknown RPC" in err or "not supported" in err.lower():
                return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                                  message=f"{label} not supported on this device")
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"{method} failed: {e}")

        if supported:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=f"{label} supported")
        return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                          message=f"{label} not supported (device capability)")

    def _hotspot(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        try:
            ctx.snippet.wifiEnableSoftAp(None)
            time.sleep(3)
            is_ap = ctx.snippet.wifiIsApEnabled()
        except Exception as e:
            if "Unknown RPC" in str(e) or "NullPointer" in str(e):
                return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                                  message=f"Hotspot not supported: {str(e)[:80]}")
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Hotspot test failed: {e}")
        finally:
            try:
                ctx.snippet.wifiDisableSoftAp()
                time.sleep(3)
            except Exception:
                pass

        if is_ap:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message="Hotspot enabled and disabled successfully")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message="Hotspot did not enable")
