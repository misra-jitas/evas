"""12-factor configuration. All settings come from environment variables.

No secrets in code. See .env.example for the full list.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EVAS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database ---
    database_url: str = "postgresql+psycopg2://evas:evas@localhost:5432/evas"

    # --- S3 / object storage ---
    s3_bucket_videos: str = "evas-videos"
    s3_bucket_frames: str = "evas-frames"
    s3_region: str = "us-east-1"
    # Optional custom endpoint for MinIO/LocalStack; None = real AWS.
    s3_endpoint_url: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None

    # --- Auth (stateless JWT; no credentials stored — see Evas2.md) ---
    jwt_secret: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    # Gates POST /auth/token. If empty, token minting is disabled (503).
    bootstrap_token: str | None = None

    # --- Webhooks ---
    webhook_timeout_seconds: float = 10.0

    # --- Anthropic ---
    anthropic_api_key: str | None = None
    ai_model: str = "claude-haiku-4-5"
    ai_max_tokens: int = 1024
    # Local/dev: use a deterministic offline reviewer instead of calling Anthropic.
    ai_stub: bool = False
    # Findings below this min-confidence get flagged for human attention.
    confidence_flag_threshold: float = 0.75

    # --- Worker ---
    worker_poll_interval_seconds: float = 2.0
    worker_batch_size: int = 1

    # --- Local scratch space for ffmpeg work ---
    work_dir: str = "/tmp/evas"

    # --- Findings export ---
    export_dir: str = "exports"


@lru_cache
def get_settings() -> Settings:
    return Settings()
