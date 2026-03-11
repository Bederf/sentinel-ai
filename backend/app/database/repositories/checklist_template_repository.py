"""Repository for inspection checklist template operations.

Phase 66: OEM-Specific Checklist Generation
Plan 01: Checklist Generation Foundation

Provides Supabase CRUD for the inspection_checklist_templates table
(created in migration 026). Handles OEM-specific template lookups
by manufacturer name matching.
"""

from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class ChecklistTemplateRepository:
    """Repository for inspection_checklist_templates Supabase table.

    Provides CRUD operations with graceful error handling.
    When Supabase is unavailable, methods return empty results
    rather than raising exceptions (JSON fallback exists in ChecklistService).
    """

    def __init__(self):
        """Initialize the repository with a Supabase client."""
        from app.database.supabase_client import get_supabase_client

        self.client = get_supabase_client()
        self._table = "inspection_checklist_templates"

    def create_template(self, template_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new checklist template.

        Args:
            template_data: Template data. Required: template_name, equipment_type,
                inspection_type, checklist_items. Optional: frequency_type,
                estimated_duration_minutes, required_tools, required_skills,
                safety_requirements, ppe_required, version, is_active, created_by.

        Returns:
            Created template dict.
        """
        # Set defaults
        template_data.setdefault("is_active", True)
        template_data.setdefault("version", 1)

        try:
            response = self.client.table(self._table).insert(template_data).execute()
            return response.data[0] if response.data else {}
        except Exception as e:
            logger.error(f"Failed to create checklist template: {e}")
            return {}

    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """Get a checklist template by UUID.

        Args:
            template_id: Template UUID.

        Returns:
            Template dict or None if not found.
        """
        try:
            response = self.client.table(self._table).select("*").eq("id", template_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.warning(f"Failed to get checklist template {template_id}: {e}")
            return None

    def get_templates_for_equipment_type(self, equipment_type: str, is_active: bool = True) -> List[Dict[str, Any]]:
        """Get all templates for an equipment type.

        Args:
            equipment_type: Equipment type (e.g., 'chiller', 'ahu').
            is_active: Filter by active status.

        Returns:
            List of matching template dicts.
        """
        try:
            response = (
                self.client.table(self._table)
                .select("*")
                .eq("equipment_type", equipment_type)
                .eq("is_active", is_active)
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.warning(f"Failed to get templates for equipment_type={equipment_type}: {e}")
            return []

    def get_oem_template(
        self, equipment_type: str, manufacturer: str, model: str = None, inspection_type: str = None
    ) -> Optional[Dict[str, Any]]:
        """Get OEM-specific template by manufacturer name matching.

        Searches for templates where template_name contains the manufacturer
        string (case-insensitive). The existing table schema does not have
        dedicated manufacturer/model columns, so we use name-based matching.

        Args:
            equipment_type: Equipment type (e.g., 'chiller').
            manufacturer: Manufacturer name (e.g., 'Carrier').
            model: Optional model for more specific matching.
            inspection_type: Optional inspection type filter.

        Returns:
            Matching template dict or None.
        """
        try:
            query = (
                self.client.table(self._table).select("*").eq("equipment_type", equipment_type).eq("is_active", True)
            )

            if inspection_type:
                query = query.eq("inspection_type", inspection_type)

            # Use ilike for case-insensitive name matching
            from app.utils import escape_like

            safe_mfr = escape_like(manufacturer)
            query = query.ilike("template_name", f"%{safe_mfr}%")

            if model:
                safe_model = escape_like(model)
                # Try with model first for more specific match
                model_query = (
                    self.client.table(self._table)
                    .select("*")
                    .eq("equipment_type", equipment_type)
                    .eq("is_active", True)
                    .ilike("template_name", f"%{safe_mfr}%{safe_model}%")
                )
                if inspection_type:
                    model_query = model_query.eq("inspection_type", inspection_type)

                model_response = model_query.execute()
                if model_response.data:
                    return model_response.data[0]

            # Fall back to manufacturer-only match
            response = query.execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.warning(f"Failed to get OEM template for {manufacturer} {equipment_type}: {e}")
            return None

    def upsert_template(self, template_data: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert a template (insert or update on conflict).

        Conflict is determined by template_name + equipment_type uniqueness.
        Uses Supabase upsert with on_conflict for idempotent writes.

        Args:
            template_data: Template data with at least template_name and equipment_type.

        Returns:
            Upserted template dict.
        """
        template_data.setdefault("is_active", True)
        template_data.setdefault("version", 1)

        try:
            response = (
                self.client.table(self._table)
                .upsert(template_data, on_conflict="template_name,equipment_type")
                .execute()
            )
            return response.data[0] if response.data else {}
        except Exception as e:
            logger.error(f"Failed to upsert checklist template: {e}")
            # Fall back to simple insert if upsert fails (constraint may not exist)
            try:
                return self.create_template(template_data)
            except Exception:
                return {}

    def update_template(self, template_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a template by UUID.

        Auto-increments version if checklist_items are being updated.

        Args:
            template_id: Template UUID.
            updates: Fields to update.

        Returns:
            Updated template dict or None if not found.
        """
        try:
            # Auto-increment version if checklist_items changed
            if "checklist_items" in updates:
                existing = self.get_template(template_id)
                if existing:
                    updates["version"] = existing.get("version", 0) + 1

            response = self.client.table(self._table).update(updates).eq("id", template_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to update checklist template {template_id}: {e}")
            return None

    def list_all_templates(self, is_active: bool = True) -> List[Dict[str, Any]]:
        """List all templates with optional active filter.

        Args:
            is_active: Filter by active status.

        Returns:
            List of template dicts.
        """
        try:
            response = (
                self.client.table(self._table).select("*").eq("is_active", is_active).order("equipment_type").execute()
            )
            return response.data or []
        except Exception as e:
            logger.warning(f"Failed to list checklist templates: {e}")
            return []

    def delete_template(self, template_id: str) -> bool:
        """Soft-delete a template (set is_active=False).

        Args:
            template_id: Template UUID.

        Returns:
            True if soft-deleted, False on failure.
        """
        try:
            response = self.client.table(self._table).update({"is_active": False}).eq("id", template_id).execute()
            return bool(response.data)
        except Exception as e:
            logger.error(f"Failed to delete checklist template {template_id}: {e}")
            return False


# ============================================================================
# Singleton Factory
# ============================================================================

_instance: Optional[ChecklistTemplateRepository] = None


def get_checklist_template_repository() -> ChecklistTemplateRepository:
    """Get singleton instance of ChecklistTemplateRepository.

    Returns:
        ChecklistTemplateRepository instance.
    """
    global _instance
    if _instance is None:
        _instance = ChecklistTemplateRepository()
    return _instance
