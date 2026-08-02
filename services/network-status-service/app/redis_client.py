import logging

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """Return the shared Redis connection, creating it on first call."""
    global _redis
    if _redis is None:
        _redis = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        logger.info("Connected to Redis at %s", settings.redis_url)
    return _redis


async def close_redis() -> None:
    """Close the Redis connection gracefully."""
    global _redis
    if _redis is not None:
        try:
            await _redis.close()
            logger.info("Redis connection closed")
        except Exception:
            logger.warning("Error closing Redis connection", exc_info=True)
        finally:
            _redis = None


async def redis_healthy() -> bool:
    """Return True if Redis responds to PING."""
    try:
        r = await get_redis()
        return await r.ping()
    except Exception:
        return False
