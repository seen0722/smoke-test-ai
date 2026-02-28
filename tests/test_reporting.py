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
            id="t3", name="SIM check", status=TestStatus.PASS, duration=0.3
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
        assert len(data["tests"]) == 3
        assert data["summary"]["total"] == 3
        assert data["summary"]["passed"] == 2
        assert data["summary"]["failed"] == 1


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
