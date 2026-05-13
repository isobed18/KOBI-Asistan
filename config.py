from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_llm_provider(name: str | None) -> str:
    """`.env` / tenant YAML'da 'claude' veya 'google' yazıldığında dahili sağlayıcı adına çevirir."""
    p = (name or "ollama").lower().strip()
    if p in ("claude", "anthropic"):
        return "anthropic"
    if p in ("google", "google_genai", "google-genai"):
        return "gemini"
    return p


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # Ollama (default provider)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3.6:27b"

    # LLM Provider — ollama | openai | anthropic | gemini
    LLM_PROVIDER: str = "ollama"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Anthropic (.env'de CLAUDE_MODEL de kullanılabilir — .env.example ile uyum)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = Field(
        default="claude-haiku-4-5-20251001",
        validation_alias=AliasChoices("ANTHROPIC_MODEL", "CLAUDE_MODEL"),
    )

    # Gemini (.env'de GOOGLE_API_KEY veya GEMINI_API_KEY kullanılabilir)
    GEMINI_API_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY", "google_api_key"),
    )
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ADMIN_CHAT_ID: str = ""   # admin Telegram chat ID (bildirimler için)
    TELEGRAM_ENABLED: bool = True

    # Intent Classifier
    USE_EMBEDDING_CLASSIFIER: bool = False   # sentence-transformers ağır; demo'da False bırak

    # Visual stock ingestion / image search
    FASHION_CLIP_MODEL: str = "hf-hub:Marqo/marqo-fashionCLIP"
    GENERAL_CLIP_MODEL: str = "sentence-transformers/clip-ViT-B-32"

    # JWT Auth
    JWT_SECRET: str = "kobi-super-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 8   # 8 saat


settings = Settings()
