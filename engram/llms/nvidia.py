import os
from typing import Optional

from engram.llms.base import BaseLLM


class NvidiaLLM(BaseLLM):
    """LLM provider for NVIDIA API (OpenAI-compatible). Default model: Kimi K2.5."""

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        try:
            from openai import OpenAI
        except Exception as exc:
            raise ImportError("openai package is required for NvidiaLLM") from exc

        api_key = self.config.get("api_key") or "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"
        if not api_key:
            raise ValueError(
                "NVIDIA API key required. Set config['api_key'] or NVIDIA_API_KEY env var."
            )

        base_url = self.config.get("base_url", "https://integrate.api.nvidia.com/v1")
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = self.config.get("model", "moonshotai/kimi-k2.5")
        self.temperature = self.config.get("temperature", 1.0)
        self.max_tokens = self.config.get("max_tokens", 16384)
        self.top_p = self.config.get("top_p", 0.7)
        self.enable_thinking = self.config.get("enable_thinking", False)

    def generate(self, prompt: str) -> str:
        extra_kwargs = {}
        if self.enable_thinking:
            extra_kwargs["extra_body"] = {
                "chat_template_kwargs": {"enable_thinking": True}
            }

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=self.max_tokens,
            stream=False,
            **extra_kwargs,
        )
        return response.choices[0].message.content
