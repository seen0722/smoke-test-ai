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
         │  AND has flash (not skip)    │
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

Add two new options to `run` and `reset-test` commands:
- `--build-type` (`user`|`userdebug`, optional, overrides YAML)
- `--keep-data` (flag, default false)

Pass both to `orch.run()`.

### 2. Orchestrator (orchestrator.py)

`run()` method signature adds `build_type` and `keep_data` parameters.

Decision logic:
```python
build_type = build_type or self.device_config.get("build_type", "userdebug")
need_flash = not skip_flash and build_dir
need_aoa = (build_type == "user" and not keep_data and need_flash)
need_setup_wizard_skip = not keep_data and (need_flash or not skip_setup)
wifi_timeout = 45 if need_setup_wizard_skip else 15
```

Stage 0: Pass `keep_data` to flash driver.
Stage 1: Condition changes from `build_type == "user"` to `need_aoa`.
Stage 2: Use `need_setup_wizard_skip` for conditional behavior.

### 3. FastbootFlashDriver (fastboot.py)

`_parse_script()` or `_run_script()` filters out userdata commands when `keep_data=True`:
```python
if config.get("keep_data"):
    commands = [cmd for cmd in commands
                if not (len(cmd) > 1 and cmd[1] == "userdata")]
```

### 4. reset-test (cli.py)

Pass `--build-type` to `orch.run()` so factory reset pipeline uses correct Stage 1 decision.

## What Does NOT Change

- Plugin system, TestRunner, PluginContext
- Flash driver base class and CustomFlashDriver
- Test suites and YAML test definitions
- Report generation
- AOA HID driver and BlindRunner internals
- Mobly Snippet handling
