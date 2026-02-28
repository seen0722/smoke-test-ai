import json

import pytest
from pathlib import Path

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.reporting.json_reporter import JsonReporter
from smoke_test_ai.reporting.html_reporter import HtmlReporter


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
