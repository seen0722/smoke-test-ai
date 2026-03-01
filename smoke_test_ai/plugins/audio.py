import time

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.base import TestPlugin, PluginContext

AUDIO_REMOTE_PATH = "/sdcard/smoke_test_audio.ogg"


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

    def _play_and_check(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        params = tc.get("params", {})
        play_duration = params.get("play_duration", 2)

        # Push audio file
        audio_source = params.get("audio_file")
        if audio_source:
            ctx.adb.push(audio_source, AUDIO_REMOTE_PATH)
        else:
            ctx.adb.shell(
                f"toybox dd if=/dev/urandom of={AUDIO_REMOTE_PATH} bs=1024 count=10"
            )

        try:
            ctx.snippet.mediaPlayAudioFile(AUDIO_REMOTE_PATH)
            time.sleep(play_duration)
            is_playing = ctx.snippet.mediaIsPlaying()
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Audio playback failed: {e}")
        finally:
            try:
                ctx.snippet.mediaStop()
            except Exception:
                pass
            try:
                ctx.adb.shell(f"rm -f {AUDIO_REMOTE_PATH}")
            except Exception:
                pass

        if is_playing:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message="Audio is playing after mediaPlayAudioFile")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message="Audio not playing after mediaPlayAudioFile")
