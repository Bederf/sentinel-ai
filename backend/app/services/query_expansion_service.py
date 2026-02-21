"""BMS-aware query expansion for improved RAG retrieval coverage.

Generates query variants using a domain-specific synonym dictionary
and equipment code extraction — no LLM calls, zero latency cost.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Regex to extract equipment type from SENTINEL equipment codes
# e.g. S002-CHILLER-B1-001 → CHILLER, S002-VAV-101 → VAV
EQUIPMENT_CODE_RE = re.compile(r"S\d{3}-([A-Z]+)-", re.IGNORECASE)

# BMS domain synonym dictionary — maps terms to alternative phrasings
# that documentation may use instead of the user's exact wording
SYNONYMS: dict[str, list[str]] = {
    # HVAC equipment
    "chiller": ["cooling plant", "water chiller", "chilled water system", "chiller plant"],
    "ahu": ["air handling unit", "air handler", "AHU"],
    "vav": ["variable air volume", "VAV box", "VAV controller"],
    "fcu": ["fan coil unit", "fan coil", "FCU"],
    "split": ["split unit", "split system", "mini-split", "DX unit"],
    "cooling tower": ["CT", "condenser water", "cooling tower"],
    "ct": ["cooling tower", "condenser water"],
    "crac": ["computer room air conditioning", "precision cooling"],
    # Electrical
    "ups": ["uninterruptible power supply", "battery backup", "UPS system"],
    "gen": ["generator", "genset", "diesel generator", "standby generator"],
    "generator": ["genset", "diesel generator", "standby power", "backup generator"],
    "transformer": ["TX", "distribution transformer", "step-down transformer"],
    "ats": ["automatic transfer switch", "changeover switch"],
    "pfc": ["power factor correction", "capacitor bank"],
    "msb": ["main switchboard", "main distribution board"],
    "mdb": ["main distribution board", "main switchboard"],
    # Lighting
    "dali": ["DALI lighting", "digital addressable lighting", "DALI-2"],
    "lighting": ["DALI", "luminaire", "light fitting", "illumination"],
    # Fire & security
    "fire": ["fire detection", "fire alarm", "fire suppression", "fire system"],
    "access": ["access control", "door access", "card reader", "ACC"],
    "cctv": ["surveillance", "camera system", "video monitoring"],
    # Operational concepts
    "health score": ["equipment health", "health scoring", "condition assessment", "health rating"],
    "health": ["equipment health", "health score", "condition", "wellness"],
    "maintenance": ["preventive maintenance", "PM schedule", "service schedule"],
    "work order": ["service request", "maintenance task", "WO"],
    "alarm": ["alert", "fault", "notification", "warning"],
    "alert": ["alarm", "notification", "warning", "fault notification"],
    # Symptom descriptions → technical terms
    "not cooling": ["compressor fault", "refrigerant leak", "low discharge pressure", "cooling failure"],
    "noisy": ["vibration", "bearing wear", "mechanical noise", "abnormal sound"],
    "tripping": ["overcurrent", "fault code", "circuit breaker trip", "overload"],
    "leaking": ["water leak", "refrigerant leak", "pipe leak", "condensate overflow"],
    "hot": ["overheating", "high temperature", "thermal runaway", "insufficient cooling"],
    # SA-specific
    "load shedding": ["loadshedding", "power outage", "eskom", "rolling blackout"],
    "loadshedding": ["load shedding", "power outage", "eskom schedule"],
    "eskom": ["load shedding", "utility power", "grid power"],
    # Platform terms
    "simbiot": ["SIMBIOT", "MCP server", "equipment onboarding"],
    "sentinel": ["SENTINEL", "BMS intelligence", "platform"],
    "parasite": ["PARASITE", "autonomous decision", "AI autonomy"],
    "sentry": ["Sentry bot", "Telegram bot", "notification bot"],
    # Energy
    "energy": ["power consumption", "electricity", "energy usage", "kWh"],
    "solar": ["PV", "photovoltaic", "solar panel", "solar generation"],
    "bess": ["battery storage", "energy storage", "battery system"],
    "tariff": ["electricity tariff", "energy cost", "rate structure", "TOU"],
}

# Maximum number of query variants to generate (original + expansions)
MAX_VARIANTS = 3


class QueryExpansionService:
    """Generate BMS-aware query variants for better retrieval coverage."""

    def expand(self, query: str) -> list[str]:
        """Return [original, variant1, variant2] — max 3 queries.

        Strategy:
        1. Always include the original query
        2. If equipment code found, add a variant with the type expanded
        3. Apply synonym expansion for matching BMS terms
        4. Generate a documentation-style rephrasing

        Args:
            query: The user's original question

        Returns:
            List of 1-3 query variants, original always first
        """
        if not query or not query.strip():
            return [query] if query else [""]

        variants = [query]
        query_lower = query.lower()

        # 1. Equipment code expansion
        code_variant = self._expand_equipment_codes(query)
        if code_variant and code_variant != query:
            variants.append(code_variant)

        # 2. Synonym expansion — find best matching synonym set
        synonym_variant = self._expand_synonyms(query, query_lower)
        if synonym_variant and synonym_variant not in variants:
            variants.append(synonym_variant)

        # 3. If we still need more variants, try documentation-style rephrasing
        if len(variants) < MAX_VARIANTS:
            doc_variant = self._documentation_rephrase(query, query_lower)
            if doc_variant and doc_variant not in variants:
                variants.append(doc_variant)

        return variants[:MAX_VARIANTS]

    def _expand_equipment_codes(self, query: str) -> str | None:
        """Replace equipment codes with expanded type names.

        S002-CHILLER-B1-001 → 'chiller chilled water system S002-CHILLER-B1-001'
        """
        matches = EQUIPMENT_CODE_RE.findall(query)
        if not matches:
            return None

        expanded_parts = []
        for eq_type in matches:
            eq_type_lower = eq_type.lower()
            synonyms = SYNONYMS.get(eq_type_lower, [])
            if synonyms:
                expanded_parts.extend(synonyms[:2])
            else:
                expanded_parts.append(eq_type_lower)

        # Prepend expanded terms to the original query
        expansion = " ".join(expanded_parts)
        return f"{expansion} {query}"

    def _expand_synonyms(self, query: str, query_lower: str) -> str | None:
        """Find BMS terms in query and substitute with synonyms."""
        best_match: tuple[str, list[str]] | None = None
        best_match_len = 0

        for term, synonyms in SYNONYMS.items():
            # Check if term appears in query (word boundary aware)
            pattern = r"\b" + re.escape(term) + r"\b"
            if re.search(pattern, query_lower):
                if len(term) > best_match_len:
                    best_match = (term, synonyms)
                    best_match_len = len(term)

        if not best_match:
            return None

        term, synonyms = best_match
        # Replace the term with the first synonym that's different
        replacement = synonyms[0] if synonyms else term
        pattern = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
        variant = pattern.sub(replacement, query, count=1)

        return variant if variant != query else None

    def _documentation_rephrase(self, query: str, query_lower: str) -> str | None:
        """Generate a documentation-style variant of the query.

        User queries are often conversational; documentation uses
        different phrasing. This bridges the vocabulary gap.
        """
        # Common question patterns → documentation-style phrasings
        rephrases = [
            (r"how does (.+) work", r"\1 architecture overview"),
            (r"how do I (.+)", r"\1 guide procedure"),
            (r"what is (.+)", r"\1 definition overview"),
            (r"why is (.+)", r"\1 explanation rationale"),
            (r"can I (.+)", r"\1 capability feature"),
            (r"how to (.+)", r"\1 setup configuration guide"),
            (r"where is (.+)", r"\1 location configuration"),
            (r"when does (.+)", r"\1 schedule trigger"),
        ]

        for pattern, replacement in rephrases:
            match = re.match(pattern, query_lower)
            if match:
                try:
                    return re.sub(pattern, replacement, query_lower)
                except Exception:
                    continue

        return None


# Singleton instance
_query_expansion_service: QueryExpansionService | None = None


def get_query_expansion_service() -> QueryExpansionService:
    """Get singleton query expansion service instance."""
    global _query_expansion_service
    if _query_expansion_service is None:
        _query_expansion_service = QueryExpansionService()
    return _query_expansion_service
