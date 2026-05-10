"""
KOBI Asistan — Merkezi Konfigurasyon
=====================================
Desteklenen LLM Provider'lar:
  - ollama  (local, ucretsiz)
  - openai  (GPT-4o, GPT-4o-mini vb.)
  - gemini  (Google Gemini)
  - claude  (Anthropic Claude)
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # -- LLM Provider Secimi --
    # "ollama", "openai", "gemini", "claude"
    LLM_PROVIDER: str = "ollama"

    # -- Ollama (Local) --
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3.6:27b"

    # -- OpenAI --
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    # -- Google Gemini --
    GOOGLE_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # -- Anthropic Claude --
    ANTHROPIC_API_KEY: Optional[str] = None
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"

    # -- Telegram --
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ENABLED: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
