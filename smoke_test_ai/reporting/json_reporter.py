import json
from datetime import datetime
from pathlib import Path

from smoke_test_ai.core.test_runner import TestResult, TestStatus


class JsonReporter:
    def generate(
        self,
        results: list[TestResult],
        suite_name: str,
        device_name: str,
        output_path: Path,
        device_info: dict | None = None,
    ) -> None:
        passed = sum(1 for r in results if r.status == TestStatus.PASS)
        failed = sum(1 for r in results if r.status == TestStatus.FAIL)
        error = sum(1 for r in results if r.status == TestStatus.ERROR)
        skipped = sum(1 for r in results if r.status == TestStatus.SKIP)
        data = {
            "suite_name": suite_name,
            "device_name": device_name,
            "timestamp": datetime.now().isoformat(),
            "device_info": device_info or {},
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": failed,
                "error": error,
                "skipped": skipped,
            },
            "tests": [r.to_dict() for r in results],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
