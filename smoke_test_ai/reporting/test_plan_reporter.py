from collections import Counter
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


class TestPlanReporter:
    def __init__(self, template_dir: Path | None = None):
        if template_dir is None:
            template_dir = Path(__file__).parent.parent.parent / "templates"
        self.env = Environment(loader=FileSystemLoader(str(template_dir)))

    def generate(self, suite_config: dict, output_path: Path) -> None:
        suite = suite_config["test_suite"]
        tests_raw = suite.get("tests", [])

        tests = []
        for tc in tests_raw:
            tests.append({
                "id": tc["id"],
                "name": tc["name"],
                "type": tc["type"],
                "command": tc.get("command") or tc.get("prompt") or tc.get("action", ""),
                "pass_criteria_display": self._build_pass_criteria(tc),
                "depends_on": tc.get("depends_on"),
                "requires": tc.get("requires", {}).get("device_capability"),
                "retry": tc.get("retry"),
                "retry_delay": tc.get("retry_delay"),
            })

        type_counts = dict(Counter(t["type"] for t in tests))

        template = self.env.get_template("test_plan.html")
        html = template.render(
            suite_name=suite.get("name", "Unknown"),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total=len(tests),
            type_counts=type_counts,
            tests=tests,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html)

    @staticmethod
    def _build_pass_criteria(tc: dict) -> str:
        t = tc["type"]

        if t == "adb_check":
            return f"Output equals \"{tc.get('expected', '')}\""

        if t == "adb_shell":
            parts = []
            if "expected_contains" in tc:
                parts.append(f"Output contains \"{tc['expected_contains']}\"")
            if "expected_not_contains" in tc:
                parts.append(f"Output does NOT contain \"{tc['expected_not_contains']}\"")
            if "expected_pattern" in tc:
                parts.append(f"Output matches /{tc['expected_pattern']}/")
            return "; ".join(parts) if parts else "Command exits with code 0"

        if t == "screenshot_llm":
            criteria = tc.get("pass_criteria", "")
            prompt = tc.get("prompt", "")
            return f"LLM judges \"{criteria}\" — Prompt: {prompt}" if criteria else f"LLM prompt: {prompt}"

        if t == "apk_instrumentation":
            pkg = tc.get("package", "")
            runner = tc.get("runner", "AndroidJUnitRunner")
            return f"Instrumentation passes ({pkg} / {runner})"

        if t == "telephony":
            action = tc.get("action", "")
            params = tc.get("params", {})
            if action == "send_sms":
                return f"SMS sent to {params.get('to_number', 'peer')} without error"
            if action == "receive_sms":
                return f"SMS received within {params.get('timeout', 30)}s"
            if action == "check_signal":
                return f"Network type matches /{params.get('expected_data_type', '.*')}/"
            if action == "make_call":
                return f"Call to {params.get('to_number', 'peer')} reaches OFFHOOK state"
            return f"Telephony action: {action}"

        if t == "wifi":
            action = tc.get("action", "")
            params = tc.get("params", {})
            if action == "scan":
                return "WiFi scan finds at least 1 network"
            if action == "scan_for_ssid":
                return f"WiFi scan finds SSID \"{params.get('expected_ssid', '')}\""
            return f"WiFi action: {action}"

        if t == "bluetooth":
            action = tc.get("action", "")
            params = tc.get("params", {})
            if action == "ble_scan":
                return f"BLE scan finds at least 1 device (scan {params.get('scan_duration', 5)}s)"
            return f"Bluetooth action: {action}"

        if t == "audio":
            action = tc.get("action", "")
            if action == "play_and_check":
                return "Audio plays and mediaIsPlaying() returns true"
            return f"Audio action: {action}"

        if t == "network":
            action = tc.get("action", "")
            params = tc.get("params", {})
            if action == "http_download":
                mode = params.get("network_mode", "auto")
                return f"HTTP download returns 200 OK (mode: {mode})"
            if action == "tcp_connect":
                return f"TCP connection to {params.get('host', '8.8.8.8')}:{params.get('port', 443)} succeeds"
            return f"Network action: {action}"

        if t == "camera":
            action = tc.get("action", "")
            params = tc.get("params", {})
            if action == "capture_photo":
                return f"New photo file created in DCIM ({params.get('camera', 'back')} camera)"
            if action == "capture_and_verify":
                return f"Photo captured and LLM verified: {params.get('verify_prompt', '')}"
            return f"Camera action: {action}"

        return "Unknown test type"
