"""Cache Invalidation Service
Manages deleting keys and broadcasting pub/sub notifications for cache invalidation.
"""

import json
import logging
from services.cache_service import redis_client

logger = logging.getLogger(__name__)


class CacheInvalidationService:
    """Handles Redis cache invalidation and pub/sub messages for multi-instance synchronization"""

    @staticmethod
    def invalidate_performance_record(employee_id: str, month: str, year: int) -> None:
        """Invalidate performance record keys and publish invalidation message"""
        if not redis_client:
            return

        key = f"performance:{employee_id}:{month}:{year}"
        try:
            redis_client.delete(key)
            # Also publish message for multi-instance sync
            message = {
                "action": "invalidate",
                "type": "performance",
                "employee_id": str(employee_id),
                "month": month,
                "year": int(year)
            }
            redis_client.publish("cache_invalidation", json.dumps(message))
        except Exception as e:
            logger.warning(f"Failed to invalidate performance record cache: {e}")

    @staticmethod
    def invalidate_team_config(team_id: str, month: str = None, year: int = None) -> None:
        """Invalidate team config/performance keys and publish invalidation message"""
        if not redis_client:
            return

        try:
            keys_to_delete = []
            if month and year:
                keys_to_delete.append(f"team_performance:{team_id}:{month}:{year}")
            else:
                # Find all keys matching team_performance:{team_id}:*
                # Use scan_iter for performance safety in production
                for key in redis_client.scan_iter(match=f"team_performance:{team_id}:*"):
                    keys_to_delete.append(key)

            if keys_to_delete:
                redis_client.delete(*keys_to_delete)

            message = {
                "action": "invalidate",
                "type": "team",
                "team_id": str(team_id),
                "month": month,
                "year": int(year) if year else None
            }
            redis_client.publish("cache_invalidation", json.dumps(message))
        except Exception as e:
            logger.warning(f"Failed to invalidate team config cache: {e}")
