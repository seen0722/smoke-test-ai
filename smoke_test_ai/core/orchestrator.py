import re
import time
from pathlib import Path
from smoke_test_ai.drivers.adb_controller import AdbController
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

logger = get_logger(__name__)


class Orchestrator:
    def __init__(self, settings: dict, device_config: dict):
        self.settings = settings
        self.device_config = device_config["device"]
        self.device_name = self.device_config["name"]

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

    def _pre_test_setup(self, adb: AdbController, suite_config: dict | None) -> None:
        """Install required APKs and clean previous test run data."""
        logger.info("Pre-test setup: install & clean")

        # 1. Auto-install Mobly Bundled Snippets APK if snippet tests exist
        if suite_config and self._has_snippet_tests(suite_config):
            snippet_pkg = "com.google.android.mobly.snippet.bundled"
            check = adb.shell(f"pm list packages {snippet_pkg}")
            installed = snippet_pkg in (check.stdout if hasattr(check, "stdout") else str(check))
            if not installed:
                # Look for the APK in common locations
                apk_candidates = [
                    Path("apks/mobly-bundled-snippets.apk"),
                    Path("apks/mobly-snippets.apk"),
                    Path(__file__).parent.parent.parent / "apks" / "mobly-bundled-snippets.apk",
                ]
                apk_path = None
                for candidate in apk_candidates:
                    if candidate.exists():
                        apk_path = candidate
                        break
                if apk_path:
                    logger.info(f"Installing Mobly Snippet APK: {apk_path}")
                    adb.install(str(apk_path))
                else:
                    logger.warning(
                        f"Mobly Snippet APK not found (searched: {[str(c) for c in apk_candidates]}). "
                        "Install manually: adb install mobly-bundled-snippets.apk"
                    )
            else:
                logger.info("Mobly Snippet APK already installed")

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
        }

        return plugins, snippet, peer_snippet

    def run(
        self,
        serial: str | None = None,
        suite_config: dict | None = None,
        build_dir: str | None = None,
        skip_flash: bool = False,
        skip_setup: bool = False,
    ) -> list[TestResult]:
        adb = AdbController(serial=serial)

        # Stage 0: Flash
        if not skip_flash and build_dir:
            logger.info("=== Stage 0: Flash Image ===")
            flash_driver = self._get_flash_driver(serial=serial)
            flash_config = self.device_config["flash"]
            flash_driver.flash(flash_config)
            logger.info("Flash complete. Waiting for device boot...")
            time.sleep(10)

        # Stage 1: Pre-ADB Setup
        if not skip_setup and self.device_config.get("build_type") == "user":
            logger.info("=== Stage 1: Pre-ADB Setup (Setup Wizard) ===")
            logger.info("Setup Wizard automation would use AOA2 HID + LLM Vision")
            logger.info("Skipping actual AOA2 in this run — waiting for ADB...")

        # Stage 2: ADB Bootstrap
        logger.info("=== Stage 2: ADB Bootstrap ===")
        if not adb.wait_for_device(timeout=120):
            logger.error("Device not found via ADB")
            return []

        # Skip Setup Wizard (userdebug: use ADB settings)
        if not skip_setup:
            adb.skip_setup_wizard()

        # FBE unlock first: must unlock before WiFi and other services work
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

        # WiFi connection
        wifi_cfg = self.settings.get("wifi", {})
        if wifi_cfg.get("ssid"):
            if adb.is_wifi_connected():
                logger.info("WiFi already connected, skipping")
            else:
                adb.connect_wifi(
                    wifi_cfg["ssid"],
                    wifi_cfg.get("password", ""),
                    security=wifi_cfg.get("security", "wpa2"),
                )

        adb.shell("settings put global stay_on_while_plugged_in 3")
        adb.shell("settings put system screen_off_timeout 1800000")
        adb.shell("input keyevent KEYCODE_WAKEUP")

        # Pre-test setup: install Mobly Snippet APK and clean previous test data
        self._pre_test_setup(adb, suite_config)

        # Collect device info for reports
        device_info = adb.get_device_info()

        # Resolve ${VAR} placeholders before test execution
        if suite_config:
            suite_config = self._resolve_variables(suite_config)

        # Store suite_config for report generation
        self._suite_config = suite_config

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

            results = runner.run_suite(suite_config)
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
        self._generate_reports(results, device_info=device_info)

        return results

    def _generate_reports(self, results: list[TestResult], device_info: dict | None = None) -> None:
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
            html_path = output_dir / f"{self.device_name}_report.html"
            HtmlReporter().generate(results, "Smoke Test", self.device_name, html_path, device_info)
            logger.info(f"HTML report: file://{html_path.resolve()}")

            if getattr(self, "_suite_config", None):
                plan_path = output_dir / f"{self.device_name}_test_plan.html"
                TestPlanReporter().generate(self._suite_config, plan_path)
                logger.info(f"Test plan: file://{plan_path.resolve()}")
