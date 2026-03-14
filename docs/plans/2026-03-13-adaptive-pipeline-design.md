# Adaptive Pipeline Design

## Problem

The smoke-test pipeline must adapt its behavior based on two independent variables:

1. **Build type** (`user` vs `userdebug`) — determines whether ADB is available after flash
2. **Userdata flash** (full vs keep-data) — determines whether Setup Wizard appears

Currently, `build_type` is a static YAML setting and there is no mechanism to skip userdata during flash. The pipeline needs to handle 4 distinct scenarios correctly.

## Decision Matrix

```
                    keep-data=false           keep-data=true
                    (full flash)              (partial flash)
  ┌──────────────┬───────────────────────┬──────────────────────┐
  │ user         │ Flash → AOA Blind     │ Flash (skip userdata)│
  │              │ (Setup Wizard +       │ → ADB Bootstrap      │
  │              │  USB Debug enable)    │ (ADB already on,     │
  │              │ → ADB Bootstrap       │  no Setup Wizard)    │
  ├──────────────┼───────────────────────┼──────────────────────┤
  │ userdebug    │ Flash → ADB Bootstrap │ Flash (skip userdata)│
  │              │ (ADB on by default,   │ → ADB Bootstrap      │
  │              │  pm disable Setup Wiz)│ (same as above)      │
  └──────────────┴───────────────────────┴──────────────────────┘
```

**Only `user + full flash` requires AOA blind automation.** All other scenarios have ADB available.

## Pipeline Flow

```
CLI Flags:
  --build-type user|userdebug   (overrides YAML build_type)
  --keep-data                   (skip erase/flash userdata)
  --build /path                 (image directory)
  --skip-flash                  (skip Stage 0 entirely)

         ┌──────────────────────────────┐
         │  Stage 0: Flash              │
         │  skip_flash → skip           │
         │  keep_data → filter out      │
         │    erase/flash userdata      │
         └──────────┬───────────────────┘
                    ▼
         ┌──────────────────────────────┐
         │  Need AOA?                   │
         │  build_type == "user"        │
         │  AND keep_data == false      │
         │  AND (has_flash OR           │
         │       is_factory_reset)      │
         └──┬─────────────┬────────────┘
          YES             NO
            ▼              ▼
  ┌─────────────┐  ┌──────────────────┐
  │ Stage 1:    │  │ (skip to         │
  │ AOA Blind   │  │  Stage 2)        │
  │ Setup Wiz   │  │                  │
  │ + USB Debug │  │                  │
  └──────┬──────┘  └────────┬─────────┘
         ▼                  │
  ┌──────────────────────────────────┐
  │ Stage 2: ADB Bootstrap          │
  │ - wait_for_device               │
  │ - skip Setup Wizard (if needed) │
  │ - FBE unlock (if needed)        │
  │ - WiFi connect                  │
  │ - screen keep-alive             │
  │ - install Mobly Snippet APK     │
  └──────────┬───────────────────────┘
             ▼
  ┌──────────────────────────────────┐
  │ Stage 3: Test Execute            │
  └──────────┬───────────────────────┘
             ▼
  ┌──────────────────────────────────┐
  │ Stage 4: Report                  │
  └──────────────────────────────────┘
```

## Stage 2 Conditional Behavior

| Scenario | Skip Setup Wizard | WiFi timeout | FBE unlock |
|----------|-------------------|-------------|------------|
| Full flash, user (after AOA) | Yes | 45s | Yes |
| Full flash, userdebug | Yes | 45s | Yes |
| Partial flash (keep-data) | No (already provisioned) | 15s | No (already unlocked) |
| Factory reset, user | AOA handles it | 45s | Yes |
| Factory reset, userdebug | Yes | 45s | Yes |

## CLI Interface

```bash
# Full flash, user build (AOA + Setup Wizard)
smoke-test run --device product_a --build /path/to/fastboot \
  --build-type user --serial SN

# Full flash, userdebug build (ADB direct)
smoke-test run --device product_a --build /path/to/fastboot \
  --build-type userdebug --serial SN

# Partial flash, keep userdata (no AOA, no Setup Wizard)
smoke-test run --device product_a --build /path/to/fastboot \
  --build-type user --keep-data --serial SN

# Factory reset, user build
smoke-test reset-test --device product_a --suite smoke_basic \
  --build-type user --serial SN

# Factory reset, userdebug build
smoke-test reset-test --device product_a --suite smoke_basic \
  --build-type userdebug --serial SN
```

**Priority:** `--build-type` CLI flag > YAML `build_type` field.

`--keep-data` is only meaningful when `--build` is provided.

## Implementation Changes

### 1. CLI (cli.py)

Add options:
- `run` command: `--build-type` (`user`|`userdebug`, optional, overrides YAML) and `--keep-data` (flag, default false)
- `reset-test` command: `--build-type` only (no `--keep-data` — factory reset always wipes data)

Pass to `orch.run()`. `reset-test` also passes `is_factory_reset=True`.

### 2. Orchestrator (orchestrator.py)

`run()` method signature adds named parameters:
```python
def run(self, ..., build_type: str | None = None,
        keep_data: bool = False, is_factory_reset: bool = False):
```

Decision logic:
```python
build_type = build_type or self.device_config.get("build_type", "userdebug")
need_flash = not skip_flash and build_dir

# AOA is needed when user build loses ADB after state reset
need_aoa = (build_type == "user" and not keep_data
            and (need_flash or is_factory_reset)
            and not skip_setup)

# Fresh state = userdata was wiped (flash or factory reset)
fresh_state = (need_flash or is_factory_reset) and not keep_data
wifi_timeout = 45 if fresh_state else 15
```

**`--skip-setup`** suppresses both Stage 1 (AOA) and Stage 2 setup-wizard skip, preserving existing semantics.

Stage 0: After `_resolve_flash_config()`, inject `keep_data` into the resolved config dict:
```python
flash_config = self._resolve_flash_config(raw_config, build_dir)
if keep_data:
    flash_config["keep_data"] = True
flash_driver.flash(flash_config)
```
Stage 1: Condition changes from `build_type == "user"` to `need_aoa`.
Stage 2: Setup Wizard skip only when `fresh_state and not need_aoa` (AOA already handles it for user builds). FBE unlock when `fresh_state`.

### 3. FastbootFlashDriver (fastboot.py)

`flash()` filters out userdata commands when `config["keep_data"]` is True, for **both** script mode and images mode:

**Script mode** — filter parsed commands in `_run_script()`:
```python
def _is_userdata_cmd(cmd):
    """Check if command targets userdata partition (including A/B slots)."""
    return len(cmd) > 1 and cmd[1].startswith("userdata")

if config.get("keep_data"):
    commands = [cmd for cmd in commands if not _is_userdata_cmd(cmd)]
    # cmd[0] is sub-command (erase/flash), cmd[1] is partition name
    # Handles: "userdata", "userdata_a", "userdata_b"
```

**Images mode** — filter image list in `flash()`:
```python
if config.get("keep_data"):
    images = [img for img in images
              if not img["partition"].startswith("userdata")]
```

### 4. reset-test (cli.py)

- Add `--build-type` option (same as `run` command).
- Pass `build_type` and `is_factory_reset=True` to `orch.run()`.
- Do **NOT** add `--keep-data` to `reset-test` — factory reset always wipes userdata by definition.
- **Critical change:** The current `reset-test` CLI calls `adb.wait_for_device()` _before_ `orch.run()`. For user builds, ADB won't be available until after AOA Stage 1. Fix: make the pre-orchestrator `adb.wait_for_device()` conditional on `build_type != "user"`, or move it into the orchestrator. The recommended approach is to keep factory reset + USB power cycle in CLI, but defer `adb.wait_for_device()` to the orchestrator's Stage 2 (which already handles it):
  ```python
  # reset-test CLI: remove adb.wait_for_device() call
  # The orchestrator's Stage 2 handles ADB wait after AOA (if needed)
  adb.factory_reset()
  usb_power.power_cycle()
  orch.run(skip_flash=True, build_type=build_type, is_factory_reset=True, ...)
  ```

## What Does NOT Change

- Plugin system, TestRunner, PluginContext
- Flash driver base class and CustomFlashDriver
- Test suites and YAML test definitions
- Report generation
- AOA HID driver and BlindRunner internals
- Mobly Snippet handling
