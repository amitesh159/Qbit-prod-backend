"""
Redis Client Manager
Uses async Redis for caching, sessions, and rate limiting
"""
import structlog
from redis.asyncio import Redis, ConnectionPool
from redis.exceptions import ConnectionError as RedisConnectionError
from config.settings import settings

logger = structlog.get_logger(__name__)

# Global Redis client instance
_redis_client: Redis | None = None
_connection_pool: ConnectionPool | None = None


async def get_redis_client() -> Redis | None:
    """
    Get Redis client instance with connection pooling.
    Creates connection on first call, reuses for subsequent calls.
    
    Returns:
        Redis | None: Async Redis client instance or None if connection failed
    """
    global _redis_client, _connection_pool
    
    if _redis_client is not None:
        return _redis_client
    
    try:
        logger.info(
            "connecting_to_redis",
            max_connections=settings.redis_max_connections
        )
        
        _connection_pool = ConnectionPool.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            socket_timeout=settings.redis_socket_timeout,
            socket_connect_timeout=settings.redis_socket_connect_timeout,
            decode_responses=True,
            encoding="utf-8"
        )
        
        _redis_client = Redis(connection_pool=_connection_pool)
        
        # Verify connection
        await _redis_client.ping()
        
        logger.info("redis_connected")
        
        return _redis_client
        
    except Exception as e:
        logger.warning(
            "redis_connection_failed_continuing_without_redis",
            error=str(e)
        )
        # Don't raise - allow app to continue without Redis
        _redis_client = None
        return None


async def close_redis_connection() -> None:
    """
    Close Redis connection and cleanup resources.
    Should be called on application shutdown.
    """
    global _redis_client, _connection_pool
    
    if _redis_client is not None:
        logger.info("closing_redis_connection")
        await _redis_client.aclose()
        _redis_client = None
    
    if _connection_pool is not None:
        await _connection_pool.aclose()
        _connection_pool = None
        
    logger.info("redis_connection_closed")


async def set_cache(key: str, value: str, expire: int | None = None) -> bool:
    """
    Set a value in Redis cache with optional expiration.
    
    Args:
        key: Cache key
        value: Value to cache
        expire: Expiration time in seconds (None = no expiration)
        
    Returns:
        bool: True if successful
    """
    redis = await get_redis_client()
    
    if redis is None:
        logger.debug("redis_unavailable_skipping_set", key=key)
        return False
    
    try:
        if expire:
            await redis.setex(key, expire, value)
        else:
            await redis.set(key, value)
        return True
    except Exception as e:
        logger.error(
            "redis_set_failed",
            key=key,
            error=str(e)
        )
        return False


async def get_cache(key: str) -> str | None:
    """
    Get a value from Redis cache.
    
    Args:
        key: Cache key
        
    Returns:
        str | None: Cached value or None if not found
    """
    redis = await get_redis_client()
    
    if redis is None:
        return None
    
    try:
        return await redis.get(key)
    except Exception as e:
        logger.error(
            "redis_get_failed",
            key=key,
            error=str(e)
        )
        return None


async def delete_cache(key: str) -> bool:
    """
    Delete a key from Redis cache.
    
    Args:
        key: Cache key
        
    Returns:
        bool: True if successful
    """
    redis = await get_redis_client()
    
    if redis is None:
        return False
    
    try:
        await redis.delete(key)
        return True
    except Exception as e:
        logger.error(
            "redis_delete_failed",
            key=key,
            error=str(e)
        )
        return False


async def increment_counter(key: str, expire: int | None = None) -> int:
    """
    Increment a counter in Redis.
    
    Args:
        key: Counter key
        expire: Set expiration if key is new (seconds)
        
    Returns:
        int: New counter value
    """
    redis = await get_redis_client()
    
    if redis is None:
        return 0
    
    try:
        count = await redis.incr(key)
        if count == 1 and expire:
            await redis.expire(key, expire)
        return count
    except Exception as e:
        logger.error(
            "redis_incr_failed",
            key=key,
            error=str(e)
        )
        return 0
