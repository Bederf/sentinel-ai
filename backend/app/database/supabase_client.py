"""Supabase client for database operations."""

from typing import Optional
from supabase import create_client, Client
from app.config.settings import settings

_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """Get or create the Supabase client singleton.

    Returns:
        Supabase client instance

    Raises:
        ValueError: If Supabase credentials are not configured
    """
    global _supabase_client

    if _supabase_client is None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise ValueError(
                "Supabase credentials not configured. "
                "Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env"
            )

        _supabase_client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key
        )

    return _supabase_client


def reset_supabase_client():
    """Reset the Supabase client (useful for testing)."""
    global _supabase_client
    _supabase_client = None
