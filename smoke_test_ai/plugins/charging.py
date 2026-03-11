import re
import time

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.base import TestPlugin, PluginContext


class ChargingPlugin(TestPlugin):
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        action = test_case.get("action", "")
        if action == "detect":
            return self._detect(test_case, context)
        return TestResult(
            id=test_case["id"], name=test_case["name"],
            status=TestStatus.ERROR,
            message=f"Unknown charging action: {action}",
        )

    def _detect(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        params = tc.get("params", {})
        off_duration = params.get("off_duration", 5)
        settle_time = params.get("settle_time", 5)

        if ctx.usb_power is None:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="usb_power not configured, skipping charging test")

        adb = ctx.adb

        # 1. Check initial state — must be charging
        initial = self._get_battery_info(adb)
        if not initial["powered"]:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Initial state not charging: {initial['raw']}")

        # 2. Power off → wait → power on
        ctx.usb_power.power_off()
        time.sleep(off_duration)
        ctx.usb_power.power_on()

        # 3. Wait for ADB reconnection + settle
        adb.wait_for_device(timeout=60)
        time.sleep(settle_time)

        # 4. Check recovered state
        recovered = self._get_battery_info(adb)
        if not recovered["powered"] or recovered["status"] != 2:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Charging not recovered after power on: "
                                      f"powered={recovered['powered']}, "
                                      f"status={recovered['status']}")

        return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                          message="Charging detection OK "
                                  "(power off → power on → charging recovered)")

    def _get_battery_info(self, adb) -> dict:
        result = adb.shell("dumpsys battery")
        stdout = result.stdout if hasattr(result, "stdout") else str(result)
        ac = bool(re.search(r"AC powered:\s*true", stdout))
        usb = bool(re.search(r"USB powered:\s*true", stdout))
        status_m = re.search(r"status:\s*(\d+)", stdout)
        status = int(status_m.group(1)) if status_m else 0
        return {
            "powered": ac or usb,
            "ac": ac,
            "usb": usb,
            "status": status,
            "raw": stdout.strip()[:200],
        }
