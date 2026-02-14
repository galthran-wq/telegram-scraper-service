from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "telegram-scraper-service"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8001
    log_level: str = "info"
    cors_origins: list[str] = ["*"]
    metrics_enabled: bool = True

    telegram_api_id: int
    telegram_api_hash: str
    sessions_dir: str = "/app/sessions"


settings = Settings()
