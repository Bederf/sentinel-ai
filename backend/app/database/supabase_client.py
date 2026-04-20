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
            _supabase_client = _DummySupabaseClient()
            return _supabase_client

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            warnings.filterwarnings(
                "ignore",
                message="The 'timeout' parameter is deprecated. Please configure it in the http client instead.",
                category=DeprecationWarning,
            )
            warnings.filterwarnings(
                "ignore",
                message="'.*' deprecated - use '.*'",
                category=DeprecationWarning,
            )
            warnings.filterwarnings(
                "ignore",
                message="'.*' argument is deprecated, use '.*'",
                category=DeprecationWarning,
            )
            from supabase import create_client

        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise ValueError(
                "Supabase credentials not configured. Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env"
            )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            warnings.filterwarnings(
                "ignore",
                message="The 'timeout' parameter is deprecated. Please configure it in the http client instead.",
                category=DeprecationWarning,
            )
            warnings.filterwarnings(
                "ignore",
                message="'.*' deprecated - use '.*'",
                category=DeprecationWarning,
            )
            warnings.filterwarnings(
                "ignore",
                message="'.*' argument is deprecated, use '.*'",
                category=DeprecationWarning,
            )
            _supabase_client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    return _supabase_client


def reset_supabase_client():
    """Reset the Supabase client (useful for testing)."""
    global _supabase_client
    _supabase_client = None


class Supabase:
    """Singleton wrapper for Supabase client."""

    @staticmethod
    def instance():
        """Get or create the Supabase client singleton.

        Returns:
            Supabase client instance
        """
        return get_supabase_client()
