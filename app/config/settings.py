from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """GhostGrid Central Application Configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server Runtime
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    DEBUG: bool = True
    SECRET_KEY: str = "cyberpunk_ghostgrid_secret_key_change_in_production_32chars"

    # Firebase Admin Configuration
    FIREBASE_CREDENTIALS_PATH: Optional[str] = "serviceAccountKey.json"
    FIREBASE_CREDENTIALS_JSON: Optional[str] = None

    # Core Proxy Engine Bounds
    MAX_REDIRECTS: int = 5
    REQUEST_TIMEOUT_SECONDS: float = 15.0
    MAX_RESPONSE_SIZE_BYTES: int = 10485760  # 10 MB limit


@lru_cache()
def get_settings() -> Settings:
    """Returns a cached singleton instance of Settings."""
    return Settings()