"""Typed settings, grouped by concern and loaded from the environment.

Every group is a nested model with its own prefix, so related values stay
together and Helm can set them one by one:

    POETRY_DB__URL, POETRY_DB__POOL_SIZE
    POETRY_GOOGLE__CLIENT_ID
    POETRY_SECURITY__SECRET_KEY

Flat legacy names (DATABASE_URL, SECRET_KEY, GOOGLE_CLIENT_ID…) are still
honoured as aliases so an existing .env keeps working.

Precedence follows the order in each AliasChoices list, not the source: a
canonical POETRY_* value wins over its legacy alias even when the legacy one
comes from the process environment and the canonical one from .env. Prefer
the canonical names when overriding for a script or a test run.
"""

import os
import secrets as _secrets
from enum import StrEnum
from pathlib import Path
from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_present(*names: str) -> bool:
    """True when any of these environment variables holds a non-empty value."""
    return any(os.environ.get(name, "").strip() for name in names)


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

    @field_validator("url", mode="after")
    @classmethod
    def _ensure_async_driver(cls, value: str) -> str:
        """Accept the plain URLs managed hosts hand out.

        Render, Heroku and friends expose `postgresql://` (or `postgres://`),
        but SQLAlchemy's async engine needs an async driver in the scheme.
        Rewriting here means the platform value can be used verbatim.
        """
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value[len(prefix) :]
        return value

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

    # Generated per process when unset: good enough for a dev run, and it
    # cannot be a known constant baked into the image. Sessions do not
    # survive a restart without an explicit key, which is the intended hint.
    secret_key: SecretStr = Field(
        default_factory=lambda: SecretStr(_secrets.token_urlsafe(64)),
        validation_alias=AliasChoices(
            "secret_key", "POETRY_SECURITY__SECRET_KEY", "SECRET_KEY"
        ),
        description="Signs session JWTs. Required in production.",
    )
    session_cookie_name: str = "poet_session"
    session_ttl_hours: int = Field(default=24 * 14, ge=1)
    # Force the Secure cookie flag independently of app_env, for a proxy
    # that terminates TLS (Render, Fly, Heroku) while the app sees plain HTTP.
    cookie_secure: bool | None = Field(
        default=None,
        description="None follows app_env; set true behind an HTTPS proxy.",
    )


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
    # When set, the API also serves the built SPA from this directory, so a
    # single-origin deployment needs no CORS and no cross-site cookie.
    static_dir: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("static_dir", "POETRY_STATIC_DIR"),
    )
    # Run Alembic migrations during startup. For hosts without a pre-deploy
    # hook (Render's free plan); prefer a real pre-deploy step where available,
    # since this serialises behind the first boot of each instance.
    run_migrations: bool = Field(
        default=False,
        validation_alias=AliasChoices("run_migrations", "POETRY_RUN_MIGRATIONS"),
    )
    # Directory for uploaded menu photos; a mounted disk in production.
    media_dir: Path = Field(
        default=Path(__file__).resolve().parents[2] / "media",
        validation_alias=AliasChoices("media_dir", "POETRY_MEDIA_DIR"),
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

    def missing_production_config(self) -> list[str]:
        """Names of required settings that production must not run without."""
        if self.app_env is not AppEnv.production:
            return []
        missing: list[str] = []
        if not _env_present("POETRY_SECURITY__SECRET_KEY", "SECRET_KEY"):
            missing.append("SECRET_KEY (or POETRY_SECURITY__SECRET_KEY)")
        if not _env_present("POETRY_DB__URL", "DATABASE_URL"):
            missing.append("DATABASE_URL (or POETRY_DB__URL)")
        return missing

    @property
    def cookie_secure(self) -> bool:
        """Whether to set the Secure flag on the session cookie."""
        if self.security.cookie_secure is not None:
            return self.security.cookie_secure
        return self.is_production

    @property
    def serve_frontend(self) -> bool:
        """True when a built SPA sits next to the API and should be served."""
        return self.static_dir is not None and self.static_dir.is_dir()

    @property
    def google_redirect_uri(self) -> str:
        """Must match the redirect URI registered in the Google console."""
        return f"{self.public_api_url}/api/auth/google/callback"


class ConfigurationError(RuntimeError):
    """Raised when production is missing configuration it must not run without."""


@lru_cache
def get_settings() -> Settings:
    """Cached accessor; clear the cache in tests that change the environment.

    Raises ConfigurationError in production when a required secret is absent.
    The check lives here rather than in a validator so pydantic does not echo
    the raw settings — including secrets — into the error message.
    """
    loaded = Settings()
    missing = loaded.missing_production_config()
    if missing:
        raise ConfigurationError(
            "Missing required configuration in production: "
            + ", ".join(missing)
            + ". Set it in the environment or, on Kubernetes, in the Secret "
            "referenced by the Helm chart."
        )
    return loaded


settings = get_settings()
