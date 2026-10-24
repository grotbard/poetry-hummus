import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .configuration import settings
from .db import get_db_handler
from .models import Base
from .routers import admin, auth, members
from .seed import seed_all

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("poetry-hummus")


async def _run_migrations() -> None:
    """Apply Alembic migrations in-process.

    Only for platforms with no pre-deploy hook (Render's free plan). Alembic
    is synchronous, so it runs in a worker thread to keep the event loop free.
    """
    import asyncio
    from alembic import command
    from alembic.config import Config

    def upgrade() -> None:
        cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
        command.upgrade(cfg, "head")

    log.info("Applying database migrations")
    await asyncio.to_thread(upgrade)
    log.info("Migrations up to date")


@asynccontextmanager
async def lifespan(app: FastAPI):
    handler = get_db_handler()
    log.info("Connecting to %s", handler.config.safe_url)

    if settings.run_migrations:
        await _run_migrations()
    elif not settings.is_production:
        # In development, create tables directly; production migrates.
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

@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Headers that only make sense once TLS terminates in front of us.

    HSTS matters most: without it a browser that tries http:// first sends
    one unencrypted request — carrying the session cookie, or a password on
    a login POST — before the redirect to https. Only sent in production,
    since pinning localhost to https would break development.
    """
    response = await call_next(request)
    if settings.is_production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Uploaded menu photos are served straight off disk, from a mounted volume
# in production (POETRY_MEDIA_DIR) so they survive a redeploy.
settings.media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")

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


# ---------------------------------------------------------------------------
# Optional single-origin mode.
#
# With POETRY_STATIC_DIR pointing at a built SPA, this process serves the
# frontend too. Same origin means no CORS and no cross-site cookie, which
# matters on hosts like *.onrender.com: those subdomains are separate sites,
# so a SameSite=Lax session cookie set by the API would never be sent by the
# web app. Mounted last so it cannot shadow /api or /media.
# ---------------------------------------------------------------------------
if settings.serve_frontend:
    static_dir = settings.static_dir
    assert static_dir is not None  # guarded by serve_frontend

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        """Serve built assets, falling back to index.html for SPA routes."""
        candidate = (static_dir / full_path).resolve()
        # Only serve files genuinely inside the build directory.
        if (
            full_path
            and candidate.is_file()
            and candidate.is_relative_to(static_dir.resolve())
        ):
            return FileResponse(candidate)
        return FileResponse(static_dir / "index.html")

    log.info("Serving frontend from %s", static_dir)
