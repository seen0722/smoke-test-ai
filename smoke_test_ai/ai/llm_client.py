import base64
import httpx
import cv2
import numpy as np
from smoke_test_ai.utils.logger import get_logger

logger = get_logger(__name__)

class LlmClient:
    def __init__(self, provider: str = "ollama", base_url: str = "http://localhost:11434", vision_model: str | None = None, text_model: str | None = None, api_key: str | None = None, timeout: int = 30):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.vision_model = vision_model
        self.text_model = text_model
        self.api_key = api_key
        self.timeout = timeout

    def _get_client(self) -> httpx.Client:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return httpx.Client(base_url=self.base_url, headers=headers, timeout=self.timeout)

    def _image_to_base64(self, image: np.ndarray) -> str:
        _, buffer = cv2.imencode(".jpg", image)
        return base64.b64encode(buffer).decode("utf-8")

    def chat(self, prompt: str, model: str | None = None) -> str:
        model = model or self.text_model
        if not model:
            raise ValueError("No text model configured")
        if self.provider == "ollama":
            return self._ollama_chat(prompt, model)
        return self._openai_compatible_chat(prompt, model)

    def chat_vision(self, prompt: str, image: np.ndarray, model: str | None = None) -> str:
        model = model or self.vision_model
        if not model:
            raise ValueError("No vision model configured")
        image_b64 = self._image_to_base64(image)
        if self.provider == "ollama":
            return self._ollama_chat_vision(prompt, image_b64, model)
        return self._openai_compatible_chat_vision(prompt, image_b64, model)

    def _ollama_chat(self, prompt: str, model: str) -> str:
        with self._get_client() as client:
            response = client.post("/api/chat", json={"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False})
            response.raise_for_status()
            return response.json()["message"]["content"]

    def _ollama_chat_vision(self, prompt: str, image_b64: str, model: str) -> str:
        with self._get_client() as client:
            response = client.post("/api/chat", json={"model": model, "messages": [{"role": "user", "content": prompt, "images": [image_b64]}], "stream": False})
            response.raise_for_status()
            return response.json()["message"]["content"]

    def _openai_compatible_chat(self, prompt: str, model: str) -> str:
        with self._get_client() as client:
            response = client.post("/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": prompt}]})
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    def _openai_compatible_chat_vision(self, prompt: str, image_b64: str, model: str) -> str:
        with self._get_client() as client:
            response = client.post("/v1/chat/completions", json={"model": model, "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}]}]})
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
