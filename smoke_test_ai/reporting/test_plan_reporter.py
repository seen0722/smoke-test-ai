from collections import Counter
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


class TestPlanReporter:
    def __init__(self, template_dir: Path | None = None):
        if template_dir is None:
            template_dir = Path(__file__).parent.parent.parent / "templates"
        self.env = Environment(loader=FileSystemLoader(str(template_dir)))

    def generate(self, suite_config: dict, output_path: Path) -> None:
        suite = suite_config["test_suite"]
        tests_raw = suite.get("tests", [])

        tests = []
        for tc in tests_raw:
            tests.append({
                "id": tc["id"],
                "name": tc["name"],
                "type": tc["type"],
                "command": tc.get("command") or tc.get("prompt", ""),
                "pass_criteria_display": self._build_pass_criteria(tc),
                "depends_on": tc.get("depends_on"),
                "requires": tc.get("requires", {}).get("device_capability"),
                "retry": tc.get("retry"),
                "retry_delay": tc.get("retry_delay"),
            })

        type_counts = dict(Counter(t["type"] for t in tests))

        template = self.env.get_template("test_plan.html")
        html = template.render(
            suite_name=suite.get("name", "Unknown"),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total=len(tests),
            type_counts=type_counts,
            tests=tests,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html)

    @staticmethod
    def _build_pass_criteria(tc: dict) -> str:
        t = tc["type"]

        if t == "adb_check":
            return f"Output equals \"{tc.get('expected', '')}\""

        if t == "adb_shell":
            parts = []
            if "expected_contains" in tc:
                parts.append(f"Output contains \"{tc['expected_contains']}\"")
            if "expected_not_contains" in tc:
                parts.append(f"Output does NOT contain \"{tc['expected_not_contains']}\"")
            if "expected_pattern" in tc:
                parts.append(f"Output matches /{tc['expected_pattern']}/")
            return "; ".join(parts) if parts else "Command exits with code 0"

        if t == "screenshot_llm":
            criteria = tc.get("pass_criteria", "")
            prompt = tc.get("prompt", "")
            return f"LLM judges \"{criteria}\" — Prompt: {prompt}" if criteria else f"LLM prompt: {prompt}"

        if t == "apk_instrumentation":
            pkg = tc.get("package", "")
            runner = tc.get("runner", "AndroidJUnitRunner")
            return f"Instrumentation passes ({pkg} / {runner})"

        return "Unknown test type"
