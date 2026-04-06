import re
import time
import zipfile
import urllib.request
from pathlib import Path
from smoke_test_ai.drivers.adb_controller import AdbController
from smoke_test_ai.drivers.usb_power_serial import SerialUsbPowerController
from smoke_test_ai.drivers.flash.base import FlashDriver
from smoke_test_ai.drivers.flash.fastboot import FastbootFlashDriver
from smoke_test_ai.drivers.flash.custom import CustomFlashDriver
from smoke_test_ai.drivers.screen_capture.base import ScreenCapture
from smoke_test_ai.drivers.screen_capture.webcam import WebcamCapture
from smoke_test_ai.drivers.screen_capture.adb_screencap import AdbScreenCapture
from smoke_test_ai.ai.llm_client import LlmClient
from smoke_test_ai.ai.visual_analyzer import VisualAnalyzer
from smoke_test_ai.core.test_runner import TestRunner, TestResult
from smoke_test_ai.reporting.cli_reporter import CliReporter
from smoke_test_ai.reporting.json_reporter import JsonReporter
from smoke_test_ai.reporting.html_reporter import HtmlReporter
from smoke_test_ai.reporting.test_plan_reporter import TestPlanReporter
from smoke_test_ai.utils.logger import get_logger
from smoke_test_ai.plugins.camera import CameraPlugin
from smoke_test_ai.plugins.telephony import TelephonyPlugin
from smoke_test_ai.plugins.wifi import WifiPlugin
from smoke_test_ai.plugins.bluetooth import BluetoothPlugin
from smoke_test_ai.plugins.audio import AudioPlugin
from smoke_test_ai.plugins.network import NetworkPlugin
from smoke_test_ai.plugins.charging import ChargingPlugin
from smoke_test_ai.plugins.suspend import SuspendPlugin

logger = get_logger(__name__)


class Orchestrator:
    def __init__(self, settings: dict, device_config: dict):
        self.settings = settings
        self.device_config = device_config["device"]
        self.device_name = self.device_config["name"]

    def _init_aoa_hid(self, aoa_cfg: dict):
        """Initialize AOA2 HID driver: find device, start accessory mode, register HIDs."""
        from smoke_test_ai.drivers.aoa_hid import (
            AoaHidDriver, HID_KEYBOARD_DESCRIPTOR,
        )

        hid = AoaHidDriver(
            vendor_id=aoa_cfg["vendor_id"],
            product_id=aoa_cfg["product_id"],
            rotation=aoa_cfg.get("rotation", 0),
        )
        hid.find_device()
        hid.start_accessory()

        kbd_id = aoa_cfg.get("keyboard_hid_id", 1)
        touch_id = aoa_cfg.get("touch_hid_id", 2)
        consumer_id = aoa_cfg.get("consumer_hid_id", 3)
        hid.register_hid(kbd_id, HID_KEYBOARD_DESCRIPTOR)
        hid.register_touch(touch_id)
        hid.register_consumer(consumer_id)

        logger.info(f"AOA HID initialized (keyboard={kbd_id}, touch={touch_id}, consumer={consumer_id})")
        return hid

    def _get_flash_driver(self, serial: str | None = None) -> FlashDriver:
        profile = self.device_config["flash"]["profile"]
        if profile == "fastboot":
            return FastbootFlashDriver(serial=serial)
        elif profile == "custom":
            return CustomFlashDriver()
        raise ValueError(f"Unknown flash profile: {profile}")

    def _get_screen_capture(self, serial: str | None = None) -> ScreenCapture:
        method = self.device_config.get("screen_capture", {}).get("method", "adb")
        if method == "adb":
            return AdbScreenCapture(serial=serial)
        elif method == "webcam":
            sc = self.device_config["screen_capture"]
            return WebcamCapture(
                device_index=sc.get("webcam_device", 0),
                crop=tuple(sc["webcam_crop"]) if "webcam_crop" in sc else None,
            )
        raise ValueError(f"Unknown screen capture method: {method}")

    def _get_webcam_capture(self) -> WebcamCapture | None:
        """Create webcam capture if configured. Returns None if not available."""
        sc = self.device_config.get("screen_capture", {})
        webcam_device = sc.get("webcam_device")
        if webcam_device is None:
            return None
        try:
            crop = tuple(sc["webcam_crop"]) if "webcam_crop" in sc else None
            cam = WebcamCapture(device_index=webcam_device, crop=crop)
            cam.open()
            logger.info(f"Webcam opened: {webcam_device}")
            return cam
        except Exception as e:
            logger.warning(f"Webcam not available ({e}), will fallback to ADB screencap")
            return None

    def _get_llm_client(self) -> LlmClient:
        llm_cfg = self.settings["llm"]
        return LlmClient(
            provider=llm_cfg["provider"],
            base_url=llm_cfg["base_url"],
            vision_model=llm_cfg.get("vision_model"),
            text_model=llm_cfg.get("text_model"),
            api_key=llm_cfg.get("api_key"),
            timeout=llm_cfg.get("timeout", 30),
        )

    # Mobly Bundled Snippets constants
    _SNIPPET_PKG = "com.google.android.mobly.snippet.bundled"
    _SNIPPET_APK_URL = (
        "https://github.com/user-attachments/files/18174301/"
        "mobly-bundled-snippets-release-0.0.1.zip"
    )

    def _find_snippet_apk(self) -> Path | None:
        """Search common locations for the Mobly Bundled Snippets APK."""
        candidates = [
            Path("apks/mobly-bundled-snippets.apk"),
            Path("apks/mobly-snippets.apk"),
            Path(__file__).parent.parent.parent / "apks" / "mobly-bundled-snippets.apk",
        ]
        for c in candidates:
            if c.exists():
                return c
        return None

    def _download_snippet_apk(self) -> Path | None:
        """Download Mobly Bundled Snippets APK from GitHub release."""
        apk_dir = Path("apks")
        apk_dir.mkdir(exist_ok=True)
        apk_path = apk_dir / "mobly-bundled-snippets.apk"
        zip_path = apk_dir / "mobly-bundled-snippets.zip"
        try:
            logger.info(f"Downloading Mobly Snippet APK from GitHub...")
            urllib.request.urlretrieve(self._SNIPPET_APK_URL, str(zip_path))
            with zipfile.ZipFile(zip_path, "r") as zf:
                # Find the .apk inside the zip
                apk_names = [n for n in zf.namelist() if n.endswith(".apk")]
                if not apk_names:
                    logger.error("No .apk found inside downloaded zip")
                    return None
                zf.extract(apk_names[0], str(apk_dir))
                extracted = apk_dir / apk_names[0]
                if extracted != apk_path:
                    extracted.rename(apk_path)
            zip_path.unlink(missing_ok=True)
            logger.info(f"Downloaded Mobly Snippet APK: {apk_path}")
            return apk_path
        except Exception as e:
            logger.error(f"Failed to download Mobly Snippet APK: {e}")
            zip_path.unlink(missing_ok=True)
            return None

    def _ensure_mobly_snippet(self, adb: AdbController) -> bool:
        """Ensure Mobly Bundled Snippets APK is installed on the device.

        Steps:
        1. Check if already installed (for current user)
        2. Verify device can install APKs (adb install capability)
        3. Find or download APK
        4. Install and verify

        Returns True if snippet is available on device.
        """
        # 1. Check if already installed for current user (user 0)
        check = adb.shell(f"pm list packages --user 0 {self._SNIPPET_PKG}")
        stdout = check.stdout if hasattr(check, "stdout") else str(check)
        if self._SNIPPET_PKG in stdout:
            logger.info("Mobly Snippet APK already installed")
            return True

        # Package might exist but not enabled for user 0 — try enabling first
        check_all = adb.shell(f"pm list packages {self._SNIPPET_PKG}")
        stdout_all = check_all.stdout if hasattr(check_all, "stdout") else str(check_all)
        if self._SNIPPET_PKG in stdout_all:
            logger.info("Mobly Snippet exists but not enabled for user 0, installing for user...")
            result = adb.shell(f"pm install-existing --user 0 {self._SNIPPET_PKG}")
            r_stdout = result.stdout if hasattr(result, "stdout") else str(result)
            if "Success" in r_stdout:
                logger.info("Mobly Snippet enabled for user 0")
                return True
            logger.warning(f"install-existing failed: {r_stdout}")

        # 2. Verify device can install APKs
        #    Check ADB is rooted or install permission is available
        whoami = adb.shell("id").stdout.strip() if hasattr(adb.shell("id"), "stdout") else ""
        logger.info(f"Device ADB identity: {whoami}")

        # 3. Find APK locally or download it
        apk_path = self._find_snippet_apk()
        if not apk_path:
            logger.info("Mobly Snippet APK not found locally, attempting download...")
            apk_path = self._download_snippet_apk()
        if not apk_path:
            logger.error(
                "Mobly Snippet APK unavailable. Snippet-dependent tests will be SKIPPED. "
                "Place mobly-bundled-snippets.apk in apks/ directory."
            )
            return False

        # 4. Install APK
        logger.info(f"Installing Mobly Snippet APK: {apk_path}")
        result = adb.install(str(apk_path))
        r_stdout = result.stdout if hasattr(result, "stdout") else str(result)
        r_stderr = result.stderr if hasattr(result, "stderr") else ""

        if result.returncode != 0:
            logger.error(f"APK install failed (rc={result.returncode}): {r_stdout} {r_stderr}")
            # Check common failure reasons
            if "INSTALL_FAILED_OLDER_SDK" in r_stdout or "INSTALL_FAILED_OLDER_SDK" in r_stderr:
                logger.error("Device SDK version too old for this APK")
            elif "INSTALL_FAILED_INSUFFICIENT_STORAGE" in (r_stdout + r_stderr):
                logger.error("Insufficient storage on device")
            elif "INSTALL_FAILED_USER_RESTRICTED" in (r_stdout + r_stderr):
                logger.error("User is restricted from installing APKs — check device policy")
            return False

        # 5. Verify installation succeeded
        verify = adb.shell(f"pm list packages --user 0 {self._SNIPPET_PKG}")
        v_stdout = verify.stdout if hasattr(verify, "stdout") else str(verify)
        if self._SNIPPET_PKG in v_stdout:
            logger.info("Mobly Snippet APK installed and verified successfully")
            return True

        logger.error("Mobly Snippet APK install command succeeded but package not found on device")
        return False

    def _pre_test_setup(self, adb: AdbController, suite_config: dict | None) -> None:
        """Install required APKs and clean previous test run data."""
        logger.info("Pre-test setup: install & clean")

        # 1. Auto-install Mobly Bundled Snippets APK if snippet tests exist
        if suite_config and self._has_snippet_tests(suite_config):
            if self._ensure_mobly_snippet(adb):
                # Grant runtime permissions required by Mobly Snippet (Android 12+)
                for perm in [
                    "android.permission.BLUETOOTH_SCAN",
                    "android.permission.BLUETOOTH_CONNECT",
                    "android.permission.BLUETOOTH_ADVERTISE",
                    "android.permission.ACCESS_FINE_LOCATION",
                    "android.permission.ACCESS_COARSE_LOCATION",
                    "android.permission.READ_PHONE_STATE",
                    "android.permission.CALL_PHONE",
                    "android.permission.SEND_SMS",
                    "android.permission.READ_SMS",
                    "android.permission.READ_PHONE_NUMBERS",
                    "android.permission.RECORD_AUDIO",
                ]:
                    adb.shell(f"pm grant {self._SNIPPET_PKG} {perm} 2>/dev/null")
                logger.info("Mobly Snippet runtime permissions granted")

        # 2. Clean previous test run data
        # Clear crash log buffer so previous crashes don't affect this run
        adb.shell("logcat -b crash -c")
        # Remove previous camera test photos
        adb.shell("rm -rf /sdcard/DCIM/Camera/*.jpg 2>/dev/null")
        # Kill camera app to ensure clean state
        adb.shell("am force-stop org.codeaurora.snapcam 2>/dev/null; "
                   "am force-stop com.android.camera2 2>/dev/null")
        # Grant camera permissions proactively
        adb.shell("pm grant org.codeaurora.snapcam android.permission.CAMERA 2>/dev/null; "
                   "pm grant org.codeaurora.snapcam android.permission.WRITE_EXTERNAL_STORAGE 2>/dev/null; "
                   "pm grant org.codeaurora.snapcam android.permission.RECORD_AUDIO 2>/dev/null; "
                   "pm grant org.codeaurora.snapcam android.permission.ACCESS_FINE_LOCATION 2>/dev/null")
        logger.info("Pre-test cleanup complete")

    @staticmethod
    def _resolve_flash_config(flash_config: dict, build_dir: str) -> dict:
        """Resolve ${BUILD_DIR} placeholders in flash config."""
        import copy
        config = copy.deepcopy(flash_config)

        def _substitute(obj):
            if isinstance(obj, str):
                return obj.replace("${BUILD_DIR}", build_dir)
            if isinstance(obj, dict):
                return {k: _substitute(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_substitute(v) for v in obj]
            return obj

        return _substitute(config)

    def _resolve_variables(self, suite_config: dict) -> dict:
        """Resolve ${VAR} placeholders in test suite config."""
        var_map = {
            "WIFI_SSID": self.settings.get("wifi", {}).get("ssid", ""),
            "WIFI_PASSWORD": self.settings.get("wifi", {}).get("password", ""),
            "PEER_PHONE_NUMBER": self.device_config.get("peer_phone_number", ""),
            "PHONE_NUMBER": self.device_config.get("phone_number", ""),
        }

        def _substitute(obj):
            if isinstance(obj, str):
                def _replacer(m):
                    return var_map.get(m.group(1), m.group(0))
                return re.sub(r"\$\{(\w+)\}", _replacer, obj)
            if isinstance(obj, dict):
                return {k: _substitute(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_substitute(v) for v in obj]
            return obj

        return _substitute(suite_config)

    @staticmethod
    def _has_snippet_tests(suite_config: dict) -> bool:
        """Check if any test in the suite requires Mobly snippet."""
        tests = suite_config.get("test_suite", {}).get("tests", [])
        snippet_types = {"telephony", "wifi", "bluetooth", "audio", "network"}
        return any(t.get("type") in snippet_types for t in tests)

    def _init_plugins(self, adb, analyzer, serial, suite_config):
        """Initialize plugins and optionally Mobly snippet connections."""
        snippet = None
        peer_snippet = None

        if self._has_snippet_tests(suite_config):
            try:
                from mobly.controllers.android_device import AndroidDevice
                mobly_dut = AndroidDevice(serial or adb.serial)
                mobly_dut.load_snippet('mbs', 'com.google.android.mobly.snippet.bundled')
                snippet = mobly_dut.mbs
                self._mobly_dut = mobly_dut
                logger.info("Mobly snippet loaded on DUT")

                peer_serial = self.device_config.get("peer_serial")
                if peer_serial:
                    mobly_peer = AndroidDevice(peer_serial)
                    mobly_peer.load_snippet('mbs', 'com.google.android.mobly.snippet.bundled')
                    peer_snippet = mobly_peer.mbs
                    self._mobly_peer = mobly_peer
                    logger.info(f"Mobly snippet loaded on peer ({peer_serial})")
            except Exception as e:
                logger.warning(f"Failed to load Mobly snippets: {e}")

        plugins = {
            "telephony": TelephonyPlugin(),
            "camera": CameraPlugin(),
            "wifi": WifiPlugin(),
            "bluetooth": BluetoothPlugin(),
            "audio": AudioPlugin(),
            "network": NetworkPlugin(),
            "charging": ChargingPlugin(),
            "suspend": SuspendPlugin(),
        }

        return plugins, snippet, peer_snippet

    def run(
        self,
        serial: str | None = None,
        suite_config: dict | None = None,
        build_dir: str | None = None,
        skip_flash: bool = False,
        skip_setup: bool = False,
        config_dir: str = "config",
        build_type: str | None = None,
        keep_data: bool = False,
        is_factory_reset: bool = False,
        build_info: dict | None = None,
    ) -> list[TestResult]:
        adb = AdbController(serial=serial)

        # Initialize USB power controller if configured
        usb_power_cfg = self.device_config.get("usb_power")
        usb_power = None
        if usb_power_cfg:
            usb_power = SerialUsbPowerController(
                port=usb_power_cfg["port"],
                off_duration=usb_power_cfg.get("off_duration", 3.0),
                serial_port=usb_power_cfg.get("serial_port"),
                device_serial=usb_power_cfg.get("device_serial"),
            )

        # Adaptive pipeline decision logic
        effective_build_type = build_type or self.device_config.get("build_type", "userdebug")
        need_flash = not skip_flash and build_dir
        need_aoa = (
            effective_build_type == "user"
            and not keep_data
            and (need_flash or is_factory_reset)
            and not skip_setup
        )
        fresh_state = (need_flash or is_factory_reset) and not keep_data
        logger.info(f"Pipeline: build_type={effective_build_type}, "
                    f"need_aoa={need_aoa}, fresh_state={fresh_state}")

        # Stage 0: Flash
        if not skip_flash and build_dir:
            logger.info("=== Stage 0: Flash Image ===")
            flash_driver = self._get_flash_driver(serial=serial)
            flash_config = self._resolve_flash_config(
                self.device_config["flash"], build_dir
            )
            if keep_data:
                flash_config["keep_data"] = True
            flash_driver.flash(flash_config)
            logger.info("Flash complete. Waiting for device boot...")
            time.sleep(10)

            if usb_power:
                logger.info("USB power cycle after flash...")
                usb_power.power_cycle()

        # Stage 1: Pre-ADB Setup (Blind AOA2 HID automation)
        if need_aoa:
            aoa_cfg = self.device_config.get("aoa", {})
            if aoa_cfg.get("enabled"):
                logger.info("=== Stage 1: Pre-ADB Setup (Blind AOA2 HID) ===")
                flow_name = self.device_config["name"].lower().replace("-", "_").replace(" ", "_")
                flow_path = Path(config_dir) / "setup_flows" / f"{flow_name}.yaml"
                if flow_path.exists():
                    try:
                        import yaml
                        from smoke_test_ai.runners.blind_runner import BlindRunner

                        hid = self._init_aoa_hid(aoa_cfg)
                        flow = yaml.safe_load(flow_path.read_text())
                        runner = BlindRunner(hid=hid, adb=adb, aoa_config=aoa_cfg, flow_config=flow, usb_power=usb_power)
                        if runner.run():
                            logger.info("Blind setup flow completed successfully")
                        else:
                            logger.warning("Blind setup flow did not complete — ADB may not be available")
                        hid.close()
                    except Exception as e:
                        logger.error(f"Blind setup flow failed: {e}")
                else:
                    logger.info(f"No setup flow at {flow_path}, skipping Stage 1")
            else:
                logger.info("=== Stage 1: Pre-ADB Setup (AOA not configured) ===")
                logger.info("Waiting for ADB to become available...")

        # Stage 2: ADB Bootstrap
        logger.info("=== Stage 2: ADB Bootstrap ===")
        if not adb.wait_for_device(timeout=120):
            logger.error("Device not found via ADB")
            return []

        # Skip Setup Wizard if fresh state (factory reset or full flash)
        # For user builds: AOA should handle it, but if AOA failed and ADB
        # is available (root/userdebug), skip via ADB as fallback
        if not skip_setup and fresh_state:
            adb.skip_setup_wizard()

        # FBE unlock: only needed after state reset (fresh_state)
        if fresh_state:
            user_state = adb.get_user_state()
            if user_state == "RUNNING_LOCKED":
                logger.warning("User storage is locked (FBE). Attempting unlock...")
                pin = self.device_config.get("lock_pin")
                if adb.unlock_keyguard(pin=pin):
                    logger.info("Device unlocked successfully — user storage is now accessible")
                else:
                    logger.error(
                        "Failed to unlock device. Many services (NFC, Launcher, etc.) "
                        "will not start until user storage is unlocked."
                    )

        # WiFi connection (longer timeout after full state reset)
        wifi_cfg = self.settings.get("wifi", {})
        wifi_timeout = 45 if fresh_state else 15
        if wifi_cfg.get("ssid"):
            if adb.is_wifi_connected():
                logger.info("WiFi already connected, skipping")
            else:
                adb.connect_wifi(
                    wifi_cfg["ssid"],
                    wifi_cfg.get("password", ""),
                    security=wifi_cfg.get("security", "wpa2"),
                    wifi_timeout=wifi_timeout,
                )

        adb.shell("settings put global stay_on_while_plugged_in 3")
        adb.shell("settings put system screen_off_timeout 2147483647")
        adb.shell("input keyevent KEYCODE_WAKEUP")
        adb.shell("wm dismiss-keyguard")

        # Pre-test setup: install Mobly Snippet APK and clean previous test data
        self._pre_test_setup(adb, suite_config)

        # Collect device info for reports
        device_info = adb.get_device_info()

        # Collect GMS version
        try:
            gms_result = adb.shell("pm dump com.google.android.gms | grep 'versionName' | head -1 | sed 's/.*versionName=//'")
            gms_ver = (gms_result.stdout if hasattr(gms_result, "stdout") else str(gms_result)).strip()
            if gms_ver:
                device_info["gms_version"] = gms_ver
        except Exception:
            pass

        # Collect component firmware versions
        fw_commands = {
            "fw_wwan": "getprop gsm.version.baseband",
            "fw_touch": "cat /sys/devices/platform/soc/a94000.i2c/i2c-5/5-002a/fw_version 2>/dev/null",
            "fw_keypad": "cat /sys/devices/platform/soc/98c000.i2c/i2c-2/2-0012/fw 2>/dev/null",
        }
        for key, cmd in fw_commands.items():
            try:
                result = adb.shell(cmd)
                val = (result.stdout if hasattr(result, "stdout") else str(result)).strip()
                if val:
                    device_info[key] = val
            except Exception:
                pass
        # Split WWAN firmware into version and build date
        wwan = device_info.get("fw_wwan", "")
        if " " in wwan:
            parts = wwan.split(" ", 1)
            device_info["fw_wwan"] = parts[0]
            device_info["fw_wwan_date"] = parts[1]

        # Build info validation
        if build_info:
            device_info["build_info"] = build_info
            build_validation = self._validate_build_info(adb, build_info)
            device_info["build_validation"] = build_validation

        # Resolve ${VAR} placeholders before test execution
        if suite_config:
            suite_config = self._resolve_variables(suite_config)

        # Store suite_config for report generation
        self._suite_config = suite_config

        # Preflight Check
        preflight = self._preflight_check(adb, suite_config, usb_power)
        device_info["preflight"] = preflight

        # Abort on CRITICAL failures
        critical_fails = [p for p in preflight if p["level"] == "CRITICAL"]
        if critical_fails:
            logger.error("Preflight CRITICAL failure — aborting test execution")
            return []

        # Stage 3: Test Execute
        if suite_config:
            logger.info("=== Stage 3: Test Execute ===")
            screen_capture = self._get_screen_capture(serial=serial)
            webcam_capture = self._get_webcam_capture()
            llm = self._get_llm_client()
            analyzer = VisualAnalyzer(llm)
            device_capabilities = {
                k: v for k, v in self.device_config.items()
                if isinstance(v, bool)
            }
            device_capabilities["usb_power"] = usb_power is not None

            plugins, snippet, peer_snippet = self._init_plugins(
                adb, analyzer, serial, suite_config
            )

            runner = TestRunner(
                adb=adb,
                visual_analyzer=analyzer,
                screen_capture=screen_capture,
                webcam_capture=webcam_capture,
                device_capabilities=device_capabilities,
                plugins=plugins,
            )
            # Inject snippet handles into runner for plugin context
            runner._snippet = snippet
            runner._peer_snippet = peer_snippet
            runner._settings = self.settings
            runner._usb_power = usb_power
            runner._mobly_dut = getattr(self, '_mobly_dut', None)

            # Run all tests EXCEPT adb_reboot (which clears logcat)
            reboot_tc = None
            tests = suite_config.get("test_suite", {}).get("tests", [])
            for tc in tests:
                if tc.get("id") == "adb_reboot":
                    reboot_tc = tc
                    break
            if reboot_tc:
                tests_without_reboot = [t for t in tests if t["id"] != "adb_reboot"]
                suite_no_reboot = dict(suite_config)
                suite_no_reboot["test_suite"] = dict(suite_config["test_suite"])
                suite_no_reboot["test_suite"]["tests"] = tests_without_reboot
                results = runner.run_suite(suite_no_reboot)
            else:
                results = runner.run_suite(suite_config)

            # Bugreport + Crash Analysis BEFORE reboot (logcat still intact)
            try:
                crash_analysis = self._capture_bugreport_and_analyze(adb)
                if crash_analysis:
                    device_info["crash_analysis"] = crash_analysis
            except Exception as e:
                logger.warning(f"Crash analysis failed: {e}")

            # Now run adb_reboot as the last test
            if reboot_tc:
                reboot_suite = dict(suite_config)
                reboot_suite["test_suite"] = dict(suite_config["test_suite"])
                reboot_suite["test_suite"]["tests"] = [reboot_tc]
                reboot_results = runner.run_suite(reboot_suite)
                results.extend(reboot_results)

            if webcam_capture:
                webcam_capture.close()
            # Cleanup Mobly devices
            if hasattr(self, '_mobly_dut'):
                try:
                    self._mobly_dut.unload_snippet('mbs')
                except Exception:
                    pass
            if hasattr(self, '_mobly_peer'):
                try:
                    self._mobly_peer.unload_snippet('mbs')
                except Exception:
                    pass
        else:
            results = []

        # Stage 4: Report
        logger.info("=== Stage 4: Report ===")
        self._generate_reports(results, device_info=device_info, suite_config=suite_config)

        return results

    def _validate_build_info(self, adb, build_info: dict) -> list[dict]:
        """Validate device against CI build info validations array."""
        logger.info("=== Build Info Validation ===")
        results = []

        for v in build_info.get("validations", []):
            cmd = v.get("command", "")
            expected = v.get("expected", "")
            mode = v.get("mode", "exact")
            name = v.get("name", cmd)
            category = v.get("category", "Other")

            try:
                result = adb.shell(cmd)
                actual = (result.stdout if hasattr(result, "stdout") else str(result)).strip()
            except Exception:
                actual = ""

            if mode == "contains":
                match = expected in actual
            else:
                match = actual == expected

            entry = {
                "property": name,
                "category": category,
                "expected": expected,
                "actual": actual,
                "match": match,
                "mode": mode,
            }
            results.append(entry)

            icon = "✓" if match else "✗"
            level = "OK" if match else "MISMATCH"
            logger.info(f"  [{icon}] {level:8s} [{category}] {name}")
            if not match:
                logger.warning(f"           expected: {expected}")
                logger.warning(f"           actual:   {actual}")

        passed = sum(1 for r in results if r["match"])
        total = len(results)
        if total > 0:
            if passed == total:
                logger.info(f"Build validation: all {total} checks passed")
            else:
                logger.warning(f"Build validation: {total - passed}/{total} MISMATCH")

        return results

    def _capture_bugreport_and_analyze(self, adb) -> dict | None:
        """Capture bugreport and analyze for crashes during test execution."""
        logger.info("=== Post-test: Bugreport & Crash Analysis ===")

        output_dir = Path(self.settings.get("output_dir", "results"))
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Capture bugreport
        bugreport_path = output_dir / f"{self.device_name}_bugreport"
        zip_path = None
        try:
            logger.info("Capturing bugreport (this may take 1-2 minutes)...")
            result = adb.bugreport(str(bugreport_path))

            # adb bugreport creates a .zip file
            zip_path = bugreport_path.with_suffix(".zip")
            if not zip_path.exists():
                zips = list(output_dir.glob(f"{self.device_name}_bugreport*.zip"))
                zip_path = zips[0] if zips else None

            if zip_path and zip_path.exists():
                logger.info(f"Bugreport saved: {zip_path}")
            else:
                logger.warning("Bugreport zip not found")
                zip_path = None
        except Exception as e:
            logger.warning(f"Bugreport capture failed: {e}")

        # 2. Analyze crashes from logcat (faster than parsing bugreport zip)
        crashes = []
        try:
            # System crashes (Java)
            crash_log = adb.shell("logcat -b crash -d")
            crash_out = crash_log.stdout if hasattr(crash_log, "stdout") else str(crash_log)
            for line in crash_out.splitlines():
                if "FATAL EXCEPTION" in line:
                    crashes.append({"type": "FATAL EXCEPTION", "detail": line.strip()})

            # ANR — extract app name and reason
            anr_log = adb.shell("logcat -b events -d | grep 'am_anr'")
            anr_out = anr_log.stdout if hasattr(anr_log, "stdout") else str(anr_log)
            for line in anr_out.splitlines():
                if "am_anr" in line:
                    crashes.append({"type": "ANR", "detail": line.strip()})

            # Also check ANR traces directory
            anr_traces = adb.shell("ls -t /data/anr/ 2>/dev/null | head -5")
            anr_traces_out = anr_traces.stdout if hasattr(anr_traces, "stdout") else str(anr_traces)
            for line in anr_traces_out.splitlines():
                line = line.strip()
                if line and line.endswith(".txt"):
                    # Read first line of trace for process name
                    trace_head = adb.shell(f"head -3 /data/anr/{line} 2>/dev/null")
                    trace_out = (trace_head.stdout if hasattr(trace_head, "stdout")
                                 else str(trace_head)).strip()
                    detail = f"/data/anr/{line}"
                    if trace_out:
                        detail += f" | {trace_out.splitlines()[0][:80]}"
                    crashes.append({"type": "ANR Trace", "detail": detail})

            # Tombstones — read process name and signal from each
            tombstones = adb.shell("ls -t /data/tombstones/ 2>/dev/null | head -5")
            tomb_out = tombstones.stdout if hasattr(tombstones, "stdout") else str(tombstones)
            for line in tomb_out.splitlines():
                line = line.strip()
                if not line:
                    continue
                # Read tombstone header for process name and signal
                tomb_head = adb.shell(
                    f"head -15 /data/tombstones/{line} 2>/dev/null "
                    f"| grep -E '(pid:|signal|>>> .+ <<<)' | head -3"
                )
                tomb_detail = (tomb_head.stdout if hasattr(tomb_head, "stdout")
                               else str(tomb_head)).strip()
                detail = f"/data/tombstones/{line}"
                if tomb_detail:
                    detail += f" | {' '.join(tomb_detail.splitlines())}"
                crashes.append({"type": "Tombstone", "detail": detail})

            # Kernel panics — filter out common false positives
            dmesg = adb.shell(
                "dmesg | grep -iE '(kernel panic|Oops:|BUG:|Unable to handle)' "
                "| grep -ivE '(debugfs|debug bus|evtlog|panic_on|flag)' | tail -5"
            )
            dmesg_out = dmesg.stdout if hasattr(dmesg, "stdout") else str(dmesg)
            for line in dmesg_out.splitlines():
                line = line.strip()
                if line:
                    crashes.append({"type": "Kernel", "detail": line})

        except Exception as e:
            logger.warning(f"Crash analysis failed: {e}")

        analysis = {
            "bugreport_path": str(zip_path) if zip_path else None,
            "total_crashes": len(crashes),
            "crashes": crashes[:20],  # Limit to 20 most recent
        }

        if crashes:
            logger.warning(f"Found {len(crashes)} crash(es) during test execution!")
            for c in crashes[:5]:
                logger.warning(f"  [{c['type']}] {c['detail'][:100]}")
        else:
            logger.info("No crashes detected during test execution")

        return analysis

    def _preflight_check(self, adb, suite_config: dict | None, usb_power) -> list[dict]:
        """Run preflight checks before test execution. Returns list of check results."""
        logger.info("=== Preflight Check ===")
        checks = []

        # 1. ADB connected (CRITICAL)
        connected = adb.is_connected()
        checks.append({
            "name": "ADB Connection",
            "level": "CRITICAL" if not connected else "OK",
            "message": f"Connected ({adb.serial})" if connected else "Device not connected",
        })
        if not connected:
            self._log_preflight(checks)
            return checks

        # 2. Boot completed (CRITICAL)
        boot = adb.shell("getprop sys.boot_completed")
        boot_val = (boot.stdout if hasattr(boot, "stdout") else str(boot)).strip()
        checks.append({
            "name": "Device Boot",
            "level": "CRITICAL" if boot_val != "1" else "OK",
            "message": "Boot completed" if boot_val == "1" else f"boot_completed={boot_val}",
        })

        # 3. WiFi (WARNING)
        wifi_ok = adb.is_wifi_connected()
        checks.append({
            "name": "WiFi",
            "level": "OK" if wifi_ok else "WARNING",
            "message": "Connected" if wifi_ok else "Not connected — network tests will fail",
        })

        # 4. LLM API (WARNING) — count how many tests need it
        llm_tests = 0
        if suite_config:
            for tc in suite_config.get("test_suite", {}).get("tests", []):
                if tc.get("type") in ("screenshot_llm",) or tc.get("action") in ("capture_and_verify", "verify_latest_photo"):
                    llm_tests += 1

        if llm_tests > 0:
            llm_ok = False
            llm_err = ""
            try:
                llm = self._get_llm_client()
                if llm:
                    # Actually test the API with a minimal request
                    import httpx
                    resp = httpx.post(
                        f"{llm.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {llm.api_key}"},
                        json={"model": llm.model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
                        timeout=10,
                    )
                    llm_ok = resp.status_code == 200
                    if not llm_ok:
                        llm_err = f"{resp.status_code} {resp.reason_phrase}"
            except Exception as e:
                llm_err = str(e)[:60]
            msg = "Available" if llm_ok else f"Not available ({llm_err}) — {llm_tests} test(s) will ERROR"
            checks.append({
                "name": "LLM API",
                "level": "OK" if llm_ok else "WARNING",
                "message": msg,
                "affected": llm_tests,
            })

        # 5. SIM card (WARNING) — count telephony tests
        sim_tests = 0
        if suite_config:
            for tc in suite_config.get("test_suite", {}).get("tests", []):
                req = tc.get("requires", {})
                if req.get("device_capability") == "has_sim":
                    sim_tests += 1

        if sim_tests > 0:
            has_sim = self.device_config.get("has_sim", False)
            if not has_sim:
                # Double check via ADB
                sim_result = adb.shell("dumpsys telephony.registry | grep mServiceState")
                sim_out = (sim_result.stdout if hasattr(sim_result, "stdout") else str(sim_result)).strip()
                has_sim = "OUT_OF_SERVICE" not in sim_out and sim_out != ""
            checks.append({
                "name": "SIM Card",
                "level": "OK" if has_sim else "WARNING",
                "message": "Detected" if has_sim else f"Not detected — {sim_tests} test(s) will SKIP",
                "affected": sim_tests,
            })

        # 6. USB Power (INFO)
        usb_tests = 0
        if suite_config:
            for tc in suite_config.get("test_suite", {}).get("tests", []):
                req = tc.get("requires", {})
                if req.get("device_capability") == "usb_power":
                    usb_tests += 1

        if usb_tests > 0:
            usb_ok = False
            usb_msg = f"Not configured — {usb_tests} test(s) will SKIP"
            if usb_power:
                try:
                    ctrl = usb_power._ensure_connected()
                    info = ctrl.get_device_info()
                    serial = info.get("serial", "unknown")
                    usb_ok = True
                    usb_msg = f"Serial hub {serial} port {usb_power.port} — connected"
                except Exception as e:
                    usb_msg = f"Serial hub connection failed: {str(e)[:40]}"
            checks.append({
                "name": "USB Power Control",
                "level": "OK" if usb_ok else ("WARNING" if usb_power else "INFO"),
                "message": usb_msg,
                "affected": usb_tests,
            })

        # 7. Mobly Snippet APK (WARNING)
        snippet_result = adb.shell("pm list packages com.google.android.mobly.snippet.bundled")
        snippet_out = (snippet_result.stdout if hasattr(snippet_result, "stdout") else str(snippet_result)).strip()
        snippet_installed = "com.google.android.mobly.snippet.bundled" in snippet_out
        checks.append({
            "name": "Mobly Snippet APK",
            "level": "OK" if snippet_installed else "WARNING",
            "message": "Installed" if snippet_installed else "Not installed — plugin tests may fail",
        })

        self._log_preflight(checks)
        return checks

    @staticmethod
    def _log_preflight(checks: list[dict]) -> None:
        """Log preflight results with visual formatting."""
        icons = {"CRITICAL": "✗", "WARNING": "!", "INFO": "~", "OK": "✓"}
        for c in checks:
            icon = icons.get(c["level"], "?")
            logger.info(f"  [{icon}] {c['level']:8s} {c['name']} — {c['message']}")

        warnings = sum(1 for c in checks if c["level"] == "WARNING")
        criticals = sum(1 for c in checks if c["level"] == "CRITICAL")
        if criticals:
            logger.error(f"Preflight: {criticals} CRITICAL failure(s) — aborting")
        elif warnings:
            logger.warning(f"Preflight: {warnings} warning(s) — proceeding with known limitations")
        else:
            logger.info("Preflight: all checks passed")

    def _generate_reports(self, results: list[TestResult], device_info: dict | None = None, suite_config: dict | None = None) -> None:
        report_cfg = self.settings.get("reporting", {})
        formats = report_cfg.get("formats", ["cli"])
        output_dir = Path(report_cfg.get("output_dir", "results/"))

        if "cli" in formats:
            CliReporter().print_results(results, "Smoke Test", self.device_name, device_info)

        if "json" in formats:
            json_path = output_dir / f"{self.device_name}_results.json"
            JsonReporter().generate(results, "Smoke Test", self.device_name, json_path, device_info)
            logger.info(f"JSON report: file://{json_path.resolve()}")

        if "html" in formats:
            # Build category map and test config map from suite config
            category_map = {}
            test_config_map = {}
            if suite_config:
                for tc in suite_config.get("test_suite", {}).get("tests", []):
                    category_map[tc["id"]] = tc.get("category", "Other")
                    test_config_map[tc["id"]] = tc

            html_path = output_dir / f"{self.device_name}_report.html"
            HtmlReporter().generate(results, "Smoke Test", self.device_name, html_path, device_info, category_map, test_config_map)
            logger.info(f"HTML report: file://{html_path.resolve()}")

            if getattr(self, "_suite_config", None):
                plan_path = output_dir / f"{self.device_name}_test_plan.html"
                TestPlanReporter().generate(self._suite_config, plan_path)
                logger.info(f"Test plan: file://{plan_path.resolve()}")
