# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from pathlib import Path as _Path

from fastapi import Depends, FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import logging
import time
import uuid

from app.config import get_settings as _get_settings
from app.database import init_db
from app.api import auth, novels, lorebook, dashboard, world
from app.api import llm as llm_api
from app.api import usage as usage_api
from app.core.rate_limit import limiter
from app.core.auth import require_admin
from app.models import User

logger = logging.getLogger(__name__)

_start_time: float = 0.0

_INSECURE_JWT_SECRETS = {"", "CHANGE-ME-IN-PRODUCTION"}


class StartupSecurityValidationError(RuntimeError):
    """Raised when startup configuration violates mandatory security constraints."""


def _validate_startup_security_settings(
    *,
    jwt_secret_key: str,
    deploy_mode: str,
    is_production: bool,
) -> None:
    """Refuse startup when using an insecure JWT secret key in unsafe modes."""
    normalized_secret = (jwt_secret_key or "").strip()
    normalized_deploy_mode = (deploy_mode or "").strip().lower()

    if normalized_deploy_mode == "hosted" and normalized_secret in _INSECURE_JWT_SECRETS:
        raise StartupSecurityValidationError(
            "Refusing to start with DEPLOY_MODE=hosted and an insecure JWT secret. "
            "Set JWT_SECRET_KEY to a non-default value."
        )

    if is_production and normalized_deploy_mode == "selfhost":
        raise StartupSecurityValidationError(
            "Refusing to start in production with DEPLOY_MODE=selfhost. "
            "Set DEPLOY_MODE=hosted for web deployments."
        )

    if is_production and normalized_secret in _INSECURE_JWT_SECRETS:
        raise StartupSecurityValidationError(
            "Refusing to start in production with an insecure JWT secret. "
            "Set JWT_SECRET_KEY to a non-default value."
        )

    if not is_production and normalized_secret in _INSECURE_JWT_SECRETS:
        logger.warning(
            "Using default JWT secret in non-production environment. "
            "Do not use this configuration outside local development."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _start_time
    _start_time = time.time()
    # Force reload settings from .env on server start/reload
    from app.config import reload_settings
    settings = reload_settings()
    _validate_startup_security_settings(
        jwt_secret_key=settings.jwt_secret_key,
        deploy_mode=settings.deploy_mode,
        is_production=settings.is_production,
    )
    _configure_logging(is_production=settings.is_production)
    init_db()
    logger.info("SCNGS started")
    yield


def _configure_logging(*, is_production: bool):
    """Set up structured JSON logging for production, console for dev."""
    import structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer() if is_production else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


app = FastAPI(
    title="AI Novel Continuation System",
    description="Automatically continue unfinished web novels using AI",
    version="0.01 Beta",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_cors_settings = _get_settings()
_default_cors = ["http://localhost:5173"]
_skip_cors = (
    _cors_settings.deploy_mode == "selfhost"
    and _cors_settings.cors_allowed_origins == _default_cors
)
if not _skip_cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(novels.router)
app.include_router(lorebook.router)
app.include_router(dashboard.router)
app.include_router(usage_api.router)
app.include_router(world.router)
app.include_router(llm_api.router)


def _mount_spa_static_files(app: FastAPI, *, static_dir: _Path) -> None:
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    static_root = static_dir.resolve()
    index_html = static_root / "index.html"
    assets_dir = static_root / "assets"

    if not index_html.is_file():
        return

    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static-assets")

    @app.get("/{full_path:path}")
    async def _spa_fallback(full_path: str):
        if full_path:
            candidate = (static_root / full_path).resolve()
            try:
                candidate.relative_to(static_root)
            except ValueError:
                candidate = None
            if candidate is not None and candidate.is_file():
                return FileResponse(candidate)
        return FileResponse(index_html)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log method, path, status_code, duration_ms for each request."""
    if request.url.path == "/api/health":
        return await call_next(request)
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    logger.info(
        "request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/api")
async def api_root():
    return {
        "message": "AI Novel Continuation System",
        "version": "0.01 Beta",
        "docs": "/docs",
    }


@app.get("/api/health")
async def health():
    db_ok = False
    try:
        from app.database import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_ok = True
        finally:
            db.close()
    except Exception:
        pass
    uptime = round(time.time() - _start_time, 1) if _start_time else 0
    return {
        "status": "healthy" if db_ok else "degraded",
        "version": "0.01 Beta",
        "uptime_seconds": uptime,
        "db_connected": db_ok,
    }


@app.get("/api/debug/settings")
async def debug_settings(admin: User = Depends(require_admin)):
    from app.config import get_settings
    settings = get_settings()
    if not settings.enable_debug_endpoints:
        raise HTTPException(status_code=404, detail="Not Found")
    return {
        "openai_base_url": settings.openai_base_url,
    }


# Serve frontend static files (SPA fallback: non-/api paths → index.html)
_static_dir = _Path(__file__).parent.parent / "static"
if _static_dir.is_dir():
    _mount_spa_static_files(app, static_dir=_static_dir)
