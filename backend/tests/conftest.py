import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "")

import pytest
import pytest_asyncio

from app.configuration import DatabaseSettings
from app.db import DatabaseHandler, set_db_handler
from app.models import Base, User, UserRole


@pytest_asyncio.fixture
async def db_handler():
    """A handler backed by a throwaway in-memory SQLite database.

    Installed as the process handler so code calling get_db_handler() —
    including FastAPI's get_db dependency — reaches this one.
    """
    handler = DatabaseHandler(
        DatabaseSettings(url="sqlite+aiosqlite:///:memory:", echo_sql=False)
    )
    async with handler.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    set_db_handler(handler)
    yield handler
    set_db_handler(None)
    await handler.dispose()


@pytest_asyncio.fixture
async def db(db_handler):
    async with db_handler.session() as session:
        yield session


@pytest_asyncio.fixture
async def member(db):
    user = User(email="poet@example.com", full_name="משורר", role=UserRole.member)
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
def anyio_backend():
    return "asyncio"
