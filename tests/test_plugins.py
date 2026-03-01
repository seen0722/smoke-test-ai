import pytest
from unittest.mock import MagicMock, patch
from smoke_test_ai.plugins.base import TestPlugin, PluginContext
from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.camera import CameraPlugin
from smoke_test_ai.plugins.telephony import TelephonyPlugin
from smoke_test_ai.plugins.wifi import WifiPlugin
from smoke_test_ai.plugins.bluetooth import BluetoothPlugin
from smoke_test_ai.plugins.audio import AudioPlugin
from smoke_test_ai.plugins.network import NetworkPlugin


class DummyPlugin(TestPlugin):
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        return TestResult(
            id=test_case["id"],
            name=test_case["name"],
            status=TestStatus.PASS,
            message="dummy",
        )


@pytest.fixture
def plugin_context():
    return PluginContext(
        adb=MagicMock(),
        settings={},
        device_capabilities={},
    )


class TestPluginBase:
    def test_plugin_context_defaults(self):
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={})
        assert ctx.snippet is None
        assert ctx.peer_snippet is None
        assert ctx.visual_analyzer is None

    def test_dummy_plugin_executes(self, plugin_context):
        plugin = DummyPlugin()
        tc = {"id": "t1", "name": "Test", "type": "dummy"}
        result = plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.PASS
        assert result.message == "dummy"

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            TestPlugin()


class TestCameraPlugin:
    @pytest.fixture
    def camera_plugin(self):
        return CameraPlugin()

    def test_capture_photo_pass(self, camera_plugin, plugin_context):
        adb = plugin_context.adb
        ok = MagicMock(stdout="", returncode=0)
        adb.shell.side_effect = [
            ok,                                                     # mkdir -p
            MagicMock(stdout="IMG_old.jpg\n", returncode=0),       # baseline ls path1
            MagicMock(stdout="\n", returncode=0),                  # baseline ls path2
            MagicMock(stdout="\n", returncode=0),                  # baseline ls path3
            ok,                                                     # force-stop
            MagicMock(stdout="Starting: Intent\n", returncode=0),  # am start (direct launcher)
            ok,                                                     # ENTER (dismiss tutorial)
            ok,                                                     # KEYCODE_VOLUME_DOWN
            MagicMock(stdout="IMG_new.jpg\n", returncode=0),       # after ls path1
            MagicMock(stdout="1234567\n", returncode=0),           # stat size
        ]
        tc = {
            "id": "cam1", "name": "Camera", "type": "camera",
            "action": "capture_photo",
            "params": {"camera": "back", "wait_seconds": 0},
        }
        result = camera_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.PASS
        assert "IMG_new.jpg" in result.message
        assert "1234567" in result.message

    def test_capture_photo_no_new_file(self, camera_plugin, plugin_context):
        adb = plugin_context.adb
        ok = MagicMock(stdout="", returncode=0)
        adb.shell.side_effect = [
            ok,                                                     # mkdir -p
            MagicMock(stdout="IMG_old.jpg\n", returncode=0),       # baseline ls path1
            MagicMock(stdout="\n", returncode=0),                  # baseline ls path2
            MagicMock(stdout="\n", returncode=0),                  # baseline ls path3
            ok,                                                     # force-stop
            MagicMock(stdout="Starting: Intent\n", returncode=0),  # am start (direct launcher)
            ok,                                                     # ENTER (dismiss tutorial)
            ok,                                                     # KEYCODE_VOLUME_DOWN
            MagicMock(stdout="IMG_old.jpg\n", returncode=0),       # after ls path1 (same)
            MagicMock(stdout="\n", returncode=0),                  # after ls path2 (same)
            MagicMock(stdout="\n", returncode=0),                  # after ls path3 (same)
        ]
        tc = {
            "id": "cam1", "name": "Camera", "type": "camera",
            "action": "capture_photo",
            "params": {"camera": "back", "wait_seconds": 0},
        }
        result = camera_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.FAIL

    def test_unknown_action_errors(self, camera_plugin, plugin_context):
        tc = {
            "id": "cam1", "name": "Camera", "type": "camera",
            "action": "unknown_action", "params": {},
        }
        result = camera_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.ERROR

    def test_capture_and_verify_no_analyzer(self, camera_plugin, plugin_context):
        """capture_and_verify without visual_analyzer returns capture result."""
        adb = plugin_context.adb
        ok = MagicMock(stdout="", returncode=0)
        adb.shell.side_effect = [
            ok,                                                     # mkdir -p
            MagicMock(stdout="IMG_old.jpg\n", returncode=0),       # baseline ls path1
            MagicMock(stdout="\n", returncode=0),                  # baseline ls path2
            MagicMock(stdout="\n", returncode=0),                  # baseline ls path3
            ok,                                                     # force-stop
            MagicMock(stdout="Starting: Intent\n", returncode=0),  # am start (direct launcher)
            ok,                                                     # ENTER (dismiss tutorial)
            ok,                                                     # KEYCODE_VOLUME_DOWN
            MagicMock(stdout="IMG_new.jpg\n", returncode=0),       # after ls path1
            MagicMock(stdout="5000\n", returncode=0),              # stat size
        ]
        tc = {
            "id": "cv1", "name": "Verify", "type": "camera",
            "action": "capture_and_verify",
            "params": {"camera": "back", "wait_seconds": 0},
        }
        result = camera_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.PASS
        assert "IMG_new.jpg" in result.message

    def test_capture_and_verify_llm_pass(self, camera_plugin):
        """capture_and_verify with LLM returning pass."""
        analyzer = MagicMock()
        analyzer.analyze_test_screenshot.return_value = {"pass": True, "reason": "clear image"}
        adb = MagicMock()
        ok = MagicMock(stdout="", returncode=0)
        adb.shell.side_effect = [
            ok,                                                     # mkdir -p
            MagicMock(stdout="IMG_old.jpg\n", returncode=0),       # baseline ls path1
            MagicMock(stdout="\n", returncode=0),                  # baseline ls path2
            MagicMock(stdout="\n", returncode=0),                  # baseline ls path3
            ok,                                                     # force-stop
            MagicMock(stdout="Starting: Intent\n", returncode=0),  # am start (direct launcher)
            ok,                                                     # ENTER (dismiss tutorial)
            ok,                                                     # KEYCODE_VOLUME_DOWN
            MagicMock(stdout="IMG_new.jpg\n", returncode=0),       # after ls path1
            MagicMock(stdout="5000\n", returncode=0),              # stat size
        ]
        # Mock adb.pull to actually create the file
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        def fake_pull(remote, local):
            Path(local).write_bytes(b"\xff\xd8fake-jpeg-data")

        adb.pull = fake_pull
        ctx = PluginContext(
            adb=adb, settings={}, device_capabilities={},
            visual_analyzer=analyzer,
        )
        tc = {
            "id": "cv2", "name": "Verify LLM", "type": "camera",
            "action": "capture_and_verify",
            "params": {"camera": "back", "wait_seconds": 0, "verify_prompt": "Is it clear?"},
        }
        with patch("smoke_test_ai.plugins.camera.cv2") as mock_cv2:
            mock_cv2.imread.return_value = MagicMock()  # fake image array
            result = camera_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        assert "Verified" in result.message

    def test_capture_and_verify_llm_fail(self, camera_plugin):
        """capture_and_verify with LLM returning fail."""
        analyzer = MagicMock()
        analyzer.analyze_test_screenshot.return_value = {"pass": False, "reason": "all black"}
        adb = MagicMock()
        ok = MagicMock(stdout="", returncode=0)
        adb.shell.side_effect = [
            ok,                                                     # mkdir -p
            MagicMock(stdout="IMG_old.jpg\n", returncode=0),       # baseline path1
            MagicMock(stdout="\n", returncode=0),                  # baseline path2
            MagicMock(stdout="\n", returncode=0),                  # baseline path3
            ok,                                                     # force-stop
            MagicMock(stdout="Starting: Intent\n", returncode=0),  # am start (direct launcher)
            ok,                                                     # ENTER (dismiss tutorial)
            ok,                                                     # KEYCODE_VOLUME_DOWN
            MagicMock(stdout="IMG_new.jpg\n", returncode=0),       # after ls path1
            MagicMock(stdout="5000\n", returncode=0),              # stat size
        ]

        def fake_pull(remote, local):
            from pathlib import Path
            Path(local).write_bytes(b"\xff\xd8fake-jpeg-data")

        adb.pull = fake_pull
        ctx = PluginContext(
            adb=adb, settings={}, device_capabilities={},
            visual_analyzer=analyzer,
        )
        tc = {
            "id": "cv3", "name": "Verify Fail", "type": "camera",
            "action": "capture_and_verify",
            "params": {"camera": "back", "wait_seconds": 0},
        }
        from unittest.mock import patch
        with patch("smoke_test_ai.plugins.camera.cv2") as mock_cv2:
            mock_cv2.imread.return_value = MagicMock()
            result = camera_plugin.execute(tc, ctx)
        assert result.status == TestStatus.FAIL
        assert "LLM rejected" in result.message


class TestTelephonyPlugin:
    @pytest.fixture
    def telephony_plugin(self):
        return TelephonyPlugin()

    def test_send_sms_pass(self, telephony_plugin):
        snippet = MagicMock()
        snippet.sendSms.return_value = None  # no error = success
        ctx = PluginContext(
            adb=MagicMock(), settings={}, device_capabilities={},
            snippet=snippet,
        )
        tc = {
            "id": "sms1", "name": "SMS Send", "type": "telephony",
            "action": "send_sms",
            "params": {"to_number": "+886900000000", "body": "test msg"},
        }
        result = telephony_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        snippet.sendSms.assert_called_once_with("+886900000000", "test msg")

    def test_send_sms_no_snippet(self, telephony_plugin, plugin_context):
        tc = {
            "id": "sms1", "name": "SMS Send", "type": "telephony",
            "action": "send_sms",
            "params": {"to_number": "+886900000000", "body": "test"},
        }
        result = telephony_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.SKIP
        assert "snippet" in result.message.lower()

    def test_receive_sms_pass(self, telephony_plugin):
        dut_snippet = MagicMock()
        dut_snippet.waitForSms.return_value = {
            "OriginatingAddress": "+886900000000",
            "MessageBody": "smoke-test-inbound-123",
        }
        peer_snippet = MagicMock()
        ctx = PluginContext(
            adb=MagicMock(), settings={},
            device_capabilities={},
            snippet=dut_snippet, peer_snippet=peer_snippet,
        )
        ctx.adb.serial = "DUT_SERIAL"
        ctx.settings = {"device": {"phone_number": "+886912345678"}}
        tc = {
            "id": "sms2", "name": "SMS Receive", "type": "telephony",
            "action": "receive_sms",
            "params": {"body": "smoke-test-inbound", "timeout": 10},
        }
        result = telephony_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        dut_snippet.asyncWaitForSms.assert_called_once_with("sms_receive_cb")
        peer_snippet.sendSms.assert_called_once_with("+886912345678", "smoke-test-inbound")
        dut_snippet.waitForSms.assert_called_once_with(10000)

    def test_receive_sms_no_phone_number(self, telephony_plugin):
        ctx = PluginContext(
            adb=MagicMock(), settings={}, device_capabilities={},
            snippet=MagicMock(), peer_snippet=MagicMock(),
        )
        tc = {
            "id": "sms2", "name": "SMS Receive", "type": "telephony",
            "action": "receive_sms",
            "params": {"body": "test", "timeout": 10},
        }
        result = telephony_plugin.execute(tc, ctx)
        assert result.status == TestStatus.SKIP
        assert "phone_number" in result.message.lower()

    def test_receive_sms_no_peer(self, telephony_plugin):
        ctx = PluginContext(
            adb=MagicMock(), settings={}, device_capabilities={},
            snippet=MagicMock(), peer_snippet=None,
        )
        tc = {
            "id": "sms2", "name": "SMS Receive", "type": "telephony",
            "action": "receive_sms",
            "params": {"body": "test", "timeout": 10},
        }
        result = telephony_plugin.execute(tc, ctx)
        assert result.status == TestStatus.SKIP
        assert "peer" in result.message.lower()

    def test_check_signal_pass(self, telephony_plugin):
        snippet = MagicMock()
        snippet.getDataNetworkType.return_value = 13  # LTE
        ctx = PluginContext(
            adb=MagicMock(), settings={}, device_capabilities={},
            snippet=snippet,
        )
        tc = {
            "id": "sig1", "name": "Signal", "type": "telephony",
            "action": "check_signal",
            "params": {"expected_data_type": "LTE|NR"},
        }
        result = telephony_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS

    def test_unknown_action_errors(self, telephony_plugin, plugin_context):
        tc = {
            "id": "t1", "name": "Bad", "type": "telephony",
            "action": "bad_action", "params": {},
        }
        result = telephony_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.ERROR

    def test_make_call_pass(self, telephony_plugin):
        snippet = MagicMock()
        snippet.telephonyGetCallState.return_value = 2  # OFFHOOK
        ctx = PluginContext(
            adb=MagicMock(), settings={}, device_capabilities={},
            snippet=snippet,
        )
        tc = {
            "id": "call1", "name": "Call", "type": "telephony",
            "action": "make_call",
            "params": {"to_number": "+886900000000", "call_duration": 0},
        }
        with patch("smoke_test_ai.plugins.telephony.time.sleep"):
            result = telephony_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        snippet.telephonyStartCall.assert_called_once_with("+886900000000")
        snippet.telephonyEndCall.assert_called_once()

    def test_make_call_no_snippet(self, telephony_plugin, plugin_context):
        tc = {
            "id": "call1", "name": "Call", "type": "telephony",
            "action": "make_call",
            "params": {"to_number": "+886900000000"},
        }
        result = telephony_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.SKIP

    def test_make_call_no_number(self, telephony_plugin):
        ctx = PluginContext(
            adb=MagicMock(), settings={}, device_capabilities={},
            snippet=MagicMock(),
        )
        tc = {
            "id": "call1", "name": "Call", "type": "telephony",
            "action": "make_call",
            "params": {},
        }
        result = telephony_plugin.execute(tc, ctx)
        assert result.status == TestStatus.SKIP
        assert "to_number" in result.message

    def test_make_call_cleanup_on_error(self, telephony_plugin):
        snippet = MagicMock()
        snippet.telephonyGetCallState.side_effect = RuntimeError("fail")
        ctx = PluginContext(
            adb=MagicMock(), settings={}, device_capabilities={},
            snippet=snippet,
        )
        tc = {
            "id": "call1", "name": "Call", "type": "telephony",
            "action": "make_call",
            "params": {"to_number": "+886900000000", "call_duration": 0},
        }
        with patch("smoke_test_ai.plugins.telephony.time.sleep"):
            result = telephony_plugin.execute(tc, ctx)
        assert result.status == TestStatus.FAIL
        snippet.telephonyEndCall.assert_called_once()


class TestWifiPlugin:
    @pytest.fixture
    def wifi_plugin(self):
        return WifiPlugin()

    def test_scan_pass(self, wifi_plugin):
        snippet = MagicMock()
        snippet.wifiScanAndGetResults.return_value = [
            {"SSID": "TestAP", "BSSID": "aa:bb:cc:dd:ee:ff"},
            {"SSID": "Office", "BSSID": "11:22:33:44:55:66"},
        ]
        ctx = PluginContext(
            adb=MagicMock(), settings={}, device_capabilities={},
            snippet=snippet,
        )
        tc = {"id": "w1", "name": "WiFi Scan", "type": "wifi", "action": "scan"}
        result = wifi_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        assert "2" in result.message
        snippet.wifiScanAndGetResults.assert_called_once()

    def test_scan_no_snippet(self, wifi_plugin, plugin_context):
        tc = {"id": "w1", "name": "WiFi Scan", "type": "wifi", "action": "scan"}
        result = wifi_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.SKIP

    def test_scan_for_ssid_found(self, wifi_plugin):
        snippet = MagicMock()
        snippet.wifiScanAndGetResults.return_value = [
            {"SSID": "TestAP", "BSSID": "aa:bb:cc:dd:ee:ff"},
            {"SSID": "Target", "BSSID": "11:22:33:44:55:66"},
        ]
        ctx = PluginContext(
            adb=MagicMock(), settings={}, device_capabilities={},
            snippet=snippet,
        )
        tc = {
            "id": "w2", "name": "WiFi SSID", "type": "wifi",
            "action": "scan_for_ssid",
            "params": {"expected_ssid": "Target"},
        }
        result = wifi_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        assert "Target" in result.message

    def test_scan_for_ssid_not_found(self, wifi_plugin):
        snippet = MagicMock()
        snippet.wifiScanAndGetResults.return_value = [
            {"SSID": "OtherAP", "BSSID": "aa:bb:cc:dd:ee:ff"},
        ]
        ctx = PluginContext(
            adb=MagicMock(), settings={}, device_capabilities={},
            snippet=snippet,
        )
        tc = {
            "id": "w2", "name": "WiFi SSID", "type": "wifi",
            "action": "scan_for_ssid",
            "params": {"expected_ssid": "Target"},
        }
        result = wifi_plugin.execute(tc, ctx)
        assert result.status == TestStatus.FAIL
        assert "Target" in result.message


class TestBluetoothPlugin:
    @pytest.fixture
    def bt_plugin(self):
        return BluetoothPlugin()

    def test_ble_scan_pass(self, bt_plugin):
        snippet = MagicMock()
        handler = MagicMock()
        handler.callback_id = "1-0"
        # Simulate returning 1 event then timeout
        event = MagicMock()
        event.data = {"name": "Device1", "address": "AA:BB:CC:DD:EE:FF"}
        handler.waitAndGet.side_effect = [event, TimeoutError("no more")]
        snippet.bleStartScan.return_value = handler
        ctx = PluginContext(
            adb=MagicMock(), settings={}, device_capabilities={},
            snippet=snippet,
        )
        tc = {
            "id": "bt1", "name": "BLE Scan", "type": "bluetooth",
            "action": "ble_scan",
            "params": {"scan_duration": 0},
        }
        with patch("smoke_test_ai.plugins.bluetooth.time.sleep"):
            result = bt_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        snippet.bleStartScan.assert_called_once_with([], {})
        snippet.bleStopScan.assert_called_once_with("1-0")

    def test_ble_scan_no_devices(self, bt_plugin):
        snippet = MagicMock()
        handler = MagicMock()
        handler.callback_id = "1-0"
        handler.waitAndGet.side_effect = TimeoutError("no events")
        snippet.bleStartScan.return_value = handler
        ctx = PluginContext(
            adb=MagicMock(), settings={}, device_capabilities={},
            snippet=snippet,
        )
        tc = {
            "id": "bt1", "name": "BLE Scan", "type": "bluetooth",
            "action": "ble_scan",
            "params": {"scan_duration": 0},
        }
        with patch("smoke_test_ai.plugins.bluetooth.time.sleep"):
            result = bt_plugin.execute(tc, ctx)
        assert result.status == TestStatus.FAIL
        snippet.bleStopScan.assert_called_once_with("1-0")

    def test_ble_scan_no_snippet(self, bt_plugin, plugin_context):
        tc = {
            "id": "bt1", "name": "BLE Scan", "type": "bluetooth",
            "action": "ble_scan", "params": {},
        }
        result = bt_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.SKIP

    def test_ble_scan_cleanup_on_error(self, bt_plugin):
        """When bleStartScan raises, bleStopScan is still attempted (handler is None, so
        the stop is skipped gracefully since no scan was started)."""
        snippet = MagicMock()
        snippet.bleStartScan.side_effect = RuntimeError("scan error")
        ctx = PluginContext(
            adb=MagicMock(), settings={}, device_capabilities={},
            snippet=snippet,
        )
        tc = {
            "id": "bt1", "name": "BLE Scan", "type": "bluetooth",
            "action": "ble_scan",
            "params": {"scan_duration": 0},
        }
        with patch("smoke_test_ai.plugins.bluetooth.time.sleep"):
            result = bt_plugin.execute(tc, ctx)
        assert result.status == TestStatus.FAIL
        # bleStopScan not called because bleStartScan failed (handler=None, no callback_id)
        snippet.bleStopScan.assert_not_called()


class TestAudioPlugin:
    @pytest.fixture
    def audio_plugin(self):
        return AudioPlugin()

    def test_play_and_check_pass(self, audio_plugin):
        snippet = MagicMock()
        snippet.isMusicActive.return_value = True
        adb = MagicMock()
        adb.shell.return_value = MagicMock(stdout="exists\n")
        ctx = PluginContext(
            adb=adb, settings={}, device_capabilities={},
            snippet=snippet,
        )
        tc = {
            "id": "a1", "name": "Audio", "type": "audio",
            "action": "play_and_check",
            "params": {"play_duration": 0},
        }
        with patch("smoke_test_ai.plugins.audio.time.sleep"):
            result = audio_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        snippet.mediaPlayAudioFile.assert_called_once()
        snippet.mediaStop.assert_called_once()

    def test_play_and_check_not_playing(self, audio_plugin):
        snippet = MagicMock()
        snippet.isMusicActive.return_value = False
        adb = MagicMock()
        adb.shell.return_value = MagicMock(stdout="exists\n")
        ctx = PluginContext(
            adb=adb, settings={}, device_capabilities={},
            snippet=snippet,
        )
        tc = {
            "id": "a1", "name": "Audio", "type": "audio",
            "action": "play_and_check",
            "params": {"play_duration": 0},
        }
        with patch("smoke_test_ai.plugins.audio.time.sleep"):
            result = audio_plugin.execute(tc, ctx)
        assert result.status == TestStatus.FAIL
        assert "not playing" in result.message.lower()

    def test_play_and_check_no_snippet(self, audio_plugin, plugin_context):
        tc = {
            "id": "a1", "name": "Audio", "type": "audio",
            "action": "play_and_check", "params": {},
        }
        result = audio_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.SKIP

    def test_play_and_check_cleanup(self, audio_plugin):
        snippet = MagicMock()
        snippet.isMusicActive.side_effect = RuntimeError("fail")
        adb = MagicMock()
        adb.shell.return_value = MagicMock(stdout="exists\n")
        ctx = PluginContext(
            adb=adb, settings={}, device_capabilities={},
            snippet=snippet,
        )
        tc = {
            "id": "a1", "name": "Audio", "type": "audio",
            "action": "play_and_check",
            "params": {"play_duration": 0},
        }
        with patch("smoke_test_ai.plugins.audio.time.sleep"):
            result = audio_plugin.execute(tc, ctx)
        assert result.status == TestStatus.FAIL
        snippet.mediaStop.assert_called_once()


class TestNetworkPlugin:
    @pytest.fixture
    def net_plugin(self):
        return NetworkPlugin()

    def test_http_download_pass(self, net_plugin):
        adb = MagicMock()
        adb.shell.return_value = MagicMock(stdout="204 0.000\n")
        ctx = PluginContext(
            adb=adb, settings={}, device_capabilities={},
        )
        tc = {
            "id": "n1", "name": "Download", "type": "network",
            "action": "http_download",
            "params": {"network_mode": "wifi"},
        }
        result = net_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        assert "204" in result.message

    def test_http_download_fail_status(self, net_plugin):
        adb = MagicMock()
        adb.shell.return_value = MagicMock(stdout="404 0.000\n")
        ctx = PluginContext(
            adb=adb, settings={}, device_capabilities={},
        )
        tc = {
            "id": "n1", "name": "Download", "type": "network",
            "action": "http_download",
            "params": {"network_mode": "auto"},
        }
        result = net_plugin.execute(tc, ctx)
        assert result.status == TestStatus.FAIL
        assert "404" in result.message

    def test_http_download_mobile_mode(self, net_plugin):
        adb = MagicMock()
        adb.shell.return_value = MagicMock(stdout="200 100000.000\n")
        ctx = PluginContext(
            adb=adb, settings={}, device_capabilities={},
        )
        tc = {
            "id": "n1", "name": "Download", "type": "network",
            "action": "http_download",
            "params": {"network_mode": "mobile"},
        }
        with patch("smoke_test_ai.plugins.network.time.sleep"):
            result = net_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        # Verify wifi disable/enable were called
        calls = [str(c) for c in adb.shell.call_args_list]
        assert any("svc wifi disable" in c for c in calls)
        assert any("svc wifi enable" in c for c in calls)

    def test_http_download_wifi_restore_on_error(self, net_plugin):
        adb = MagicMock()
        # First call is wifi disable, second call (curl) raises
        call_count = 0

        def shell_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # svc wifi disable
                return MagicMock(stdout="")
            if call_count == 2:  # curl
                raise RuntimeError("connection refused")
            return MagicMock(stdout="")  # svc wifi enable

        adb.shell.side_effect = shell_side_effect
        ctx = PluginContext(
            adb=adb, settings={}, device_capabilities={},
        )
        tc = {
            "id": "n1", "name": "Download", "type": "network",
            "action": "http_download",
            "params": {"network_mode": "mobile"},
        }
        with patch("smoke_test_ai.plugins.network.time.sleep"):
            result = net_plugin.execute(tc, ctx)
        assert result.status == TestStatus.FAIL
        # Verify wifi was re-enabled despite error
        calls = [str(c) for c in adb.shell.call_args_list]
        assert any("svc wifi enable" in c for c in calls)

    def test_tcp_connect_pass(self, net_plugin):
        snippet = MagicMock()
        snippet.networkIsTcpConnectable.return_value = True
        ctx = PluginContext(
            adb=MagicMock(), settings={}, device_capabilities={},
            snippet=snippet,
        )
        tc = {
            "id": "n2", "name": "TCP", "type": "network",
            "action": "tcp_connect",
            "params": {"host": "8.8.8.8", "port": 443},
        }
        result = net_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        snippet.networkIsTcpConnectable.assert_called_once_with("8.8.8.8", 443)

    def test_tcp_connect_no_snippet(self, net_plugin, plugin_context):
        tc = {
            "id": "n2", "name": "TCP", "type": "network",
            "action": "tcp_connect",
            "params": {"host": "8.8.8.8", "port": 443},
        }
        result = net_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.SKIP
