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
        if action == "volume_control":
            return self._volume_control(test_case, context)
        if action == "microphone_test":
            return self._microphone_test(test_case, context)
        if action == "list_devices":
            return self._list_devices(test_case, context)
        if action == "audio_route":
            return self._audio_route(test_case, context)
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

    def _volume_control(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        try:
            original = ctx.snippet.getMusicVolume()
            max_vol = ctx.snippet.getMusicMaxVolume()
            target = max_vol // 2 if max_vol > 1 else 1
            ctx.snippet.setMusicVolume(target)
            actual = ctx.snippet.getMusicVolume()
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Volume control failed: {e}")
        finally:
            try:
                ctx.snippet.setMusicVolume(original)
            except Exception:
                pass

        if actual == target:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=f"Volume set to {target}/{max_vol} and verified")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message=f"Volume mismatch: set {target}, got {actual}")

    def _microphone_test(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        try:
            ctx.snippet.setMicrophoneMute(True)
            is_muted = ctx.snippet.isMicrophoneMute()
            ctx.snippet.setMicrophoneMute(False)
        except Exception as e:
            try:
                ctx.snippet.setMicrophoneMute(False)
            except Exception:
                pass
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Microphone test failed: {e}")

        if is_muted:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message="Microphone mute/unmute OK")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message="Microphone mute state not reflected")

    def _list_devices(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        try:
            devices = ctx.snippet.getAudioDeviceTypes()
        except Exception as e:
            if "Unknown RPC" in str(e):
                return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                                  message="getAudioDeviceTypes not in installed Snippet APK")
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"getAudioDeviceTypes failed: {e}")

        count = len(devices) if isinstance(devices, list) else 0
        if count > 0:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=f"Found {count} audio devices: {devices}")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message="No audio devices found")

    def _audio_route(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available")
        try:
            route_type = ctx.snippet.mediaGetLiveAudioRouteType()
            route_name = ctx.snippet.mediaGetLiveAudioRouteName()
        except Exception as e:
            if "Unknown RPC" in str(e):
                return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                                  message="Audio route RPC not in installed Snippet APK")
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"Audio route query failed: {e}")

        return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                          message=f"Audio route: {route_name} (type: {route_type})")
