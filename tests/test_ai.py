import pytest
import json
import numpy as np
from unittest.mock import patch, MagicMock
from smoke_test_ai.ai.llm_client import LlmClient
from smoke_test_ai.ai.visual_analyzer import VisualAnalyzer

class TestLlmClient:
    def test_init_ollama(self):
        client = LlmClient(provider="ollama", base_url="http://localhost:11434", vision_model="llava:13b", text_model="llama3:8b")
        assert client.provider == "ollama"

    @patch("smoke_test_ai.ai.llm_client.httpx.Client")
    def test_chat_text(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": "Hello world"}}
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        client = LlmClient(provider="ollama", base_url="http://localhost:11434", text_model="llama3:8b")
        result = client.chat("Say hello")
        assert result == "Hello world"

    @patch("smoke_test_ai.ai.llm_client.httpx.Client")
    def test_chat_vision(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": '{"screen_state": "home", "completed": true}'}}
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        client = LlmClient(provider="ollama", base_url="http://localhost:11434", vision_model="llava:13b")
        fake_image = np.zeros((100, 100, 3), dtype=np.uint8)
        result = client.chat_vision("What do you see?", fake_image)
        assert "completed" in result

class TestVisualAnalyzer:
    @patch("smoke_test_ai.ai.llm_client.httpx.Client")
    def test_analyze_setup_wizard(self, mock_client_cls):
        response_json = {"screen_state": "language_selection", "completed": False, "action": {"type": "tap", "x": 540, "y": 1200}, "confidence": 0.95}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": json.dumps(response_json)}}
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        llm = LlmClient(provider="ollama", base_url="http://localhost:11434", vision_model="llava:13b")
        analyzer = VisualAnalyzer(llm)
        fake_image = np.zeros((1920, 1080, 3), dtype=np.uint8)
        result = analyzer.analyze_setup_wizard(fake_image)
        assert result["screen_state"] == "language_selection"
        assert result["completed"] is False
        assert result["action"]["type"] == "tap"

    @patch("smoke_test_ai.ai.llm_client.httpx.Client")
    def test_analyze_test_screenshot(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": '{"pass": true, "reason": "Screen looks normal"}'}}
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        llm = LlmClient(provider="ollama", base_url="http://localhost:11434", vision_model="llava:13b")
        analyzer = VisualAnalyzer(llm)
        fake_image = np.zeros((1920, 1080, 3), dtype=np.uint8)
        result = analyzer.analyze_test_screenshot(fake_image, "Is the screen normal?")
        assert result["pass"] is True
