"""Application configuration loaded from environment variables and .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings shared by the application and its service factories."""

    llm_provider: str = "mock"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "llama3.1"
    llm_timeout_seconds: float = 30
    database_url: str = "sqlite:///./pim.db"
    woo_base_url: str = "https://your-store.example.com"
    woo_consumer_key: str = ""
    woo_consumer_secret: str = ""
    woo_webhook_secret: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return the cached process settings."""
    return Settings()
