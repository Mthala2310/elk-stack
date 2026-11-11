from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):

    # Elasticsearch
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index_allowlist: str = "app-logs-*"
    tool_max_results: int = 100
    tool_max_lookback_hours: int = 168

    # LLM / OpenRouter
    openrouter_api_key: str = ""
    llm_provider: str = "openrouter"
    llm_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_timeout_seconds: int = 120
    llm_max_retries: int = 2
    llm_retry_base_seconds: float = 1.0

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()