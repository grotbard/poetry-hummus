import os
import secrets

# Canonical POETRY_* names: a canonical value outranks its legacy alias
# whatever the source, so a developer's .env would otherwise win here.
os.environ["POETRY_APP_ENV"] = "test"
os.environ["POETRY_DB__URL"] = "sqlite+aiosqlite:///:memory:"
# Generated per run: a fixed string in the repo is a credential waiting to
# be reused somewhere real.
os.environ["POETRY_SECURITY__SECRET_KEY"] = secrets.token_urlsafe(32)
os.environ["POETRY_ADMIN__EMAIL"] = ""
os.environ["POETRY_ADMIN__PASSWORD"] = ""
for _legacy in ("DATABASE_URL", "SECRET_KEY", "APP_ENV",
                "BOOTSTRAP_ADMIN_EMAIL", "BOOTSTRAP_ADMIN_PASSWORD"):
    os.environ.pop(_legacy, None)

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
