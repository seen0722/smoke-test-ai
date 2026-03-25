import re
import time

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.base import TestPlugin, PluginContext
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)


class SuspendPlugin(TestPlugin):
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        action = test_case.get("action", "")
        if action == "deep_sleep":
            return self._deep_sleep(test_case, context)
        if action == "reboot":
            return self._reboot(test_case, context)
        return TestResult(
            id=test_case["id"], name=test_case["name"],
            status=TestStatus.ERROR,
            message=f"Unknown suspend action: {action}",
        )

    def _reboot(self, tc: dict, ctx: PluginContext) -> TestResult:
        """Reboot device and verify it comes back up."""
        tid, tname = tc["id"], tc["name"]
        params = tc.get("params", {})
        boot_timeout = params.get("boot_timeout", 120)

        adb = ctx.adb

        # 1. Reboot
        logger.info("Initiating ADB reboot...")
        adb.shell("reboot")

        # 2. Wait for device to disconnect first
        logger.info("Waiting for device to disconnect...")
        for _ in range(30):
            time.sleep(1)
            if not adb.is_connected():
                logger.info("Device disconnected")
                break

        # 3. Wait for device to reconnect
        time.sleep(5)
        if not adb.wait_for_device(timeout=boot_timeout):
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Device not found via ADB after reboot "
                                      f"(timeout: {boot_timeout}s)")

        # 4. Wait for boot to fully complete (poll sys.boot_completed)
        logger.info("Device reconnected, waiting for boot to complete...")
        for _ in range(60):
            try:
                result = adb.shell("getprop sys.boot_completed")
                boot_out = result.stdout if hasattr(result, "stdout") else str(result)
                if boot_out.strip() == "1":
                    return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                                      message="ADB reboot + boot completed OK")
            except Exception:
                pass
            time.sleep(2)

        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message="Boot not completed after reboot (timeout)")

    def _deep_sleep(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        params = tc.get("params", {})
        suspend_duration = params.get("suspend_duration", 120)
        adb_timeout = params.get("adb_timeout", 60)

        if ctx.usb_power is None:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="usb_power not configured, skipping suspend test")

        adb = ctx.adb

        # 1. Read initial soc_sleep stats
        initial_stats = self._read_sleep_stats(adb)
        if initial_stats is None:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Cannot read /sys/power/soc_sleep/stats "
                                      "(may need root or file not present)")

        logger.info(f"Initial sleep stats: {initial_stats}")

        # 2. Enable airplane mode (prevent radio wakelocks)
        adb.shell("cmd connectivity airplane-mode enable")
        logger.info("Airplane mode enabled")
        time.sleep(2)

        # 3. Turn screen off — device must be in screen-off state to enter suspend
        adb.shell("input keyevent KEYCODE_POWER")
        logger.info("Screen off (KEYCODE_POWER)")
        time.sleep(2)

        # 4. USB power off — ADB disconnects, device can enter deep sleep
        logger.info(f"USB power off, waiting {suspend_duration}s for deep sleep...")
        ctx.usb_power.power_off()
        time.sleep(suspend_duration)

        # 4. USB power on — reconnect
        ctx.usb_power.power_on()
        logger.info("USB power on, waiting for ADB...")

        if not adb.wait_for_device(timeout=adb_timeout):
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message="Device not found via ADB after suspend")

        time.sleep(5)  # settle time

        # 5. Wake screen and verify system is functional
        adb.shell("input keyevent KEYCODE_WAKEUP")
        time.sleep(1)
        screen_state = adb.shell("dumpsys display | grep 'mScreenState'")
        screen_out = screen_state.stdout if hasattr(screen_state, "stdout") else str(screen_state)

        screen_awake = "ON" in screen_out.upper()
        logger.info(f"Screen state after wake: {screen_out.strip()}")

        # 6. Read final soc_sleep stats
        final_stats = self._read_sleep_stats(adb)
        if final_stats is None:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message="Cannot read soc_sleep stats after resume")

        logger.info(f"Final sleep stats: {final_stats}")

        # 7. Disable airplane mode
        adb.shell("cmd connectivity airplane-mode disable")
        logger.info("Airplane mode disabled")

        # 8. Verify deep sleep occurred
        entered_deep_sleep = self._verify_deep_sleep(initial_stats, final_stats)

        if not screen_awake:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Screen did not wake after resume: {screen_out.strip()}")

        if not entered_deep_sleep:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Deep sleep not entered during {suspend_duration}s suspend. "
                                      f"Before: {initial_stats}, After: {final_stats}")

        return TestResult(
            id=tid, name=tname, status=TestStatus.PASS,
            message=f"Suspend/Resume OK + Deep sleep verified "
                    f"(aosd: {initial_stats['aosd']}→{final_stats['aosd']}, "
                    f"cxsd: {initial_stats['cxsd']}→{final_stats['cxsd']}, "
                    f"ddr: {initial_stats['ddr']}→{final_stats['ddr']})"
        )

    @staticmethod
    def _read_sleep_stats(adb) -> dict | None:
        """Read /sys/power/soc_sleep/stats and parse aosd/cxsd/ddr counts.

        Supports two formats:
        1. Inline: "aosd:3, cxsd:3, ddr:3"
        2. Multi-line (Qualcomm):
           aosd
               Count                    :3
           cxsd
               Count                    :3
           ddr
               Count                    :3
        """
        result = adb.shell("cat /sys/power/soc_sleep/stats")
        stdout = result.stdout if hasattr(result, "stdout") else str(result)

        if not stdout or "No such file" in stdout or "Permission denied" in stdout:
            return None

        stats = {}

        # Try multi-line Qualcomm format first (section header + Count line)
        for key in ("aosd", "cxsd", "ddr"):
            pattern = rf"^{key}\b.*?\n\s*Count\s*:\s*(\d+)"
            m = re.search(pattern, stdout, re.MULTILINE | re.IGNORECASE)
            if m:
                stats[key] = int(m.group(1))

        # Fallback: inline format "aosd:3" or "aosd = 3"
        if not stats:
            for key in ("aosd", "cxsd", "ddr"):
                m = re.search(rf"{key}\s*[:=]\s*(\d+)", stdout, re.IGNORECASE)
                if m:
                    stats[key] = int(m.group(1))

        if not stats:
            return None

        for key in ("aosd", "cxsd", "ddr"):
            stats.setdefault(key, 0)

        return stats

    @staticmethod
    def _verify_deep_sleep(before: dict, after: dict) -> bool:
        """Verify that at least one deep sleep counter increased."""
        return (after["aosd"] > before["aosd"]
                or after["cxsd"] > before["cxsd"]
                or after["ddr"] > before["ddr"])
