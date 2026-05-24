"""Site Occupant Repository — staff/residents/visitors registered via WhatsApp."""

from __future__ import annotations

import logging

from ..supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class SiteOccupantRepository:
    def __init__(self):
        self.client = get_supabase_client()

    def _resolve_site_uuid(self, site_id: str) -> str:
        import re

        uuid_pattern = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
        if uuid_pattern.match(site_id):
            return site_id
        result = self.client.table("sites").select("id").eq("code", site_id).limit(1).execute()
        if result.data:
            return result.data[0]["id"]
        return site_id

    def _resolve_site_by_whatsapp(self, phone: str | None = None, waba_id: str | None = None) -> dict | None:
        """Find site by WhatsApp Business phone ID (WABA) or Business phone number."""
        if not self.client:
            return None
        try:
            query = self.client.table("sites").select("id, code, name, whatsapp_phone")
            if waba_id:
                # Match against the stored WABA phone number ID
                query = query.eq("whatsapp_phone", waba_id)
            elif phone:
                query = query.eq("whatsapp_phone", phone)
            else:
                return None
            result = query.limit(1).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error resolving site by WhatsApp: {e}")
            return None

    async def get_by_phone(self, phone: str) -> dict | None:
        """Look up an occupant by normalized WhatsApp phone number."""
        if not self.client or not phone:
            return None
        try:
            result = (
                self.client.table("site_occupants")
                .select("*")
                .eq("phone", phone)
                .eq("active", True)
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Error looking up occupant by phone {phone}: {e}")
            return None

    async def create(
        self,
        site_id: str,
        phone: str,
        name: str,
        location: str,
        whatsapp_id: str | None = None,
    ) -> dict | None:
        """Register a new occupant for a site."""
        if not self.client:
            logger.warning("Supabase client not available")
            return None
        try:
            import uuid

            resolved = self._resolve_site_uuid(site_id)
            data = {
                "site_id": resolved,
                "phone": phone,
                "name": name,
                "location": location,
                "whatsapp_id": whatsapp_id,
                "active": True,
            }
            result = self.client.table("site_occupants").insert(data).execute()
            if not result.data:
                return None
            occupant = result.data[0]
            logger.info(f"Registered occupant {name} at {site_id} via WhatsApp")
            return occupant
        except Exception as e:
            logger.error(f"Error registering occupant: {e}")
            return None

    async def get_site_occupants(self, site_id: str) -> list[dict]:
        """Get all active occupants for a site."""
        if not self.client:
            return []
        try:
            resolved = self._resolve_site_uuid(site_id)
            result = (
                self.client.table("site_occupants")
                .select("*")
                .eq("site_id", resolved)
                .eq("active", True)
                .order("name")
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting occupants for site {site_id}: {e}")
            return []
