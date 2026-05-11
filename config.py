from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Ollama (default provider)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3.6:27b"

    # LLM Provider — ollama | openai | anthropic | gemini
    LLM_PROVIDER: str = "ollama"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-haiku-4-5-20251001"

    # Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ENABLED: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
