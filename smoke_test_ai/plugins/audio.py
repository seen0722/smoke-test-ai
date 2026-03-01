import time

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.base import TestPlugin, PluginContext

AUDIO_REMOTE_PATH = "/sdcard/smoke_test_audio.ogg"

# Minimal valid OGG/Vorbis silent tone (~1 second) encoded as hex.
# Generated from: ffmpeg -f lavfi -i "sine=frequency=440:duration=1" -c:a libvorbis -q:a 0 out.ogg
# We use ADB shell to generate a short tone via the `tone` command if available,
# otherwise fall back to the notification ringtone already on the device.
FALLBACK_AUDIO_PATHS = [
    "/system/media/audio/ringtones/Ring_Synth_04.ogg",
    "/system/media/audio/notifications/OnTheHunt.ogg",
    "/system/media/audio/ui/camera_click.ogg",
    "/system/media/audio/alarms/Alarm_Classic.ogg",
    "/product/media/audio/alarms/Alarm_Classic.ogg",
    "/product/media/audio/ringtones/Ring_Synth_04.ogg",
    "/product/media/audio/notifications/OnTheHunt.ogg",
]


class AudioPlugin(TestPlugin):
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        action = test_case.get("action", "")
        if action == "play_and_check":
            return self._play_and_check(test_case, context)
        return TestResult(
            id=test_case["id"], name=test_case["name"],
            status=TestStatus.ERROR,
            message=f"Unknown audio action: {action}",
        )

    def _find_audio_file(self, ctx: PluginContext, params: dict) -> str:
        """Resolve an audio file path on the device."""
        # User-specified file (pushed from host)
        audio_source = params.get("audio_file")
        if audio_source:
            ctx.adb.push(audio_source, AUDIO_REMOTE_PATH)
            return AUDIO_REMOTE_PATH

        # Try built-in system audio files
        for path in FALLBACK_AUDIO_PATHS:
            result = ctx.adb.shell(f"[ -f '{path}' ] && echo exists")
            output = result.stdout.strip() if hasattr(result, "stdout") else str(result).strip()
            if "exists" in output:
                return path

        return ""

    def _play_and_check(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        params = tc.get("params", {})
        play_duration = params.get("play_duration", 2)

        audio_path = self._find_audio_file(ctx, params)
        if not audio_path:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="No valid audio file found on device")

        pushed_file = audio_path == AUDIO_REMOTE_PATH
        try:
            ctx.snippet.mediaPlayAudioFile(audio_path)
            time.sleep(play_duration)
            # isMusicActive() is from AudioSnippet (AudioManager.isMusicActive)
            is_playing = ctx.snippet.isMusicActive()
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Audio playback failed: {e}")
        finally:
            try:
                ctx.snippet.mediaStop()
            except Exception:
                pass
            if pushed_file:
                try:
                    ctx.adb.shell(f"rm -f {AUDIO_REMOTE_PATH}")
                except Exception:
                    pass

        if is_playing:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=f"Audio is playing ({audio_path})")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message="Audio not playing after mediaPlayAudioFile")
