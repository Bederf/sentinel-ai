"""Shared technician document upload processor.

This module contains the upload pipeline used by both:
- the TechnicianChat frontend API path
- the Telegram document intake flow

The processor validates technician metadata, stores the file in Supabase
Storage, updates the documents table, runs LLM extraction, normalises the
upload into the manual adapter, and applies asset resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException

from app.database.supabase_client import get_supabase_client
from app.models.auth import AuthContext, SentinelRole

TECHNICIAN_DOCUMENT_NAMES = {
    "Roof Guarantee Certificate",
    "Warranties",
    "Air-Handler Unit (AHU) Major Service",
    "Air-Handler Unit (AHU) Minor Service",
    "Air-Handler Unit (AHU) Weekly Inspection",
    "Cooling Tower (CT) Major Service",
    "Cooling Tower (CT) Minor Service",
    "Cooling Tower (CT) Weekly Inspection",
    "Chiller Major Service",
    "Chiller Minor Service",
    "Chiller Weekly Inspection",
    "Kitchen Canopy Manual Service",
    "Building Management System (BMS) Service",
    "Distribution Boards (DB) Maintenance",
    "Transformer Service",
    "Fire Pump System Inspection",
    "Generator Major Service",
    "Generator Minor Service",
    "Generator Weekly Test",
    "Lift Service",
    "Lift test Report",
    "Escalator Monthly Service",
    "Solar PV Weekly Inspection",
    "UPS Weekly Inspection",
    "Waste Management Service",
    "Structural Integrity Report",
    "Certificate of Compliance (COC)",
    "Earth Leakage Test",
    "Plumbing Certificate of Compliance",
    "Electrical Equipment Certificates",
    "Smoke Detectors Service",
    "ASIB Certificate",
    "Portable Electrical Tool Inspection",
    "Potable Water Test Results",
    "Pressure Vessel Test Certificate",
    "Spillage Incidents Report",
    "Water Consumption Reports",
    "Building Inspection Report",
    "Occupational Hygiene Surveys",
    "Waste disposal certificates",
    "Audit Reports",
    "BSI Audit certificate",
}

TECHNICIAN_SUB_CLASSES = {
    "HVAC",
    "Electrical",
    "Fire",
    "Plumbing",
    "Lifts",
    "Building Fabric",
    "Power Factor Correction",
    "UPS",
    "Solar PV",
    "General Facilities",
}

TECHNICIAN_CATEGORIES = {
    "Preventive Maintenance",
    "Corrective Maintenance",
    "Compliance",
    "Safety",
    "Energy",
    "Water",
    "Testing & Commissioning",
    "Incident & Repair",
}


def _resolve_site_uuid(site_id: str) -> str:
    if len(site_id) == 36 and site_id.count("-") == 4:
        return site_id

    client = get_supabase_client()
    result = client.table("sites").select("id").eq("code", site_id).single().execute()
    if result.data and result.data.get("id"):
        return str(result.data["id"])
    raise HTTPException(status_code=404, detail="Site not found")


@dataclass(slots=True)
class InMemoryUploadFile:
    """Minimal UploadFile-compatible wrapper around raw bytes."""

    filename: str
    content: bytes
    content_type: str | None = None
    _position: int = 0

    async def read(self) -> bytes:
        if self._position >= len(self.content):
            return b""
        data = self.content[self._position :]
        self._position = len(self.content)
        return data

    async def seek(self, offset: int) -> None:
        self._position = max(0, min(offset, len(self.content)))


async def process_technician_document_upload(
    *,
    file: Any,
    site_id: str,
    equipment_id: str,
    document_name: str,
    document_sub_class: str,
    category_discipline: str,
    document_creation_date: str,
    trigger_date: str,
    uploaded_by_user_id: str,
    user_role: str = "operator",
    title: str | None = None,
) -> dict[str, Any]:
    """Proxy the existing technician upload endpoint with Telegram-friendly auth."""
    from app.api.documents import upload_technician_document

    resolved_site_id = _resolve_site_uuid(site_id)
    fake_request = SimpleNamespace(state=SimpleNamespace(user_id=uploaded_by_user_id, user_role=user_role))
    fake_auth = AuthContext(
        user_id=uploaded_by_user_id,
        role=SentinelRole.ADMIN,
        auth_method="telegram",
        source_ip="telegram",
        email=None,
    )

    return await upload_technician_document(
        request=fake_request,
        file=file,
        equipment_id=equipment_id,
        document_name=document_name,
        document_sub_class=document_sub_class,
        category_discipline=category_discipline,
        document_creation_date=document_creation_date,
        trigger_date=trigger_date,
        title=title,
        site_id=resolved_site_id,
        auth=fake_auth,
    )
