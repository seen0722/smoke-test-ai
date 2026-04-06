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
@click.option("--build-type", type=click.Choice(["user", "userdebug"]), default=None, help="Build type (overrides YAML)")
@click.option("--keep-data", is_flag=True, help="Skip userdata flash (preserve existing data)")
@click.option("--build-info", default=None, type=click.Path(exists=True), help="Build info JSON from CI (expected values)")
@click.option("--config-dir", default="config", help="Config directory path")
def run(device, suite, build, serial, skip_flash, skip_setup, build_type, keep_data, build_info, config_dir):
    """Run full smoke test pipeline."""
    from smoke_test_ai.core.orchestrator import Orchestrator

    config_path = Path(config_dir)
    settings = load_settings(config_path / "settings.yaml")
    device_config = load_device_config(config_path / "devices" / f"{device}.yaml")
    suite_config = load_test_suite(config_path / "test_suites" / f"{suite}.yaml")

    orch = Orchestrator(settings=settings, device_config=device_config)
    # Load build info JSON if provided
    build_info_data = None
    if build_info:
        import json
        build_info_data = json.loads(Path(build_info).read_text())
        console.print(f"[cyan]Build info loaded: {build_info}[/]")

    results = orch.run(
        serial=serial,
        suite_config=suite_config,
        build_dir=build,
        skip_flash=skip_flash,
        skip_setup=skip_setup,
        build_type=build_type,
        keep_data=keep_data,
        build_info=build_info_data,
        config_dir=str(config_path),
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
@click.option("--reset-delay", default=None, type=int, help="Seconds to wait after factory reset before USB power cycle (default: from YAML or 10)")
@click.option("--build-type", type=click.Choice(["user", "userdebug"]), default=None, help="Build type (overrides YAML)")
@click.option("--build-info", default=None, type=click.Path(exists=True), help="Build info JSON from CI (expected values)")
def reset_test(device, suite, serial, config_dir, boot_timeout, reset_delay, build_type, build_info):
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
    console.print("Factory reset initiated.")

    # USB power cycle to avoid offline charging mode
    usb_power_cfg = device_config.get("device", {}).get("usb_power")
    if usb_power_cfg:
        from smoke_test_ai.drivers.usb_power_serial import SerialUsbPowerController
        usb_power = SerialUsbPowerController(
            port=usb_power_cfg["port"],
            off_duration=usb_power_cfg.get("off_duration", 3.0),
            serial_port=usb_power_cfg.get("serial_port"),
            device_serial=usb_power_cfg.get("device_serial"),
        )
        delay = reset_delay or usb_power_cfg.get("reset_delay", 3)
        console.print(f"[cyan]Waiting {delay}s for device shutdown before USB power cycle...[/]")
        import time
        time.sleep(delay)
        console.print("[cyan]USB power cycle to prevent offline charging...[/]")
        usb_power.power_cycle()
    else:
        console.print("\n[bold cyan]>>> Please UNPLUG the USB cable now <<<[/]")
        console.print("Wait for the device to fully boot into the home screen,")
        console.print("then plug the USB cable back in.")
        click.pause("Press any key after USB is reconnected...")

    # Wait for device to come back via ADB
    # For user builds, ADB won't be available until after AOA Stage 1
    effective_build_type = build_type or device_config.get("device", {}).get("build_type", "userdebug")
    if effective_build_type != "user":
        console.print(f"\nWaiting for ADB connection (timeout: {boot_timeout}s)...")
        if not adb.wait_for_device(timeout=boot_timeout):
            console.print("[red]Device not found via ADB[/]")
            raise SystemExit(1)
        console.print("[green]Device connected via ADB[/]\n")
    else:
        console.print("\n[cyan]User build: ADB wait deferred to orchestrator (after AOA)[/]")

    # Load build info JSON if provided
    build_info_data = None
    if build_info:
        import json
        build_info_data = json.loads(Path(build_info).read_text())
        console.print(f"[cyan]Build info loaded: {build_info}[/]")

    # Run full pipeline (skip flash, run setup wizard skip + bootstrap)
    orch = Orchestrator(settings=settings, device_config=device_config)
    results = orch.run(
        serial=serial,
        suite_config=suite_config,
        skip_flash=True,
        skip_setup=False,
        build_type=build_type,
        is_factory_reset=True,
        build_info=build_info_data,
        config_dir=str(config_path),
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


@main.command()
@click.option("--device", required=True, help="Device config name (e.g. product_a)")
@click.option("--serial", default=None, help="Device serial number for ADB screencap")
@click.option("--config-dir", default="config", help="Config directory path")
def record(device, serial, config_dir):
    """Record a setup flow by clicking on ADB screenshots."""
    from smoke_test_ai.runners.recorder import StepRecorder

    config_path = Path(config_dir)
    device_config = load_device_config(config_path / "devices" / f"{device}.yaml")
    device_name = device_config["device"]["name"]

    flow_name = device_name.lower().replace("-", "_").replace(" ", "_")
    output_path = config_path / "setup_flows" / f"{flow_name}.yaml"

    console.print(f"[bold]Recording setup flow for {device_name}[/]")
    console.print(f"Output: {output_path}")

    recorder = StepRecorder(serial=serial, device_name=device_name, output_path=output_path)
    recorder.run()


@main.command()
@click.option("--device", required=True, help="Device config name (e.g. product_a)")
@click.option("--serial", default=None, help="Device serial number")
@click.option("--config-dir", default="config", help="Config directory path")
def replay(device, serial, config_dir):
    """Replay a recorded setup flow via ADB (for testing)."""
    import subprocess
    import time
    import yaml

    config_path = Path(config_dir)
    device_config = load_device_config(config_path / "devices" / f"{device}.yaml")
    device_name = device_config["device"]["name"]
    flow_name = device_name.lower().replace("-", "_").replace(" ", "_")
    flow_path = config_path / "setup_flows" / f"{flow_name}.yaml"

    if not flow_path.exists():
        console.print(f"[red]Flow file not found: {flow_path}[/]")
        raise SystemExit(1)

    flow = yaml.safe_load(flow_path.read_text())
    steps = flow.get("steps", [])
    console.print(f"[bold]Replaying {len(steps)} steps for {device_name} via ADB[/]\n")

    def adb_cmd(*args):
        cmd = ["adb"]
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(args)
        subprocess.run(cmd, capture_output=True, timeout=10)

    for i, step in enumerate(steps):
        action = step["action"]
        desc = step.get("description", action)
        delay = step.get("delay", 1.0)
        console.print(f"  [{i+1}/{len(steps)}] {action}: {desc}")

        if action == "tap":
            repeat = step.get("repeat", 1)
            for r in range(repeat):
                adb_cmd("shell", "input", "tap", str(step["x"]), str(step["y"]))
                if repeat > 1 and r < repeat - 1:
                    time.sleep(delay)
        elif action == "swipe":
            dur_ms = int(step.get("duration", 0.3) * 1000)
            adb_cmd("shell", "input", "swipe",
                    str(step["x1"]), str(step["y1"]),
                    str(step["x2"]), str(step["y2"]), str(dur_ms))
        elif action == "type":
            adb_cmd("shell", "input", "text", step["text"])
        elif action == "key":
            key_map = {"enter": "KEYCODE_ENTER", "tab": "KEYCODE_TAB"}
            adb_cmd("shell", "input", "keyevent", key_map.get(step["key"], step["key"]))
        elif action == "wake":
            adb_cmd("shell", "input", "keyevent", "KEYCODE_WAKEUP")
        elif action == "home":
            adb_cmd("shell", "input", "keyevent", "KEYCODE_HOME")
        elif action == "back":
            adb_cmd("shell", "input", "keyevent", "KEYCODE_BACK")
        elif action == "sleep":
            time.sleep(step.get("duration", 1.0))
            continue
        elif action == "wait_for_adb":
            console.print("    [yellow](skipped in ADB replay mode)[/]")
            continue

        time.sleep(delay)

    console.print(f"\n[bold green]Replay complete ({len(steps)} steps)[/]")


if __name__ == "__main__":
    main()
