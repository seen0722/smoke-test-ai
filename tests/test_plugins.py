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
            ok,                                                     # finally: force-stop cleanup
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
            ok,                                                     # finally: force-stop cleanup
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

    def test_capture_front_skip_single_camera(self, camera_plugin, plugin_context):
        """Front camera test should SKIP when device has only 1 camera."""
        adb = plugin_context.adb
        adb.shell.return_value = MagicMock(
            stdout="Number of camera devices: 1\n", returncode=0,
        )
        tc = {
            "id": "cam_f1", "name": "Front Camera", "type": "camera",
            "action": "capture_photo",
            "params": {"camera": "front", "wait_seconds": 0},
        }
        result = camera_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.SKIP
        assert "1 camera" in result.message
        # Only 1 shell call (dumpsys), no force-stop since camera was never launched
        adb.shell.assert_called_once()

    def test_capture_front_pass_dual_camera(self, camera_plugin, plugin_context):
        """Front camera test should proceed normally when device has 2 cameras."""
        adb = plugin_context.adb
        ok = MagicMock(stdout="", returncode=0)
        adb.shell.side_effect = [
            MagicMock(stdout="Number of camera devices: 2\n", returncode=0),  # dumpsys
            ok,                                                     # mkdir -p
            MagicMock(stdout="IMG_old.jpg\n", returncode=0),       # baseline ls path1
            MagicMock(stdout="\n", returncode=0),                  # baseline ls path2
            MagicMock(stdout="\n", returncode=0),                  # baseline ls path3
            ok,                                                     # force-stop
            MagicMock(stdout="Starting: Intent\n", returncode=0),  # am start (direct launcher)
            ok,                                                     # ENTER (dismiss tutorial)
            ok,                                                     # KEYCODE_VOLUME_DOWN
            MagicMock(stdout="IMG_front.jpg\n", returncode=0),     # after ls path1
            MagicMock(stdout="2048000\n", returncode=0),           # stat size
            ok,                                                     # finally: force-stop cleanup
        ]
        tc = {
            "id": "cam_f2", "name": "Front Camera", "type": "camera",
            "action": "capture_photo",
            "params": {"camera": "front", "wait_seconds": 0},
        }
        result = camera_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.PASS
        assert "IMG_front.jpg" in result.message
        assert "front camera" in result.message

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
            ok,                                                     # finally: force-stop cleanup
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
            ok,                                                     # finally: force-stop cleanup
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
            ok,                                                     # finally: force-stop cleanup
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
        snippet.getTelephonyCallState.return_value = 2  # OFFHOOK
        adb = MagicMock()
        ctx = PluginContext(
            adb=adb, settings={}, device_capabilities={},
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
        # Dial via ADB intent, not snippet
        calls = [str(c) for c in adb.shell.call_args_list]
        assert any("android.intent.action.CALL" in c and "+886900000000" in c for c in calls)
        # Hang up via ADB keyevent
        assert any("KEYCODE_ENDCALL" in c for c in calls)

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
        snippet.getTelephonyCallState.side_effect = RuntimeError("fail")
        adb = MagicMock()
        ctx = PluginContext(
            adb=adb, settings={}, device_capabilities={},
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
        # Hang up via ADB even on error
        calls = [str(c) for c in adb.shell.call_args_list]
        assert any("KEYCODE_ENDCALL" in c for c in calls)

    def test_check_voice_type_pass(self, telephony_plugin):
        snippet = MagicMock()
        snippet.getVoiceNetworkType.return_value = 13  # LTE
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "vt1", "name": "Voice Type", "type": "telephony", "action": "check_voice_type"}
        result = telephony_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        assert "LTE" in result.message

    def test_check_voice_type_unknown(self, telephony_plugin):
        snippet = MagicMock()
        snippet.getVoiceNetworkType.return_value = 0  # UNKNOWN
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "vt1", "name": "Voice Type", "type": "telephony", "action": "check_voice_type"}
        result = telephony_plugin.execute(tc, ctx)
        assert result.status == TestStatus.FAIL

    def test_sim_info_pass(self, telephony_plugin):
        snippet = MagicMock()
        snippet.getLine1Number.return_value = "+886912345678"
        snippet.getSubscriberId.return_value = "466920123456789"
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "si1", "name": "SIM Info", "type": "telephony", "action": "sim_info"}
        result = telephony_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        assert "+886912345678" in result.message
        # IMSI should be masked
        assert "46692" in result.message
        assert "0123456789" not in result.message

    def test_sim_info_empty(self, telephony_plugin):
        snippet = MagicMock()
        snippet.getLine1Number.return_value = ""
        snippet.getSubscriberId.return_value = ""
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "si1", "name": "SIM Info", "type": "telephony", "action": "sim_info"}
        result = telephony_plugin.execute(tc, ctx)
        assert result.status == TestStatus.FAIL


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

    def test_toggle_pass(self, wifi_plugin):
        snippet = MagicMock()
        snippet.wifiIsEnabled.return_value = True
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "w3", "name": "WiFi Toggle", "type": "wifi", "action": "toggle"}
        with patch("smoke_test_ai.plugins.wifi.time.sleep"):
            result = wifi_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        snippet.wifiDisable.assert_called_once()
        snippet.wifiEnable.assert_called_once()

    def test_connection_info_pass(self, wifi_plugin):
        snippet = MagicMock()
        snippet.wifiGetConnectionInfo.return_value = {"SSID": "TestAP", "rssi": -50, "linkSpeed": 72}
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "w4", "name": "WiFi Info", "type": "wifi", "action": "connection_info", "params": {"min_rssi": -80}}
        result = wifi_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        assert "TestAP" in result.message

    def test_connection_info_weak_signal(self, wifi_plugin):
        snippet = MagicMock()
        snippet.wifiGetConnectionInfo.return_value = {"SSID": "WeakAP", "rssi": -90, "linkSpeed": 10}
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "w4", "name": "WiFi Info", "type": "wifi", "action": "connection_info", "params": {"min_rssi": -80}}
        result = wifi_plugin.execute(tc, ctx)
        assert result.status == TestStatus.FAIL
        assert "-90" in result.message

    def test_dhcp_info_pass(self, wifi_plugin):
        snippet = MagicMock()
        snippet.wifiGetDhcpInfo.return_value = {"ipAddress": 3232235876, "gateway": 3232235777, "dns1": 134744072}
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "w5", "name": "DHCP", "type": "wifi", "action": "dhcp_info"}
        result = wifi_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS

    def test_dhcp_info_no_ip(self, wifi_plugin):
        snippet = MagicMock()
        snippet.wifiGetDhcpInfo.return_value = {"ipAddress": 0, "gateway": 0, "dns1": 0}
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "w5", "name": "DHCP", "type": "wifi", "action": "dhcp_info"}
        result = wifi_plugin.execute(tc, ctx)
        assert result.status == TestStatus.FAIL

    def test_capability_check_5ghz(self, wifi_plugin):
        snippet = MagicMock()
        snippet.wifiIs5GHzBandSupported.return_value = True
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "w6", "name": "5GHz", "type": "wifi", "action": "is_5ghz_supported"}
        result = wifi_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        assert "5GHz" in result.message

    def test_hotspot_pass(self, wifi_plugin):
        snippet = MagicMock()
        snippet.wifiIsApEnabled.return_value = True
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "w7", "name": "Hotspot", "type": "wifi", "action": "hotspot"}
        with patch("smoke_test_ai.plugins.wifi.time.sleep"):
            result = wifi_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS


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

    def test_toggle_pass(self, bt_plugin):
        snippet = MagicMock()
        snippet.btIsEnabled.return_value = True
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "bt2", "name": "BT Toggle", "type": "bluetooth", "action": "toggle"}
        with patch("smoke_test_ai.plugins.bluetooth.time.sleep"):
            result = bt_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        snippet.btDisable.assert_called_once()
        snippet.btEnable.assert_called_once()

    def test_classic_scan_pass(self, bt_plugin):
        snippet = MagicMock()
        snippet.btDiscoverAndGetResults.return_value = [{"name": "Speaker", "address": "AA:BB:CC:DD:EE:FF"}]
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "bt3", "name": "Classic Scan", "type": "bluetooth", "action": "classic_scan"}
        result = bt_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        assert "1" in result.message

    def test_adapter_info_pass(self, bt_plugin):
        snippet = MagicMock()
        snippet.btGetName.return_value = "MyDevice"
        snippet.btGetAddress.return_value = "AA:BB:CC:DD:EE:FF"
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "bt4", "name": "Adapter Info", "type": "bluetooth", "action": "adapter_info"}
        result = bt_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        assert "MyDevice" in result.message

    def test_paired_devices(self, bt_plugin):
        snippet = MagicMock()
        snippet.btGetPairedDevices.return_value = []
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "bt5", "name": "Paired", "type": "bluetooth", "action": "paired_devices"}
        result = bt_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS

    def test_ble_advertise_pass(self, bt_plugin):
        snippet = MagicMock()
        handler = MagicMock()
        handler.callback_id = "adv-1"
        snippet.bleStartAdvertising.return_value = handler
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "bt6", "name": "BLE Adv", "type": "bluetooth", "action": "ble_advertise", "params": {"duration": 0}}
        with patch("smoke_test_ai.plugins.bluetooth.time.sleep"):
            result = bt_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        snippet.bleStopAdvertising.assert_called_once_with("adv-1")

    def test_le_audio_supported(self, bt_plugin):
        snippet = MagicMock()
        snippet.btIsLeAudioSupported.return_value = False
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "bt7", "name": "LE Audio", "type": "bluetooth", "action": "le_audio_supported"}
        result = bt_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        assert "not supported" in result.message


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

    def test_volume_control_pass(self, audio_plugin):
        snippet = MagicMock()
        snippet.getMusicVolume.return_value = 7
        snippet.getMusicMaxVolume.return_value = 15
        snippet.setMusicVolume.return_value = None
        # After set, readback returns target (15//2 = 7)
        snippet.getMusicVolume.side_effect = [7, 7]  # original, after set
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "a2", "name": "Volume", "type": "audio", "action": "volume_control"}
        result = audio_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS

    def test_microphone_test_pass(self, audio_plugin):
        snippet = MagicMock()
        snippet.isMicrophoneMute.return_value = True
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "a3", "name": "Mic", "type": "audio", "action": "microphone_test"}
        result = audio_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        assert snippet.setMicrophoneMute.call_count == 2  # mute + unmute

    def test_list_devices_pass(self, audio_plugin):
        snippet = MagicMock()
        snippet.getAudioDeviceTypes.return_value = ["speaker", "earpiece"]
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "a4", "name": "Devices", "type": "audio", "action": "list_devices"}
        result = audio_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        assert "2" in result.message

    def test_list_devices_empty(self, audio_plugin):
        snippet = MagicMock()
        snippet.getAudioDeviceTypes.return_value = []
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "a4", "name": "Devices", "type": "audio", "action": "list_devices"}
        result = audio_plugin.execute(tc, ctx)
        assert result.status == TestStatus.FAIL

    def test_audio_route_pass(self, audio_plugin):
        snippet = MagicMock()
        snippet.mediaGetLiveAudioRouteType.return_value = 2
        snippet.mediaGetLiveAudioRouteName.return_value = "Speaker"
        ctx = PluginContext(adb=MagicMock(), settings={}, device_capabilities={}, snippet=snippet)
        tc = {"id": "a5", "name": "Route", "type": "audio", "action": "audio_route"}
        result = audio_plugin.execute(tc, ctx)
        assert result.status == TestStatus.PASS
        assert "Speaker" in result.message


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
        assert "connectivity check" in result.message
        assert "speed" not in result.message

    def test_http_download_pass_200(self, net_plugin):
        adb = MagicMock()
        adb.shell.return_value = MagicMock(stdout="200 100000.000\n")
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
        assert "speed" in result.message
        assert "100000" in result.message

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
