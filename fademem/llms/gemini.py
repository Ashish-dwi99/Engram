import os
from typing import Optional

from fadem.llms.base import BaseLLM


class GeminiLLM(BaseLLM):
    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.api_key = self.config.get("api_key") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("Gemini API key not provided. Set GEMINI_API_KEY or pass api_key in config.")

        self.model = self.config.get("model", "gemini-1.5-flash")
        self.temperature = self.config.get("temperature", 0.1)
        self.max_tokens = self.config.get("max_tokens", 1024)

        self._client_type = None
        self._model = None
        self._client = None

        try:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            self._client_type = "generativeai"
            self._genai = genai
            self._model = genai.GenerativeModel(self.model)
        except Exception:
            try:
                from google import genai

                self._client_type = "genai"
                self._client = genai.Client(api_key=self.api_key)
            except Exception as exc:
                raise ImportError(
                    "Install google-generativeai or google-genai to use GeminiLLM"
                ) from exc

    def generate(self, prompt: str) -> str:
        if self._client_type == "generativeai":
            response = self._model.generate_content(
                prompt,
                generation_config={
                    "temperature": self.temperature,
                    "max_output_tokens": self.max_tokens,
                },
            )
            return getattr(response, "text", "") or ""

        if self._client_type == "genai":
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "temperature": self.temperature,
                    "max_output_tokens": self.max_tokens,
                },
            )
            return _extract_text_from_response(response)

        return ""


def _extract_text_from_response(response) -> str:
    if response is None:
        return ""
    text = getattr(response, "text", None)
    if text:
        return text
    candidates = getattr(response, "candidates", None)
    if not candidates:
        return ""
    first = candidates[0]
    content = getattr(first, "content", None)
    if not content:
        return ""
    parts = getattr(content, "parts", None)
    if not parts:
        return ""
    return "".join([getattr(part, "text", "") for part in parts if getattr(part, "text", None)])
