import pytest

from rag_lab.core.config import Settings
from rag_lab.core.errors import AppError
from rag_lab.core.providers import Provider


def test_oversized_prompt_rejected_before_model_call(monkeypatch):
    provider = Provider(Settings(provider_mode="demo", llm_context_tokens=2048, _env_file=None))
    provider.config.provider_mode = "ollama"

    def unexpected_call(**kwargs):
        pytest.fail("oversized reference reached the model")

    monkeypatch.setattr("rag_lab.core.providers.ChatOllama", unexpected_call)
    with pytest.raises(AppError, match="context_limit"):
        provider.answer("Summarize", "evidence " * 3000)
