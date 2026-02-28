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
    def __init__(self, adb: AdbController, visual_analyzer=None, screen_capture=None):
        self.adb = adb
        self.visual_analyzer = visual_analyzer
        self.screen_capture = screen_capture

    def run_suite(self, suite_config: dict) -> list[TestResult]:
        suite = suite_config["test_suite"]
        logger.info(f"Running test suite: {suite['name']}")
        results = []
        for test_case in suite["tests"]:
            result = self.run_test(test_case)
            results.append(result)
            status_icon = "PASS" if result.passed else result.status.value
            logger.info(f"  [{status_icon}] {result.name}: {result.message}")
        return results

    def run_test(self, test_case: dict) -> TestResult:
        test_id = test_case["id"]
        test_name = test_case["name"]
        test_type = test_case["type"]
        start_time = time.time()
        try:
            if test_type == "adb_check":
                result = self._run_adb_check(test_case)
            elif test_type == "adb_shell":
                result = self._run_adb_shell(test_case)
            elif test_type == "screenshot_llm":
                result = self._run_screenshot_llm(test_case)
            elif test_type == "apk_instrumentation":
                result = self._run_apk_instrumentation(test_case)
            else:
                result = TestResult(id=test_id, name=test_name, status=TestStatus.ERROR, message=f"Unknown test type: {test_type}")
        except Exception as e:
            result = TestResult(id=test_id, name=test_name, status=TestStatus.ERROR, message=str(e))
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
        if "expected_contains" in tc:
            if tc["expected_contains"] in output:
                return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS)
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.FAIL, message=f"Output does not contain '{tc['expected_contains']}'")
        if "expected_not_contains" in tc:
            if tc["expected_not_contains"] not in output:
                return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS)
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.FAIL, message=f"Output contains '{tc['expected_not_contains']}'")
        if "expected_pattern" in tc:
            if re.search(tc["expected_pattern"], output):
                return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS)
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.FAIL, message=f"Output does not match pattern '{tc['expected_pattern']}'")
        if proc.returncode == 0:
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS)
        return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.FAIL, message=f"Command failed with exit code {proc.returncode}")

    def _run_screenshot_llm(self, tc: dict) -> TestResult:
        if not self.visual_analyzer or not self.screen_capture:
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.SKIP, message="Visual analyzer or screen capture not configured")
        image = self.screen_capture.capture()
        if image is None:
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.ERROR, message="Failed to capture screen")
        result = self.visual_analyzer.analyze_test_screenshot(image, tc["prompt"])
        if result.get("pass", False):
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS, message=result.get("reason", ""))
        return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.FAIL, message=result.get("reason", "LLM judged as fail"))

    def _run_apk_instrumentation(self, tc: dict) -> TestResult:
        package = tc["package"]
        runner = tc.get("runner", "androidx.test.runner.AndroidJUnitRunner")
        timeout = tc.get("timeout", 120)
        proc = self.adb.shell(f"am instrument -w {package}/{runner}", timeout=timeout)
        if "OK (" in proc.stdout:
            return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.PASS)
        return TestResult(id=tc["id"], name=tc["name"], status=TestStatus.FAIL, message=proc.stdout[:500])
