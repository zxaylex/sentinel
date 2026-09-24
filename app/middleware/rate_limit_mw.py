from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import get_settings
from app.core.rate_limiter import SlidingWindowRateLimiter

settings = get_settings()

# Paths that get stricter rate limits
AUTH_PATHS = {"/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh"}
# Paths that skip rate limiting entirely
EXEMPT_PATHS = {"/health", "/health/ready", "/docs", "/redoc", "/openapi.json"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip rate limiting for health/docs
        if path in EXEMPT_PATHS:
            return await call_next(request)

        # Get Redis from app state (set during lifespan)
        redis = getattr(request.app.state, "redis", None)
        if not redis:
            # Redis not available — let request through
            return await call_next(request)

        limiter = SlidingWindowRateLimiter(redis)

        # Determine rate limit key and limits
        # Use IP for anonymous, user_id for authenticated (from header set by auth)
        client_ip = request.client.host if request.client else "unknown"
        key_prefix = f"ratelimit:{client_ip}"

        if path in AUTH_PATHS:
            max_requests = settings.RATE_LIMIT_AUTH
            key = f"{key_prefix}:auth"
        else:
            max_requests = settings.RATE_LIMIT_DEFAULT
            key = f"{key_prefix}:default"

        allowed, info = await limiter.check(key, max_requests=max_requests, window_seconds=60)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests"},
                headers={
                    "Retry-After": str(info["retry_after"]),
                    "X-RateLimit-Limit": str(info["limit"]),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)

        # Add rate limit headers to successful responses
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])

        return response
