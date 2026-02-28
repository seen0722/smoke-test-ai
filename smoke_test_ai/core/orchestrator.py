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
from smoke_test_ai.utils.logger import get_logger

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

        wifi_cfg = self.settings.get("wifi", {})
        if wifi_cfg.get("ssid"):
            adb.connect_wifi(wifi_cfg["ssid"], wifi_cfg.get("password", ""))

        # FBE unlock: check if user storage is locked
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

        adb.shell("settings put global stay_on_while_plugged_in 3")
        adb.shell("settings put system screen_off_timeout 1800000")
        adb.shell("input keyevent KEYCODE_WAKEUP")

        # Stage 3: Test Execute
        if suite_config:
            logger.info("=== Stage 3: Test Execute ===")
            screen_capture = self._get_screen_capture(serial=serial)
            llm = self._get_llm_client()
            analyzer = VisualAnalyzer(llm)
            runner = TestRunner(
                adb=adb,
                visual_analyzer=analyzer,
                screen_capture=screen_capture,
            )
            results = runner.run_suite(suite_config)
        else:
            results = []

        # Stage 4: Report
        logger.info("=== Stage 4: Report ===")
        self._generate_reports(results)

        return results

    def _generate_reports(self, results: list[TestResult]) -> None:
        report_cfg = self.settings.get("reporting", {})
        formats = report_cfg.get("formats", ["cli"])
        output_dir = Path(report_cfg.get("output_dir", "results/"))

        if "cli" in formats:
            CliReporter().print_results(results, "Smoke Test", self.device_name)

        if "json" in formats:
            json_path = output_dir / f"{self.device_name}_results.json"
            JsonReporter().generate(results, "Smoke Test", self.device_name, json_path)
            logger.info(f"JSON report: {json_path}")

        if "html" in formats:
            html_path = output_dir / f"{self.device_name}_report.html"
            HtmlReporter().generate(results, "Smoke Test", self.device_name, html_path)
            logger.info(f"HTML report: {html_path}")
