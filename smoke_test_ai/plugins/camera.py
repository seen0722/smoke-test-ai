import tempfile
import time
from pathlib import Path

try:
    import cv2
except ImportError:
    cv2 = None

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.base import TestPlugin, PluginContext

DCIM_PATH = "/sdcard/DCIM/Camera"


class CameraPlugin(TestPlugin):
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        action = test_case.get("action", "")
        if action == "capture_photo":
            result, _ = self._do_capture(test_case, context)
            return result
        if action == "capture_and_verify":
            return self._capture_and_verify(test_case, context)
        return TestResult(
            id=test_case["id"], name=test_case["name"],
            status=TestStatus.ERROR,
            message=f"Unknown camera action: {action}",
        )

    def _do_capture(self, tc: dict, ctx: PluginContext) -> tuple[TestResult, str]:
        """Take a photo and return (result, filename). Filename is empty on failure."""
        tid, tname = tc["id"], tc["name"]
        params = tc.get("params", {})
        camera = params.get("camera", "back")
        wait_seconds = params.get("wait_seconds", 5)
        adb = ctx.adb

        # 1. Record baseline: newest file in DCIM
        baseline = adb.shell(f"ls -t '{DCIM_PATH}/' | head -1").stdout.strip()

        # 2. Launch camera
        camera_id = 0 if camera == "back" else 1
        adb.shell(
            f"am start -a android.media.action.IMAGE_CAPTURE "
            f"--ei android.intent.extras.CAMERA_FACING {camera_id}"
        )
        time.sleep(2)

        # 3. Trigger shutter
        adb.shell("input keyevent KEYCODE_CAMERA")
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        # 4. Check for new file
        newest = adb.shell(f"ls -t '{DCIM_PATH}/' | head -1").stdout.strip()
        if not newest or newest == baseline:
            return TestResult(
                id=tid, name=tname, status=TestStatus.FAIL,
                message=f"No new photo in {DCIM_PATH}/ (newest: {newest})",
            ), ""

        # 5. Check file size > 0
        size_out = adb.shell(f"stat -c %s '{DCIM_PATH}/{newest}'").stdout.strip()
        try:
            size = int(size_out)
        except ValueError:
            size = 0
        if size == 0:
            return TestResult(
                id=tid, name=tname, status=TestStatus.FAIL,
                message=f"Photo {newest} has zero bytes",
            ), ""

        return TestResult(
            id=tid, name=tname, status=TestStatus.PASS,
            message=f"Captured {newest} ({size} bytes, {camera} camera)",
        ), newest

    def _capture_and_verify(self, tc: dict, ctx: PluginContext) -> TestResult:
        result, newest = self._do_capture(tc, ctx)
        if result.status != TestStatus.PASS:
            return result

        if not ctx.visual_analyzer:
            return result

        prompt = tc.get("params", {}).get(
            "verify_prompt", "Is the photo clear, not black, not white?"
        )
        adb = ctx.adb

        # Pull photo to temp path and verify with LLM
        with tempfile.TemporaryDirectory() as tmp:
            local_path = Path(tmp) / newest
            image = None
            if hasattr(adb, "pull"):
                adb.pull(f"{DCIM_PATH}/{newest}", str(local_path))
                if local_path.exists() and cv2 is not None:
                    image = cv2.imread(str(local_path))

            if image is None:
                return result  # can't pull, return capture-only result

            analysis = ctx.visual_analyzer.analyze_test_screenshot(image, prompt)

        if analysis.get("pass", False):
            return TestResult(
                id=tc["id"], name=tc["name"], status=TestStatus.PASS,
                message=f"Verified: {analysis.get('reason', '')}",
            )
        return TestResult(
            id=tc["id"], name=tc["name"], status=TestStatus.FAIL,
            message=f"LLM rejected: {analysis.get('reason', '')}",
        )
