"""Cache management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel, SentinelRole
from app.services.cache_service import cache

router = APIRouter(prefix="/api/cache", tags=["cache"])


class CacheStatsResponse(BaseModel):
    """Cache statistics response."""
    connected: bool
    hits: int
    misses: int
    errors: int
    hit_rate_percent: float
    total_requests: int


class CacheFlushResponse(BaseModel):
    """Response for cache flush operations."""
    success: bool
    message: str
    keys_deleted: Optional[int] = None


@router.get("/health")
async def cache_health() -> dict:
    """Check cache health status."""
    return {
        "status": "healthy" if cache.is_connected else "unavailable",
        "connected": cache.is_connected,
        "service": "redis",
    }


@router.get("/stats", response_model=CacheStatsResponse)
async def cache_stats(
    auth: AuthContext = Depends(require_auth(AuthLevel.AUTHENTICATED))
) -> CacheStatsResponse:
    """Get cache statistics (authenticated users only)."""
    stats = cache.get_stats()
    return CacheStatsResponse(**stats)


@router.post("/flush", response_model=CacheFlushResponse)
async def flush_cache(
    pattern: Optional[str] = None,
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN))
) -> CacheFlushResponse:
    """Flush cache entries (admin only).

    Args:
        pattern: Optional glob pattern to flush (e.g., "equipment:*").
                 If not provided, flushes all BMS cache keys.
    """
    if auth.role != SentinelRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    if not cache.is_connected:
        return CacheFlushResponse(
            success=False,
            message="Redis cache not connected"
        )

    if pattern:
        count = cache.delete_pattern(pattern)
        return CacheFlushResponse(
            success=True,
            message=f"Flushed cache entries matching: {pattern}",
            keys_deleted=count
        )
    else:
        success = cache.flush_all()
        return CacheFlushResponse(
            success=success,
            message="Flushed all BMS cache entries" if success else "No entries to flush"
        )


@router.post("/reset-stats")
async def reset_cache_stats(
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN))
) -> dict:
    """Reset cache statistics counters (admin only)."""
    if auth.role != SentinelRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    cache.reset_stats()
    return {"success": True, "message": "Cache statistics reset"}


@router.delete("/key/{key_name}")
async def delete_cache_key(
    key_name: str,
    auth: AuthContext = Depends(require_auth(AuthLevel.ADMIN))
) -> CacheFlushResponse:
    """Delete a specific cache key (admin only).

    Args:
        key_name: The cache key to delete (without bms: prefix)
    """
    if auth.role != SentinelRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    if not cache.is_connected:
        return CacheFlushResponse(
            success=False,
            message="Redis cache not connected"
        )

    success = cache.delete(key_name)
    return CacheFlushResponse(
        success=success,
        message=f"Deleted cache key: {key_name}" if success else f"Key not found: {key_name}"
    )
