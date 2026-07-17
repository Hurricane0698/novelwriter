# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

import os
from pathlib import Path as _Path

from fastapi import Depends, FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import logging
import time
import uuid

from app.config import get_settings as _get_settings
from app.database import init_db
from app.logging_setup import configure_logging
from app.api import auth, novels, novel_support, world, copilot
from app.api import llm as llm_api
from app.api import usage as usage_api
from app.core.rate_limit import limiter
from app.core.auth import require_admin
from app.models import User
from app.version import APP_VERSION

logger = logging.getLogger(__name__)

_start_time: float = 0.0

_INSECURE_JWT_SECRETS = {"", "CHANGE-ME-IN-PRODUCTION"}
_ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"
_STATIC_FILE_CACHE_CONTROL = "public, max-age=3600"
_HTML_CACHE_CONTROL = "no-store"


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
    configure_logging(is_production=settings.is_production)
    init_db()
    logger.info("SCNGS started")
    yield


app = FastAPI(
    title="AI Novel Continuation System",
    description="Automatically continue unfinished web novels using AI",
    version=APP_VERSION,
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
app.include_router(usage_api.router)
app.include_router(world.router)
app.include_router(copilot.router)
app.include_router(llm_api.router)


class _CacheControlStaticFiles(StaticFiles):
    def __init__(self, *args, cache_control: str, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache_control = cache_control

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers.setdefault("Cache-Control", self._cache_control)
        return response


def _file_response_with_cache(path: _Path, *, cache_control: str):
    from fastapi.responses import FileResponse

    return FileResponse(path, headers={"Cache-Control": cache_control})


def _is_versioned_home_screenshot_request(request: Request, *, static_root: _Path, candidate: _Path) -> bool:
    if not request.query_params.get("v"):
        return False
    try:
        relative = candidate.relative_to(static_root)
    except ValueError:
        return False
    return relative.parts[:2] == ("screenshots", "home")


def _mount_spa_static_files(app: FastAPI, *, static_dir: _Path) -> None:
    static_root = static_dir.resolve()
    index_html = static_root / "index.html"
    assets_dir = static_root / "assets"

    if not index_html.is_file():
        return

    if assets_dir.is_dir():
        app.mount(
            "/assets",
            _CacheControlStaticFiles(directory=str(assets_dir), cache_control=_ASSET_CACHE_CONTROL),
            name="static-assets",
        )

    @app.get("/{full_path:path}")
    async def _spa_fallback(request: Request, full_path: str):
        if full_path:
            candidate = (static_root / full_path).resolve()
            try:
                candidate.relative_to(static_root)
            except ValueError:
                candidate = None
            if candidate is not None and candidate.is_file():
                if candidate.suffix == ".html":
                    cache_control = _HTML_CACHE_CONTROL
                elif _is_versioned_home_screenshot_request(request, static_root=static_root, candidate=candidate):
                    cache_control = _ASSET_CACHE_CONTROL
                else:
                    cache_control = _STATIC_FILE_CACHE_CONTROL
                return _file_response_with_cache(candidate, cache_control=cache_control)
        return _file_response_with_cache(index_html, cache_control=_HTML_CACHE_CONTROL)


def _probe_database_connection() -> bool:
    try:
        from app.database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            return True
        finally:
            db.close()
    except Exception:
        return False


def _uptime_seconds() -> float:
    return round(time.time() - _start_time, 1) if _start_time else 0


def _directory_is_writable(path: _Path) -> bool:
    return path.is_dir() and os.access(path, os.W_OK)


def _build_access_health_report(*, static_dir: _Path | None) -> dict[str, object]:
    settings = _get_settings()
    db_ok = _probe_database_connection()

    static_root = static_dir.resolve() if static_dir is not None else None
    index_html = static_root / "index.html" if static_root is not None else None
    assets_dir = static_root / "assets" if static_root is not None else None
    assets_present = bool(assets_dir and assets_dir.is_dir() and any(assets_dir.iterdir()))

    upload_dir = novel_support.UPLOAD_DIR
    invite_ready = settings.deploy_mode != "hosted" or settings.hosted_invite_login_enabled
    github_configured = auth._github_oauth_is_configured()
    github_enabled = settings.deploy_mode == "hosted" and settings.hosted_github_login_enabled and github_configured
    hosted_llm_ready = settings.deploy_mode != "hosted" or all(
        [
            settings.hosted_llm_base_url.strip(),
            settings.hosted_llm_api_key.strip(),
            settings.hosted_llm_model.strip(),
        ]
    )
    generation_ready = hosted_llm_ready and not settings.ai_manual_disable

    checks = {
        "database": {
            "critical": True,
            "ready": db_ok,
        },
        "static_delivery": {
            "critical": True,
            "ready": bool(index_html and index_html.is_file() and assets_present),
            "index_present": bool(index_html and index_html.is_file()),
            "assets_present": assets_present,
            "asset_cache_control": _ASSET_CACHE_CONTROL,
            "html_cache_control": _HTML_CACHE_CONTROL,
        },
        "auth": {
            "critical": settings.deploy_mode == "hosted",
            "ready": invite_ready,
            "invite_login_enabled": settings.deploy_mode == "hosted" and settings.hosted_invite_login_enabled,
            "invite_configured": settings.hosted_invite_login_enabled,
            "invite_code_count": len(settings.hosted_invite_code_entries),
            "github_login_enabled": github_enabled,
            "github_oauth_configured": github_configured,
        },
        "upload": {
            "critical": True,
            "ready": _directory_is_writable(upload_dir),
            "directory": str(upload_dir),
            "max_megabytes": int(settings.upload_max_megabytes),
        },
        "generation": {
            "critical": settings.deploy_mode == "hosted",
            "ready": generation_ready,
            "hosted_llm_configured": hosted_llm_ready,
            "ai_manual_disable": settings.ai_manual_disable,
            "stream_media_type": "application/x-ndjson",
            "stream_headers": novel_support.STREAMING_RESPONSE_HEADERS,
            "max_concurrent_llm_calls": settings.max_concurrent_llm_calls,
            "max_background_concurrent_llm_calls": settings.max_background_concurrent_llm_calls,
        },
        "monitoring": {
            "critical": False,
            "ready": settings.enable_event_tracking,
            "event_tracking_enabled": settings.enable_event_tracking,
        },
    }
    critical_failures = [name for name, check in checks.items() if check.get("critical") and not check.get("ready")]

    return {
        "status": "healthy" if not critical_failures else "degraded",
        "version": APP_VERSION,
        "uptime_seconds": _uptime_seconds(),
        "critical_failures": critical_failures,
        "checks": checks,
    }


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log method, path, status_code, duration_ms for each request."""
    if request.url.path in {"/api/health", "/api/health/access"}:
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
        "version": APP_VERSION,
        "docs": "/docs",
    }


@app.get("/api/health")
async def health():
    db_ok = _probe_database_connection()
    return {
        "status": "healthy" if db_ok else "degraded",
        "version": APP_VERSION,
        "uptime_seconds": _uptime_seconds(),
        "db_connected": db_ok,
    }


@app.get("/api/health/access")
async def access_health():
    return _build_access_health_report(static_dir=_static_dir if _static_dir.is_dir() else None)


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
