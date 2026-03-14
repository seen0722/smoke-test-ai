# Adaptive Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the smoke-test pipeline adapt its behavior based on `build_type` (user/userdebug) and `keep_data` (true/false), correctly handling AOA blind setup, Setup Wizard, and userdata flash filtering across 4 scenarios.

**Architecture:** Add `--build-type` and `--keep-data` CLI flags. Orchestrator computes `need_aoa` and `fresh_state` from these inputs to gate Stage 1 (AOA) and Stage 2 (ADB bootstrap) behavior. Flash driver filters userdata commands when `keep_data=True`. Factory reset via `reset-test` passes `is_factory_reset=True` and defers ADB wait to orchestrator.

**Tech Stack:** Click CLI, orchestrator decision logic, FastbootFlashDriver filtering

---

## Context

Spec: `docs/plans/2026-03-13-adaptive-pipeline-design.md`

Current state:
- `cli.py:23` — `run()` has no `build_type` or `keep_data` params
- `cli.py:84` — `reset_test()` has no `build_type`, does manual `adb.wait_for_device()` before orchestrator
- `orchestrator.py:351-359` — `run()` has no `build_type`, `keep_data`, `is_factory_reset` params
- `orchestrator.py:386` — Stage 1 condition: `self.device_config.get("build_type") == "user"`
- `orchestrator.py:420-421` — Stage 2 setup wizard skip: unconditional when `not skip_setup`
- `orchestrator.py:437-438` — WiFi timeout: `45 if not skip_setup else 15`
- `fastboot.py:50-79` — `_run_script()` has no `keep_data` filtering

Key formulas from spec:
```
need_aoa = user AND NOT keep_data AND (need_flash OR is_factory_reset) AND NOT skip_setup
fresh_state = (need_flash OR is_factory_reset) AND NOT keep_data
```

## Key Files

| File | Action |
|------|--------|
| `smoke_test_ai/drivers/flash/fastboot.py` | Add `keep_data` filtering (script + images mode) |
| `smoke_test_ai/core/orchestrator.py:351-460` | Add params, decision logic, update Stage 0/1/2 |
| `cli.py:15-48` | Add `--build-type`, `--keep-data` to `run` |
| `cli.py:77-151` | Add `--build-type` to `reset-test`, defer ADB wait |
| `tests/test_flash.py` | Add `TestKeepDataFiltering` (5 tests) |
| `tests/test_orchestrator.py` | Add `TestAdaptivePipeline` (7 tests) |

## Existing Reusable Code

- `Orchestrator._resolve_flash_config()` (orchestrator.py:270-284) — deepcopy + `${BUILD_DIR}` substitution
- `FastbootFlashDriver._parse_script()` (fastboot.py:81-104) — returns `[["erase","userdata"], ...]`
- `_make_shell_result()` helper (test_orchestrator.py:43-49)
- `device_config` fixture (test_orchestrator.py:29-40) — already has `build_type: "user"`

---

## Task 1: Flash driver `keep_data` filtering

**Files:**
- Modify: `smoke_test_ai/drivers/flash/fastboot.py:37-44` (images mode), `50-79` (_run_script)
- Test: `tests/test_flash.py`

- [ ] **Step 1: Write failing tests for script mode filtering**

Add to `tests/test_flash.py` before `TestCustomFlashDriver`:

```python
class TestKeepDataFiltering:
    @patch("smoke_test_ai.drivers.flash.fastboot.subprocess.run")
    def test_keep_data_filters_userdata_script(self, mock_run):
        """keep_data=True filters erase/flash userdata from script."""
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        driver = FastbootFlashDriver(serial="FAKE")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bash", delete=False) as f:
            f.write('$fastboot_tool erase userdata\n')
            f.write('$fastboot_tool flash userdata ${image_dir}userdata.img\n')
            f.write('$fastboot_tool flash super ${image_dir}super.img\n')
            f.write('$fastboot_tool set_active a\n')
            script_path = f.name
        try:
            driver.flash({"script": script_path, "keep_data": True})
            assert mock_run.call_count == 2  # super + set_active only
        finally:
            os.unlink(script_path)

    @patch("smoke_test_ai.drivers.flash.fastboot.subprocess.run")
    def test_keep_data_filters_ab_slots(self, mock_run):
        """keep_data=True filters userdata_a and userdata_b slots."""
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        driver = FastbootFlashDriver(serial="FAKE")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bash", delete=False) as f:
            f.write('$fastboot_tool erase userdata_a\n')
            f.write('$fastboot_tool erase userdata_b\n')
            f.write('$fastboot_tool flash boot_a ${image_dir}boot.img\n')
            script_path = f.name
        try:
            driver.flash({"script": script_path, "keep_data": True})
            assert mock_run.call_count == 1  # boot_a only
        finally:
            os.unlink(script_path)

    @patch("smoke_test_ai.drivers.flash.fastboot.subprocess.run")
    def test_keep_data_false_includes_all(self, mock_run):
        """keep_data=False includes all commands."""
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        driver = FastbootFlashDriver(serial="FAKE")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bash", delete=False) as f:
            f.write('$fastboot_tool erase userdata\n')
            f.write('$fastboot_tool flash userdata ${image_dir}userdata.img\n')
            f.write('$fastboot_tool flash super ${image_dir}super.img\n')
            script_path = f.name
        try:
            driver.flash({"script": script_path})
            assert mock_run.call_count == 3
        finally:
            os.unlink(script_path)

    @patch("smoke_test_ai.drivers.flash.fastboot.subprocess.run")
    def test_keep_data_filters_images_mode(self, mock_run):
        """keep_data=True filters userdata in images mode."""
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        driver = FastbootFlashDriver(serial="FAKE")
        config = {
            "images": [
                {"partition": "system", "file": "/p/system.img"},
                {"partition": "userdata", "file": "/p/userdata.img"},
                {"partition": "boot", "file": "/p/boot.img"},
            ],
            "keep_data": True,
        }
        driver.flash(config)
        assert mock_run.call_count == 2  # system + boot

    @patch("smoke_test_ai.drivers.flash.fastboot.subprocess.run")
    def test_keep_data_filters_userdata_ab_images(self, mock_run):
        """keep_data=True filters userdata_a/b in images mode."""
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        driver = FastbootFlashDriver(serial="FAKE")
        config = {
            "images": [
                {"partition": "system", "file": "/p/system.img"},
                {"partition": "userdata_a", "file": "/p/ud_a.img"},
                {"partition": "userdata_b", "file": "/p/ud_b.img"},
            ],
            "keep_data": True,
        }
        driver.flash(config)
        assert mock_run.call_count == 1  # system only
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_flash.py::TestKeepDataFiltering -v`
Expected: FAIL (no filtering logic yet)

- [ ] **Step 3: Implement keep_data filtering in _run_script()**

In `smoke_test_ai/drivers/flash/fastboot.py:50-79`, after `commands = self._parse_script(script)` (line 57), add:

```python
        # Filter out userdata commands when keep_data is set
        if config.get("keep_data"):
            original_count = len(commands)
            commands = [cmd for cmd in commands
                        if not (len(cmd) > 1 and cmd[1].startswith("userdata"))]
            skipped = original_count - len(commands)
            if skipped:
                logger.info(f"keep_data: skipped {skipped} userdata command(s)")
```

- [ ] **Step 4: Implement keep_data filtering in flash() images mode**

In `smoke_test_ai/drivers/flash/fastboot.py:37-44`, replace the images loop:

```python
        # Partition-by-partition mode
        images = config.get("images", [])
        if config.get("keep_data"):
            original_count = len(images)
            images = [img for img in images
                      if not img["partition"].startswith("userdata")]
            skipped = original_count - len(images)
            if skipped:
                logger.info(f"keep_data: skipped {skipped} userdata image(s)")

        for image in images:
            partition = image["partition"]
            file_path = image["file"]
            logger.info(f"Flashing {partition}: {file_path}")
            result = self._run("flash", partition, file_path)
            if result.returncode != 0:
                raise RuntimeError(f"Flash failed for {partition}: {result.stderr}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_flash.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add smoke_test_ai/drivers/flash/fastboot.py tests/test_flash.py
git commit -m "feat: add keep_data filtering to flash driver for script and images mode"
```

---

## Task 2: Orchestrator adaptive decision logic

**Files:**
- Modify: `smoke_test_ai/core/orchestrator.py:351-460`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write failing tests for adaptive pipeline**

Add to `tests/test_orchestrator.py` after existing test classes:

```python
class TestAdaptivePipeline:
    """Tests for build_type / keep_data / is_factory_reset decision logic."""

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_user_full_flash_triggers_aoa(self, MockAdb, mock_sleep, settings, device_config):
        """user build + full flash (keep_data=False) → need_aoa=True."""
        device_config["device"]["aoa"] = {"enabled": True, "vendor_id": 0x18D1, "product_id": 0x4EE2}
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb = MagicMock()
        mock_adb.wait_for_device.return_value = True
        mock_adb.is_wifi_connected.return_value = True
        mock_adb.get_user_state.return_value = "RUNNING_UNLOCKED"
        mock_adb.get_device_info.return_value = {"model": "T", "sdk": "33"}
        MockAdb.return_value = mock_adb

        with patch.object(orch, "_get_flash_driver") as mock_gfd, \
             patch.object(orch, "_init_aoa_hid") as mock_aoa, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            mock_gfd.return_value = MagicMock()
            orch.run(serial="S", build_dir="/b", build_type="user", keep_data=False)
            mock_aoa.assert_called_once()

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_user_keep_data_skips_aoa(self, MockAdb, mock_sleep, settings, device_config):
        """user build + keep_data=True → need_aoa=False."""
        device_config["device"]["aoa"] = {"enabled": True, "vendor_id": 0x18D1, "product_id": 0x4EE2}
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb = MagicMock()
        mock_adb.wait_for_device.return_value = True
        mock_adb.is_wifi_connected.return_value = True
        mock_adb.get_user_state.return_value = "RUNNING_UNLOCKED"
        mock_adb.get_device_info.return_value = {"model": "T", "sdk": "33"}
        MockAdb.return_value = mock_adb

        with patch.object(orch, "_get_flash_driver") as mock_gfd, \
             patch.object(orch, "_init_aoa_hid") as mock_aoa, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            mock_gfd.return_value = MagicMock()
            orch.run(serial="S", build_dir="/b", build_type="user", keep_data=True)
            mock_aoa.assert_not_called()

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_userdebug_never_aoa(self, MockAdb, mock_sleep, settings, device_config):
        """userdebug build → need_aoa=False regardless of keep_data."""
        device_config["device"]["aoa"] = {"enabled": True, "vendor_id": 0x18D1, "product_id": 0x4EE2}
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb = MagicMock()
        mock_adb.wait_for_device.return_value = True
        mock_adb.is_wifi_connected.return_value = True
        mock_adb.get_user_state.return_value = "RUNNING_UNLOCKED"
        mock_adb.get_device_info.return_value = {"model": "T", "sdk": "33"}
        MockAdb.return_value = mock_adb

        with patch.object(orch, "_get_flash_driver") as mock_gfd, \
             patch.object(orch, "_init_aoa_hid") as mock_aoa, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            mock_gfd.return_value = MagicMock()
            orch.run(serial="S", build_dir="/b", build_type="userdebug")
            mock_aoa.assert_not_called()

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_keep_data_injected_to_flash_config(self, MockAdb, mock_sleep, settings, device_config):
        """keep_data=True is injected into flash_config for driver."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb = MagicMock()
        mock_adb.wait_for_device.return_value = True
        mock_adb.is_wifi_connected.return_value = True
        mock_adb.get_user_state.return_value = "RUNNING_UNLOCKED"
        mock_adb.get_device_info.return_value = {"model": "T", "sdk": "33"}
        MockAdb.return_value = mock_adb
        mock_fd = MagicMock()

        with patch.object(orch, "_get_flash_driver", return_value=mock_fd), \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            orch.run(serial="S", build_dir="/b", keep_data=True)
            flash_cfg = mock_fd.flash.call_args[0][0]
            assert flash_cfg.get("keep_data") is True

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_factory_reset_user_triggers_aoa(self, MockAdb, mock_sleep, settings, device_config):
        """is_factory_reset=True + user build → need_aoa=True."""
        device_config["device"]["aoa"] = {"enabled": True, "vendor_id": 0x18D1, "product_id": 0x4EE2}
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb = MagicMock()
        mock_adb.wait_for_device.return_value = True
        mock_adb.is_wifi_connected.return_value = True
        mock_adb.get_user_state.return_value = "RUNNING_UNLOCKED"
        mock_adb.get_device_info.return_value = {"model": "T", "sdk": "33"}
        MockAdb.return_value = mock_adb

        with patch.object(orch, "_init_aoa_hid") as mock_aoa, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            orch.run(serial="S", build_type="user", is_factory_reset=True)
            mock_aoa.assert_called_once()

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_cli_build_type_overrides_yaml(self, MockAdb, mock_sleep, settings, device_config):
        """CLI --build-type overrides YAML build_type."""
        # YAML says "user", CLI says "userdebug"
        device_config["device"]["aoa"] = {"enabled": True, "vendor_id": 0x18D1, "product_id": 0x4EE2}
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb = MagicMock()
        mock_adb.wait_for_device.return_value = True
        mock_adb.is_wifi_connected.return_value = True
        mock_adb.get_user_state.return_value = "RUNNING_UNLOCKED"
        mock_adb.get_device_info.return_value = {"model": "T", "sdk": "33"}
        MockAdb.return_value = mock_adb

        with patch.object(orch, "_get_flash_driver") as mock_gfd, \
             patch.object(orch, "_init_aoa_hid") as mock_aoa, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            mock_gfd.return_value = MagicMock()
            # YAML is "user" but CLI overrides to "userdebug" → no AOA
            orch.run(serial="S", build_dir="/b", build_type="userdebug")
            mock_aoa.assert_not_called()

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_fresh_state_longer_wifi_timeout(self, MockAdb, mock_sleep, settings, device_config):
        """fresh_state=True uses 45s WiFi timeout."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb = MagicMock()
        mock_adb.wait_for_device.return_value = True
        mock_adb.is_wifi_connected.return_value = False
        mock_adb.get_user_state.return_value = "RUNNING_UNLOCKED"
        mock_adb.get_device_info.return_value = {"model": "T", "sdk": "33"}
        MockAdb.return_value = mock_adb

        with patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            orch.run(serial="S", is_factory_reset=True)
            # WiFi connect should use 45s timeout (fresh_state=True)
            mock_adb.connect_wifi.assert_called_once()
            assert mock_adb.connect_wifi.call_args.kwargs.get("wifi_timeout") == 45

    @patch("smoke_test_ai.core.orchestrator.time.sleep")
    @patch("smoke_test_ai.core.orchestrator.AdbController")
    def test_keep_data_shorter_wifi_timeout(self, MockAdb, mock_sleep, settings, device_config):
        """keep_data=True (fresh_state=False) uses 15s WiFi timeout."""
        orch = Orchestrator(settings=settings, device_config=device_config)
        mock_adb = MagicMock()
        mock_adb.wait_for_device.return_value = True
        mock_adb.is_wifi_connected.return_value = False
        mock_adb.get_user_state.return_value = "RUNNING_UNLOCKED"
        mock_adb.get_device_info.return_value = {"model": "T", "sdk": "33"}
        MockAdb.return_value = mock_adb

        with patch.object(orch, "_get_flash_driver") as mock_gfd, \
             patch.object(orch, "_generate_reports"), \
             patch.object(orch, "_pre_test_setup"):
            mock_gfd.return_value = MagicMock()
            orch.run(serial="S", build_dir="/b", keep_data=True)
            mock_adb.connect_wifi.assert_called_once()
            assert mock_adb.connect_wifi.call_args.kwargs.get("wifi_timeout") == 15
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_orchestrator.py::TestAdaptivePipeline -v`
Expected: FAIL (run() doesn't accept new params)

- [ ] **Step 3: Update orchestrator run() signature**

In `smoke_test_ai/core/orchestrator.py:351-359`, change to:

```python
    def run(
        self,
        serial: str | None = None,
        suite_config: dict | None = None,
        build_dir: str | None = None,
        skip_flash: bool = False,
        skip_setup: bool = False,
        config_dir: str = "config",
        build_type: str | None = None,
        keep_data: bool = False,
        is_factory_reset: bool = False,
    ) -> list[TestResult]:
```

- [ ] **Step 4: Add decision logic after line 360**

After `adb = AdbController(serial=serial)` and USB power init, add:

```python
        # Adaptive pipeline decision logic
        effective_build_type = build_type or self.device_config.get("build_type", "userdebug")
        need_flash = not skip_flash and build_dir
        need_aoa = (
            effective_build_type == "user"
            and not keep_data
            and (need_flash or is_factory_reset)
            and not skip_setup
        )
        fresh_state = (need_flash or is_factory_reset) and not keep_data
        logger.info(f"Pipeline: build_type={effective_build_type}, "
                    f"need_aoa={need_aoa}, fresh_state={fresh_state}")
```

- [ ] **Step 5: Update Stage 0 — inject keep_data into flash_config**

In Stage 0 block (line 370-383), after `_resolve_flash_config()` and before `flash_driver.flash()`:

```python
            if keep_data:
                flash_config["keep_data"] = True
```

- [ ] **Step 6: Update Stage 1 condition**

Replace line 386:
```python
        if not skip_setup and self.device_config.get("build_type") == "user":
```
With:
```python
        if need_aoa:
```

- [ ] **Step 7: Update Stage 2 — setup wizard skip, FBE unlock, WiFi timeout**

Replace line 420-421:
```python
        if not skip_setup:
            adb.skip_setup_wizard()
```
With:
```python
        if not skip_setup and fresh_state and not need_aoa:
            adb.skip_setup_wizard()
```

Replace lines 423-434 (FBE unlock block), wrap with `if fresh_state:`:
```python
        # FBE unlock: only needed after state reset (fresh_state)
        if fresh_state:
            user_state = adb.get_user_state()
            if user_state == "RUNNING_LOCKED":
                logger.warning("User storage is locked (FBE). Attempting unlock...")
                pin = self.device_config.get("lock_pin")
                if adb.unlock_keyguard(pin=pin):
                    logger.info("Device unlocked successfully — user storage is now accessible")
                else:
                    logger.error(
                        "Failed to unlock device. Many services (NFC, Launcher, etc.) "
                        "will not start until user storage is unlocked."
                    )
```

Replace line 438:
```python
        wifi_timeout = 45 if not skip_setup else 15
```
With:
```python
        wifi_timeout = 45 if fresh_state else 15
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/test_orchestrator.py -v`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add smoke_test_ai/core/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: add adaptive pipeline decision logic to orchestrator"
```

---

## Task 3: CLI `--build-type` and `--keep-data` flags

**Files:**
- Modify: `cli.py:15-48` (run), `cli.py:77-151` (reset-test)

- [ ] **Step 1: Add options to `run` command**

In `cli.py`, add two decorators before `@click.option("--config-dir"...)` (line 22):

```python
@click.option("--build-type", type=click.Choice(["user", "userdebug"]), default=None, help="Build type (overrides YAML)")
@click.option("--keep-data", is_flag=True, help="Skip userdata flash (preserve existing data)")
```

Update function signature (line 23):
```python
def run(device, suite, build, serial, skip_flash, skip_setup, build_type, keep_data, config_dir):
```

Update `orch.run()` call (lines 33-40):
```python
    results = orch.run(
        serial=serial,
        suite_config=suite_config,
        build_dir=build,
        skip_flash=skip_flash,
        skip_setup=skip_setup,
        build_type=build_type,
        keep_data=keep_data,
        config_dir=str(config_path),
    )
```

- [ ] **Step 2: Add `--build-type` to `reset-test` command**

In `cli.py`, add decorator before `@click.option("--boot-timeout"...)` (line 82):

```python
@click.option("--build-type", type=click.Choice(["user", "userdebug"]), default=None, help="Build type (overrides YAML)")
```

Update function signature (line 84):
```python
def reset_test(device, suite, serial, config_dir, boot_timeout, reset_delay, build_type):
```

- [ ] **Step 3: Update reset-test to conditionally defer ADB wait**

Replace lines 128-133 (ADB wait block):
```python
    # Wait for device to come back via ADB
    console.print(f"\nWaiting for ADB connection (timeout: {boot_timeout}s)...")
    if not adb.wait_for_device(timeout=boot_timeout):
        console.print("[red]Device not found via ADB[/]")
        raise SystemExit(1)
    console.print("[green]Device connected via ADB[/]\n")
```

With:
```python
    # Resolve build type for ADB wait decision
    effective_build_type = build_type or device_config.get("device", {}).get("build_type", "userdebug")

    # For user builds, ADB won't be available until after AOA Stage 1
    # So defer ADB wait to orchestrator
    if effective_build_type != "user":
        console.print(f"\nWaiting for ADB connection (timeout: {boot_timeout}s)...")
        if not adb.wait_for_device(timeout=boot_timeout):
            console.print("[red]Device not found via ADB[/]")
            raise SystemExit(1)
        console.print("[green]Device connected via ADB[/]\n")
    else:
        console.print("\n[cyan]User build: ADB wait deferred to orchestrator (after AOA)[/]")
```

- [ ] **Step 4: Pass build_type and is_factory_reset to orchestrator**

Replace lines 137-143:
```python
    results = orch.run(
        serial=serial,
        suite_config=suite_config,
        skip_flash=True,
        skip_setup=False,
        config_dir=str(config_path),
    )
```

With:
```python
    results = orch.run(
        serial=serial,
        suite_config=suite_config,
        skip_flash=True,
        skip_setup=False,
        build_type=build_type,
        is_factory_reset=True,
        config_dir=str(config_path),
    )
```

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add cli.py
git commit -m "feat: add --build-type and --keep-data CLI flags for adaptive pipeline"
```

---

## Task 4: Full verification

- [ ] **Step 1: Run all tests**

```bash
python -m pytest tests/ -v --tb=short
```
Expected: ALL PASS

- [ ] **Step 2: Run coverage**

```bash
python -m pytest tests/ --cov=smoke_test_ai --cov-report=term-missing
```
Expected: Coverage ≥ 69%

- [ ] **Step 3: Verify CLI help**

```bash
python -m smoke_test_ai run --help
python -m smoke_test_ai reset-test --help
```
Expected: `--build-type` and `--keep-data` visible in help

- [ ] **Step 4: Final commit if needed**

---

## Verification

1. `python -m pytest tests/ -v` — all tests pass
2. `python -m pytest tests/ --cov=smoke_test_ai` — coverage ≥ 69%
3. CLI `--help` shows new flags
4. Manual test on DUT: `smoke-test run --device product_a --build /path --build-type user --serial SN`
5. Manual test: `smoke-test run --device product_a --build /path --keep-data --serial SN`
6. Manual test: `smoke-test reset-test --device product_a --suite smoke_basic --build-type user --serial SN`
