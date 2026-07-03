import sys
from types import SimpleNamespace

from dhee.llms.nvidia import NvidiaLLM


class _FakeCompletions:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class _FakeOpenAI:
    completions = None

    def __init__(self, **_kwargs):
        self.chat = SimpleNamespace(completions=self.completions)


def test_nvidia_llm_ping_uses_configured_model(monkeypatch):
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))]
    )
    completions = _FakeCompletions(response=response)
    _FakeOpenAI.completions = completions
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")

    llm = NvidiaLLM({"model": "moonshotai/kimi-k2.6"})
    health = llm.ping()

    assert health["ok"] is True
    assert health["status"] == "ready"
    assert health["model"] == "moonshotai/kimi-k2.6"
    assert completions.calls[0]["model"] == "moonshotai/kimi-k2.6"
    assert completions.calls[0]["max_tokens"] == 2


def test_nvidia_llm_ping_reports_model_failure(monkeypatch):
    completions = _FakeCompletions(error=RuntimeError("404 model not found"))
    _FakeOpenAI.completions = completions
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")

    llm = NvidiaLLM({"model": "moonshotai/kimi-k2.5"})
    health = llm.ping()

    assert health["ok"] is False
    assert health["status"] == "unavailable"
    assert health["model"] == "moonshotai/kimi-k2.5"
    assert health["error_type"] == "RuntimeError"
    assert "404" in health["error"]
