from rich.console import Console
from rich.table import Table

from smoke_test_ai.core.test_runner import TestResult, TestStatus

console = Console()


class CliReporter:
    def print_results(
        self,
        results: list[TestResult],
        suite_name: str,
        device_name: str,
    ) -> None:
        table = Table(title=f"Smoke Test Results: {suite_name} @ {device_name}")
        table.add_column("ID", style="dim")
        table.add_column("Test Name")
        table.add_column("Status")
        table.add_column("Duration", justify="right")
        table.add_column("Message")

        for r in results:
            status_style = {
                TestStatus.PASS: "[bold green]PASS[/]",
                TestStatus.FAIL: "[bold red]FAIL[/]",
                TestStatus.SKIP: "[bold yellow]SKIP[/]",
                TestStatus.ERROR: "[bold red]ERROR[/]",
            }.get(r.status, r.status.value)
            table.add_row(
                r.id, r.name, status_style, f"{r.duration:.2f}s", r.message
            )

        console.print(table)

        passed = sum(1 for r in results if r.passed)
        total = len(results)
        console.print(
            f"\n[bold]Summary:[/] {passed}/{total} passed "
            f"({'[green]ALL PASS[/]' if passed == total else '[red]HAS FAILURES[/]'})"
        )
