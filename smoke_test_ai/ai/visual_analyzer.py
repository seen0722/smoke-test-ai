import json
import numpy as np
from smoke_test_ai.ai.llm_client import LlmClient
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)

SETUP_WIZARD_PROMPT = """You are an Android Setup Wizard automation assistant.
Analyze this screenshot and determine:
1. What step of the Setup Wizard is currently displayed?
2. What action should be taken?
3. Is the Setup Wizard complete?

Return ONLY valid JSON:
{"screen_state": "language_selection | wifi_setup | google_login | terms | pin_setup | home | unknown", "completed": false, "action": {"type": "tap | swipe | type | wait", "x": 540, "y": 1200, "text": "", "direction": "up | down | left | right", "wait_seconds": 0}, "confidence": 0.95}"""

TEST_SCREENSHOT_PROMPT = """Analyze this Android device screenshot for testing.
Question: {question}

Return ONLY valid JSON:
{{"pass": true, "reason": "explanation"}}"""

class VisualAnalyzer:
    def __init__(self, llm: LlmClient):
        self.llm = llm

    def analyze_setup_wizard(self, image: np.ndarray) -> dict:
        response = self.llm.chat_vision(SETUP_WIZARD_PROMPT, image)
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response: {response}")
            return {"screen_state": "unknown", "completed": False, "action": {"type": "wait", "wait_seconds": 3}, "confidence": 0.0}

    def analyze_test_screenshot(self, image: np.ndarray, question: str) -> dict:
        prompt = TEST_SCREENSHOT_PROMPT.format(question=question)
        response = self.llm.chat_vision(prompt, image)
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response: {response}")
            return {"pass": False, "reason": f"LLM parse error: {response}"}

    def generate_report_summary(self, results_json: str) -> str:
        prompt = f"Summarize the following Android smoke test results. Highlight failures and provide recommendations.\n\n{results_json}"
        return self.llm.chat(prompt)
