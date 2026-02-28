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
        device_info: dict | None = None,
    ) -> None:
        if device_info:
            console.print("\n[bold]Device Information[/]")
            hw_keys = [
                ("model", "Model"),
                ("brand", "Brand"),
                ("manufacturer", "Manufacturer"),
                ("device", "Device"),
                ("hardware", "Hardware"),
                ("board", "Board"),
                ("platform", "Platform"),
                ("cpu_abi", "CPU ABI"),
                ("serial", "Serial"),
            ]
            sw_keys = [
                ("android_version", "Android Version"),
                ("sdk_version", "SDK Level"),
                ("security_patch", "Security Patch"),
                ("build_id", "Build ID"),
                ("build_type", "Build Type"),
                ("build_fingerprint", "Fingerprint"),
                ("kernel_version", "Kernel"),
            ]
            console.print("  [bold cyan]Hardware:[/]")
            for key, label in hw_keys:
                val = device_info.get(key, "")
                if val:
                    console.print(f"    {label}: {val}")
            console.print("  [bold cyan]Software:[/]")
            for key, label in sw_keys:
                val = device_info.get(key, "")
                if val:
                    console.print(f"    {label}: {val}")
            console.print()

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

        passed = sum(1 for r in results if r.status == TestStatus.PASS)
        failed = sum(1 for r in results if r.status == TestStatus.FAIL)
        error = sum(1 for r in results if r.status == TestStatus.ERROR)
        skipped = sum(1 for r in results if r.status == TestStatus.SKIP)
        total = len(results)
        all_ok = failed == 0 and error == 0
        console.print(
            f"\n[bold]Summary:[/] {passed} passed, {failed} failed, {error} error, {skipped} skipped / {total} total "
            f"({'[green]ALL PASS[/]' if all_ok else '[red]HAS FAILURES[/]'})"
        )
