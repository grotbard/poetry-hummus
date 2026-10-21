"""Configuration loading and the database handler."""

import os

import pytest

from app.configuration import (
    AppEnv,
    DatabaseSettings,
    GoogleOAuthSettings,
    SecuritySettings,
    Settings,
)
from app.db import DatabaseHandler, get_db_handler, set_db_handler

AMBIENT = (
    "DATABASE_URL",
    "SECRET_KEY",
    "APP_ENV",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "BOOTSTRAP_ADMIN_EMAIL",
    "BOOTSTRAP_ADMIN_PASSWORD",
    "PUBLIC_API_URL",
    "FRONTEND_URL",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Isolate each test from the ambient env set by conftest and the shell."""
    for name in AMBIENT:
        monkeypatch.delenv(name, raising=False)
    for name in list(os.environ):
        if name.startswith("POETRY_"):
            monkeypatch.delenv(name, raising=False)


def test_database_defaults_to_the_local_dev_database():
    cfg = DatabaseSettings(_env_file=None)
    assert cfg.url.startswith("postgresql+asyncpg://")
    assert "localhost" in cfg.url
    assert cfg.pool_pre_ping is True


def test_nested_env_var_sets_the_database_url(monkeypatch):
    monkeypatch.setenv("POETRY_DB__URL", "postgresql+asyncpg://u:p@db.internal:5432/x")
    monkeypatch.setenv("POETRY_DB__POOL_SIZE", "42")
    cfg = DatabaseSettings(_env_file=None)
    assert cfg.url.endswith("/x")
    assert cfg.pool_size == 42


def test_legacy_flat_env_var_still_works(monkeypatch):
    """An existing .env using DATABASE_URL must keep working."""
    monkeypatch.delenv("POETRY_DB__URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./legacy.db")
    cfg = DatabaseSettings(_env_file=None)
    assert cfg.url == "sqlite+aiosqlite:///./legacy.db"
    assert cfg.is_sqlite is True


def test_safe_url_masks_the_password():
    cfg = DatabaseSettings(
        url="postgresql+asyncpg://poet:sup3rs3cret@db:5432/poetry", _env_file=None
    )
    assert "sup3rs3cret" not in cfg.safe_url
    assert cfg.safe_url == "postgresql+asyncpg://poet:***@db:5432/poetry"


def test_safe_url_handles_a_url_without_credentials():
    cfg = DatabaseSettings(url="sqlite+aiosqlite:///./x.db", _env_file=None)
    assert cfg.safe_url == "sqlite+aiosqlite:///./x.db"


def test_secrets_are_not_exposed_by_repr():
    sec = SecuritySettings(secret_key="top-secret-value", _env_file=None)
    assert "top-secret-value" not in repr(sec)
    assert sec.secret_key.get_secret_value() == "top-secret-value"


@pytest.mark.parametrize(
    "client_id,client_secret,expected",
    [("id", "secret", True), ("", "secret", False), ("id", "", False), ("", "", False)],
)
def test_google_is_configured_only_with_both_halves(client_id, client_secret, expected):
    cfg = GoogleOAuthSettings(
        client_id=client_id, client_secret=client_secret, _env_file=None
    )
    assert cfg.configured is expected


def test_pool_size_is_validated():
    with pytest.raises(ValueError):
        DatabaseSettings(pool_size=0, _env_file=None)


def test_is_production_follows_app_env():
    assert Settings(app_env=AppEnv.production, _env_file=None).is_production is True
    assert Settings(app_env=AppEnv.development, _env_file=None).is_production is False


def test_google_redirect_uri_is_derived_from_the_api_url():
    s = Settings(public_api_url="https://api.example.com", _env_file=None)
    assert s.google_redirect_uri == "https://api.example.com/api/auth/google/callback"


def test_handler_is_a_singleton_and_can_be_swapped():
    original = get_db_handler()
    assert get_db_handler() is original

    replacement = DatabaseHandler(
        DatabaseSettings(url="sqlite+aiosqlite:///:memory:", _env_file=None)
    )
    set_db_handler(replacement)
    assert get_db_handler() is replacement

    set_db_handler(None)
    assert get_db_handler() is not replacement


def test_engine_is_not_built_until_first_use():
    """Importing must never open a connection."""
    handler = DatabaseHandler(
        DatabaseSettings(url="sqlite+aiosqlite:///:memory:", _env_file=None)
    )
    assert handler._engine is None
    assert handler.engine is not None
    assert handler.engine is handler.engine  # cached


def test_sqlite_engine_skips_pool_arguments():
    """SQLite rejects pool_size, so it must not be passed through."""
    handler = DatabaseHandler(
        DatabaseSettings(url="sqlite+aiosqlite:///:memory:", pool_size=20, _env_file=None)
    )
    assert handler.engine is not None  # would raise if pool args leaked through


async def test_healthcheck_passes_against_a_live_database(db_handler):
    assert await db_handler.healthcheck() is True


async def test_healthcheck_fails_against_an_unreachable_database():
    handler = DatabaseHandler(
        DatabaseSettings(
            url="postgresql+asyncpg://nobody:nobody@127.0.0.1:1/none",
            pool_timeout_seconds=1,
            _env_file=None,
        )
    )
    assert await handler.healthcheck() is False
    await handler.dispose()
