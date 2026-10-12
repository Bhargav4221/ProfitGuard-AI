import logging
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1 import api_v1_router
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.crypto import AESGCMCryptoService
from app.services.ml_shadow_service import ml_shadow_service

logger = logging.getLogger("profitguard.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Executes safe startup validation and logging on application boot."""
    # 1. Database validation
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        logger.info("Startup validation: Database connected successfully.")
    except Exception as exc:
        logger.error("Startup validation failure: Database unreachable: %s", exc)

    # 2. Encryption keys validation
    try:
        crypto = AESGCMCryptoService()
        token = crypto.encrypt("startup_healthcheck_probe")
        assert crypto.decrypt(token) == "startup_healthcheck_probe"
        logger.info("Startup validation: AES-256-GCM encryption initialized (active version: %s).", crypto.active_version)
    except Exception as exc:
        logger.error("Startup validation failure: Encryption configuration error: %s", exc)

    # 3. ML Model Readiness check
    if ml_shadow_service.is_ready():
        logger.info("Startup validation: Shadow ML inference ready (model_version: %s).",
                    ml_shadow_service._artifact.get("model_version") if ml_shadow_service._artifact else "unknown")
    else:
        logger.warning("Startup validation notice: Shadow ML inference running in fallback mode (%s).",
                       ml_shadow_service._load_error or "Artifact unavailable")

    # 4. Production security warnings
    if settings.ENVIRONMENT == "production":
        if "dev-secret-key" in settings.JWT_SECRET_KEY:
            logger.critical("SECURITY WARNING: Running in production with default development JWT_SECRET_KEY!")
        if settings.DEBUG:
            logger.warning("SECURITY WARNING: DEBUG mode is active in production environment.")

    yield


# FastAPI 0.110+ backward compatibility:
# In FastAPI 0.110+, include_router wraps sub-routers in _IncludedRouter instances
# which lack .methods and .path attributes. Provide safe property accessors so
# diagnostic scripts, test runners, and inspectors iterating over app.routes
# do not raise AttributeError: '_IncludedRouter' object has no attribute 'methods'.
try:
    from fastapi.routing import _IncludedRouter
    if not hasattr(_IncludedRouter, "methods"):
        def _get_included_methods(self):
            methods = set()
            for candidate in self.effective_candidates():
                if hasattr(candidate, "methods") and candidate.methods:
                    methods.update(candidate.methods)
                elif hasattr(candidate, "original_route") and hasattr(candidate.original_route, "methods"):
                    if candidate.original_route.methods:
                        methods.update(candidate.original_route.methods)
            return methods or {"GET"}
        _IncludedRouter.methods = property(_get_included_methods)

    if not hasattr(_IncludedRouter, "path"):
        _IncludedRouter.path = property(lambda self: getattr(self.include_context, "prefix", "") or "")
except (ImportError, AttributeError):
    pass

app = FastAPI(
    title=settings.APP_NAME,
    description="Multi-tenant SaaS platform for Indian D2C e-commerce order-risk reduction and contribution-profit optimization.",
    version="0.1.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz", tags=["Health"])
def health_check(session: Session = Depends(get_db)):
    """Healthcheck endpoint for container orchestration and uptime monitoring."""
    try:
        session.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected",
            "service": settings.APP_NAME,
            "environment": settings.ENVIRONMENT,
            "version": "0.1.0",
        }
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "database": f"unreachable: {str(e)}",
                "service": settings.APP_NAME,
                "environment": settings.ENVIRONMENT,
                "version": "0.1.0",
            },
        )


# Include API v1
app.include_router(api_v1_router, prefix=settings.API_V1_STR)


def get_all_registered_endpoints():
    """Returns a structured list of all registered API endpoints, methods, and tags."""
    openapi_spec = app.openapi()
    endpoints = []
    for path, methods in openapi_spec.get("paths", {}).items():
        for method, details in methods.items():
            endpoints.append({
                "path": path,
                "method": method.upper(),
                "summary": details.get("summary", ""),
                "tags": details.get("tags", []),
            })
    return endpoints


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Fallback exception handler ensuring structured error responses without leaking tracebacks in production."""
    if settings.DEBUG:
        # In debug mode let FastAPI format or return detailed message
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": str(exc), "type": type(exc).__name__},
        )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please contact support."},
    )
