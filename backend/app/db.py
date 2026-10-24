"""Single entry point for database access.

Everything that touches Postgres goes through `get_db_handler()`, which owns
the engine and session factory. The engine is built lazily from
`settings.database`, so importing this module never opens a connection and
tests can point it somewhere else before first use.

FastAPI routes depend on `get_db`; background scripts use the handler's
`session()` context manager directly.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .configuration import DatabaseSettings, settings

log = logging.getLogger(__name__)


class DatabaseHandler:
    """Owns the engine and hands out sessions."""

    def __init__(self, config: DatabaseSettings) -> None:
        self._config = config
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    @property
    def config(self) -> DatabaseSettings:
        return self._config

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = self._create_engine()
            log.info("Database engine created for %s", self._config.safe_url)
        return self._engine

    @property
    def sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        if self._sessionmaker is None:
            self._sessionmaker = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
            )
        return self._sessionmaker

    def _create_engine(self) -> AsyncEngine:
        kwargs: dict = {"echo": self._config.echo_sql}
        # SQLite (used by tests) has no connection pool to size.
        if not self._config.is_sqlite:
            kwargs.update(
                pool_size=self._config.pool_size,
                max_overflow=self._config.max_overflow,
                pool_timeout=self._config.pool_timeout_seconds,
                pool_recycle=self._config.pool_recycle_seconds,
                pool_pre_ping=self._config.pool_pre_ping,
            )
        engine = create_async_engine(self._config.url, **kwargs)

        if self._config.is_sqlite:
            # SQLite ships with foreign keys disabled, so ON DELETE CASCADE
            # silently does nothing and tests would diverge from Postgres,
            # which always enforces them.
            from sqlalchemy import event

            @event.listens_for(engine.sync_engine, "connect")
            def _enable_foreign_keys(dbapi_connection, _record):  # noqa: ANN001
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        return engine

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Session for scripts and startup tasks, outside the request cycle."""
        async with self.sessionmaker() as session:
            yield session

    async def dispose(self) -> None:
        """Close pooled connections; called on application shutdown."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._sessionmaker = None

    async def healthcheck(self) -> bool:
        """True when a trivial query succeeds against the configured database."""
        from sqlalchemy import text

        try:
            async with self.session() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 - health must never raise
            log.exception("Database healthcheck failed")
            return False


_handler: DatabaseHandler | None = None


def get_db_handler() -> DatabaseHandler:
    """The process-wide database handler."""
    global _handler
    if _handler is None:
        _handler = DatabaseHandler(settings.database)
    return _handler


def set_db_handler(handler: DatabaseHandler | None) -> None:
    """Swap the handler. Intended for tests; pass None to reset."""
    global _handler
    _handler = handler


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped session."""
    async with get_db_handler().session() as session:
        yield session
