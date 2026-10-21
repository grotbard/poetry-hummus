from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: Literal["development", "production", "test"] = "development"
    secret_key: str = "dev-only-insecure-secret-change-me"
    frontend_url: str = "http://localhost:5173"
    public_api_url: str = "http://localhost:8000"

    database_url: str = "postgresql+asyncpg://poet:poet@localhost:5432/poetry_hummus"

    google_client_id: str = ""
    google_client_secret: str = ""

    # Loyalty program tuning.
    coins_per_shekel: int = 1
    signup_bonus_coins: int = 20

    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""

    # Session cookie
    session_cookie_name: str = "poet_session"
    session_ttl_hours: int = 24 * 14

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.public_api_url}/api/auth/google/callback"

    @property
    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
