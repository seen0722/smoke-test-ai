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

    # --- B1: FAIL message contains actual output ---
    def test_fail_message_contains_actual_output(self, runner, mock_adb):
        mock_adb.shell.return_value = MagicMock(returncode=0, stdout="some unexpected output\n", stderr="")
        tc = {"id": "t", "name": "T", "type": "adb_shell", "command": "cmd", "expected_contains": "expected_value"}
        result = runner.run_test(tc)
        assert result.status == TestStatus.FAIL
        assert "actual:" in result.message
        assert "some unexpected output" in result.message

    def test_fail_pattern_message_contains_actual(self, runner, mock_adb):
        mock_adb.shell.return_value = MagicMock(returncode=0, stdout="no match here\n", stderr="")
        tc = {"id": "t", "name": "T", "type": "adb_shell", "command": "cmd", "expected_pattern": "^[0-9]+$"}
        result = runner.run_test(tc)
        assert result.status == TestStatus.FAIL
        assert "actual:" in result.message

    def test_fail_not_contains_message_has_actual(self, runner, mock_adb):
        mock_adb.shell.return_value = MagicMock(returncode=0, stdout="BAD_VALUE present\n", stderr="")
        tc = {"id": "t", "name": "T", "type": "adb_shell", "command": "cmd", "expected_not_contains": "BAD_VALUE"}
        result = runner.run_test(tc)
        assert result.status == TestStatus.FAIL
        assert "actual:" in result.message

    # --- B2: requires / device_capability ---
    def test_requires_capability_skip(self, mock_adb):
        runner = TestRunner(adb=mock_adb, device_capabilities={"has_sim": False})
        tc = {"id": "sim", "name": "SIM", "type": "adb_shell", "command": "cmd",
              "expected_contains": "ok", "requires": {"device_capability": "has_sim"}}
        result = runner.run_test(tc)
        assert result.status == TestStatus.SKIP
        assert "has_sim" in result.message

    def test_requires_capability_pass(self, mock_adb):
        mock_adb.shell.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
        runner = TestRunner(adb=mock_adb, device_capabilities={"has_sim": True})
        tc = {"id": "sim", "name": "SIM", "type": "adb_shell", "command": "cmd",
              "expected_contains": "ok", "requires": {"device_capability": "has_sim"}}
        result = runner.run_test(tc)
        assert result.status == TestStatus.PASS

    def test_requires_missing_capability_skip(self, mock_adb):
        runner = TestRunner(adb=mock_adb, device_capabilities={})
        tc = {"id": "dp", "name": "DP", "type": "adb_shell", "command": "cmd",
              "expected_contains": "ok", "requires": {"device_capability": "has_dp_output"}}
        result = runner.run_test(tc)
        assert result.status == TestStatus.SKIP

    # --- B3: retry ---
    def test_retry_on_fail(self, mock_adb):
        # First call fails, second passes
        mock_adb.shell.side_effect = [
            MagicMock(returncode=0, stdout="bad\n", stderr=""),
            MagicMock(returncode=0, stdout="ok\n", stderr=""),
        ]
        runner = TestRunner(adb=mock_adb)
        tc = {"id": "r", "name": "Retry", "type": "adb_shell", "command": "cmd",
              "expected_contains": "ok", "retry": 2, "retry_delay": 0}
        result = runner.run_test(tc)
        assert result.status == TestStatus.PASS
        assert mock_adb.shell.call_count == 2

    def test_no_retry_on_error(self, mock_adb):
        mock_adb.shell.side_effect = Exception("device offline")
        runner = TestRunner(adb=mock_adb)
        tc = {"id": "r", "name": "Retry", "type": "adb_shell", "command": "cmd",
              "expected_contains": "ok", "retry": 3, "retry_delay": 0}
        result = runner.run_test(tc)
        assert result.status == TestStatus.ERROR
        assert mock_adb.shell.call_count == 1

    def test_retry_exhausted(self, mock_adb):
        mock_adb.shell.return_value = MagicMock(returncode=0, stdout="bad\n", stderr="")
        runner = TestRunner(adb=mock_adb)
        tc = {"id": "r", "name": "Retry", "type": "adb_shell", "command": "cmd",
              "expected_contains": "ok", "retry": 3, "retry_delay": 0}
        result = runner.run_test(tc)
        assert result.status == TestStatus.FAIL
        assert mock_adb.shell.call_count == 3

    # --- B4: depends_on ---
    def test_depends_on_skip(self, mock_adb):
        mock_adb.shell.return_value = MagicMock(returncode=0, stdout="no match\n", stderr="")
        runner = TestRunner(adb=mock_adb)
        suite = {"test_suite": {"name": "Dep", "timeout": 60, "tests": [
            {"id": "wifi", "name": "WiFi", "type": "adb_shell", "command": "cmd", "expected_contains": "CONNECTED"},
            {"id": "internet", "name": "Internet", "type": "adb_shell", "command": "cmd",
             "expected_contains": "ok", "depends_on": "wifi"},
        ]}}
        results = runner.run_suite(suite)
        assert results[0].status == TestStatus.FAIL
        assert results[1].status == TestStatus.SKIP
        assert "dependency" in results[1].message

    def test_depends_on_pass(self, mock_adb):
        mock_adb.shell.return_value = MagicMock(returncode=0, stdout="CONNECTED ok\n", stderr="")
        runner = TestRunner(adb=mock_adb)
        suite = {"test_suite": {"name": "Dep", "timeout": 60, "tests": [
            {"id": "wifi", "name": "WiFi", "type": "adb_shell", "command": "cmd", "expected_contains": "CONNECTED"},
            {"id": "internet", "name": "Internet", "type": "adb_shell", "command": "cmd",
             "expected_contains": "ok", "depends_on": "wifi"},
        ]}}
        results = runner.run_suite(suite)
        assert results[0].status == TestStatus.PASS
        assert results[1].status == TestStatus.PASS
