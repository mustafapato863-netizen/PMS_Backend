"""Redis Caching Service
Provides get and set helpers for performance and team data caches,
falling back to in-memory cache when Redis is unavailable.
"""

import json
import logging
import redis
from config import settings
from services.session_cache import SessionCache

logger = logging.getLogger(__name__)

# Initialize central Redis client (connect immediately to avoid 1s lazy-connect timeout on every call)
redis_client = None
try:
    _client = redis.Redis.from_url(
        settings.REDIS_URL, 
        decode_responses=True,
        socket_timeout=1.0,
        socket_connect_timeout=1.0
    )
    _client.ping()
    redis_client = _client
except Exception as e:
    logger.warning(f"Could not connect to Redis at {settings.REDIS_URL}: {e}. Fallback to in-memory cache.")
    redis_client = None

# Process-level in-memory cache fallback (128 MB limit)
in_memory_cache = SessionCache(max_bytes=128 * 1024 * 1024)


class CacheService:
    """Enterprise Redis Caching Service (with in-memory fallback)"""

    @staticmethod
    def get_performance_cache(employee_id: str, month: str, year: int) -> dict:
        """Retrieve performance record from cache"""
        key = f"performance:{employee_id}:{month}:{year}"
        if redis_client:
            try:
                val = redis_client.get(key)
                if val:
                    return json.loads(val)
            except Exception as e:
                logger.warning(f"Redis get performance cache error: {e}")
        return in_memory_cache.get_session(key)

    @staticmethod
    def set_performance_cache(employee_id: str, month: str, year: int, data: dict, ttl: int = 3600) -> bool:
        """Set performance record in cache"""
        key = f"performance:{employee_id}:{month}:{year}"
        if redis_client:
            try:
                redis_client.set(key, json.dumps(data), ex=ttl)
            except Exception as e:
                logger.warning(f"Redis set performance cache error: {e}")
        in_memory_cache.set_session(key, data, ttl)
        return True

    @staticmethod
    def get_team_performance_cache(team_id: str, month: str, year: int) -> dict:
        """Retrieve team performance from cache"""
        key = f"team_performance:{team_id}:{month}:{year}"
        if redis_client:
            try:
                val = redis_client.get(key)
                if val:
                    return json.loads(val)
            except Exception as e:
                logger.warning(f"Redis get team performance cache error: {e}")
        return in_memory_cache.get_session(key)

    @staticmethod
    def set_team_performance_cache(team_id: str, month: str, year: int, data: dict, ttl: int = 3600) -> bool:
        """Set team performance in cache"""
        key = f"team_performance:{team_id}:{month}:{year}"
        if redis_client:
            try:
                redis_client.set(key, json.dumps(data), ex=ttl)
            except Exception as e:
                logger.warning(f"Redis set team performance cache error: {e}")
        in_memory_cache.set_session(key, data, ttl)
        return True
