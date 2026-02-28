import json

import pytest
from pathlib import Path

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.reporting.json_reporter import JsonReporter
from smoke_test_ai.reporting.html_reporter import HtmlReporter
from smoke_test_ai.reporting.test_plan_reporter import TestPlanReporter


@pytest.fixture
def sample_results():
    return [
        TestResult(
            id="t1", name="Boot check", status=TestStatus.PASS, duration=0.5
        ),
        TestResult(
            id="t2",
            name="WiFi check",
            status=TestStatus.FAIL,
            message="Not connected",
            duration=1.2,
        ),
        TestResult(
            id="t3", name="SIM check", status=TestStatus.SKIP, message="No SIM", duration=0.0
        ),
        TestResult(
            id="t4", name="Crash test", status=TestStatus.ERROR, message="device offline", duration=0.1
        ),
    ]


class TestJsonReporter:
    def test_generate(self, sample_results, tmp_path):
        output = tmp_path / "results.json"
        reporter = JsonReporter()
        reporter.generate(
            results=sample_results,
            suite_name="Basic Smoke",
            device_name="Product-A",
            output_path=output,
        )
        assert output.exists()
        data = json.loads(output.read_text())
        assert data["suite_name"] == "Basic Smoke"
        assert data["device_name"] == "Product-A"
        assert len(data["tests"]) == 4
        assert data["summary"]["total"] == 4
        assert data["summary"]["passed"] == 1
        assert data["summary"]["failed"] == 1
        assert data["summary"]["error"] == 1
        assert data["summary"]["skipped"] == 1


class TestHtmlReporter:
    def test_generate(self, sample_results, tmp_path):
        output = tmp_path / "report.html"
        reporter = HtmlReporter(
            template_dir=Path(__file__).parent.parent / "templates"
        )
        reporter.generate(
            results=sample_results,
            suite_name="Basic Smoke",
            device_name="Product-A",
            output_path=output,
        )
        assert output.exists()
        html = output.read_text()
        assert "Basic Smoke" in html
        assert "Product-A" in html
        assert "PASS" in html
        assert "FAIL" in html
        assert "SKIP" in html
        assert "ERROR" in html
        assert "Skipped" in html  # summary card label
        assert "Error" in html    # summary card label


@pytest.fixture
def sample_suite_config():
    return {
        "test_suite": {
            "name": "Basic Smoke Test",
            "timeout": 600,
            "tests": [
                {
                    "id": "boot_complete",
                    "name": "Boot check",
                    "type": "adb_check",
                    "command": "getprop sys.boot_completed",
                    "expected": "1",
                },
                {
                    "id": "wifi_connected",
                    "name": "WiFi check",
                    "type": "adb_shell",
                    "command": "cmd wifi status",
                    "expected_contains": "Wifi is connected",
                },
                {
                    "id": "internet_access",
                    "name": "Internet check",
                    "type": "adb_shell",
                    "command": "ping -c 3 8.8.8.8",
                    "expected_pattern": "[1-3] received",
                    "depends_on": "wifi_connected",
                    "retry": 2,
                    "retry_delay": 3,
                },
                {
                    "id": "display_normal",
                    "name": "Display check",
                    "type": "screenshot_llm",
                    "prompt": "Is screen normal?",
                    "pass_criteria": "normal",
                },
                {
                    "id": "sim_status",
                    "name": "SIM check",
                    "type": "adb_shell",
                    "command": "dumpsys telephony",
                    "expected_not_contains": "OUT_OF_SERVICE",
                    "requires": {"device_capability": "has_sim"},
                },
            ],
        }
    }


class TestTestPlanReporter:
    def test_generate(self, sample_suite_config, tmp_path):
        output = tmp_path / "test_plan.html"
        reporter = TestPlanReporter(
            template_dir=Path(__file__).parent.parent / "templates"
        )
        reporter.generate(suite_config=sample_suite_config, output_path=output)

        assert output.exists()
        html = output.read_text()
        assert "Basic Smoke Test" in html
        assert "boot_complete" in html
        assert "wifi_connected" in html
        assert "internet_access" in html
        assert "display_normal" in html
        assert "sim_status" in html

    def test_pass_criteria_adb_check(self, sample_suite_config, tmp_path):
        output = tmp_path / "plan.html"
        reporter = TestPlanReporter(
            template_dir=Path(__file__).parent.parent / "templates"
        )
        reporter.generate(suite_config=sample_suite_config, output_path=output)
        html = output.read_text()
        assert 'Output equals "1"' in html

    def test_pass_criteria_adb_shell_contains(self, sample_suite_config, tmp_path):
        output = tmp_path / "plan.html"
        reporter = TestPlanReporter(
            template_dir=Path(__file__).parent.parent / "templates"
        )
        reporter.generate(suite_config=sample_suite_config, output_path=output)
        html = output.read_text()
        assert 'Output contains "Wifi is connected"' in html

    def test_pass_criteria_adb_shell_pattern(self, sample_suite_config, tmp_path):
        output = tmp_path / "plan.html"
        reporter = TestPlanReporter(
            template_dir=Path(__file__).parent.parent / "templates"
        )
        reporter.generate(suite_config=sample_suite_config, output_path=output)
        html = output.read_text()
        assert "Output matches /[1-3] received/" in html

    def test_pass_criteria_not_contains(self, sample_suite_config, tmp_path):
        output = tmp_path / "plan.html"
        reporter = TestPlanReporter(
            template_dir=Path(__file__).parent.parent / "templates"
        )
        reporter.generate(suite_config=sample_suite_config, output_path=output)
        html = output.read_text()
        assert 'Output does NOT contain "OUT_OF_SERVICE"' in html

    def test_pass_criteria_screenshot_llm(self, sample_suite_config, tmp_path):
        output = tmp_path / "plan.html"
        reporter = TestPlanReporter(
            template_dir=Path(__file__).parent.parent / "templates"
        )
        reporter.generate(suite_config=sample_suite_config, output_path=output)
        html = output.read_text()
        assert 'LLM judges "normal"' in html

    def test_conditions_displayed(self, sample_suite_config, tmp_path):
        output = tmp_path / "plan.html"
        reporter = TestPlanReporter(
            template_dir=Path(__file__).parent.parent / "templates"
        )
        reporter.generate(suite_config=sample_suite_config, output_path=output)
        html = output.read_text()
        assert "depends_on:" in html
        assert "requires:" in html
        assert "has_sim" in html
        assert "retry: 2" in html
        assert "delay 3s" in html

    def test_type_counts(self, sample_suite_config, tmp_path):
        output = tmp_path / "plan.html"
        reporter = TestPlanReporter(
            template_dir=Path(__file__).parent.parent / "templates"
        )
        reporter.generate(suite_config=sample_suite_config, output_path=output)
        html = output.read_text()
        assert "adb_check" in html
        assert "adb_shell" in html
        assert "screenshot_llm" in html

    def test_creates_parent_directories(self, sample_suite_config, tmp_path):
        output = tmp_path / "sub" / "dir" / "plan.html"
        reporter = TestPlanReporter(
            template_dir=Path(__file__).parent.parent / "templates"
        )
        reporter.generate(suite_config=sample_suite_config, output_path=output)
        assert output.exists()
