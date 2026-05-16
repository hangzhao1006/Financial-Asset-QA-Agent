"""Centralised settings loaded from env / .env file."""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    fallback_llm_model: str = "gpt-3.5-turbo"

    # Embedding
    embedding_provider: str = "openai"  # openai | sentence_transformers
    embedding_model: str = "text-embedding-3-small"

    # Rerank
    rerank_provider: str = "none"  # llm_relevance | cross_encoder | none
    rerank_model: str = ""

    # Search
    tavily_api_key: str = ""
    serpapi_api_key: str = ""

    # Chroma
    chroma_persist_dir: str = str(Path(__file__).resolve().parent.parent / ".chroma")

    # Cache
    cache_backend: str = "memory"
    redis_url: str = "redis://localhost:6379/0"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()