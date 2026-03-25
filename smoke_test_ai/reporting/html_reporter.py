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
    ) -> None:
        passed = sum(1 for r in results if r.status == TestStatus.PASS)
        failed = sum(1 for r in results if r.status == TestStatus.FAIL)
        error = sum(1 for r in results if r.status == TestStatus.ERROR)
        skipped = sum(1 for r in results if r.status == TestStatus.SKIP)

        # Build category summary and grouped results
        category_map = category_map or {}
        categories = self._build_category_summary(results, category_map)

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
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html)

    @staticmethod
    def _build_category_summary(
        results: list[TestResult], category_map: dict
    ) -> list[dict]:
        """Group results by category and compute per-category stats."""
        # Preserve insertion order from category_map
        seen_order = []
        for r in results:
            cat = category_map.get(r.id, "Other")
            if cat not in seen_order:
                seen_order.append(cat)

        groups: dict[str, list[dict]] = OrderedDict()
        for cat in seen_order:
            groups[cat] = []

        for r in results:
            cat = category_map.get(r.id, "Other")
            rd = r.to_dict()
            rd["category"] = cat
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
