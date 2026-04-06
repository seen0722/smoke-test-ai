from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from smoke_test_ai.core.test_runner import TestResult, TestStatus


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
        category_map: dict | None = None,
        test_config_map: dict | None = None,
    ) -> None:
        passed = sum(1 for r in results if r.status == TestStatus.PASS)
        failed = sum(1 for r in results if r.status == TestStatus.FAIL)
        error = sum(1 for r in results if r.status == TestStatus.ERROR)
        skipped = sum(1 for r in results if r.status == TestStatus.SKIP)
        total_duration = sum(r.duration for r in results)

        # Build category summary and grouped results
        category_map = category_map or {}
        test_config_map = test_config_map or {}
        categories = self._build_category_summary(results, category_map, test_config_map)

        template = self.env.get_template("report.html")
        html = template.render(
            suite_name=suite_name,
            device_name=device_name,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total=len(results),
            passed=passed,
            failed=failed,
            error=error,
            skipped=skipped,
            results=[r.to_dict() for r in results],
            device_info=device_info or {},
            categories=categories,
            has_categories=bool(category_map),
            total_duration=total_duration,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html)

    @staticmethod
    def _build_procedure(tc: dict) -> str:
        """Extract human-readable procedure from test config."""
        test_type = tc.get("type", "")
        if test_type in ("adb_check", "adb_shell"):
            return tc.get("command", "")
        if test_type == "screenshot_llm":
            return f"Screenshot + LLM: {tc.get('prompt', '')}"
        # Plugin types
        action = tc.get("action", "")
        params = tc.get("params", {})
        if action:
            parts = [f"{test_type}.{action}"]
            for k, v in params.items():
                parts.append(f"{k}={v}")
            return " | ".join(parts)
        return test_type

    @staticmethod
    def _build_criteria(tc: dict) -> str:
        """Extract human-readable pass criteria from test config."""
        if tc.get("expected"):
            return f"== \"{tc['expected']}\""
        if tc.get("expected_pattern"):
            return f"match /{tc['expected_pattern']}/"
        if tc.get("expected_contains"):
            return f"contains \"{tc['expected_contains']}\""
        if tc.get("expected_not_contains"):
            return f"not contains \"{tc['expected_not_contains']}\""
        # Plugin: infer from action
        action = tc.get("action", "")
        if action:
            return f"{action} succeeds"
        return ""

    @staticmethod
    def _build_category_summary(
        results: list[TestResult], category_map: dict, test_config_map: dict | None = None
    ) -> list[dict]:
        """Group results by category and compute per-category stats."""
        test_config_map = test_config_map or {}

        seen_order = []
        for r in results:
            cat = category_map.get(r.id, "Other")
            if cat not in seen_order:
                seen_order.append(cat)

        groups: dict[str, list[dict]] = OrderedDict()
        for cat in seen_order:
            groups[cat] = []

        for seq, r in enumerate(results, 1):
            cat = category_map.get(r.id, "Other")
            rd = r.to_dict()
            rd["category"] = cat
            rd["seq"] = seq
            # Enrich with procedure and criteria
            tc = test_config_map.get(r.id, {})
            rd["procedure"] = HtmlReporter._build_procedure(tc) if tc else ""
            rd["criteria"] = HtmlReporter._build_criteria(tc) if tc else ""
            groups[cat].append(rd)

        categories = []
        for cat, items in groups.items():
            total = len(items)
            p = sum(1 for i in items if i["status"] == "PASS")
            f = sum(1 for i in items if i["status"] == "FAIL")
            e = sum(1 for i in items if i["status"] == "ERROR")
            s = sum(1 for i in items if i["status"] == "SKIP")
            status = "PASS" if f == 0 and e == 0 else "FAIL"
            categories.append({
                "name": cat,
                "total": total,
                "passed": p,
                "failed": f,
                "error": e,
                "skipped": s,
                "status": status,
                "tests": items,
            })
        return categories
