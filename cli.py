import click
from pathlib import Path
from rich.console import Console
from smoke_test_ai.utils.config import load_settings, load_device_config, load_test_suite

console = Console()


@click.group()
def main():
    """smoke-test-ai: Android OS smoke test automation"""
    pass


@main.command()
@click.option("--device", required=True, help="Device config name (e.g. product_a)")
@click.option("--suite", required=True, help="Test suite name (e.g. smoke_basic)")
@click.option("--build", default=None, help="Build directory with images")
@click.option("--serial", default=None, help="Device serial number")
@click.option("--skip-flash", is_flag=True, help="Skip flashing stage")
@click.option("--skip-setup", is_flag=True, help="Skip Setup Wizard stage")
@click.option("--config-dir", default="config", help="Config directory path")
def run(device, suite, build, serial, skip_flash, skip_setup, config_dir):
    """Run full smoke test pipeline."""
    from smoke_test_ai.core.orchestrator import Orchestrator

    config_path = Path(config_dir)
    settings = load_settings(config_path / "settings.yaml")
    device_config = load_device_config(config_path / "devices" / f"{device}.yaml")
    suite_config = load_test_suite(config_path / "test_suites" / f"{suite}.yaml")

    orch = Orchestrator(settings=settings, device_config=device_config)
    results = orch.run(
        serial=serial,
        suite_config=suite_config,
        build_dir=build,
        skip_flash=skip_flash,
        skip_setup=skip_setup,
    )

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    if passed == total and total > 0:
        console.print(f"\n[bold green]ALL {total} TESTS PASSED[/]")
    else:
        console.print(f"\n[bold red]{total - passed}/{total} TESTS FAILED[/]")
        raise SystemExit(1)


@main.command()
@click.option("--suite", required=True, help="Test suite name")
@click.option("--serial", default=None, help="Device serial number")
@click.option("--config-dir", default="config", help="Config directory path")
def test(suite, serial, config_dir):
    """Run tests only (assumes ADB is available)."""
    from smoke_test_ai.core.orchestrator import Orchestrator

    config_path = Path(config_dir)
    settings = load_settings(config_path / "settings.yaml")
    device_config = {"device": {"name": "direct", "screen_capture": {"method": "adb"}}}
    suite_config = load_test_suite(config_path / "test_suites" / f"{suite}.yaml")

    orch = Orchestrator(settings=settings, device_config=device_config)
    results = orch.run(
        serial=serial,
        suite_config=suite_config,
        skip_flash=True,
        skip_setup=True,
    )

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    raise SystemExit(0 if passed == total and total > 0 else 1)


@main.command("reset-test")
@click.option("--device", default=None, help="Device config name (e.g. product_a)")
@click.option("--suite", required=True, help="Test suite name")
@click.option("--serial", required=True, help="Device serial number")
@click.option("--config-dir", default="config", help="Config directory path")
@click.option("--boot-timeout", default=180, help="Max seconds to wait for boot after reset")
def reset_test(device, suite, serial, config_dir, boot_timeout):
    """Factory reset → bootstrap → full smoke test."""
    from smoke_test_ai.core.orchestrator import Orchestrator
    from smoke_test_ai.drivers.adb_controller import AdbController

    config_path = Path(config_dir)
    settings = load_settings(config_path / "settings.yaml")
    if device:
        device_config = load_device_config(config_path / "devices" / f"{device}.yaml")
    else:
        device_config = {"device": {"name": "direct", "screen_capture": {"method": "adb"}}}
    suite_config = load_test_suite(config_path / "test_suites" / f"{suite}.yaml")

    adb = AdbController(serial=serial)

    # Stage 0: Factory Reset
    console.print("\n[bold yellow]=== Factory Reset ===[/]")
    if not adb.is_connected():
        console.print("[red]Device not connected. Cannot factory reset.[/]")
        raise SystemExit(1)
    adb.factory_reset()
    console.print("Factory reset initiated. Waiting for reboot...")

    # Wait for device to disconnect (reset in progress)
    import time
    time.sleep(10)

    # Wait for device to come back and boot
    console.print(f"Waiting for device to boot (timeout: {boot_timeout}s)...")
    if not adb.wait_for_boot(timeout=boot_timeout):
        console.print("[red]Device did not boot after factory reset[/]")
        raise SystemExit(1)
    console.print("[green]Device booted successfully after factory reset[/]\n")

    # Run full pipeline (skip flash, skip setup wizard for userdebug)
    orch = Orchestrator(settings=settings, device_config=device_config)
    results = orch.run(
        serial=serial,
        suite_config=suite_config,
        skip_flash=True,
        skip_setup=True,
    )

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    if passed == total and total > 0:
        console.print(f"\n[bold green]ALL {total} TESTS PASSED[/]")
    else:
        console.print(f"\n[bold red]{total - passed}/{total} TESTS FAILED[/]")
    raise SystemExit(0 if passed == total and total > 0 else 1)


@main.group()
def devices():
    """Manage device configurations."""
    pass


@devices.command("list")
@click.option("--config-dir", default="config", help="Config directory path")
def devices_list(config_dir):
    """List available device configs."""
    config_path = Path(config_dir) / "devices"
    if not config_path.exists():
        console.print("[yellow]No device configs found[/]")
        return
    for f in sorted(config_path.glob("*.yaml")):
        config = load_device_config(f)
        name = config.get("device", {}).get("name", f.stem)
        build_type = config.get("device", {}).get("build_type", "unknown")
        console.print(f"  {f.stem}: {name} ({build_type})")


@main.group()
def suites():
    """Manage test suites."""
    pass


@suites.command("list")
@click.option("--config-dir", default="config", help="Config directory path")
def suites_list(config_dir):
    """List available test suites."""
    config_path = Path(config_dir) / "test_suites"
    if not config_path.exists():
        console.print("[yellow]No test suites found[/]")
        return
    for f in sorted(config_path.glob("*.yaml")):
        config = load_test_suite(f)
        name = config.get("test_suite", {}).get("name", f.stem)
        count = len(config.get("test_suite", {}).get("tests", []))
        console.print(f"  {f.stem}: {name} ({count} tests)")


if __name__ == "__main__":
    main()
