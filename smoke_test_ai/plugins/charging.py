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

        # 2. Record charge counter before power off
        before_cc = initial["charge_counter"]
        logger.info(f"Initial: powered={initial['powered']}, "
                    f"status={initial['status']}, charge_counter={before_cc}")

        # 3. Power off → wait → power on
        ctx.usb_power.power_off()
        time.sleep(off_duration)
        ctx.usb_power.power_on()

        # 4. Wait for ADB reconnection + settle
        adb.wait_for_device(timeout=60)
        time.sleep(settle_time)

        # 5. Check recovered state (first reading after power on)
        recovered = self._get_battery_info(adb)
        after_cc = recovered["charge_counter"]
        discharge_delta = after_cc - before_cc

        logger.info(f"Recovered: powered={recovered['powered']}, "
                    f"status={recovered['status']}, charge_counter={after_cc}, "
                    f"discharge_delta={discharge_delta}")

        # 6. Validate: charging recovered
        if not recovered["powered"] or recovered["status"] not in (2, 5):
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Charging not recovered after power on: "
                                      f"powered={recovered['powered']}, "
                                      f"status={recovered['status']}")

        # 7. Validate: discharge occurred (charge counter decreased)
        if before_cc > 0 and discharge_delta >= 0:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"No discharge detected during power off "
                                      f"(charge_counter: {before_cc}→{after_cc}, "
                                      f"delta={discharge_delta}). "
                                      f"USB hub may not be cutting VBUS power.")

        # 8. Wait and verify charge is flowing in (counter increasing)
        # Skip charge inflow check if battery is full (100%) — charging IC stops at full
        battery_level = recovered.get("level", 0)
        if battery_level >= 100 or recovered["status"] == 5:
            logger.info(f"Battery full (level={battery_level}%, status=5) — "
                        f"skip charge inflow check")
            return TestResult(
                id=tid, name=tname, status=TestStatus.PASS,
                message=f"Charging detection OK — "
                        f"discharge: {before_cc}→{after_cc} ({discharge_delta} uAh), "
                        f"battery full ({battery_level}%) — charge inflow check skipped")

        time.sleep(settle_time)
        charging = self._get_battery_info(adb)
        charging_cc = charging["charge_counter"]
        charge_delta = charging_cc - after_cc

        logger.info(f"Charging: charge_counter={charging_cc}, "
                    f"charge_delta=+{charge_delta}")

        if charge_delta <= 0:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"No charge inflow detected after power on "
                                      f"(charge_counter: {after_cc}→{charging_cc}, "
                                      f"delta={charge_delta}). "
                                      f"Charging circuit may not be working.")

        return TestResult(
            id=tid, name=tname, status=TestStatus.PASS,
            message=f"Charging detection OK — "
                    f"discharge: {before_cc}→{after_cc} ({discharge_delta} uAh), "
                    f"recharge: {after_cc}→{charging_cc} (+{charge_delta} uAh)")

    @staticmethod
    def _get_battery_info(adb) -> dict:
        result = adb.shell("dumpsys battery")
        stdout = result.stdout if hasattr(result, "stdout") else str(result)
        ac = bool(re.search(r"AC powered:\s*true", stdout))
        usb = bool(re.search(r"USB powered:\s*true", stdout))
        status_m = re.search(r"status:\s*(\d+)", stdout)
        status = int(status_m.group(1)) if status_m else 0
        cc_m = re.search(r"Charge counter:\s*(\d+)", stdout)
        charge_counter = int(cc_m.group(1)) if cc_m else 0
        level_m = re.search(r"level:\s*(\d+)", stdout)
        level = int(level_m.group(1)) if level_m else 0
        return {
            "powered": ac or usb,
            "ac": ac,
            "usb": usb,
            "status": status,
            "charge_counter": charge_counter,
            "level": level,
            "raw": stdout.strip()[:200],
        }
