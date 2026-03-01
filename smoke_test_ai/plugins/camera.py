import time

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.base import TestPlugin, PluginContext

DCIM_PATH = "/sdcard/DCIM/Camera"


class CameraPlugin(TestPlugin):
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        action = test_case.get("action", "")
        if action == "capture_photo":
            return self._capture_photo(test_case, context)
        if action == "capture_and_verify":
            return self._capture_and_verify(test_case, context)
        return TestResult(
            id=test_case["id"], name=test_case["name"],
            status=TestStatus.ERROR,
            message=f"Unknown camera action: {action}",
        )

    def _capture_photo(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        params = tc.get("params", {})
        camera = params.get("camera", "back")
        wait_seconds = params.get("wait_seconds", 5)
        adb = ctx.adb

        # 1. Record baseline: newest file in DCIM
        baseline = adb.shell(f"ls -t {DCIM_PATH}/ | head -1").stdout.strip()

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
        newest = adb.shell(f"ls -t {DCIM_PATH}/ | head -1").stdout.strip()
        if not newest or newest == baseline:
            return TestResult(
                id=tid, name=tname, status=TestStatus.FAIL,
                message=f"No new photo in {DCIM_PATH}/ (newest: {newest})",
            )

        # 5. Check file size > 0
        size_out = adb.shell(f"stat -c %s {DCIM_PATH}/{newest}").stdout.strip()
        try:
            size = int(size_out)
        except ValueError:
            size = 0
        if size == 0:
            return TestResult(
                id=tid, name=tname, status=TestStatus.FAIL,
                message=f"Photo {newest} has zero bytes",
            )

        return TestResult(
            id=tid, name=tname, status=TestStatus.PASS,
            message=f"Captured {newest} ({size} bytes, {camera} camera)",
        )

    def _capture_and_verify(self, tc: dict, ctx: PluginContext) -> TestResult:
        # First, take the photo
        result = self._capture_photo(tc, ctx)
        if result.status != TestStatus.PASS:
            return result

        # Then verify with LLM if available
        if not ctx.visual_analyzer:
            return result  # no LLM, just return capture result

        prompt = tc.get("params", {}).get(
            "verify_prompt", "Is the photo clear, not black, not white?"
        )
        newest = result.message.split()[1]  # extract filename from message
        adb = ctx.adb

        # Pull photo to temp path
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            local_path = Path(tmp) / newest
            adb.shell(f"cat {DCIM_PATH}/{newest}", timeout=30)
            # Use screen capture as fallback for LLM analysis
            image = None
            if hasattr(adb, "pull"):
                adb.pull(f"{DCIM_PATH}/{newest}", str(local_path))
                import cv2
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
