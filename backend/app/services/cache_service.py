"""Redis cache service for Supabase query results.

Provides a centralized caching layer to reduce database load for frequently
accessed data like buildings, equipment lists, and configuration.

Usage:
    from app.services.cache_service import cache

    # Cache a value
    cache.set("buildings:all", buildings_data, ttl=300)

    # Get cached value
    data = cache.get("buildings:all")

    # Use decorator for automatic caching
    @cache.cached("equipment:building:{site_id}", ttl=300)
    def get_equipment_by_site(site_id: str):
        return repo.query(...)

    # Invalidate on write
    cache.delete("buildings:all")
    cache.delete_pattern("equipment:*")
"""

import json
import logging
import logging as _logging
import os as _os
import time as _time
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Type hints for decorator
P = ParamSpec("P")
R = TypeVar("R")


class CacheService:
    """Redis-backed cache service with fallback to no-op when unavailable."""

    # TTL presets by data type (seconds)
    TTL_STATIC = 600  # 10 min - rarely changes (safety rules, config)
    TTL_SEMI_STATIC = 300  # 5 min - changes occasionally (buildings, equipment list)
    TTL_DYNAMIC = 60  # 1 min - changes frequently (alerts, predictions)
    TTL_REALTIME = 15  # 15 sec - near-realtime (device state)

    def __init__(self):
        self._client = None
        self._connected = False
        self._stats = {"hits": 0, "misses": 0, "errors": 0}

    def _get_client(self):
        """Lazy initialization of Redis client."""
        if self._client is not None:
            return self._client

        if not settings.redis_enabled:
            logger.info("Redis caching disabled by configuration")
            return None

        try:
            import redis

            self._client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            # Test connection
            self._client.ping()
            self._connected = True
            logger.info(f"Redis cache connected: {settings.redis_url}")
            return self._client
        except Exception as e:
            logger.warning(f"Redis unavailable, caching disabled: {e}")
            self._client = None
            self._connected = False
            return None

    @property
    def is_connected(self) -> bool:
        """Check if Redis is available."""
        client = self._get_client()
        return client is not None and self._connected

    def _make_key(self, key: str) -> str:
        """Prefix key with namespace."""
        return f"bms:{key}"

    def get(self, key: str) -> Any | None:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        client = self._get_client()
        if not client:
            return None

        try:
            full_key = self._make_key(key)
            data = client.get(full_key)
            if data:
                self._stats["hits"] += 1
                self._inc_prometheus("hit")
                return json.loads(data)
            self._stats["misses"] += 1
            self._inc_prometheus("miss")
            return None
        except Exception as e:
            self._stats["errors"] += 1
            self._inc_prometheus("error")
            logger.debug(f"Cache get error for {key}: {e}")
            return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl: Time-to-live in seconds (default from settings)

        Returns:
            True if cached successfully
        """
        client = self._get_client()
        if not client:
            return False

        try:
            full_key = self._make_key(key)
            ttl = ttl or settings.redis_default_ttl
            data = json.dumps(value, default=str)
            client.setex(full_key, ttl, data)
            return True
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"Cache set error for {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """Delete a key from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if deleted
        """
        client = self._get_client()
        if not client:
            return False

        try:
            full_key = self._make_key(key)
            client.delete(full_key)
            return True
        except Exception as e:
            logger.debug(f"Cache delete error for {key}: {e}")
            return False

    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern.

        Args:
            pattern: Glob pattern (e.g., "equipment:*")

        Returns:
            Number of keys deleted
        """
        client = self._get_client()
        if not client:
            return 0

        try:
            full_pattern = self._make_key(pattern)
            keys = list(client.scan_iter(match=full_pattern, count=100))
            if keys:
                return client.delete(*keys)
            return 0
        except Exception as e:
            logger.debug(f"Cache delete_pattern error for {pattern}: {e}")
            return 0

    def get_or_set(self, key: str, factory: Callable[[], Any], ttl: int | None = None) -> Any:
        """Get from cache or compute and store.

        Args:
            key: Cache key
            factory: Function to compute value if not cached
            ttl: Time-to-live in seconds

        Returns:
            Cached or computed value
        """
        # Try cache first
        cached = self.get(key)
        if cached is not None:
            return cached

        # Compute value
        value = factory()

        # Cache it
        if value is not None:
            self.set(key, value, ttl)

        return value

    async def get_or_set_async(self, key: str, factory: Callable[[], Any], ttl: int | None = None) -> Any:
        """Async version of get_or_set.

        Args:
            key: Cache key
            factory: Async function to compute value if not cached
            ttl: Time-to-live in seconds

        Returns:
            Cached or computed value
        """
        # Try cache first
        cached = self.get(key)
        if cached is not None:
            return cached

        # Compute value (await if coroutine)
        import asyncio

        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()

        # Cache it
        if value is not None:
            self.set(key, value, ttl)

        return value

    def cached(self, key_template: str, ttl: int | None = None) -> Callable[[Callable[P, R]], Callable[P, R]]:
        """Decorator for caching function results.

        Args:
            key_template: Key template with {param} placeholders
            ttl: Time-to-live in seconds

        Example:
            @cache.cached("equipment:building:{site_id}", ttl=300)
            def get_equipment(site_id: str):
                return repo.query(...)
        """

        def decorator(func: Callable[P, R]) -> Callable[P, R]:
            @wraps(func)
            def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                # Build cache key from template and arguments
                import inspect

                sig = inspect.signature(func)
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                cache_key = key_template.format(**bound.arguments)

                # Try cache
                cached = self.get(cache_key)
                if cached is not None:
                    return cached

                # Call function
                result = func(*args, **kwargs)

                # Cache result
                if result is not None:
                    self.set(cache_key, result, ttl)

                return result

            return wrapper

        return decorator

    def cached_async(self, key_template: str, ttl: int | None = None) -> Callable[[Callable[P, R]], Callable[P, R]]:
        """Async decorator for caching function results.

        Args:
            key_template: Key template with {param} placeholders
            ttl: Time-to-live in seconds
        """

        def decorator(func: Callable[P, R]) -> Callable[P, R]:
            @wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                import inspect

                sig = inspect.signature(func)
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                cache_key = key_template.format(**bound.arguments)

                # Try cache
                cached = self.get(cache_key)
                if cached is not None:
                    return cached

                # Call async function
                result = await func(*args, **kwargs)

                # Cache result
                if result is not None:
                    self.set(cache_key, result, ttl)

                return result

            return wrapper

        return decorator

    def _inc_prometheus(self, operation: str) -> None:
        """Increment Prometheus cache counter (lazy import to avoid circular deps)."""
        try:
            from app.api.metrics import sentinel_cache_operations_total

            sentinel_cache_operations_total.labels(operation=operation).inc()
        except Exception:
            pass

    def _sync_prometheus_gauge(self) -> None:
        """Update Prometheus gauge with current hit rate."""
        try:
            from app.api.metrics import sentinel_cache_hit_rate_percent

            total = self._stats["hits"] + self._stats["misses"]
            if total > 0:
                sentinel_cache_hit_rate_percent.set(round(self._stats["hits"] / total * 100, 2))
        except Exception:
            pass

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0.0

        self._sync_prometheus_gauge()

        return {
            "connected": self._connected,
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "errors": self._stats["errors"],
            "hit_rate_percent": round(hit_rate, 2),
            "total_requests": total,
        }

    def reset_stats(self):
        """Reset statistics counters."""
        self._stats = {"hits": 0, "misses": 0, "errors": 0}

    def flush_all(self) -> bool:
        """Flush all BMS cache keys (not entire Redis DB).

        Returns:
            True if successful
        """
        return self.delete_pattern("*") > 0


# Global singleton
cache = CacheService()


# Cache key builders for common patterns
class CacheKeys:
    """Standard cache key patterns."""

    @staticmethod
    def sites_all() -> str:
        return "buildings:all"

    @staticmethod
    def building(code: str) -> str:
        return f"buildings:code:{code}"

    @staticmethod
    def building_by_id(uuid: str) -> str:
        return f"buildings:id:{uuid}"

    @staticmethod
    def equipment_all() -> str:
        return "equipment:all"

    @staticmethod
    def equipment_by_site(site_id: str) -> str:
        return f"equipment:building:{site_id}"

    @staticmethod
    def equipment_by_code(code: str) -> str:
        return f"equipment:code:{code}"

    @staticmethod
    def equipment_count(site_id: str) -> str:
        return f"equipment:count:{site_id}"

    @staticmethod
    def alerts_active(site_id: str | None = None) -> str:
        if site_id:
            return f"alerts:active:building:{site_id}"
        return "alerts:active:all"

    @staticmethod
    def predictions_active(site_id: str | None = None) -> str:
        if site_id:
            return f"predictions:active:building:{site_id}"
        return "predictions:active:all"

    @staticmethod
    def technicians_by_site(site_id: str) -> str:
        return f"technicians:building:{site_id}"

    @staticmethod
    def user_access(email: str) -> str:
        return f"user_access:{email}"

    @staticmethod
    def asset_summary(site_code: str) -> str:
        return f"asset_summary:{site_code}"


# Invalidation helpers
class CacheInvalidation:
    """Cache invalidation patterns for write operations."""

    @staticmethod
    def on_building_change(site_id: str = None, site_code: str = None):
        """Invalidate building-related caches."""
        cache.delete(CacheKeys.sites_all())
        if site_id:
            cache.delete(CacheKeys.building_by_id(site_id))
        if site_code:
            cache.delete(CacheKeys.building(site_code))
            cache.delete(CacheKeys.asset_summary(site_code))

    @staticmethod
    def on_equipment_change(site_id: str = None, equipment_code: str = None):
        """Invalidate equipment-related caches."""
        cache.delete(CacheKeys.equipment_all())
        if site_id:
            cache.delete(CacheKeys.equipment_by_site(site_id))
            cache.delete(CacheKeys.equipment_count(site_id))
        if equipment_code:
            cache.delete(CacheKeys.equipment_by_code(equipment_code))

    @staticmethod
    def on_alert_change(site_id: str = None):
        """Invalidate alert-related caches."""
        cache.delete(CacheKeys.alerts_active())
        if site_id:
            cache.delete(CacheKeys.alerts_active(site_id))

    @staticmethod
    def on_prediction_change(site_id: str = None):
        """Invalidate prediction-related caches."""
        cache.delete(CacheKeys.predictions_active())
        if site_id:
            cache.delete(CacheKeys.predictions_active(site_id))

    @staticmethod
    def on_user_access_change(email: str):
        """Invalidate user access cache."""
        cache.delete(CacheKeys.user_access(email))


_slow_query_logger = _logging.getLogger("sentinel.slow_queries")

# Threshold in seconds — queries slower than this get logged as warnings
SLOW_QUERY_THRESHOLD_S = float(_os.environ.get("SLOW_QUERY_THRESHOLD_S", "0.5"))


@contextmanager
def track_query(repository: str, method: str):
    """Context manager to time Supabase queries for Prometheus.

    Logs a warning for queries exceeding SLOW_QUERY_THRESHOLD_S (default 0.5s).

    Usage:
        with track_query("equipment", "get_all"):
            response = query.execute()
    """
    start = _time.perf_counter()
    try:
        yield
    finally:
        duration = _time.perf_counter() - start
        try:
            from app.api.metrics import sentinel_db_query_duration_seconds

            sentinel_db_query_duration_seconds.labels(repository=repository, method=method).observe(duration)
        except Exception:
            pass

        if duration >= SLOW_QUERY_THRESHOLD_S:
            _slow_query_logger.warning(
                "SLOW_QUERY repo=%s method=%s duration=%.3fs threshold=%.3fs",
                repository,
                method,
                duration,
                SLOW_QUERY_THRESHOLD_S,
            )
