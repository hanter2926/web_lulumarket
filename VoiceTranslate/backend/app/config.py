from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "VoiceTranslate API"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = False
    cors_origins: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://voicetranslate:voicetranslate@localhost:5432/voicetranslate"
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    max_websocket_frame_bytes: int = 65536
    max_audio_buffer_bytes: int = 1048576
    max_audio_segment_seconds: float = 30.0
    max_audio_chunk_bytes: int = 65536
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
