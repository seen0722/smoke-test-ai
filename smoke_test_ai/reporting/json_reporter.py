import json
from datetime import datetime
from pathlib import Path

from smoke_test_ai.core.test_runner import TestResult


class JsonReporter:
    def generate(
        self,
        results: list[TestResult],
        suite_name: str,
        device_name: str,
        output_path: Path,
    ) -> None:
        passed = sum(1 for r in results if r.passed)
        data = {
            "suite_name": suite_name,
            "device_name": device_name,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": len(results) - passed,
            },
            "tests": [r.to_dict() for r in results],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
