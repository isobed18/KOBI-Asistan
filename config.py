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
    TELEGRAM_ADMIN_CHAT_ID: str = ""   # admin Telegram chat ID (bildirimler için)
    TELEGRAM_ENABLED: bool = True

    # Intent Classifier
    USE_EMBEDDING_CLASSIFIER: bool = False   # sentence-transformers ağır; demo'da False bırak

    # JWT Auth
    JWT_SECRET: str = "kobi-super-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 8   # 8 saat

    class Config:
        env_file = ".env"


settings = Settings()
