from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.middleware.logging_mw import LoggingMiddleware
from app.middleware.rate_limit_mw import RateLimitMiddleware
from app.utils.health import router as health_router
from app.utils.logging import setup_logging

settings = get_settings()

# Configure structured logging
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print(f"🚀 {settings.APP_NAME} starting up...")

    # Initialize Redis
    app.state.redis = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )
    try:
        await app.state.redis.ping()
        print("✅ Redis connected")
    except Exception as e:
        print(f"⚠️  Redis connection failed: {e} — rate limiting disabled")
        app.state.redis = None

    yield

    # Shutdown
    print(f"👋 {settings.APP_NAME} shutting down...")
    if app.state.redis:
        await app.state.redis.close()


app = FastAPI(
    title=settings.APP_NAME,
    description="Authentication Gateway & RBAC Service",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom middleware (order matters — outermost runs first)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RateLimitMiddleware)

# Health check routes (no /api/v1 prefix)
app.include_router(health_router)

# API routes
app.include_router(api_router, prefix="/api/v1")
