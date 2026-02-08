"""
Centralized configuration via Pydantic Settings.
All settings and parameters in one file; env vars use nested delimiter (e.g. DB__HOST, API__PORT).
"""

from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DbSettings(BaseModel):
    """Database connection. When user is empty, SQLite is used."""

    host: str = "127.0.0.1"
    port: int = 5432
    name: str = "donate"
    user: str = ""
    password: str = ""

    def database_url(self) -> str:
        if not self.user:
            return "sqlite:///./overlay.db"
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class EncodingSettings(BaseModel):
    """H.264 encoding defaults for YouTube Live: CBR 4500k, GOP 2s, high/4.1, zerolatency."""

    cbr_bitrate_k: int = 4500
    fps: int = 30
    gop_frames: int = 60
    profile: str = "high"
    level: str = "4.1"
    tune: str = "zerolatency"
    encoder: str = "libx264"
    default_width: int = 1920
    default_height: int = 1080


class ApiSettings(BaseModel):
    """Overlay API server bind address and port; optional API key for /payment-link (FR-6)."""

    host: str = "0.0.0.0"
    port: int = 5001
    payment_link_api_key: str = ""


class WorkerSettings(BaseModel):
    """Stream worker: overlay refresh interval, default input URL, source retry, and optional RTMP output."""

    overlay_refresh_interval_seconds: int = 8
    default_input_url: str = "rtsp://localhost:554/stream"
    source_retry_interval_seconds: float = 5.0
    rtmp_output_url: str = ""


class YouTubeSettings(BaseModel):
    """YouTube Live: OAuth client and per-channel refresh tokens (JSON). Push config path for overlay API."""

    client_id: str = ""
    client_secret: str = ""
    refresh_tokens: str = ""  # JSON: {"UCxxx":"refresh_token1",...}
    push_conf_path: str = "/etc/nginx/conf.d/youtube_push.conf"
    refresh_interval_seconds: int = 300


class StripeSettings(BaseModel):
    """Stripe webhook secret for payment-to-donor sync (FR-5). When empty, webhook is disabled."""

    webhook_secret: str = ""


class Settings(BaseSettings):
    """Root settings. Nested models populated from env via DB__*, API__*, etc."""

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_ignore_empty=True,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db: DbSettings = Field(default_factory=DbSettings)
    encoding: EncodingSettings = Field(default_factory=EncodingSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    youtube: YouTubeSettings = Field(default_factory=YouTubeSettings)
    stripe: StripeSettings = Field(default_factory=StripeSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance (lazy load once)."""
    return Settings()
