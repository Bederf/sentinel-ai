"""Base repository class providing async Supabase client access."""

from app.database.supabase_client import get_async_supabase_client


class SupabaseRepository:
    """Base class for repositories that need async database access.

    Subclasses retrieve the async Supabase client via self.get_client().
    """

    _async_client_instance = None

    async def get_client(self):
        """Get the async Supabase client singleton.

        Returns:
            Async Supabase client instance
        """
        return await get_async_supabase_client()
