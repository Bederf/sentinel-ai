"""
Email Cluster Service — occupant complaint heatmap.

Clusters incoming emails by zone + complaint_type.
Threshold: 3 emails → cockpit heatmap signal.

Adjacency rule: same zone OR same floor + adjacent zone_letter (A↔B, B↔C).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from app.database.repositories.desk_repository import DeskRepository
from app.database.repositories.email_cluster_repository import EmailClusterRepository
from app.database.repositories.zone_repository import ZoneRepository

logger = logging.getLogger(__name__)

# Severity tiers by email count
_CLUSTER_SEVERITY = {
    (3, 5): "medium",
    (6, 10): "high",
    (11, 999): "critical",
}


def _derive_severity(email_count: int) -> str:
    for (lo, hi), severity in _CLUSTER_SEVERITY.items():
        if lo <= email_count <= hi:
            return severity
    return "low"


def _letter_adjacent(a: str, b: str) -> bool:
    """True if zone_letters are adjacent (A↔B, B↔C, etc)."""
    try:
        return 0 < abs(ord(a.upper()) - ord(b.upper())) <= 1
    except Exception:
        return False


def _build_summary(complaint_type: str, email_count: int, zone_name: str, floor: str) -> str:
    type_label = complaint_type.replace("_", " ")
    return f"{email_count} occupant {type_label} reports in {zone_name} ({floor})"


def _resolve_site_code_to_uuid(site_id: str) -> str:
    """Convert site CODE (e.g. 'site-001') to site UUID for desk/zone table lookups."""
    try:
        from app.database.supabase_client import get_supabase_client

        sb = get_supabase_client()
        r = sb.table("sites").select("id,code").execute()
        for s in r.data:
            if s.get("code") == site_id:
                return s["id"]
    except Exception as exc:
        logger.warning("Site code→UUID lookup failed for %s: %s", site_id, exc)
    return site_id  # Fall back: try as-is


class EmailClusterService:
    def __init__(self) -> None:
        self.cluster_repo = EmailClusterRepository()
        self.zone_repo = ZoneRepository()
        self.desk_repo = DeskRepository()

    def _resolve_zone(
        self, site_code: str, desk_hint: str | None, floor_hint: str | None
    ) -> Optional[tuple[dict[str, Any], str]]:
        """Resolve desk_hint or floor_hint → (zone_record, site_uuid).

        Returns tuple of zone dict and the resolved site UUID.
        Returns None if no zone can be found.
        """
        site_uuid = _resolve_site_code_to_uuid(site_code)

        # Try desk first
        if desk_hint:
            try:
                desks = self.desk_repo.get_all(site_uuid)
                for d in desks:
                    if d.get("desk_id", "").lower() == desk_hint.lower():
                        zone_id = d.get("zone_id")
                        if zone_id:
                            zones = self.zone_repo.get_all(site_uuid)
                            for z in zones:
                                if z.get("zone_id") == zone_id:
                                    return z, site_uuid
                        # Fall back to desk floor
                        desk_floor = d.get("floor")
                        if desk_floor:
                            zones = self.zone_repo.get_all(site_uuid)
                            for z in zones:
                                if z.get("floor") == desk_floor:
                                    return z, site_uuid
            except Exception as exc:
                logger.warning("_resolve_zone desk lookup failed: %s", exc)

        # Fall back to floor_hint
        if floor_hint:
            try:
                zones = self.zone_repo.get_all(site_uuid)
                for z in zones:
                    if z.get("floor") == floor_hint.upper():
                        return z, site_uuid
            except Exception as exc:
                logger.warning("_resolve_zone floor lookup failed: %s", exc)

        return None

    def _get_adjacent_zones(self, site_uuid: str, zone: dict[str, Any]) -> list[str]:
        """Return zone_ids of adjacent zones on the same floor (by zone_letter)."""
        target_floor = zone.get("floor", "")
        target_letter = zone.get("zone_letter", "")
        adjacent: list[str] = []

        try:
            all_zones = self.zone_repo.get_all(site_uuid)
            for z in all_zones:
                if z.get("floor") == target_floor:
                    zl = z.get("zone_letter", "")
                    if zl and _letter_adjacent(target_letter, zl):
                        adjacent.append(z.get("zone_id"))
        except Exception as exc:
            logger.warning("_get_adjacent_zones failed: %s", exc)

        return adjacent

    def _extract_keywords(self, subject: str, body: str, issue_category: str | None) -> list[str]:
        """Extract relevant keywords from email content."""
        text = f"{subject} {body}".lower()
        keywords: list[str] = []
        if issue_category:
            keywords.append(issue_category)

        comfort_kw = [
            "hot",
            "cold",
            "stuffy",
            "drafty",
            "noisy",
            "smell",
            "air",
            "temp",
            "temperature",
            "ac",
            "aircon",
            "heating",
            "cooling",
        ]
        for kw in comfort_kw:
            if kw in text:
                keywords.append(kw)

        desk_match = re.findall(r"desk\s*(\d+)", text, re.IGNORECASE)
        keywords.extend([f"desk-{d}" for d in desk_match])
        floor_match = re.findall(r"(?:level|floor|l)\s*([A-Z0-9]+)", text, re.IGNORECASE)
        keywords.extend([f"floor-{f}" for f in floor_match])

        return list(set(keywords))[:10]

    def _normalize_complaint_type(self, category: str, subject: str, body: str) -> str:
        """Map n8n taxonomy → our complaint_type taxonomy."""
        cat_lower = (category or "").lower()
        text = f"{subject} {body}".lower()

        if cat_lower in ("hvac", "thermal", "fault"):
            return cat_lower
        if "noise" in text or "sound" in text or "loud" in text:
            return "occupant"
        if "power" in text or "electric" in text:
            return "energy"
        if "water" in text or "leak" in text:
            return "water"
        if "security" in text or "access" in text or "door" in text:
            return "security"
        return cat_lower or "general"

    def intake_email(
        self,
        from_email: str,
        subject: str,
        body_plain: str,
        site_id: str,
        desk_hint: str | None,
        floor_hint: str | None,
        issue_category: str,
        message_id: str | None,
    ) -> dict[str, Any]:
        """
        Process an incoming email from n8n.

        Returns cluster state:
            cluster_id, zone_id, zone_name, floor, email_count,
            complaint_type, severity, summary, is_new
        """
        zone_result = self._resolve_zone(site_id, desk_hint, floor_hint)
        if not zone_result:
            logger.warning("Could not resolve zone for site=%s desk=%s floor=%s", site_id, desk_hint, floor_hint)
            return {
                "cluster_id": None,
                "zone_id": None,
                "zone_name": None,
                "floor": floor_hint,
                "email_count": 0,
                "complaint_type": issue_category,
                "severity": "low",
                "summary": "Zone could not be resolved from desk/floor hint.",
                "is_new": False,
            }

        zone, site_uuid = zone_result
        zone_id = zone.get("zone_id", "")
        zone_name = zone.get("zone_name", zone_id)
        floor = zone.get("floor", floor_hint or "")
        adjacent_zone_ids = self._get_adjacent_zones(site_uuid, zone)
        keywords = self._extract_keywords(subject, body_plain, issue_category)
        complaint_type = self._normalize_complaint_type(issue_category, subject, body_plain)

        # Find open cluster: same zone first, then adjacent
        cluster = self.cluster_repo.find_open_cluster(site_id, zone_id, complaint_type)
        if not cluster:
            for adj_zone_id in adjacent_zone_ids:
                cluster = self.cluster_repo.find_open_cluster(site_id, adj_zone_id, complaint_type)
                if cluster:
                    break

        is_new = False
        if cluster:
            self.cluster_repo.increment_cluster(cluster["id"])
            cluster = self.cluster_repo.get_by_id(cluster["id"])
            email_count = cluster["email_count"] if cluster else 1
        else:
            cluster = self.cluster_repo.upsert_cluster(
                {
                    "site_id": site_id,
                    "zone_id": zone_id,
                    "zone_name": zone_name,
                    "floor": floor,
                    "complaint_type": complaint_type,
                    "keywords": keywords,
                    "email_count": 1,
                    "severity": "low",
                    "status": "open",
                }
            )
            email_count = 1
            is_new = True

        severity = _derive_severity(email_count)
        summary = _build_summary(complaint_type, email_count, zone_name, floor)
        if cluster:
            self.cluster_repo.update_severity(cluster["id"], severity, summary)

        logger.info(
            "Email cluster: site=%s zone=%s count=%d severity=%s is_new=%s",
            site_id,
            zone_id,
            email_count,
            severity,
            is_new,
        )

        return {
            "cluster_id": cluster["id"] if cluster else None,
            "zone_id": zone_id,
            "zone_name": zone_name,
            "floor": floor,
            "email_count": email_count,
            "complaint_type": complaint_type,
            "severity": severity,
            "summary": summary,
            "is_new": is_new,
        }

    def get_open_clusters(self, site_id: str) -> list[dict[str, Any]]:
        """Return all open clusters for cockpit heatmap."""
        return self.cluster_repo.get_open_by_site(site_id)


_email_cluster_service: EmailClusterService | None = None


def get_email_cluster_service() -> EmailClusterService:
    global _email_cluster_service
    if _email_cluster_service is None:
        _email_cluster_service = EmailClusterService()
    return _email_cluster_service
