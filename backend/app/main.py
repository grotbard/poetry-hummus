import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import SessionLocal, engine
from .models import Base
from .routers import admin, auth, members
from .seed import seed_all

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("poetry-hummus")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # In development, create tables directly; production uses Alembic migrations.
    if not settings.is_production:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        await seed_all(db)
    log.info("Poetry Hummus API ready (env=%s)", settings.app_env)
    yield
    await engine.dispose()


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
    return {"status": "ok", "env": settings.app_env}
