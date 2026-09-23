from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "VoiceTranslate API"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = False
    cors_origins: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://voicetranslate:voicetranslate@localhost:5432/voicetranslate"
    device: str = "cpu"
    whisper_model_size: str = "small"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
