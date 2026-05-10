from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3.6:27b"
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ENABLED: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
