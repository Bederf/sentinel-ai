"""Database package for Supabase integration."""

from app.database.supabase_client import get_supabase_client

__all__ = ['get_supabase_client']
