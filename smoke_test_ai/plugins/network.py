import time

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.base import TestPlugin, PluginContext


class NetworkPlugin(TestPlugin):
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        action = test_case.get("action", "")
        if action == "http_download":
            return self._http_download(test_case, context)
        if action == "tcp_connect":
            return self._tcp_connect(test_case, context)
        return TestResult(
            id=test_case["id"], name=test_case["name"],
            status=TestStatus.ERROR,
            message=f"Unknown network action: {action}",
        )

    def _http_download(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        params = tc.get("params", {})
        url = params.get("url", "https://www.google.com/generate_204")
        network_mode = params.get("network_mode", "auto")
        disable_wifi = network_mode == "mobile"

        if disable_wifi:
            ctx.adb.shell("svc wifi disable")
            time.sleep(3)

        try:
            result = ctx.adb.shell(
                f"curl -o /dev/null -s -w '%{{http_code}} %{{speed_download}}' '{url}'",
                timeout=60,
            )
            output = result.stdout.strip() if hasattr(result, "stdout") else str(result).strip()
            parts = output.split()
            http_code = parts[0] if parts else ""
            speed = parts[1] if len(parts) > 1 else "0"
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"HTTP download failed: {e}")
        finally:
            if disable_wifi:
                try:
                    ctx.adb.shell("svc wifi enable")
                    time.sleep(3)
                except Exception:
                    pass

        if http_code.startswith("2"):
            if http_code == "204":
                msg = "HTTP 204 OK (connectivity check)"
            else:
                msg = f"HTTP {http_code} OK, speed: {speed} bytes/s"
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=msg)
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message=f"HTTP {http_code}")

    def _tcp_connect(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        params = tc.get("params", {})
        host = params.get("host", "8.8.8.8")
        port = params.get("port", 443)

        try:
            connectable = ctx.snippet.networkIsTcpConnectable(host, port)
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"TCP connect check failed: {e}")

        if connectable:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=f"TCP connection to {host}:{port} succeeded")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message=f"TCP connection to {host}:{port} failed")
