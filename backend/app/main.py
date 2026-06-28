import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import (
    admin,
    authors,
    books,
    feedback,
    notifications,
    onboarding,
    profile,
    recommendations,
    tbr,
)
from app.config import settings
from app.integrations import qdrant
from app.logging import log_entry_exit, setup_logging

# Structured JSON logging (replaces standard logging.basicConfig)
_log_worker = setup_logging()
logger = logging.getLogger(__name__)

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up PageTurner API...")

    # Qdrant startup assertion — prevent silent unauthenticated cloud connections
    if settings.QDRANT_URL and "cloud.qdrant.io" in settings.QDRANT_URL:
        if not settings.QDRANT_API_KEY:
            logger.error(
                "FATAL: QDRANT_API_KEY is required when using Qdrant Cloud. "
                "Set it in .env before starting."
            )
            raise RuntimeError("Missing QDRANT_API_KEY for Qdrant Cloud.")

    try:
        qdrant.create_collection_if_not_exists("books_catalog")
        logger.info("Qdrant collection 'books_catalog' verified/created.")
    except Exception as e:
        logger.error(f"Failed to initialize Qdrant: {e}")

    yield

    # Shutdown MongoDB log worker
    from app.logging import _log_worker

    if _log_worker:
        _log_worker.stop()

    logger.info("Shutting down PageTurner API...")


app = FastAPI(
    title="PageTurner API",
    description="Backend for the Contextual Reading Intelligence System",
    version="2.0",
    lifespan=lifespan,
)

# ── Rate limit error handler ──────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(onboarding.router, prefix="/api/v1/onboarding", tags=["Onboarding"])
app.include_router(
    recommendations.router, prefix="/api/v1/recommend", tags=["Recommendations"]
)
app.include_router(feedback.router, prefix="/api/v1/feedback", tags=["Feedback"])
app.include_router(books.router, prefix="/api/v1/books", tags=["Books & Enrichment"])
app.include_router(tbr.router, prefix="/api/v1/tbr", tags=["TBR Queue"])
app.include_router(authors.router, prefix="/api/v1/authors", tags=["Authors"])
app.include_router(
    notifications.router, prefix="/api/v1/notifications", tags=["Notifications"]
)
app.include_router(profile.router, prefix="/api/v1/profile", tags=["Profile"])
# Admin — protected by require_admin dependency inside the router
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])


@app.get("/health", tags=["System"])
def health_check():
    return {"status": "healthy", "version": "2.0"}
