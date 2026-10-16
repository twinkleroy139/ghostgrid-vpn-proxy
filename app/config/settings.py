from functools import lru_cache
from typing import Dict, Optional
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
    REQUEST_TIMEOUT_SECONDS: float = 20.0
    MAX_RESPONSE_SIZE_BYTES: int = 36700160  # 35 MB to accommodate heavy client-side scripts

    # VPN / Egress Gateway Registry
    PROXY_NODE_US: Optional[str] = None
    PROXY_NODE_DE: Optional[str] = None
    PROXY_NODE_SG: Optional[str] = None
    PROXY_NODE_UK: Optional[str] = None

    @property
    def available_nodes(self) -> Dict[str, dict]:
        return {
            "direct": {"name": "⚡ Direct Uplink (Local/Cloud)", "url": None},
            "us": {"name": "🇺🇸 United States (CyberNode-US)", "url": self.PROXY_NODE_US},
            "de": {"name": "🇩🇪 Germany (CyberNode-DE)", "url": self.PROXY_NODE_DE},
            "sg": {"name": "🇸🇬 Singapore (CyberNode-SG)", "url": self.PROXY_NODE_SG},
            "uk": {"name": "🇬🇧 United Kingdom (CyberNode-UK)", "url": self.PROXY_NODE_UK},
        }


@lru_cache()
def get_settings() -> Settings:
    return Settings()