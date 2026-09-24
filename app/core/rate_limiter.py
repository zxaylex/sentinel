
import time
import redis.asyncio as redis
from app.config import get_settings

settings = get_settings()


class SlidingWindowRateLimiter:
    """
    Redis-backed sliding window rate limiter.

    Usage:
        limiter = SlidingWindowRateLimiter(redis_client)
        allowed = await limiter.check("user:123", max_requests=100, window_seconds=60)
    """

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def check(self, key: str, max_requests: int, window_seconds: int = 60) -> tuple[bool, dict]:
        """
        Check if a request is allowed under the rate limit.

        Returns:
            (allowed: bool, info: dict) where info contains limit, remaining, retry_after
        """
        now = time.time()
        window_start = now - window_seconds
        pipe = self.redis.pipeline()

        # Remove expired entries
        pipe.zremrangebyscore(key, 0, window_start)
        # Add current request
        pipe.zadd(key, {f"{now}": now})
        # Count requests in window
        pipe.zcard(key)
        # Set TTL on the key
        pipe.expire(key, window_seconds)

        results = await pipe.execute()
        request_count = results[2]

        info = {
            "limit": max_requests,
            "remaining": max(0, max_requests - request_count),
            "retry_after": int(window_seconds - (now - window_start)) if request_count > max_requests else 0,
        }

        return request_count <= max_requests, info