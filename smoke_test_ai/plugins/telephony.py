import re
import time

from smoke_test_ai.core.test_runner import TestResult, TestStatus
from smoke_test_ai.plugins.base import TestPlugin, PluginContext

# Android data network type constants (TelephonyManager.NETWORK_TYPE_*)
NETWORK_TYPE_NAMES = {
    0: "UNKNOWN", 1: "GPRS", 2: "EDGE", 3: "UMTS", 4: "CDMA",
    5: "EVDO_0", 6: "EVDO_A", 7: "1xRTT", 8: "HSDPA", 9: "HSUPA",
    10: "HSPA", 11: "IDEN", 12: "EVDO_B", 13: "LTE", 14: "EHRPD",
    15: "HSPAP", 16: "GSM", 17: "TD_SCDMA", 18: "IWLAN", 19: "LTE_CA",
    20: "NR",
}


class TelephonyPlugin(TestPlugin):
    def execute(self, test_case: dict, context: PluginContext) -> TestResult:
        action = test_case.get("action", "")
        if action == "send_sms":
            return self._send_sms(test_case, context)
        if action == "receive_sms":
            return self._receive_sms(test_case, context)
        if action == "check_signal":
            return self._check_signal(test_case, context)
        if action == "make_call":
            return self._make_call(test_case, context)
        if action == "check_voice_type":
            return self._check_voice_type(test_case, context)
        if action == "sim_info":
            return self._sim_info(test_case, context)
        return TestResult(
            id=test_case["id"], name=test_case["name"],
            status=TestStatus.ERROR,
            message=f"Unknown telephony action: {action}",
        )

    def _send_sms(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available on DUT")
        params = tc.get("params", {})
        to_number = params.get("to_number", "")
        body = self._render_body(params.get("body", "smoke-test"))

        try:
            ctx.snippet.sendSms(to_number, body)
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"sendSms failed: {e}")

        return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                          message=f"SMS sent to {to_number}")

    def _receive_sms(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available on DUT")
        if not ctx.peer_snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Peer device snippet not available")

        params = tc.get("params", {})
        body = self._render_body(params.get("body", "smoke-test"))
        timeout = params.get("timeout", 30)
        dut_number = ctx.settings.get("device", {}).get("phone_number", "")
        if not dut_number:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="DUT phone number not configured (set device.phone_number in settings)")

        try:
            # DUT starts listening (non-blocking)
            ctx.snippet.asyncWaitForSms("sms_receive_cb")
            # Peer sends SMS to DUT
            ctx.peer_snippet.sendSms(dut_number, body)
            # DUT waits for receipt
            received = ctx.snippet.waitForSms(timeout * 1000)
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"SMS receive failed: {e}")

        msg_body = received.get("MessageBody", "")
        if body in msg_body:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=f"Received SMS: {msg_body[:80]}")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message=f"Expected '{body}' in message, got: {msg_body[:80]}")

    def _check_signal(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available on DUT")
        params = tc.get("params", {})
        expected_pattern = params.get("expected_data_type", ".*")

        try:
            net_type_int = ctx.snippet.getDataNetworkType()
            net_type_name = NETWORK_TYPE_NAMES.get(net_type_int, f"UNKNOWN({net_type_int})")
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"getDataNetworkType failed: {e}")

        try:
            matched = re.search(expected_pattern, net_type_name)
        except re.error as exc:
            return TestResult(id=tid, name=tname, status=TestStatus.ERROR,
                              message=f"Invalid expected_data_type regex '{expected_pattern}': {exc}")

        if matched:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=f"Network type: {net_type_name}")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message=f"Network type {net_type_name} does not match /{expected_pattern}/")

    def _make_call(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available on DUT")
        params = tc.get("params", {})
        to_number = params.get("to_number", "")
        if not to_number:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="to_number not configured")
        call_duration = params.get("call_duration", 5)

        try:
            # Dial via ADB intent (telephonyStartCall does not exist in Mobly)
            ctx.adb.shell(
                f"am start -a android.intent.action.CALL -d tel:{to_number}"
            )
            time.sleep(call_duration)
            call_state = ctx.snippet.getTelephonyCallState()
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"make_call failed: {e}")
        finally:
            try:
                ctx.adb.shell("input keyevent KEYCODE_ENDCALL")
            except Exception:
                pass

        # CALL_STATE_OFFHOOK = 2, CALL_STATE_IDLE = 0
        if call_state == 2:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=f"Call to {to_number} active (state=OFFHOOK)")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message=f"Call state={call_state}, expected OFFHOOK(2)")

    def _check_voice_type(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available on DUT")
        try:
            vtype = ctx.snippet.getVoiceNetworkType()
            vtype_name = NETWORK_TYPE_NAMES.get(vtype, f"UNKNOWN({vtype})")
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"getVoiceNetworkType failed: {e}")

        if vtype != 0:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=f"Voice network type: {vtype_name}")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message="Voice network type is UNKNOWN (0)")

    def _sim_info(self, tc: dict, ctx: PluginContext) -> TestResult:
        tid, tname = tc["id"], tc["name"]
        if not ctx.snippet:
            return TestResult(id=tid, name=tname, status=TestStatus.SKIP,
                              message="Snippet not available on DUT")
        try:
            line1 = ctx.snippet.getLine1Number()
            imsi = ctx.snippet.getSubscriberId()
        except Exception as e:
            return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                              message=f"SIM info query failed: {e}")

        parts = []
        if line1:
            parts.append(f"number={line1}")
        if imsi:
            # Mask IMSI for privacy: show first 5 + last 2
            masked = imsi[:5] + "****" + imsi[-2:] if len(imsi) > 7 else imsi
            parts.append(f"IMSI={masked}")

        if parts:
            return TestResult(id=tid, name=tname, status=TestStatus.PASS,
                              message=f"SIM info: {', '.join(parts)}")
        return TestResult(id=tid, name=tname, status=TestStatus.FAIL,
                          message="SIM info unavailable (no number, no IMSI)")

    @staticmethod
    def _render_body(template: str) -> str:
        return template.replace("{timestamp}", str(int(time.time())))
