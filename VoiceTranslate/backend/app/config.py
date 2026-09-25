from functools import lru_cache

from pydantic import Field
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
    max_websocket_frame_bytes: int = Field(default=65536, gt=0)
    max_audio_buffer_bytes: int = Field(default=1048576, gt=0)
    max_audio_segment_seconds: float = Field(default=30.0, gt=0)
    max_audio_chunk_bytes: int = Field(default=65536, gt=0)
    vad_enabled: bool = True
    vad_threshold: float = Field(default=500.0, ge=0)
    vad_min_speech_ms: int = Field(default=200, gt=0)
    vad_min_silence_ms: int = Field(default=300, gt=0)
    vad_max_speech_ms: int = Field(default=30000, gt=0)
    vad_frame_ms: int = Field(default=20, gt=0)
    whisper_enabled: bool = True
    whisper_model_size: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str = ""
    whisper_beam_size: int = Field(default=5, gt=0)
    whisper_vad_filter: bool = False
    translation_enabled: bool = True
    translation_model: str = "facebook/seamless-m4t-v2-large"
    translation_device: str = "cpu"
    translation_compute_type: str = "default"
    translation_source_language: str = ""
    translation_target_language: str = ""
    device: str = "cpu"

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
