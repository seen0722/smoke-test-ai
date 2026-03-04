# Test Quality Improvement Design

## Goal

Improve test coverage across all modules using a layer-by-layer approach, from core infrastructure to edge modules.

## Approach: Layer-by-Layer ("逐層補齊")

Each phase is independently verifiable. Coverage infrastructure is added first so every subsequent phase shows measurable improvement.

## Phases

### Phase 1: Coverage Infrastructure

Add `pytest-cov` dependency and configure in `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["smoke_test_ai"]
omit = ["*/tests/*"]

[tool.coverage.report]
show_missing = true
```

### Phase 2: BlindRunner New Features (~8 tests)

Cover recently added USBError reconnect, ADB fallback, VID-only matching, and press_duration:

- `test_usb_error_triggers_reconnect` — USBError in _execute_step triggers _reconnect_aoa
- `test_usb_error_reconnect_fails` — reconnect failure returns False
- `test_wait_for_adb_usb_scan_finds_device` — USB VID scan succeeds, AOA re-init
- `test_wait_for_adb_adb_fallback` — USB scan fails, ADB fallback detects device
- `test_wait_for_adb_dispose_resources` — usb.util.dispose_resources called
- `test_tap_custom_press_duration` — YAML press_duration forwarded correctly
- `test_reconnect_aoa_delegates` — _reconnect_aoa calls _wait_for_adb(30)
- `test_wait_for_adb_both_fail` — USB + ADB both fail, timeout returns False

### Phase 3: Plugin execute() (~12 tests)

Each plugin gets 2 tests covering the execute() entry point:

- Camera: capture_photo, unknown_action
- Telephony: send_sms, unknown_action
- Wifi: scan, unknown_action
- Bluetooth: ble_scan, unknown_action
- Audio: play_and_check, unknown_action
- Network: http_download, unknown_action

### Phase 4: Orchestrator.run() (~6 tests)

- `test_run_full_pipeline` — all stages execute in order
- `test_run_flash_stage` — flash driver called correctly
- `test_run_setup_wizard_blind` — method=blind triggers BlindRunner
- `test_run_skips_flash_when_disabled` — flash.enabled=false skips flash
- `test_run_generates_report` — reporter called
- `test_run_mobly_snippet_failure_warns` — snippet failure logs warning, doesn't abort

### Phase 5: SetupWizardAgent (~5 tests)

- `test_run_completes_on_home_screen` — LLM returns "home screen" → done
- `test_run_executes_llm_action` — LLM returns tap → ADB tap called
- `test_run_timeout` — exceeds max_steps → failure
- `test_run_screenshot_failure` — screencap fails → no crash
- `test_run_swipe_action` — LLM returns swipe → correct coordinates

### Phase 6: Recorder (~4 tests)

- `test_screenshot_via_adb` — captures screenshot + sends tap to DUT
- `test_save_generates_yaml` — recorded steps output valid YAML
- `test_click_sends_adb_tap` — click event triggers adb shell input tap
- `test_refresh_updates_screenshot` — R key triggers re-screenshot

### Phase 7: Coverage Threshold

After all tests pass, set `fail_under = 70` in pyproject.toml.

## Expected Outcome

- ~35 new tests (194 → ~229)
- Coverage ≥ 70% with enforced threshold
- All recently changed modules have test coverage
