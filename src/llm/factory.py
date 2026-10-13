"""Factory for selecting an LLM provider."""

from src.config import Settings, get_settings
from src.llm.base import LLMClient
from src.llm.mock_client import MockLLMClient
from src.llm.openai_compatible import OpenAICompatibleClient


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    """Build the configured mock, Groq, or Ollama client."""
    config = settings or get_settings()
    provider = config.llm_provider.lower()
    if provider == "mock":
        return MockLLMClient()
    if provider == "groq":
        if not config.groq_api_key:
            raise ValueError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        return OpenAICompatibleClient(config.groq_base_url, config.groq_api_key, config.groq_model, config.llm_timeout_seconds)
    if provider == "ollama":
        return OpenAICompatibleClient(config.ollama_base_url, "ollama", config.ollama_model, config.llm_timeout_seconds)
    raise ValueError(f"Unsupported LLM_PROVIDER '{config.llm_provider}'; expected mock, groq, or ollama")
