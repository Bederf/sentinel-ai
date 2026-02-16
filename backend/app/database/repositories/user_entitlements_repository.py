"""
User Entitlements Repository

Manages user module entitlements with 3-tier fallback:
1. Supabase user_entitlements table
2. JSON file (demo mode)
3. Hardcoded defaults for testing
"""

import json
import logging
from pathlib import Path
from typing import Optional

from app.models.user_entitlements import UserModuleEntitlement, UserEntitlementProfile, PRESET_ENTITLEMENTS
from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class UserEntitlementsRepository:
    """Repository for user module entitlements."""
    
    def __init__(self):
        self.data_dir = Path(__file__).parent.parent.parent / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.entitlements_file = self.data_dir / "user_entitlements.json"
        self._load_seed_data()
    
    def _load_seed_data(self) -> None:
        """Load or create seed data for demo users."""
        if not self.entitlements_file.exists():
            seed_data = {
                "grant@demo.local": PRESET_ENTITLEMENTS["grant"]["modules"],
                "bederf@demo.local": PRESET_ENTITLEMENTS["bederf"]["modules"],
                "admin@demo.local": PRESET_ENTITLEMENTS["full"]["modules"],
                "demo@sentinel.local": PRESET_ENTITLEMENTS["full"]["modules"],
            }
            with open(self.entitlements_file, 'w') as f:
                json.dump(seed_data, f, indent=2)
            logger.info("Created seed user entitlements file")
    
    async def get_user_entitlements(self, user_email: str) -> Optional[UserEntitlementProfile]:
        """Get module entitlements for a user.
        
        3-tier fallback:
        1. Try Supabase user_entitlements table
        2. Try JSON file (demo mode)
        3. Return None if user has no entitlements
        
        Args:
            user_email: User email address
            
        Returns:
            UserEntitlementProfile or None
        """
        # 1. Try Supabase
        try:
            client = get_supabase_client()
            response = client.table("user_entitlements").select(
                "user_id, user_email, modules"
            ).eq("user_email", user_email).single().execute()
            
            if response.data:
                return UserEntitlementProfile(
                    user_id=response.data.get("user_id", user_email),
                    user_email=response.data.get("user_email", user_email),
                    entitlements=response.data.get("modules", []),
                    last_updated=response.data.get("updated_at", "")
                )
        except Exception as e:
            logger.debug(f"Supabase entitlements query failed for {user_email}: {e}")
        
        # 2. Try JSON file
        try:
            if self.entitlements_file.exists():
                with open(self.entitlements_file) as f:
                    data = json.load(f)
                    if user_email in data:
                        return UserEntitlementProfile(
                            user_id=user_email,
                            user_email=user_email,
                            entitlements=data[user_email],
                            last_updated=""
                        )
        except Exception as e:
            logger.debug(f"JSON entitlements query failed for {user_email}: {e}")
        
        # 3. No entitlements found
        logger.debug(f"No entitlements found for user {user_email}")
        return None
    
    async def set_user_entitlements(
        self,
        user_email: str,
        modules: list[str],
        user_id: Optional[str] = None
    ) -> UserEntitlementProfile:
        """Set/update module entitlements for a user.
        
        Tries Supabase first, falls back to JSON file.
        
        Args:
            user_email: User email address
            modules: List of module type strings
            user_id: Optional user ID (defaults to email)
            
        Returns:
            Updated UserEntitlementProfile
        """
        user_id = user_id or user_email
        
        # 1. Try Supabase
        try:
            client = get_supabase_client()
            # Upsert: update if exists, insert if not
            client.table("user_entitlements").upsert({
                "user_id": user_id,
                "user_email": user_email,
                "modules": modules
            }).execute()
            logger.info(f"Updated entitlements in Supabase for {user_email}: {modules}")
        except Exception as e:
            logger.debug(f"Supabase update failed for {user_email}, using JSON: {e}")
            
            # 2. Fall back to JSON file
            try:
                data = {}
                if self.entitlements_file.exists():
                    with open(self.entitlements_file) as f:
                        data = json.load(f)
                
                data[user_email] = modules
                with open(self.entitlements_file, 'w') as f:
                    json.dump(data, f, indent=2)
                logger.info(f"Updated entitlements in JSON file for {user_email}: {modules}")
            except Exception as json_e:
                logger.error(f"Failed to update entitlements for {user_email}: {json_e}")
        
        return UserEntitlementProfile(
            user_id=user_id,
            user_email=user_email,
            entitlements=modules,
            last_updated=""
        )
    
    async def apply_preset_to_user(
        self,
        user_email: str,
        preset_name: str,
        user_id: Optional[str] = None
    ) -> Optional[UserEntitlementProfile]:
        """Apply a preset (grant, bederf, full) to a user.
        
        Args:
            user_email: User email address
            preset_name: Preset name (grant, bederf, full)
            user_id: Optional user ID
            
        Returns:
            Updated UserEntitlementProfile or None if preset not found
        """
        if preset_name not in PRESET_ENTITLEMENTS:
            logger.error(f"Unknown preset: {preset_name}")
            return None
        
        modules = PRESET_ENTITLEMENTS[preset_name]["modules"]
        return await self.set_user_entitlements(user_email, modules, user_id)


def get_user_entitlements_repository() -> UserEntitlementsRepository:
    """Get singleton instance of user entitlements repository."""
    return UserEntitlementsRepository()
