import numpy as np
from unittest.mock import MagicMock, patch

from smoke_test_ai.ai.setup_wizard_agent import SetupWizardAgent


def _make_agent(max_steps=30, timeout=300):
    hid = MagicMock()
    screen_capture = MagicMock()
    analyzer = MagicMock()
    adb = MagicMock()
    agent = SetupWizardAgent(
        hid=hid,
        screen_capture=screen_capture,
        analyzer=analyzer,
        adb=adb,
        screen_w=1080,
        screen_h=2400,
        hid_id=2,
        keyboard_hid_id=1,
        max_steps=max_steps,
        timeout=timeout,
    )
    return agent, hid, screen_capture, analyzer, adb


def _bright_image():
    """Return a bright image that passes the _is_screen_off check."""
    return np.ones((100, 100, 3), dtype=np.uint8) * 128


@patch("smoke_test_ai.ai.setup_wizard_agent.time.sleep")
@patch("smoke_test_ai.ai.setup_wizard_agent.time.time")
def test_run_completes_when_adb_boot_done(mock_time, mock_sleep):
    """ADB reports boot_completed=1 -> returns True immediately
    without calling screen capture or analyzer."""
    mock_time.return_value = 0  # Never timeout

    agent, hid, screen_capture, analyzer, adb = _make_agent()
    adb.is_connected.return_value = True
    adb.getprop.return_value = "1"

    result = agent.run()

    assert result is True
    screen_capture.capture.assert_not_called()
    analyzer.analyze_setup_wizard.assert_not_called()


@patch("smoke_test_ai.ai.setup_wizard_agent.time.sleep")
@patch("smoke_test_ai.ai.setup_wizard_agent.time.time")
def test_run_executes_tap_action(mock_time, mock_sleep):
    """ADB not connected, LLM suggests tap action -> hid.tap called
    with correct coords. Second LLM call returns completed=True."""
    mock_time.return_value = 0

    agent, hid, screen_capture, analyzer, adb = _make_agent()
    adb.is_connected.return_value = False
    screen_capture.capture.return_value = _bright_image()

    tap_x, tap_y = 540, 1200
    analyzer.analyze_setup_wizard.side_effect = [
        {
            "screen_state": "language_selection",
            "completed": False,
            "confidence": 0.9,
            "action": {"type": "tap", "x": tap_x, "y": tap_y},
        },
        {
            "screen_state": "home",
            "completed": True,
            "confidence": 0.95,
            "action": {},
        },
    ]

    result = agent.run()

    assert result is True
    hid.tap.assert_called_once_with(2, tap_x, tap_y, 1080, 2400)


@patch("smoke_test_ai.ai.setup_wizard_agent.time.sleep")
@patch("smoke_test_ai.ai.setup_wizard_agent.time.time")
def test_run_max_steps_exceeded(mock_time, mock_sleep):
    """max_steps=2, LLM always returns wait action -> returns False."""
    mock_time.return_value = 0

    agent, hid, screen_capture, analyzer, adb = _make_agent(max_steps=2)
    adb.is_connected.return_value = False
    screen_capture.capture.return_value = _bright_image()

    analyzer.analyze_setup_wizard.return_value = {
        "screen_state": "loading",
        "completed": False,
        "confidence": 0.5,
        "action": {"type": "wait", "wait_seconds": 3},
    }

    result = agent.run()

    assert result is False
    assert analyzer.analyze_setup_wizard.call_count == 2


@patch("smoke_test_ai.ai.setup_wizard_agent.time.sleep")
@patch("smoke_test_ai.ai.setup_wizard_agent.time.time")
def test_run_screenshot_failure_continues(mock_time, mock_sleep):
    """screen_capture.capture returns None on first call, bright image
    on second -> doesn't crash, eventually completes."""
    mock_time.return_value = 0

    agent, hid, screen_capture, analyzer, adb = _make_agent()
    adb.is_connected.return_value = False
    screen_capture.capture.side_effect = [None, _bright_image()]

    analyzer.analyze_setup_wizard.return_value = {
        "screen_state": "home",
        "completed": True,
        "confidence": 0.95,
        "action": {},
    }

    result = agent.run()

    assert result is True
    # Analyzer should only be called once (after the second capture succeeds)
    analyzer.analyze_setup_wizard.assert_called_once()


@patch("smoke_test_ai.ai.setup_wizard_agent.time.sleep")
@patch("smoke_test_ai.ai.setup_wizard_agent.time.time")
def test_run_swipe_action(mock_time, mock_sleep):
    """LLM suggests swipe direction='up' -> hid.swipe called,
    verify y1 > y2 (upward swipe)."""
    mock_time.return_value = 0

    agent, hid, screen_capture, analyzer, adb = _make_agent()
    adb.is_connected.return_value = False
    screen_capture.capture.return_value = _bright_image()

    analyzer.analyze_setup_wizard.side_effect = [
        {
            "screen_state": "terms_of_service",
            "completed": False,
            "confidence": 0.85,
            "action": {"type": "swipe", "direction": "up"},
        },
        {
            "screen_state": "home",
            "completed": True,
            "confidence": 0.95,
            "action": {},
        },
    ]

    result = agent.run()

    assert result is True
    hid.swipe.assert_called_once()
    call_args = hid.swipe.call_args[0]
    # call_args: (hid_id, x1, y1, x2, y2, screen_w, screen_h)
    _, x1, y1, x2, y2, sw, sh = call_args
    # For "up" swipe: y1 should be greater than y2 (start lower, move higher)
    assert y1 > y2, f"Expected y1 > y2 for upward swipe, got y1={y1}, y2={y2}"
    assert sw == 1080
    assert sh == 2400
