import pytest
from unittest.mock import MagicMock
from smoke_test_ai.core.test_runner import TestRunner, TestResult, TestStatus

@pytest.fixture
def mock_adb():
    adb = MagicMock()
    adb.serial = "FAKE"
    return adb

@pytest.fixture
def runner(mock_adb):
    return TestRunner(adb=mock_adb)

class TestTestResult:
    def test_pass_result(self):
        r = TestResult(id="t1", name="Test1", status=TestStatus.PASS)
        assert r.passed

    def test_fail_result(self):
        r = TestResult(id="t1", name="Test1", status=TestStatus.FAIL, message="oops")
        assert not r.passed
        assert r.message == "oops"

class TestTestRunner:
    def test_run_adb_check_pass(self, runner, mock_adb):
        mock_adb.shell.return_value = MagicMock(returncode=0, stdout="1\n", stderr="")
        test_case = {"id": "boot", "name": "Boot check", "type": "adb_check", "command": "getprop sys.boot_completed", "expected": "1"}
        result = runner.run_test(test_case)
        assert result.status == TestStatus.PASS

    def test_run_adb_check_fail(self, runner, mock_adb):
        mock_adb.shell.return_value = MagicMock(returncode=0, stdout="0\n", stderr="")
        test_case = {"id": "boot", "name": "Boot check", "type": "adb_check", "command": "getprop sys.boot_completed", "expected": "1"}
        result = runner.run_test(test_case)
        assert result.status == TestStatus.FAIL

    def test_run_adb_shell_expected_contains(self, runner, mock_adb):
        mock_adb.shell.return_value = MagicMock(returncode=0, stdout="Wi-Fi is enabled\n", stderr="")
        test_case = {"id": "wifi", "name": "WiFi check", "type": "adb_shell", "command": "dumpsys wifi", "expected_contains": "enabled"}
        result = runner.run_test(test_case)
        assert result.status == TestStatus.PASS

    def test_run_adb_shell_expected_not_contains(self, runner, mock_adb):
        mock_adb.shell.return_value = MagicMock(returncode=0, stdout="STATE_IN_SERVICE\n", stderr="")
        test_case = {"id": "sim", "name": "SIM check", "type": "adb_shell", "command": "dumpsys telephony.registry", "expected_not_contains": "OUT_OF_SERVICE"}
        result = runner.run_test(test_case)
        assert result.status == TestStatus.PASS

    def test_run_suite(self, runner, mock_adb):
        mock_adb.shell.return_value = MagicMock(returncode=0, stdout="1\n", stderr="")
        suite = {"test_suite": {"name": "Basic", "timeout": 60, "tests": [
            {"id": "t1", "name": "Test1", "type": "adb_check", "command": "getprop sys.boot_completed", "expected": "1"},
            {"id": "t2", "name": "Test2", "type": "adb_check", "command": "getprop ro.build.type", "expected": "1"},
        ]}}
        results = runner.run_suite(suite)
        assert len(results) == 2

    def test_unknown_test_type_errors(self, runner):
        test_case = {"id": "bad", "name": "Bad", "type": "nonexistent"}
        result = runner.run_test(test_case)
        assert result.status == TestStatus.ERROR
