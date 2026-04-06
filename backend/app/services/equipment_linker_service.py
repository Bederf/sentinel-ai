"""Equipment auto-detection and linking from OCR text.

Detects equipment codes in extracted text using 3-tier strategy:
1. Regex — known SENTINEL code patterns (S002-VAV-101, S002-CHILLER-B1-001)
2. Fuzzy — difflib.SequenceMatcher against site equipment inventory
3. Context — descriptive names ("AHU 1", "Chiller Plant") mapped to equipment
"""

import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# Equipment code patterns
# Plant format: S{site}-{TYPE}-{LOC}-{SEQ}  e.g. S002-CHILLER-B1-001
# Zone format: S{site}-{TYPE}-{ZONE}  e.g. S002-VAV-101
PLANT_PATTERN = re.compile(r"S\d{3}-[A-Z]+-[A-Z0-9]+-\d{3}")
ZONE_PATTERN = re.compile(r"S\d{3}-[A-Z]+-\d{3}")
# Partial: just the type-zone part, e.g. "CHILLER-B1-001", "VAV-101"
PARTIAL_PATTERN = re.compile(r"\b([A-Z]{2,}(?:-[A-Z0-9]+)?-\d{2,3})\b")

# Context patterns: descriptive names that map to equipment types
CONTEXT_PATTERNS = {
    r"\bAHU\s*(\d+)": "AHU",
    r"\bChiller\s*(?:Plant\s*)?(\d+)?": "CHILLER",
    r"\bGen(?:erator)?\s*(?:Room\s*)?(\d+)?": "GEN",
    r"\bUPS\s*(\d+)?": "UPS",
    r"\bFCU\s*(\d+)": "FCU",
    r"\bVAV\s*(\d+)": "VAV",
    r"\bCRAC\s*(\d+)?": "CRAC",
    r"\bCooling\s*Tower\s*(\d+)?": "CT",
    r"\bBESS": "BESS",
    r"\bInverter\s*(\d+)?": "INV",
    r"\bTransformer\s*(\d+)?": "TX",
    r"\bATS\s*(\d+)?": "ATS",
    r"\bDALI\s*(?:Controller)?\s*(\d+)?": "DALI",
    r"\bFire\s*(?:Panel|System)": "FIRE",
}

FUZZY_THRESHOLD = 0.75


@dataclass
class EquipmentMatch:
    """A detected equipment reference in text."""

    equipment_code: str
    equipment_id: str | None  # UUID from equipment table
    confidence: float
    detection_method: str  # regex, fuzzy, context
    matched_text: str


class EquipmentLinkerService:
    """Detect and link equipment references in OCR-extracted text."""

    def detect_equipment_codes(
        self,
        text: str,
        site_id: str,
        equipment_inventory: list[dict] | None = None,
    ) -> list[EquipmentMatch]:
        """Detect equipment codes in text using 3-tier strategy.

        Args:
            text: OCR-extracted text to search
            site_id: Site identifier for scoping matches
            equipment_inventory: Pre-loaded list of equipment dicts (code, name, type, id)
                                 If None, will be loaded from Supabase.
        """
        if not text:
            return []

        inventory = equipment_inventory or self._load_inventory(site_id)
        inventory_codes = {eq.get("code", ""): eq for eq in inventory}
        matches: list[EquipmentMatch] = []
        seen_codes: set = set()

        # Tier 1: Regex — exact code patterns
        for pattern in [PLANT_PATTERN, ZONE_PATTERN]:
            for m in pattern.finditer(text):
                code = m.group()
                if code not in seen_codes:
                    eq = inventory_codes.get(code)
                    matches.append(
                        EquipmentMatch(
                            equipment_code=code,
                            equipment_id=eq.get("id") if eq else None,
                            confidence=1.0 if eq else 0.8,
                            detection_method="regex",
                            matched_text=code,
                        )
                    )
                    seen_codes.add(code)

        # Also try partial codes and resolve against inventory
        for m in PARTIAL_PATTERN.finditer(text):
            partial = m.group(1)
            if partial in seen_codes:
                continue
            # Try to match partial against inventory
            for code, eq in inventory_codes.items():
                if partial in code and code not in seen_codes:
                    matches.append(
                        EquipmentMatch(
                            equipment_code=code,
                            equipment_id=eq.get("id"),
                            confidence=0.85,
                            detection_method="regex",
                            matched_text=partial,
                        )
                    )
                    seen_codes.add(code)

        # Tier 2: Fuzzy match against equipment names
        text_upper = text.upper()
        for code, eq in inventory_codes.items():
            if code in seen_codes:
                continue
            name = eq.get("name", "")
            if not name:
                continue
            # Check if equipment name appears fuzzy in text
            ratio = SequenceMatcher(None, name.upper(), text_upper).ratio()
            # Also check substring match
            if name.upper() in text_upper:
                matches.append(
                    EquipmentMatch(
                        equipment_code=code,
                        equipment_id=eq.get("id"),
                        confidence=0.9,
                        detection_method="fuzzy",
                        matched_text=name,
                    )
                )
                seen_codes.add(code)
            elif ratio > FUZZY_THRESHOLD:
                matches.append(
                    EquipmentMatch(
                        equipment_code=code,
                        equipment_id=eq.get("id"),
                        confidence=round(ratio, 2),
                        detection_method="fuzzy",
                        matched_text=name,
                    )
                )
                seen_codes.add(code)

        # Tier 3: Context patterns — descriptive equipment references
        for pattern_str, eq_type in CONTEXT_PATTERNS.items():
            for m in re.finditer(pattern_str, text, re.IGNORECASE):
                matched_text = m.group()
                # Find matching equipment in inventory by type
                for code, eq in inventory_codes.items():
                    if code in seen_codes:
                        continue
                    if eq.get("type", "").upper() == eq_type:
                        matches.append(
                            EquipmentMatch(
                                equipment_code=code,
                                equipment_id=eq.get("id"),
                                confidence=0.6,
                                detection_method="context",
                                matched_text=matched_text,
                            )
                        )
                        seen_codes.add(code)
                        break  # One match per context pattern

        return matches

    def link_to_equipment(
        self,
        matches: list[EquipmentMatch],
        document_id: str,
        site_id: str,
    ) -> list[dict]:
        """Store equipment-document links in Supabase.

        Args:
            matches: Detected equipment matches
            document_id: Document UUID
            site_id: Site identifier

        Returns:
            List of created link records
        """
        if not matches:
            return []

        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()

            links = []
            for match in matches:
                if not match.equipment_id:
                    continue
                link = {
                    "document_id": document_id,
                    "equipment_id": match.equipment_id,
                    "confidence": match.confidence,
                    "detection_method": match.detection_method,
                    "matched_text": match.matched_text,
                }
                links.append(link)

            if links:
                result = client.table("document_equipment_links").insert(links).execute()
                logger.info("Linked document %s to %d equipment items", document_id, len(links))
                return result.data or []

        except Exception as e:
            logger.error("Failed to store equipment links for document %s: %s", document_id, e)

        return []

    def _load_inventory(self, site_id: str) -> list[dict]:
        """Load equipment inventory for a site from Supabase."""
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            result = client.table("equipment").select("id, code, name, type").eq("site_id", site_id).execute()
            return result.data or []
        except Exception as e:
            logger.warning("Failed to load equipment inventory for %s: %s", site_id, e)
            return []


# Singleton
_linker: EquipmentLinkerService | None = None


def get_equipment_linker() -> EquipmentLinkerService:
    global _linker
    if _linker is None:
        _linker = EquipmentLinkerService()
    return _linker
