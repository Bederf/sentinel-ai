"""Visit service layer — wraps VisitRepository + VisitTokenService.

API routers call this service, not the repository directly.
Provides business-logic operations on top of raw repository access.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.database.repositories.visit_repository import BuildingMapRepository, VisitRepository
from app.models.visit import BuildingMap, Visit, VisitStatus
from app.services.visit_token_service import VisitTokenService


class VisitService:
    """Service layer for visit management operations."""

    def __init__(self) -> None:
        self._repo = VisitRepository()
        self._building_map_repo = BuildingMapRepository()
        self._token_service = VisitTokenService(repo=self._repo)

    # -------------------------------------------------------------------------
    # Token operations
    # -------------------------------------------------------------------------

    def create_visit(
        self,
        visitor_email: str,
        host_email: str,
        building_id: str,
        meeting_start: datetime,
        meeting_end: datetime,
        host_name: str | None = None,
        host_mobile: str | None = None,
        visitor_name: str | None = None,
        visitor_vehicle: str | None = None,
        status: VisitStatus = VisitStatus.CREATED,
    ) -> Visit:
        """Create a new visit with token, PIN, and QR code."""
        visit, _ = self._token_service.create_visit_token(
            visitor_email=visitor_email,
            host_email=host_email,
            host_name=host_name,
            host_mobile=host_mobile,
            building_id=building_id,
            meeting_start=meeting_start,
            meeting_end=meeting_end,
            visitor_name=visitor_name,
            visitor_vehicle=visitor_vehicle,
            status=status,
        )
        return visit

    def scan_visit(self, token: UUID | None = None, pin: str | None = None) -> Visit | None:
        """Look up a visit by token or PIN. Returns None if not found."""
        if token is not None:
            return self._token_service.validate_token(token)
        elif pin is not None:
            return self._token_service.validate_pin(pin)
        return None

    def is_within_time_window(self, visit: Visit) -> bool:
        """Check if current time is within the valid visit window."""
        return self._token_service.is_valid_time_window(visit)

    def arrive_visit(self, visit: Visit) -> Visit:
        """Mark a visit as ARRIVED (scanned at reception).

        Only transitions from CREATED -> ARRIVED.
        """
        if visit.status != VisitStatus.CREATED:
            return visit  # No-op if already arrived
        return self._repo.update_visit(visit.id, {"status": VisitStatus.ARRIVED})

    def register_visit(
        self,
        token: UUID,
        visitor_name: str,
        photo: str,
        vehicle: str | None = None,
        id_number: str | None = None,
    ) -> Visit | None:
        """Register a visitor's details (name, photo, vehicle, ID).

        Updates an EXISTING visit only — never creates a new one.
        Returns None if visit not found.
        """
        visit = self._repo.get_visit_by_token(token)
        if visit is None:
            return None

        # Can only register visits that have arrived
        if visit.status != VisitStatus.ARRIVED:
            # Already registered or not yet arrived — return as-is
            return visit

        updates = {
            "visitor_name": visitor_name,
            "visitor_photo": photo,
            "visitor_vehicle": vehicle,
            "visitor_id_number": id_number,
            "status": VisitStatus.REGISTERED,
        }
        return self._repo.update_visit(visit.id, updates)

    def issue_card(self, token: UUID, access_card_id: str) -> Visit | None:
        """Issue an access card to a registered visitor.

        Returns None if visit not found.
        Raises ValueError if visit is not in REGISTERED status.
        """
        visit = self._repo.get_visit_by_token(token)
        if visit is None:
            return None

        if visit.status != VisitStatus.REGISTERED:
            raise ValueError(f"Visit must be in REGISTERED status to issue card, got {visit.status}")

        # TODO: In Plan 4, wire in C-CURE adapter for actual card issuance
        return self._repo.update_visit(
            visit.id,
            {
                "access_card_id": access_card_id,
                "status": VisitStatus.ACTIVE,
            },
        )

    def get_visit(self, token: UUID) -> Visit | None:
        """Get a visit by token."""
        return self._repo.get_visit_by_token(token)

    def list_active_visits(self) -> list[Visit]:
        """List all currently active visits (for reception dashboard)."""
        return self._repo.list_active_visits()

    # -------------------------------------------------------------------------
    # Building Map operations
    # -------------------------------------------------------------------------

    def resolve_building_id(self, outlook_location_string: str) -> str | None:
        """Resolve an Outlook location string to a building_id via BuildingMap.

        Returns the site_id (which serves as building_id) or None if not found.
        """
        mapping = self._building_map_repo.get_building_map_by_outlook_location(outlook_location_string)
        return mapping.site_id if mapping else None

    def get_building_name(self, building_id: str) -> str | None:
        """Get the human-readable building name for a building_id."""
        all_maps = self._building_map_repo.list_building_maps()
        for mapping in all_maps:
            if mapping.site_id == building_id:
                return mapping.name
        return None

    def add_building_map(
        self,
        name: str,
        outlook_location_string: str,
        site_id: str,
    ) -> BuildingMap:
        """Add a new building map entry."""
        from uuid import uuid4

        mapping = BuildingMap(
            id=uuid4(),
            name=name,
            outlook_location_string=outlook_location_string,
            site_id=site_id,
        )
        return self._building_map_repo.create_building_map(mapping)
