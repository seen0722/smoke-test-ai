import pytest
from unittest.mock import MagicMock
from smoke_test_ai.plugins.base import TestPlugin, PluginContext
from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.camera import CameraPlugin
from smoke_test_ai.plugins.telephony import TelephonyPlugin


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
        adb.shell.side_effect = [
            MagicMock(stdout="IMG_20260101.jpg\n", returncode=0),  # baseline ls
            MagicMock(stdout="", returncode=0),                     # am start
            MagicMock(stdout="", returncode=0),                     # keyevent
            MagicMock(stdout="IMG_20260301.jpg\n", returncode=0),  # after ls
            MagicMock(stdout="1234567\n", returncode=0),           # stat size
        ]
        tc = {
            "id": "cam1", "name": "Camera", "type": "camera",
            "action": "capture_photo",
            "params": {"camera": "back", "wait_seconds": 0},
        }
        result = camera_plugin.execute(tc, plugin_context)
        assert result.status == TestStatus.PASS
        assert "IMG_20260301.jpg" in result.message
        assert "1234567" in result.message

    def test_capture_photo_no_new_file(self, camera_plugin, plugin_context):
        adb = plugin_context.adb
        adb.shell.side_effect = [
            MagicMock(stdout="IMG_20260101.jpg\n", returncode=0),  # baseline
            MagicMock(stdout="", returncode=0),                     # am start
            MagicMock(stdout="", returncode=0),                     # keyevent
            MagicMock(stdout="IMG_20260101.jpg\n", returncode=0),  # same file
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
        adb.shell.side_effect = [
            MagicMock(stdout="IMG_old.jpg\n", returncode=0),
            MagicMock(stdout="", returncode=0),
            MagicMock(stdout="", returncode=0),
            MagicMock(stdout="IMG_new.jpg\n", returncode=0),
            MagicMock(stdout="5000\n", returncode=0),
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
        adb.shell.side_effect = [
            MagicMock(stdout="IMG_old.jpg\n", returncode=0),
            MagicMock(stdout="", returncode=0),
            MagicMock(stdout="", returncode=0),
            MagicMock(stdout="IMG_new.jpg\n", returncode=0),
            MagicMock(stdout="5000\n", returncode=0),
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
        adb.shell.side_effect = [
            MagicMock(stdout="IMG_old.jpg\n", returncode=0),
            MagicMock(stdout="", returncode=0),
            MagicMock(stdout="", returncode=0),
            MagicMock(stdout="IMG_new.jpg\n", returncode=0),
            MagicMock(stdout="5000\n", returncode=0),
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
