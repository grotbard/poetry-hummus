import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .configuration import settings
from .db import get_db_handler
from .models import Base
from .routers import admin, auth, members
from .seed import seed_all

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("poetry-hummus")


@asynccontextmanager
async def lifespan(app: FastAPI):
    handler = get_db_handler()
    log.info("Connecting to %s", handler.config.safe_url)

    # In development, create tables directly; production uses Alembic migrations.
    if not settings.is_production:
        async with handler.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    async with handler.session() as db:
        await seed_all(db)

    log.info("Poetry Hummus API ready (env=%s)", settings.app_env)
    yield
    await handler.dispose()


app = FastAPI(
    title="Poetry Hummus Club API",
    description="חומוס המשורר — club members, orders and Poet Coins",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Uploaded menu photos are served straight off disk.
MEDIA_DIR = Path(__file__).resolve().parents[1] / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

app.include_router(auth.router)
app.include_router(members.router)
app.include_router(admin.router)


@app.get("/api/health")
async def health() -> dict:
    """Liveness: the process is up. Cheap enough for frequent polling."""
    return {"status": "ok", "env": settings.app_env}


@app.get("/api/ready")
async def ready(response: Response) -> dict:
    """Readiness: the database is actually reachable."""
    healthy = await get_db_handler().healthcheck()
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "degraded", "database": healthy}
