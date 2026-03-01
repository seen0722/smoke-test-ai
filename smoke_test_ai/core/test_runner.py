import re
import time
from dataclasses import dataclass
from enum import Enum
from smoke_test_ai.drivers.adb_controller import AdbController
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)

class TestStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"

@dataclass
class TestResult:
    id: str
    name: str
    status: TestStatus
    message: str = ""
    duration: float = 0.0
    screenshot_path: str | None = None

    @property
    def passed(self) -> bool:
        return self.status == TestStatus.PASS

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "status": self.status.value, "message": self.message, "duration": self.duration, "screenshot_path": self.screenshot_path}

class TestRunner:
    def __init__(self, adb: AdbController, visual_analyzer=None, screen_capture=None, webcam_capture=None, device_capabilities: dict | None = None, plugins: dict | None = None):
        self.adb = adb
        self.visual_analyzer = visual_analyzer
        self.screen_capture = screen_capture
        self.webcam_capture = webcam_capture
        self.device_capabilities = device_capabilities or {}
        self._plugins = plugins or {}

    def run_suite(self, suite_config: dict) -> list[TestResult]:
        suite = suite_config["test_suite"]
        logger.info(f"Running test suite: {suite['name']}")
        results = []
        completed: dict[str, TestStatus] = {}
        for test_case in suite["tests"]:
            # depends_on: skip if dependency failed
            dep = test_case.get("depends_on")
            if dep and completed.get(dep) not in (TestStatus.PASS, None):
                result = TestResult(
                    id=test_case["id"],
                    name=test_case["name"],
                    status=TestStatus.SKIP,
                    message=f"Skipped: dependency '{dep}' did not pass",
                )
            else:
                result = self.run_test(test_case)
            results.append(result)
            completed[test_case["id"]] = result.status
            status_icon = "PASS" if result.passed else result.status.value
            logger.info(f"  [{status_icon}] {result.name}: {result.message}")
        return results

    def run_test(self, test_case: dict) -> TestResult:
        test_id = test_case["id"]
        test_name = test_case["name"]
        test_type = test_case["type"]

        # requires: check device capabilities
        requires = test_case.get("requires", {})
        cap_key = requires.get("device_capability")
        if cap_key and not self.device_capabilities.get(cap_key, False):
            return TestResult(id=test_id, name=test_name, status=TestStatus.SKIP, message=f"Skipped: device lacks '{cap_key}'")

        max_attempts = test_case.get("retry", 1)
        retry_delay = test_case.get("retry_delay", 0)

        start_time = time.time()
        result = None
        for attempt in range(max_attempts):
            try:
                if test_type == "adb_check":
                    result = self._run_adb_check(test_case)
                elif test_type == "adb_shell":
                    result = self._run_adb_shell(test_case)
                elif test_type == "screenshot_llm":
                    result = self._run_screenshot_llm(test_case)
                elif test_type == "apk_instrumentation":
                    result = self._run_apk_instrumentation(test_case)
                elif test_type in self._plugins:
                    from smoke_test_ai.plugins.base import PluginContext
                    ctx = PluginContext(
                        adb=self.adb,
                        settings=getattr(self, '_settings', {}),
                        device_capabilities=self.device_capabilities,
                        snippet=getattr(self, '_snippet', None),
                        peer_snippet=getattr(self, '_peer_snippet', None),
                        visual_analyzer=self.visual_analyzer,
                    )
                    result = self._plugins[test_type].execute(test_case, ctx)
                else:
                    result = TestResult(id=test_id, name=test_name, status=TestStatus.ERROR, message=f"Unknown test type: {test_type}")
            except Exception as e:
                result = TestResult(id=test_id, name=test_name, status=TestStatus.ERROR, message=str(e))

            # Only retry on FAIL (not ERROR or PASS)
            if result.status != TestStatus.FAIL or attempt >= max_attempts - 1:
                break
            logger.info(f"  Retry {attempt + 1}/{max_attempts - 1} for '{test_name}' after {retry_delay}s")
            if retry_delay > 0:
                time.sleep(retry_delay)

        result.duration = time.time() - start_time
        return result

    def _run_adb_check(self, tc: dict) -> TestResult:
        proc = self.adb.shell(tc["command"])
        actual = proc.stdout.strip()
        expected = tc["expected"]
        if actual == expected:
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS)
        return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.FAIL, message=f"Expected '{expected}', got '{actual}'")

    def _run_adb_shell(self, tc: dict) -> TestResult:
        proc = self.adb.shell(tc["command"])
        output = proc.stdout.strip()
        actual_snippet = output[:200]
        if "expected_contains" in tc:
            if tc["expected_contains"] in output:
                return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS)
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.FAIL, message=f"Output does not contain '{tc['expected_contains']}' | actual: {actual_snippet}")
        if "expected_not_contains" in tc:
            if tc["expected_not_contains"] not in output:
                return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS)
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.FAIL, message=f"Output contains '{tc['expected_not_contains']}' | actual: {actual_snippet}")
        if "expected_pattern" in tc:
            if re.search(tc["expected_pattern"], output):
                return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS)
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.FAIL, message=f"Output does not match pattern '{tc['expected_pattern']}' | actual: {actual_snippet}")
        if proc.returncode == 0:
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS)
        return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.FAIL, message=f"Command failed with exit code {proc.returncode} | actual: {actual_snippet}")

    def _run_screenshot_llm(self, tc: dict) -> TestResult:
        if not self.visual_analyzer:
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.SKIP, message="Visual analyzer not configured")

        # Priority: webcam (sees real screen) > adb screencap (framebuffer only)
        image = None
        capture_method = None
        if self.webcam_capture:
            image = self.webcam_capture.capture()
            if image is not None:
                capture_method = "webcam"
                logger.info(f"  Captured via webcam")
        if image is None and self.screen_capture:
            image = self.screen_capture.capture()
            if image is not None:
                capture_method = "adb_screencap"
                logger.info(f"  Captured via ADB screencap (webcam unavailable)")
        if image is None:
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.ERROR, message="Failed to capture screen (no capture source available)")

        result = self.visual_analyzer.analyze_test_screenshot(image, tc["prompt"])
        reason = result.get("reason", "")
        if capture_method:
            reason = f"[{capture_method}] {reason}"
        if result.get("pass", False):
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS, message=reason)
        return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.FAIL, message=reason or "LLM judged as fail")

    def _run_apk_instrumentation(self, tc: dict) -> TestResult:
        package = tc["package"]
        runner = tc.get("runner", "androidx.test.runner.AndroidJUnitRunner")
        timeout = tc.get("timeout", 120)
        proc = self.adb.shell(f"am instrument -w {package}/{runner}", timeout=timeout)
        if "OK (" in proc.stdout:
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS)
        return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.FAIL, message=proc.stdout[:500])
