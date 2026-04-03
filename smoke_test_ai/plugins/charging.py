import re
import time

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.base import TestPlugin, PluginContext
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)


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

        logger.info(f"Initial: powered={initial['powered']}, "
                    f"status={initial['status']}, current={initial['current_ma']:.0f}mA")

        # 2. Power off → wait → power on
        ctx.usb_power.power_off()
        time.sleep(off_duration)
        ctx.usb_power.power_on()

        # 3. Wait for ADB reconnection + settle
        adb.wait_for_device(timeout=60)
        time.sleep(settle_time)

        # 4. Check recovered state
        recovered = self._get_battery_info(adb)
        logger.info(f"Recovered: powered={recovered['powered']}, "
                    f"status={recovered['status']}, current={recovered['current_ma']:.0f}mA")

        # 5. Validate: charging recovered
        if not recovered["powered"] or recovered["status"] not in (2, 5):
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Charging not recovered after power on: "
                                      f"powered={recovered['powered']}, "
                                      f"status={recovered['status']}")

        # 6. Validate: battery is not discharging (current >= 0)
        current = recovered["current_ma"]
        if current < 0:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Battery discharging after power on: "
                                      f"current={current:.0f}mA (expected >= 0)")

        return TestResult(
            id=tid, name=tname, status=TestStatus.PASS,
            message=f"Charging detection OK — "
                    f"powered={recovered['powered']}, "
                    f"status={recovered['status']}, "
                    f"current={current:.0f}mA")

    @staticmethod
    def _get_battery_info(adb) -> dict:
        result = adb.shell("dumpsys battery")
        stdout = result.stdout if hasattr(result, "stdout") else str(result)
        ac = bool(re.search(r"AC powered:\s*true", stdout))
        usb = bool(re.search(r"USB powered:\s*true", stdout))
        status_m = re.search(r"status:\s*(\d+)", stdout)
        status = int(status_m.group(1)) if status_m else 0
        level_m = re.search(r"level:\s*(\d+)", stdout)
        level = int(level_m.group(1)) if level_m else 0

        # Read battery current (uA → mA)
        current_ma = 0.0
        try:
            cur_result = adb.shell("cat /sys/class/power_supply/battery/current_now")
            cur_out = cur_result.stdout if hasattr(cur_result, "stdout") else str(cur_result)
            current_ma = int(cur_out.strip()) / 1000  # uA → mA
        except Exception:
            pass

        return {
            "powered": ac or usb,
            "ac": ac,
            "usb": usb,
            "status": status,
            "level": level,
            "current_ma": current_ma,
            "raw": stdout.strip()[:200],
        }
