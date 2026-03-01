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
        if action == "verify_latest_photo":
            return self._verify_latest_photo(test_case, context)
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

            # 1. Create a timestamp marker for reliable new-file detection
            marker = "/sdcard/.smoke_test_cam_marker"
            adb.shell(f"touch {marker}")
            time.sleep(0.5)

            # 2. Launch camera in standalone mode
            adb.shell("am force-stop org.codeaurora.snapcam 2>/dev/null; "
                       "am force-stop com.android.camera2 2>/dev/null")
            camera_id = 0 if camera == "back" else 1
            launch_result = adb.shell(
                "am start -n org.codeaurora.snapcam/com.android.camera.CameraLauncher 2>&1"
            )
            launch_out = launch_result.stdout if hasattr(launch_result, "stdout") else str(launch_result)
            if "Error" in launch_out or "does not exist" in launch_out:
                adb.shell(f"am start -a android.media.action.STILL_IMAGE_CAMERA "
                           f"--ei android.intent.extras.CAMERA_FACING {camera_id}")
            time.sleep(5)

            # 3. Trigger shutter — try dedicated camera key first, then volume
            shutter_keys = ["KEYCODE_CAMERA", "KEYCODE_VOLUME_DOWN"]
            for key in shutter_keys:
                adb.shell(f"input keyevent {key}")
                time.sleep(1)

            if wait_seconds > 0:
                time.sleep(wait_seconds)

            # 4. Find new photo files created after the marker
            found = self._find_new_photo(adb, marker)

            # 5. Retry once if not found — wait longer and check again
            if not found:
                time.sleep(5)
                found = self._find_new_photo(adb, marker)

            # Clean up marker
            adb.shell(f"rm -f {marker}")

            if not found:
                return TestResult(
                    id=tid, name=tname, status=TestStatus.FAIL,
                    message="No new photo after capture attempt",
                ), ""

            # 6. Check file size > 0
            size_out = adb.shell(f"stat -c %s '{found}'").stdout.strip()
            try:
                size = int(size_out)
            except ValueError:
                size = 0
            if size == 0:
                return TestResult(
                    id=tid, name=tname, status=TestStatus.FAIL,
                    message=f"Photo {found} has zero bytes",
                ), ""

            filename = Path(found).name
            return TestResult(
                id=tid, name=tname, status=TestStatus.PASS,
                message=f"Captured {filename} ({size} bytes, {camera} camera)",
            ), found
        finally:
            adb.shell("am force-stop org.codeaurora.snapcam 2>/dev/null; "
                       "am force-stop com.android.camera2 2>/dev/null")

    def _find_new_photo(self, adb, marker: str) -> str:
        """Find the newest photo file created after the marker timestamp."""
        search_dirs = [DCIM_PATH, "/sdcard/DCIM", "/sdcard/Pictures"]
        for dp in search_dirs:
            out = adb.shell(
                f"find '{dp}' -maxdepth 1 -newer {marker} "
                f"\\( -name '*.jpg' -o -name '*.jpeg' -o -name '*.png' \\) "
                f"-type f 2>/dev/null | head -1"
            ).stdout.strip()
            if out:
                return out
        return ""

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

    def _verify_latest_photo(self, tc: dict, ctx: PluginContext) -> TestResult:
        """Verify the latest photo on device without taking a new one."""
        tid, tname = tc["id"], tc["name"]
        adb = ctx.adb
        prompt = tc.get("params", {}).get(
            "verify_prompt", "Is the photo clear, not black, not white?"
        )

        # Find the newest photo across DCIM paths
        dcim_paths = [DCIM_PATH, "/sdcard/DCIM", "/sdcard/Pictures"]
        remote_path = ""
        for dp in dcim_paths:
            newest = adb.shell(f"ls -t '{dp}/' 2>/dev/null | head -1").stdout.strip()
            if newest:
                remote_path = f"{dp}/{newest}"
                break

        if not remote_path:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="No photo found on device to verify")

        if not ctx.visual_analyzer:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Visual analyzer not available")

        filename = Path(remote_path).name
        with tempfile.TemporaryDirectory() as tmp:
            local_path = Path(tmp) / filename
            image = None
            if hasattr(adb, "pull"):
                adb.pull(remote_path, str(local_path))
                if local_path.exists() and cv2 is not None:
                    image = cv2.imread(str(local_path))

            if image is None:
                return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                                  message=f"Cannot pull/read {remote_path}")

            analysis = ctx.visual_analyzer.analyze_test_screenshot(image, prompt)

        if analysis.get("pass", False):
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=f"Verified: {analysis.get('reason', '')}")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message=f"LLM rejected: {analysis.get('reason', '')}")
