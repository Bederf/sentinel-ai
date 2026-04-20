"""
Phase 180: Asset ID Resolver — stages 1–4 (Normalise → Exact → Fuzzy → LLM).

Stage 1 — Alias exact match  (normalised key → KNOWN_ALIASES or asset_resolver_aliases table)
Stage 2 — Equipment.code exact match (normalised)
Stage 3 — rapidfuzz.token_set_ratio fuzzy match across code, display_name, manufacturer, model, type
Stage 4 — LLM assisted resolution via ModelGateway (Wave 2)

Usage
----
    resolver = AssetIDResolver(db=supabase_client, site_id="site-002")
    result = resolver.resolve("Chiller B1 compressor unit", document_type="maint_work_order")
"""

from __future__ import annotations

import json
import logging
import re
import string
from typing import Any

from rapidfuzz import fuzz

from app.models.asset_resolution import (
    ResolutionConfidence,
    ResolutionMethod,
    ResolutionResult,
)
from app.services.model_gateway import model_gateway

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------- #
# KNOWN_ALIASES — used as fallback when asset_resolver_aliases table is
# missing or returns no results.  Format: {normalised_alias: asset_id}
# -------------------------------------------------------------------------- #
KNOWN_ALIASES: dict[str, str] = {
    "chiller": "S002-CHILLER-B1-001",
    "chiller b1": "S002-CHILLER-B1-001",
    "chiller b2": "S002-CHILLER-B1-002",
    "ahu 1": "S002-AHU-001",
    "ahu 2": "S002-AHU-002",
    "ahu 3": "S002-AHU-003",
    "ahu 4": "S002-AHU-004",
    "ahu 5": "S002-AHU-005",
    "fcu 101": "S002-FCU-101",
    "fcu 102": "S002-FCU-102",
    "vav 101": "S002-VAV-101",
    "vav 102": "S002-VAV-102",
    "generator": "S002-GEN-001",
    "ups 1": "S002-UPS-001",
    "meter main": "S002-MTR-B1-MAIN",
    "solar inverter": "S002-INV-SOLAR-001",
    "bess": "S002-BESS-001",
}


class AssetIDResolver:
    """
    Resolves free-text equipment descriptions to SENTINEL asset IDs.

    Parameters
    ----------
    db : Supabase client
        Initialised Supabase client (async table() API).
    site_id : str
        SENTINEL site identifier (e.g. "site-002").  Required; raises ValueError
        if None or empty string.
    """

    def __init__(self, db: Any, site_id: str) -> None:
        if not site_id or not isinstance(site_id, str) or not site_id.strip():
            raise ValueError("site_id must be a non-empty string")
        self.db = db
        self.site_id = site_id
        self._equipment_cache: list[dict[str, Any]] | None = None

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _get_equipment(self) -> list[dict[str, Any]]:
        """
        Load active equipment for the site, cached in-memory.

        Returns
        -------
        list[dict]
            Each dict contains: code, type, manufacturer, model, display_name
        """
        if self._equipment_cache is not None:
            return self._equipment_cache

        result = (
            self.db.table("equipment")
            .select("code, type, manufacturer, model, display_name")
            .eq("site_id", self.site_id)
            .eq("active", True)
            .execute()
        )
        self._equipment_cache = result.data if result.data else []
        return self._equipment_cache

    @staticmethod
    def _normalise(raw: str) -> str:
        """
        Normalise an equipment description for matching.

        Steps: lowercase → strip punctuation → collapse internal whitespace.
        """
        if not raw:
            return ""
        lowered = raw.lower()
        # Remove punctuation except spaces/hyphens
        translation = str.maketrans("", "", string.punctuation.replace("-", ""))
        stripped = lowered.translate(translation)
        # Collapse multiple spaces into one
        normalised = re.sub(r"\s+", " ", stripped).strip()
        return normalised

    @staticmethod
    def _confidence_band(score: float) -> ResolutionConfidence:
        """
        Map a raw score (0.0–1.0) to a confidence band.

        >= 0.85 → HIGH
        0.60–0.84 → MEDIUM
        < 0.60 → LOW
        """
        if score >= 0.85:
            return ResolutionConfidence.HIGH
        elif score >= 0.60:
            return ResolutionConfidence.MEDIUM
        else:
            return ResolutionConfidence.LOW

    def _load_aliases(self) -> dict[str, str]:
        """
        Load alias→asset_id mappings for the site.

        Queries the asset_resolver_aliases table.  Returns an empty dict if
        the table does not exist yet (graceful degradation to KNOWN_ALIASES).
        """
        try:
            result = (
                self.db.table("asset_resolver_aliases").select("alias, asset_id").eq("site_id", self.site_id).execute()
            )
            aliases: dict[str, str] = {}
            if result.data:
                for row in result.data:
                    aliases[self._normalise(row["alias"])] = row["asset_id"]
            return aliases
        except Exception:
            # Table may not exist yet — fall back to KNOWN_ALIASES
            return {}

    # ------------------------------------------------------------------ #
    # Core resolve API
    # ------------------------------------------------------------------ #

    async def resolve(
        self,
        equipment_description: str,
        document_type: str | None = None,
        gateway: Any = None,
    ) -> ResolutionResult:
        """
        Resolve a free-text equipment description to a SENTINEL asset_id.

        Parameters
        ----------
        equipment_description : str
            Raw text from the document (e.g. "Chiller B1 — compressor unit").
        document_type : str | None
            Optional document context (e.g. "maint_work_order").

        Returns
        -------
        ResolutionResult
            Frozen dataclass with asset_id, confidence, band, method, and
            review flags.
        """
        # ---- Stage 0: empty input quarantine ---- #
        if not equipment_description or not equipment_description.strip():
            return ResolutionResult(
                asset_id=None,
                confidence=0.0,
                confidence_band=ResolutionConfidence.LOW,
                method=ResolutionMethod.UNRESOLVED,
                matched_on=None,
                needs_review=True,
                review_reason="empty description",
            )

        normalised = self._normalise(equipment_description)

        # ---- Stage 1: alias exact match ---- #
        aliases = {**KNOWN_ALIASES, **self._load_aliases()}
        if normalised in aliases:
            asset_id = aliases[normalised]
            return ResolutionResult(
                asset_id=asset_id,
                confidence=1.0,
                confidence_band=ResolutionConfidence.HIGH,
                method=ResolutionMethod.EXACT,
                matched_on="alias",
                needs_review=False,
                review_reason=None,
            )

        equipment = self._get_equipment()

        # ---- Stage 2: exact match on equipment.code (normalised) ---- #
        for eq in equipment:
            code_norm = self._normalise(eq.get("code") or "")
            if code_norm and code_norm == normalised:
                return ResolutionResult(
                    asset_id=eq["code"],
                    confidence=1.0,
                    confidence_band=ResolutionConfidence.HIGH,
                    method=ResolutionMethod.EXACT,
                    matched_on="code",
                    needs_review=False,
                    review_reason=None,
                )

        # ---- Stage 3: fuzzy match via rapidfuzz token_set_ratio ---- #
        best_score = 0.0
        best_eq: dict[str, Any] | None = None
        best_field: str | None = None

        for eq in equipment:
            searchable_fields = [
                ("code", eq.get("code") or ""),
                ("display_name", eq.get("display_name") or ""),
                ("manufacturer", eq.get("manufacturer") or ""),
                ("model", eq.get("model") or ""),
                ("type", eq.get("type") or ""),
            ]
            for field_name, field_value in searchable_fields:
                if not field_value:
                    continue
                searchable_norm = self._normalise(field_value)
                if not searchable_norm:
                    continue
                # rapidfuzz.fuzz.token_set_ratio returns int 0-100
                raw_score = fuzz.token_set_ratio(normalised, searchable_norm)
                score = raw_score / 100.0
                if score > best_score:
                    best_score = score
                    best_eq = eq
                    best_field = field_name

        if best_score >= 0.60:
            band = self._confidence_band(best_score)
            needs_review = band != ResolutionConfidence.HIGH
            review_reason = None
            if needs_review:
                review_reason = f"fuzzy match ({best_field}) score {best_score:.2f} below HIGH threshold"
            return ResolutionResult(
                asset_id=best_eq["code"],
                confidence=round(best_score, 4),
                confidence_band=band,
                method=ResolutionMethod.FUZZY,
                matched_on=best_field,
                needs_review=needs_review,
                review_reason=review_reason,
            )

        # ---- Stage 4: LLM assisted ---- #
        return await self._llm_resolve(equipment_description, equipment, document_type, gateway=gateway)

    # ------------------------------------------------------------------ #
    # Stage 4 — LLM assisted resolution
    # ------------------------------------------------------------------ #

    @staticmethod
    def _esc(s: str) -> str:
        """
        Escape Jinja2/template braces in user-supplied text to prevent
        format-string injection when text is embedded in a prompt.
        """
        return s.replace("{", "{{").replace("}", "}}")

    async def _llm_resolve(
        self,
        equipment_description: str,
        equipment: list[dict[str, Any]],
        document_type: str | None,
        gateway: Any = None,
    ) -> ResolutionResult:
        """
        Stage 4 — LLM-assisted resolution via ModelGateway.

        Args:
            equipment_description: Raw text from the document.
            equipment: List of equipment dicts for the site.
            document_type: Optional document type hint.
            gateway: Injectable ModelGateway instance for testing.
                    Defaults to the module-level model_gateway singleton.

        B2 FIX: model_gateway.call() returns str directly; use response_text.
        B6 FIX: escape all user-supplied text before inserting into prompt.
        B3 FIX: quarantine if asset_id is None OR confidence_band is LOW.
        """
        if gateway is None:
            gateway = model_gateway

        escaped_desc = self._esc(equipment_description)
        document_type_esc = self._esc(document_type) if document_type else "unknown"

        equipment_list = "\n".join(
            [
                f"- {self._esc(eq.get('code', ''))}: {self._esc(eq.get('display_name', ''))} "
                f"({self._esc(eq.get('manufacturer', ''))} {self._esc(eq.get('model', ''))})"
                for eq in equipment
            ]
        )

        prompt = (
            f"You are a BMS equipment resolution assistant.\n"
            f'Return ONLY valid JSON with keys: "asset_id" (string or null), "confidence" (number 0-1), '
            f'"reason" (string).\n\n'
            f"Document type: {document_type_esc}\n"
            f"Equipment description to resolve: {escaped_desc}\n\n"
            f"Available equipment at this site:\n"
            f"{equipment_list}\n\n"
            f"Return null for asset_id if no equipment matches the description above.\n"
            f"JSON response:"
        )

        try:
            response_text: str = await gateway.call(
                task_class="medium",
                messages=[{"role": "user", "content": prompt}],
                system="You are a BMS equipment resolution assistant. Return JSON only.",
            )
            parsed = json.loads(response_text)

            asset_id = parsed.get("asset_id")
            confidence = float(parsed.get("confidence", 0.0))
            reason = parsed.get("reason", "")

            # Validate asset_id exists in equipment list if provided
            if asset_id is not None:
                valid_codes = {eq.get("code") for eq in equipment}
                if asset_id not in valid_codes:
                    logger.warning(
                        "LLM returned asset_id %s not in valid equipment list; quarantining",
                        asset_id,
                    )
                    return ResolutionResult(
                        asset_id=None,
                        confidence=confidence,
                        confidence_band=ResolutionConfidence.LOW,
                        method=ResolutionMethod.LLM_ASSISTED,
                        matched_on="llm",
                        needs_review=True,
                        review_reason=f"llm returned invalid asset_id '{asset_id}': {reason}",
                    )

            band = self._confidence_band(confidence)
            needs_review = band in (ResolutionConfidence.LOW, ResolutionConfidence.MEDIUM) or asset_id is None

            return ResolutionResult(
                asset_id=asset_id,
                confidence=round(confidence, 4),
                confidence_band=band,
                method=ResolutionMethod.LLM_ASSISTED,
                matched_on="llm",
                needs_review=needs_review,
                review_reason=reason if needs_review else None,
            )

        except (json.JSONDecodeError, AttributeError, TypeError, ValueError, RuntimeError) as exc:
            logger.error("Stage 4 LLM resolution failed: %s", exc)
            return ResolutionResult(
                asset_id=None,
                confidence=0.0,
                confidence_band=ResolutionConfidence.LOW,
                method=ResolutionMethod.UNRESOLVED,
                matched_on=None,
                needs_review=True,
                review_reason=f"llm stage failed: {exc}",
            )

    # ------------------------------------------------------------------ #
    # Convenience entry point — resolve + apply in one call
    # ------------------------------------------------------------------ #

    async def resolve_and_apply(self, document_id: str, gateway: Any = None) -> ResolutionResult:
        """
        Fetch a document by ID, resolve its equipment description, and apply
        the resolution result to the document record in the database.

        Parameters
        ----------
        document_id : str
            UUID of the document to process.
        gateway : ModelGateway | None
            Optional injectable ModelGateway for testing; defaults to module singleton.

        Returns
        -------
        ResolutionResult
            The resolution result from the resolve() call.
        """
        from app.services.asset_resolution_service import apply_resolution

        # Fetch document record
        doc_result = (
            self.db.table("documents")
            .select("id, equipment_description, document_type")
            .eq("id", document_id)
            .execute()
        )
        if not doc_result.data:
            return ResolutionResult(
                asset_id=None,
                confidence=0.0,
                confidence_band=ResolutionConfidence.LOW,
                method=ResolutionMethod.UNRESOLVED,
                matched_on=None,
                needs_review=True,
                review_reason=f"document {document_id} not found",
            )

        doc = doc_result.data[0]
        equipment_description = doc.get("equipment_description") or ""
        document_type = doc.get("document_type")

        # Resolve
        result = await self.resolve(equipment_description, document_type, gateway=gateway)

        # Apply resolution to document record
        apply_resolution(document_id, result, self.db)

        return result
