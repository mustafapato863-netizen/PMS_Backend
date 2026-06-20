"""Redis Caching Service
Provides get and set helpers for performance and team data caches,
falling back gracefully on connection errors.
"""

import json
import logging
import redis
from config import settings

logger = logging.getLogger(__name__)

# Initialize central Redis client
try:
    redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
except Exception as e:
    logger.warning(f"Could not connect to Redis at {settings.REDIS_URL}: {e}. Fallback to DB only.")
    redis_client = None


class CacheService:
    """Enterprise Redis Caching Service"""

    @staticmethod
    def get_performance_cache(employee_id: str, month: str, year: int) -> dict:
        """Retrieve performance record from cache"""
        if not redis_client:
            return None
        key = f"performance:{employee_id}:{month}:{year}"
        try:
            val = redis_client.get(key)
            if val:
                return json.loads(val)
        except Exception as e:
            logger.warning(f"Redis get performance cache error: {e}")
        return None

    @staticmethod
    def set_performance_cache(employee_id: str, month: str, year: int, data: dict, ttl: int = 3600) -> bool:
        """Set performance record in cache"""
        if not redis_client:
            return False
        key = f"performance:{employee_id}:{month}:{year}"
        try:
            redis_client.set(key, json.dumps(data), ex=ttl)
            return True
        except Exception as e:
            logger.warning(f"Redis set performance cache error: {e}")
        return False

    @staticmethod
    def get_team_performance_cache(team_id: str, month: str, year: int) -> dict:
        """Retrieve team performance from cache"""
        if not redis_client:
            return None
        key = f"team_performance:{team_id}:{month}:{year}"
        try:
            val = redis_client.get(key)
            if val:
                return json.loads(val)
        except Exception as e:
            logger.warning(f"Redis get team performance cache error: {e}")
        return None

    @staticmethod
    def set_team_performance_cache(team_id: str, month: str, year: int, data: dict, ttl: int = 3600) -> bool:
        """Set team performance in cache"""
        if not redis_client:
            return False
        key = f"team_performance:{team_id}:{month}:{year}"
        try:
            redis_client.set(key, json.dumps(data), ex=ttl)
            return True
        except Exception as e:
            logger.warning(f"Redis set team performance cache error: {e}")
        return False
