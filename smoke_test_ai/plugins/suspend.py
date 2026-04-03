import re
import time
from pathlib import Path

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.base import TestPlugin, PluginContext
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)


class SuspendPlugin(TestPlugin):
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        action = test_case.get("action", "")
        if action == "deep_sleep":
            return self._deep_sleep(test_case, context)
        if action == "wakelock_check":
            return self._wakelock_check(test_case, context)
        if action == "thermal_check":
            return self._thermal_check(test_case, context)
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
            # Diagnose: collect wakelock info to identify blockers
            diag = self._diagnose_wakelocks(adb)
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Deep sleep not entered during {suspend_duration}s suspend. "
                                      f"Before: {initial_stats}, After: {final_stats}\n"
                                      f"--- Wakelock Diagnosis ---\n{diag}")

        return TestResult(
            id=tid, name=tname, status=TestStatus.PASS,
            message=f"Suspend/Resume OK + Deep sleep verified "
                    f"(aosd: {initial_stats['aosd']}→{final_stats['aosd']}, "
                    f"cxsd: {initial_stats['cxsd']}→{final_stats['cxsd']}, "
                    f"ddr: {initial_stats['ddr']}→{final_stats['ddr']})"
        )

    def _thermal_check(self, tc: dict, ctx: PluginContext) -> TestResult:
        """Check thermal subsystem: zone temps in range + cooling devices exist."""
        tid, tname = tc["id"], tc["name"]
        params = tc.get("params", {})
        # Key zones to check (common across Qualcomm platforms)
        key_zones = params.get("key_zones", [
            "battery", "xo-therm-usr", "quiet-therm-usr",
        ])

        adb = ctx.adb

        # 1. Read all thermal zones
        result = adb.shell(
            "for tz in /sys/class/thermal/thermal_zone*/; do "
            "echo \"$(cat $tz/type 2>/dev/null)|$(cat $tz/temp 2>/dev/null)\"; done"
        )
        stdout = result.stdout if hasattr(result, "stdout") else str(result)

        zones = {}
        errors = []
        for line in stdout.splitlines():
            line = line.strip()
            if "|" not in line:
                continue
            parts = line.split("|", 1)
            name = parts[0].strip()
            temp_str = parts[1].strip()
            if not name or not temp_str:
                continue
            try:
                temp = int(temp_str)
            except ValueError:
                continue
            # Skip BCL zones (negative/special values) and step zones with 0
            if temp < -100000 or name.endswith("-bcl-lvl0") or name.endswith("-bcl-lvl1") or name.endswith("-bcl-lvl2"):
                continue
            zones[name] = temp

        zone_count = len(zones)
        logger.info(f"Thermal zones with valid temp: {zone_count}")

        # 2. Check key zones exist
        for kz in key_zones:
            if kz in zones:
                logger.info(f"  {kz}: {zones[kz]/1000:.1f}°C ✓")
            else:
                errors.append(f"{kz}: zone not found")

        # 3. Find hottest zone (informational, no fail on high temp)
        hottest_name = ""
        hottest_temp = 0.0
        if zones:
            hottest_name = max(zones, key=zones.get)
            hottest_temp = zones[hottest_name] / 1000
            logger.info(f"  Hottest: {hottest_name} = {hottest_temp:.1f}°C")

        # 4. Check cooling devices exist
        cool_result = adb.shell("ls /sys/class/thermal/cooling_device*/type 2>/dev/null | wc -l")
        cool_out = cool_result.stdout if hasattr(cool_result, "stdout") else str(cool_result)
        try:
            cool_count = int(cool_out.strip())
        except ValueError:
            cool_count = 0
        logger.info(f"  Cooling devices: {cool_count}")

        if cool_count == 0:
            errors.append("No cooling devices registered")

        # 5. Sensor reactivity: stress CPU → verify all key zones + CPU zone respond
        #    Pick a CPU zone for primary check
        cpu_zone = None
        for name, temp in zones.items():
            if name.startswith("cpu") and "usr" in name and temp > 0:
                cpu_zone = name
                break

        # Zones to verify reactivity: key_zones + CPU zone
        verify_zones = list(key_zones)
        if cpu_zone and cpu_zone not in verify_zones:
            verify_zones.insert(0, cpu_zone)

        # Record before temps
        before_temps = {z: zones[z] for z in verify_zones if z in zones}

        stress_duration = params.get("stress_duration", 120)
        stale_zones = []
        active_zones = []

        if before_temps:
            logger.info(f"  Before stress: {', '.join(f'{z}={t/1000:.1f}°C' for z, t in before_temps.items())}")

            # Record system_server PID + uptime before stress
            ss_result = adb.shell("pidof system_server")
            ss_pid_before = (ss_result.stdout if hasattr(ss_result, "stdout")
                             else str(ss_result)).strip()
            uptime_result = adb.shell("cat /proc/uptime | awk '{print $1}'")
            uptime_before = float((uptime_result.stdout if hasattr(uptime_result, "stdout")
                                   else str(uptime_result)).strip() or "0")
            logger.info(f"  system_server PID={ss_pid_before}, uptime={uptime_before:.0f}s")

            dur = stress_duration
            stress_mem = params.get("stress_memory_mb", 64)
            stress_threads = params.get("stress_threads", 4)

            # Check if stressapptest is available, push if not
            sat_check = adb.shell("ls /data/local/tmp/stressapptest 2>/dev/null")
            sat_out = (sat_check.stdout if hasattr(sat_check, "stdout") else str(sat_check)).strip()
            if not sat_out:
                # Try to push from project tools/ directory
                sat_local = Path(__file__).parent.parent.parent / "tools" / "stressapptest-arm64"
                if sat_local.exists():
                    try:
                        import subprocess
                        subprocess.run(
                            ["adb", "-s", adb.serial, "push", str(sat_local), "/data/local/tmp/stressapptest"],
                            capture_output=True, timeout=10)
                        adb.shell("chmod +x /data/local/tmp/stressapptest")
                        logger.info("  stressapptest pushed to device")
                        sat_out = "/data/local/tmp/stressapptest"
                    except Exception as e:
                        logger.warning(f"  Failed to push stressapptest: {e}")
            has_sat = bool(sat_out)

            # Keep screen alive during stress
            adb.shell("input keyevent KEYCODE_WAKEUP")
            adb.shell("wm dismiss-keyguard")
            adb.shell("settings put system screen_off_timeout 2147483647")
            # Display: max brightness + Flash LED
            adb.shell("echo 255 > /sys/class/backlight/panel0-backlight/brightness 2>/dev/null")
            adb.shell("echo 200 > /sys/class/leds/led:torch_0/brightness 2>/dev/null; "
                       "echo 200 > /sys/class/leds/led:torch_1/brightness 2>/dev/null")

            if has_sat:
                logger.info(f"  Running stressapptest for {dur}s "
                            f"({stress_threads} threads, {stress_mem}MB RAM + Display + Flash)...")
                adb.shell(
                    f"nohup /data/local/tmp/stressapptest "
                    f"-s {dur} -C {stress_threads} -M {stress_mem} -W "
                    f"> /data/local/tmp/stressapptest.log 2>&1 &")
            else:
                logger.info(f"  stressapptest not found, using busy loop for {dur}s "
                            f"(CPU x4 + Display + Flash)...")
                adb.shell("nohup sh -c '"
                           "for i in 1 2 3 4; do "
                           "  while true; do true; done & "
                           "done; wait' > /dev/null 2>&1 &")

            # GPU stress: screenrecord HW encoder
            adb.shell(f"nohup screenrecord --time-limit {dur} /dev/null > /dev/null 2>&1 &")
            logger.info("  Stress components started")

            # Wait for stress duration
            time.sleep(dur)

            # Cleanup
            if not adb.is_connected():
                logger.warning("  ADB disconnected after stress, waiting for reconnect...")
                adb.wait_for_device(timeout=120)

            adb.shell("killall stressapptest screenrecord 2>/dev/null; "
                       "pkill -f 'while true' 2>/dev/null; "
                       "echo 0 > /sys/class/leds/led:torch_0/brightness 2>/dev/null; "
                       "echo 0 > /sys/class/leds/led:torch_1/brightness 2>/dev/null; "
                       "echo 128 > /sys/class/backlight/panel0-backlight/brightness 2>/dev/null")

            # Check stressapptest result
            if has_sat:
                sat_log = adb.shell("tail -3 /data/local/tmp/stressapptest.log 2>/dev/null")
                sat_result = (sat_log.stdout if hasattr(sat_log, "stdout") else str(sat_log)).strip()
                if "FAIL" in sat_result:
                    errors.append(f"stressapptest FAIL: {sat_result}")
                logger.info(f"  stressapptest result: {sat_result}")

            logger.info("  Stress cleanup done")

            # Check stability: kernel reboot + system_server crash
            try:
                uptime_result = adb.shell("cat /proc/uptime | awk '{print $1}'")
                uptime_after = float((uptime_result.stdout if hasattr(uptime_result, "stdout")
                                      else str(uptime_result)).strip() or "0")
            except Exception:
                uptime_after = 0

            ss_result = adb.shell("pidof system_server")
            ss_pid_after = (ss_result.stdout if hasattr(ss_result, "stdout")
                            else str(ss_result)).strip()

            if uptime_after < uptime_before:
                errors.append(f"Kernel reboot during stress! "
                              f"uptime {uptime_before:.0f}s → {uptime_after:.0f}s")
                logger.error(f"  KERNEL REBOOT: uptime {uptime_before:.0f}s → {uptime_after:.0f}s")
            elif ss_pid_before and ss_pid_after and ss_pid_before != ss_pid_after:
                errors.append(f"system_server crashed during stress! "
                              f"PID {ss_pid_before} → {ss_pid_after} (framework restart)")
                logger.error(f"  SYSTEM_SERVER CRASH: PID {ss_pid_before} → {ss_pid_after}")
            else:
                logger.info(f"  System stable (uptime {uptime_before:.0f}→{uptime_after:.0f}s, "
                            f"system_server PID={ss_pid_after})")

            # Re-read all thermal zones after stress
            re_result = adb.shell(
                "for tz in /sys/class/thermal/thermal_zone*/; do "
                "echo \"$(cat $tz/type 2>/dev/null)|$(cat $tz/temp 2>/dev/null)\"; done"
            )
            re_out = re_result.stdout if hasattr(re_result, "stdout") else str(re_result)
            after_zones = {}
            for line in re_out.splitlines():
                if "|" not in line:
                    continue
                parts = line.split("|", 1)
                name = parts[0].strip()
                try:
                    after_zones[name] = int(parts[1].strip())
                except (ValueError, IndexError):
                    pass

            # Compare before/after for each verify zone
            for z in verify_zones:
                if z not in before_temps or z not in after_zones:
                    continue
                before = before_temps[z]
                after = after_zones[z]
                delta = after - before
                if delta > 0:
                    active_zones.append({"name": z, "before": before, "after": after, "delta": delta})
                    logger.info(f"  {z}: {before/1000:.1f}→{after/1000:.1f}°C "
                                f"(+{delta/1000:.1f}°C) ✓")
                else:
                    stale_zones.append(z)
                    logger.warning(f"  {z}: {before/1000:.1f}→{after/1000:.1f}°C "
                                   f"({delta/1000:+.1f}°C) ✗ STALE")

        # CPU zone must respond (mandatory)
        if cpu_zone and cpu_zone in [s for s in stale_zones]:
            errors.append(f"CPU sensor stale: {cpu_zone} did not change after {stress_duration}s stress")

        # Warn if key zones are stale (non-CPU zones may not always change)
        if stale_zones:
            logger.warning(f"  Stale zones: {', '.join(stale_zones)}")

        if errors:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Thermal check failed: {'; '.join(errors)}")

        key_temps = ", ".join(
            f"{kz}={zones[kz]/1000:.1f}°C" for kz in key_zones if kz in zones
        )
        reactivity_parts = [f"{a['name']}+{a['delta']/1000:.1f}°C" for a in active_zones]
        reactivity = f", verified: {', '.join(reactivity_parts)}" if reactivity_parts else ""
        stale_note = f", stale: {', '.join(stale_zones)}" if stale_zones else ""
        return TestResult(
            id=tid, name=tname, status=TestStatus.PASS,
            message=f"Thermal OK — {zone_count} zones, {cool_count} cooling devices, "
                    f"hottest: {hottest_name}={hottest_temp:.1f}°C. "
                    f"Key: {key_temps}{reactivity}{stale_note}")

    def _wakelock_check(self, tc: dict, ctx: PluginContext) -> TestResult:
        """Check for abnormal wakelocks that would block suspend."""
        tid, tname = tc["id"], tc["name"]
        params = tc.get("params", {})
        max_partial = params.get("max_partial_wakelocks", 3)

        adb = ctx.adb

        # 1. Get Android framework wakelocks
        framework_wl = self._get_framework_wakelocks(adb)
        # 2. Get kernel wakeup sources with prevent_suspend_time > 0
        kernel_blockers = self._get_kernel_wakeup_blockers(adb)

        partial_count = len(framework_wl)
        blocker_count = len(kernel_blockers)

        logger.info(f"Framework partial wakelocks: {partial_count}")
        for wl in framework_wl:
            logger.info(f"  [{wl['type']}] {wl['tag']} (uid={wl['uid']})")
        logger.info(f"Kernel wakeup blockers: {blocker_count}")
        for kb in kernel_blockers[:5]:
            logger.info(f"  {kb['name']}: active_count={kb['active_count']}, "
                        f"total_time={kb['total_time']}ms")

        if partial_count > max_partial:
            wl_list = ", ".join(wl["tag"] for wl in framework_wl[:5])
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Too many partial wakelocks: {partial_count} "
                                      f"(max {max_partial}). Top: {wl_list}")

        details = []
        if framework_wl:
            details.append(f"partial_wakelocks: {partial_count} "
                          f"({', '.join(wl['tag'] for wl in framework_wl)})")
        if kernel_blockers:
            details.append(f"kernel_blockers: {blocker_count} "
                          f"({', '.join(kb['name'] for kb in kernel_blockers[:3])})")

        return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                          message=f"Wakelock check OK — "
                                  f"{partial_count} partial wakelocks, "
                                  f"{blocker_count} kernel blockers. "
                                  + "; ".join(details) if details else "")

    @staticmethod
    def _get_framework_wakelocks(adb) -> list[dict]:
        """Get active partial wakelocks from Android framework."""
        result = adb.shell("dumpsys power | grep 'PARTIAL_WAKE_LOCK'")
        stdout = result.stdout if hasattr(result, "stdout") else str(result)
        wakelocks = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line or "PARTIAL_WAKE_LOCK" not in line:
                continue
            # Format: PARTIAL_WAKE_LOCK  'tag' ACQ=... (uid=... pid=...)
            tag_m = re.search(r"'([^']+)'", line)
            uid_m = re.search(r"uid=(\d+)", line)
            wakelocks.append({
                "type": "PARTIAL",
                "tag": tag_m.group(1) if tag_m else line[:50],
                "uid": uid_m.group(1) if uid_m else "?",
                "raw": line,
            })
        return wakelocks

    @staticmethod
    def _get_kernel_wakeup_blockers(adb) -> list[dict]:
        """Get kernel wakeup sources that actively prevent suspend."""
        result = adb.shell("cat /d/wakeup_sources 2>/dev/null || "
                          "cat /sys/kernel/debug/wakeup_sources 2>/dev/null")
        stdout = result.stdout if hasattr(result, "stdout") else str(result)
        blockers = []
        for line in stdout.splitlines():
            if line.startswith("name") or not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 9:
                continue
            name = parts[0].strip()
            if not name:
                continue
            try:
                active_count = int(parts[1].strip())
                total_time = int(parts[6].strip())
                prevent_time = int(parts[8].strip())
            except (ValueError, IndexError):
                continue
            # Only include sources with significant activity
            if active_count > 10 and total_time > 1000:
                blockers.append({
                    "name": name,
                    "active_count": active_count,
                    "total_time": total_time,
                    "prevent_suspend_time": prevent_time,
                })
        # Sort by total_time descending
        blockers.sort(key=lambda x: x["total_time"], reverse=True)
        return blockers[:10]

    @staticmethod
    def _diagnose_wakelocks(adb) -> str:
        """Collect wakelock diagnostics for deep sleep failure analysis."""
        lines = []

        # Framework wakelocks
        result = adb.shell("dumpsys power | grep -E 'WAKE_LOCK|Suspend Blockers' -A5")
        stdout = result.stdout if hasattr(result, "stdout") else str(result)
        fw_locks = [l.strip() for l in stdout.splitlines() if l.strip()]
        if fw_locks:
            lines.append("Framework wakelocks:")
            for l in fw_locks[:10]:
                lines.append(f"  {l}")

        # Kernel wakeup sources (top by total_time)
        result = adb.shell("cat /d/wakeup_sources 2>/dev/null || "
                          "cat /sys/kernel/debug/wakeup_sources 2>/dev/null")
        stdout = result.stdout if hasattr(result, "stdout") else str(result)
        sources = []
        for line in stdout.splitlines():
            if line.startswith("name") or not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                name = parts[0].strip()
                try:
                    total = int(parts[6].strip())
                except (ValueError, IndexError):
                    total = 0
                if name and total > 1000:
                    sources.append((name, total))
        sources.sort(key=lambda x: x[1], reverse=True)
        if sources:
            lines.append("Top kernel wakeup sources (by total_time ms):")
            for name, total in sources[:10]:
                lines.append(f"  {name}: {total}ms")

        return "\n".join(lines) if lines else "No wakelock data available"

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
