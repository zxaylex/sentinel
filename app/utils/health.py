"""Health check endpoints."""

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.database import async_session

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health():
    """Basic liveness check — is the server process alive?"""
    return {"status": "healthy"}


@router.get("/health/ready")
async def readiness(request: Request):
    """
    Readiness check — can the service actually handle traffic?
    Checks database and Redis connectivity.
    """
    checks: dict[str, str] = {}

    # Database check
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Redis check
    redis = getattr(request.app.state, "redis", None)
    if redis:
        try:
            await redis.ping()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = f"error: {e}"
    else:
        checks["redis"] = "not configured"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "ready" if all_ok else "degraded",
        "checks": checks,
    }
