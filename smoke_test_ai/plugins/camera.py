import re
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

        # Skip front camera test if device has fewer than 2 cameras
        if camera == "front":
            count_out = adb.shell(
                "dumpsys media.camera | grep 'Number of camera devices'"
            ).stdout.strip()
            m = re.search(r"Number of camera devices:\s*(\d+)", count_out)
            cam_count = int(m.group(1)) if m else 0
            if cam_count < 2:
                return TestResult(
                    id=tid, name=tname, status=TestStatus.SKIP,
                    message=f"Device has {cam_count} camera(s), no front camera",
                ), ""

        try:
            # Ensure DCIM/Camera directory exists
            adb.shell(f"mkdir -p '{DCIM_PATH}'")

            # 1. Record baseline: newest file in DCIM (check multiple paths)
            dcim_paths = [DCIM_PATH, "/sdcard/DCIM", "/sdcard/Pictures"]
            baselines = {}
            for dp in dcim_paths:
                out = adb.shell(f"ls -t '{dp}/' 2>/dev/null | head -1").stdout.strip()
                baselines[dp] = out

            # 2. Launch camera in standalone mode (not IMAGE_CAPTURE intent, which
            #    shows a confirm dialog and doesn't auto-save). Direct launch saves
            #    photos immediately to DCIM.
            adb.shell("am force-stop org.codeaurora.snapcam 2>/dev/null; "
                       "am force-stop com.android.camera2 2>/dev/null")
            camera_id = 0 if camera == "back" else 1
            # Try direct camera launcher first; fall back to generic STILL_IMAGE intent
            launch_result = adb.shell(
                "am start -n org.codeaurora.snapcam/com.android.camera.CameraLauncher 2>&1"
            )
            launch_out = launch_result.stdout if hasattr(launch_result, "stdout") else str(launch_result)
            if "Error" in launch_out or "does not exist" in launch_out:
                adb.shell(f"am start -a android.media.action.STILL_IMAGE_CAMERA "
                           f"--ei android.intent.extras.CAMERA_FACING {camera_id}")
            time.sleep(3)
            # Dismiss first-launch tutorial / permission dialog if present
            adb.shell("input keyevent KEYCODE_ENTER")
            time.sleep(2)

            # 3. Trigger shutter via VOLUME_DOWN (standard hardware shutter)
            adb.shell("input keyevent KEYCODE_VOLUME_DOWN")
            if wait_seconds > 0:
                time.sleep(wait_seconds)

            # 4. Check for new file across all candidate paths
            found_path = ""
            found_file = ""
            for dp in dcim_paths:
                newest = adb.shell(f"ls -t '{dp}/' 2>/dev/null | head -1").stdout.strip()
                if newest and newest != baselines.get(dp, ""):
                    found_path = dp
                    found_file = newest
                    break

            if not found_file:
                return TestResult(
                    id=tid, name=tname, status=TestStatus.FAIL,
                    message=f"No new photo in {dcim_paths} (baselines: {baselines})",
                ), ""

            # 5. Check file size > 0
            full_path = f"{found_path}/{found_file}"
            size_out = adb.shell(f"stat -c %s '{full_path}'").stdout.strip()
            try:
                size = int(size_out)
            except ValueError:
                size = 0
            if size == 0:
                return TestResult(
                    id=tid, name=tname, status=TestStatus.FAIL,
                    message=f"Photo {found_file} has zero bytes",
                ), ""

            return TestResult(
                id=tid, name=tname, status=TestStatus.PASS,
                message=f"Captured {found_file} ({size} bytes, {camera} camera)",
            ), full_path
        finally:
            adb.shell("am force-stop org.codeaurora.snapcam 2>/dev/null; "
                       "am force-stop com.android.camera2 2>/dev/null")

    def _capture_and_verify(self, tc: dict, ctx: PluginContext) -> TestResult:
        result, remote_path = self._do_capture(tc, ctx)
        if result.status != TestStatus.PASS:
            return result

        if not ctx.visual_analyzer:
            return result

        prompt = tc.get("params", {}).get(
            "verify_prompt", "Is the photo clear, not black, not white?"
        )
        adb = ctx.adb

        # Pull photo to temp path and verify with LLM
        filename = Path(remote_path).name if remote_path else ""
        with tempfile.TemporaryDirectory() as tmp:
            local_path = Path(tmp) / filename if filename else Path(tmp) / "photo.jpg"
            image = None
            if hasattr(adb, "pull") and remote_path:
                adb.pull(remote_path, str(local_path))
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
