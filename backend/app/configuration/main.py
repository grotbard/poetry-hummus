"""Typed settings, grouped by concern and loaded from the environment.

Every group is a nested model with its own prefix, so related values stay
together and Helm can set them one by one:

    POETRY_DB__URL, POETRY_DB__POOL_SIZE
    POETRY_GOOGLE__CLIENT_ID
    POETRY_SECURITY__SECRET_KEY

Flat legacy names (DATABASE_URL, SECRET_KEY, GOOGLE_CLIENT_ID…) are still
honoured as aliases so an existing .env keeps working.
"""

from enum import StrEnum
from functools import lru_cache

from pydantic import AliasChoices, Field, PostgresDsn, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    development = "development"
    test = "test"
    production = "production"


_BASE_CONFIG = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    env_nested_delimiter="__",
    extra="ignore",
)


class DatabaseSettings(BaseSettings):
    """Postgres connection and pool sizing."""

    model_config = _BASE_CONFIG | SettingsConfigDict(env_prefix="POETRY_DB__")

    # Defaults to the local development database so a fresh clone runs.
    url: str = Field(
        default="postgresql+asyncpg://poet:poet@localhost:5432/poetry_hummus",
        validation_alias=AliasChoices("url", "POETRY_DB__URL", "DATABASE_URL"),
        description="SQLAlchemy async URL, e.g. postgresql+asyncpg://user:pw@host/db",
    )
    pool_size: int = Field(default=5, ge=1, le=100)
    max_overflow: int = Field(default=10, ge=0, le=100)
    pool_timeout_seconds: int = Field(default=30, ge=1)
    pool_recycle_seconds: int = Field(default=1800, ge=-1)
    # Costs one round trip per checkout but survives a database restart.
    pool_pre_ping: bool = True
    echo_sql: bool = False

    @computed_field
    @property
    def is_sqlite(self) -> bool:
        return self.url.startswith("sqlite")

    @computed_field
    @property
    def safe_url(self) -> str:
        """URL with any password masked, for logs."""
        try:
            scheme, rest = self.url.split("://", 1)
        except ValueError:
            return self.url
        if "@" not in rest:
            return self.url
        creds, host = rest.rsplit("@", 1)
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"


class SecuritySettings(BaseSettings):
    """Session signing and cookie behaviour."""

    model_config = _BASE_CONFIG | SettingsConfigDict(env_prefix="POETRY_SECURITY__")

    secret_key: SecretStr = Field(
        default=SecretStr("dev-only-insecure-secret-change-me"),
        validation_alias=AliasChoices(
            "secret_key", "POETRY_SECURITY__SECRET_KEY", "SECRET_KEY"
        ),
    )
    session_cookie_name: str = "poet_session"
    session_ttl_hours: int = Field(default=24 * 14, ge=1)


class GoogleOAuthSettings(BaseSettings):
    """Google sign-in credentials. Blank disables the member login."""

    model_config = _BASE_CONFIG | SettingsConfigDict(env_prefix="POETRY_GOOGLE__")

    client_id: str = Field(
        default="",
        validation_alias=AliasChoices(
            "client_id", "POETRY_GOOGLE__CLIENT_ID", "GOOGLE_CLIENT_ID"
        ),
    )
    client_secret: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices(
            "client_secret", "POETRY_GOOGLE__CLIENT_SECRET", "GOOGLE_CLIENT_SECRET"
        ),
    )

    @computed_field
    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret.get_secret_value())


class LoyaltySettings(BaseSettings):
    """Poet Coin tuning."""

    model_config = _BASE_CONFIG | SettingsConfigDict(env_prefix="POETRY_LOYALTY__")

    coins_per_shekel: int = Field(
        default=1,
        ge=0,
        validation_alias=AliasChoices(
            "coins_per_shekel", "POETRY_LOYALTY__COINS_PER_SHEKEL", "COINS_PER_SHEKEL"
        ),
    )
    signup_bonus_coins: int = Field(
        default=20,
        ge=0,
        validation_alias=AliasChoices(
            "signup_bonus_coins",
            "POETRY_LOYALTY__SIGNUP_BONUS_COINS",
            "SIGNUP_BONUS_COINS",
        ),
    )


class AdminBootstrapSettings(BaseSettings):
    """First admin, created on startup when both values are set."""

    model_config = _BASE_CONFIG | SettingsConfigDict(env_prefix="POETRY_ADMIN__")

    email: str = Field(
        default="",
        validation_alias=AliasChoices(
            "email", "POETRY_ADMIN__EMAIL", "BOOTSTRAP_ADMIN_EMAIL"
        ),
    )
    password: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices(
            "password", "POETRY_ADMIN__PASSWORD", "BOOTSTRAP_ADMIN_PASSWORD"
        ),
    )

    @computed_field
    @property
    def configured(self) -> bool:
        return bool(self.email and self.password.get_secret_value())


class Settings(BaseSettings):
    """Root settings object. Use the `settings` singleton below."""

    model_config = _BASE_CONFIG | SettingsConfigDict(env_prefix="POETRY_")

    app_env: AppEnv = Field(
        default=AppEnv.development,
        validation_alias=AliasChoices("app_env", "POETRY_APP_ENV", "APP_ENV"),
    )
    frontend_url: str = Field(
        default="http://localhost:5173",
        validation_alias=AliasChoices(
            "frontend_url", "POETRY_FRONTEND_URL", "FRONTEND_URL"
        ),
    )
    public_api_url: str = Field(
        default="http://localhost:8000",
        validation_alias=AliasChoices(
            "public_api_url", "POETRY_PUBLIC_API_URL", "PUBLIC_API_URL"
        ),
    )

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    google: GoogleOAuthSettings = Field(default_factory=GoogleOAuthSettings)
    loyalty: LoyaltySettings = Field(default_factory=LoyaltySettings)
    admin: AdminBootstrapSettings = Field(default_factory=AdminBootstrapSettings)

    @computed_field
    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.production

    @property
    def google_redirect_uri(self) -> str:
        """Must match the redirect URI registered in the Google console."""
        return f"{self.public_api_url}/api/auth/google/callback"


@lru_cache
def get_settings() -> Settings:
    """Cached accessor; clear the cache in tests that change the environment."""
    return Settings()


settings = get_settings()
