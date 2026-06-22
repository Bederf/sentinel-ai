"""Supabase client for database operations."""

import os
import warnings

from app.config.settings import settings


class _DummySupabaseClient:
    def __getattr__(self, name):
        raise RuntimeError(
            "Supabase client is not available in TESTING mode. Provide a stub or disable this code path in tests."
        )


_supabase_client: object | None = None


def get_supabase_client():
    """Get or create the Supabase client singleton.

    Returns:
        Supabase client instance

    Raises:
        ValueError: If Supabase credentials are not configured
    """
    global _supabase_client

    if _supabase_client is None:
        if os.getenv("TESTING", "").lower() == "true":
            if not settings.supabase_url or not settings.supabase_service_role_key:
                _supabase_client = _DummySupabaseClient()
                return _supabase_client

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from supabase import create_client

        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise ValueError(
                "Supabase credentials not configured. Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env"
            )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _supabase_client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    return _supabase_client


_async_supabase_client: object | None = None


async def get_async_supabase_client():
    """Get or create the async Supabase client singleton.

    Returns:
        Async Supabase client instance

    Raises:
        ValueError: If Supabase credentials are not configured
    """
    global _async_supabase_client

    if _async_supabase_client is None:
        if os.getenv("TESTING", "").lower() == "true":
            if not settings.supabase_url or not settings.supabase_service_role_key:
                _async_supabase_client = _DummySupabaseClient()
                return _async_supabase_client

        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise ValueError(
                "Supabase credentials not configured. Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env"
            )

        from supabase._async.client import create_client as create_async_client

        _async_supabase_client = await create_async_client(settings.supabase_url, settings.supabase_service_role_key)

    return _async_supabase_client


def reset_supabase_client():
    """Reset the Supabase client (useful for testing)."""
    global _supabase_client, _async_supabase_client
    _supabase_client = None
    _async_supabase_client = None


class Supabase:
    """Singleton wrapper for Supabase client."""

    @staticmethod
    def instance():
        return get_supabase_client()
