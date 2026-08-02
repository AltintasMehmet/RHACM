import logging

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None


async def get_redis() -> redis.Redis | None:
    """Return the module-level async Redis client, or None if unavailable."""
    return _redis


async def connect_redis() -> None:
    """Create the async Redis connection on startup."""
    global _redis
    try:
        _redis = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        # Verify connectivity
        await _redis.ping()
        logger.info("Connected to Redis")
    except Exception:
        logger.warning(
            "Could not connect to Redis — usage counters will fall back to DB",
            exc_info=True,
        )
        _redis = None


async def close_redis() -> None:
    """Close the Redis connection gracefully."""
    global _redis
    try:
        if _redis is not None:
            await _redis.aclose()
            logger.info("Redis connection closed")
    except Exception:
        logger.warning("Error closing Redis connection", exc_info=True)
    finally:
        _redis = None
