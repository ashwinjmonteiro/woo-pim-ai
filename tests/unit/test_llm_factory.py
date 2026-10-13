"""LLM factory selection tests."""

import pytest

from src.config import Settings
from src.llm.factory import get_llm_client
from src.llm.mock_client import MockLLMClient
from src.llm.openai_compatible import OpenAICompatibleClient


def test_factory_selects_mock_by_default():
    assert isinstance(get_llm_client(Settings(_env_file=None)), MockLLMClient)


def test_factory_selects_groq_and_requires_key():
    config = Settings(_env_file=None, llm_provider="groq", groq_api_key="free-tier-key")
    assert isinstance(get_llm_client(config), OpenAICompatibleClient)
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        get_llm_client(Settings(_env_file=None, llm_provider="groq"))


def test_factory_selects_ollama_and_rejects_unknown_provider():
    assert isinstance(get_llm_client(Settings(_env_file=None, llm_provider="ollama")), OpenAICompatibleClient)
    with pytest.raises(ValueError, match="Unsupported"):
        get_llm_client(Settings(_env_file=None, llm_provider="other"))


@pytest.mark.live
def test_optional_live_groq_client_is_explicitly_opt_in():
    """Check client construction only; live network calls remain manually invoked."""
    import os

    pytest.importorskip("openai")
    if not os.getenv("GROQ_API_KEY") or os.getenv("RUN_LIVE_LLM") != "true":
        pytest.skip("Set GROQ_API_KEY and RUN_LIVE_LLM=true to opt in")
    assert isinstance(get_llm_client(Settings(llm_provider="groq", groq_api_key=os.environ["GROQ_API_KEY"])), OpenAICompatibleClient)
