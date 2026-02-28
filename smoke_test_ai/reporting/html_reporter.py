from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from smoke_test_ai.core.test_runner import TestResult


class HtmlReporter:
    def __init__(self, template_dir: Path | None = None):
        if template_dir is None:
            template_dir = Path(__file__).parent.parent.parent / "templates"
        self.env = Environment(loader=FileSystemLoader(str(template_dir)))

    def generate(
        self,
        results: list[TestResult],
        suite_name: str,
        device_name: str,
        output_path: Path,
        device_info: dict | None = None,
    ) -> None:
        passed = sum(1 for r in results if r.passed)
        template = self.env.get_template("report.html")
        html = template.render(
            suite_name=suite_name,
            device_name=device_name,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
            results=[r.to_dict() for r in results],
            device_info=device_info or {},
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html)
