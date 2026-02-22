"""Intent recognition for BMS conversational queries.

Classifies user queries into intents and extracts entities (equipment IDs,
equipment types, time ranges) for routing to the appropriate service.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Intent(str, Enum):
    """Supported query intents for local LLM routing."""

    WHY_PREDICTION = "why_prediction"
    MAINTENANCE_DUE = "maintenance_due"
    COMPARE_EQUIPMENT = "compare_equipment"
    SHOW_TRENDS = "show_trends"
    EXPLAIN_ANOMALY = "explain_anomaly"
    EQUIPMENT_STATUS = "equipment_status"
    GENERAL_QUERY = "general_query"


@dataclass
class ClassifiedQuery:
    """Result of intent classification with extracted entities."""

    intent: Intent
    confidence: float
    equipment_ids: list[str] = field(default_factory=list)
    equipment_type: Optional[str] = None
    time_range: Optional[str] = None
    original_query: str = ""


# Equipment ID v2.0 pattern: S###-TYPE-FLOOR-ZONE
_EQUIPMENT_ID_PATTERN = re.compile(r"\b(S\d{3}-[A-Z]+-[A-Z0-9]+-[A-Z0-9]+)\b", re.IGNORECASE)

# Equipment type keywords
_EQUIPMENT_TYPES = {
    "chiller": "chiller",
    "chillers": "chiller",
    "ahu": "ahu",
    "air handling": "ahu",
    "fcu": "fcu",
    "fan coil": "fcu",
    "vav": "vav",
    "generator": "generator",
    "generators": "generator",
    "genset": "generator",
    "pump": "pump",
    "pumps": "pump",
    "cooling tower": "cooling_tower",
    "ct": "cooling_tower",
    "boiler": "boiler",
    "boilers": "boiler",
    "ups": "ups",
    "dali": "dali",
    "lighting": "dali",
    "meter": "meter",
    "meters": "meter",
    "heat exchanger": "heat_exchanger",
    "split": "split",
    "split unit": "split",
}

# Time range patterns
_TIME_PATTERNS = {
    r"\b(?:last|past)\s+(\d+)\s+days?\b": "days",
    r"\b(?:last|past)\s+(\d+)\s+hours?\b": "hours",
    r"\b(?:last|past)\s+(\d+)\s+weeks?\b": "weeks",
    r"\b(?:last|past)\s+month\b": "30d",
    r"\b(?:last|past)\s+week\b": "7d",
    r"\b(?:this|today)\b": "1d",
    r"\b(?:next)\s+(\d+)\s+days?\b": "future_days",
}


class IntentClassifier:
    """Classify BMS queries into intents using pattern matching.

    Designed for local-first operation (no LLM needed for classification).
    Patterns are ordered by specificity - more specific patterns match first.
    """

    # Intent patterns ordered by specificity (most specific first)
    _INTENT_PATTERNS: list[tuple[Intent, list[re.Pattern], float]] = [
        # WHY_PREDICTION: Asking about prediction reasoning
        (
            Intent.WHY_PREDICTION,
            [
                re.compile(r"why\s+(?:is|does|will|did|has)", re.I),
                re.compile(r"what\s+(?:caused|causes|is causing)", re.I),
                re.compile(r"explain\s+(?:the\s+)?(?:prediction|forecast|failure)", re.I),
                re.compile(r"reason\s+(?:for|behind)", re.I),
                re.compile(r"root\s+cause", re.I),
                re.compile(r"what.+?going\s+(?:wrong|on)\s+with", re.I),
                re.compile(r"why.+?(?:failing|degrading|declining)", re.I),
            ],
            0.85,
        ),
        # EXPLAIN_ANOMALY: Asking about unusual readings or anomalies
        (
            Intent.EXPLAIN_ANOMALY,
            [
                re.compile(r"\banomal(?:y|ies|ous)\b", re.I),
                re.compile(r"unusual\s+(?:reading|value|pattern|behavior)", re.I),
                re.compile(r"abnormal", re.I),
                re.compile(r"spike\s+in", re.I),
                re.compile(r"(?:sudden|unexpected)\s+(?:change|drop|increase|rise)", re.I),
                re.compile(r"out\s+of\s+(?:range|spec|normal)", re.I),
                re.compile(r"deviation", re.I),
            ],
            0.85,
        ),
        # MAINTENANCE_DUE: Asking about maintenance schedules or needs
        (
            Intent.MAINTENANCE_DUE,
            [
                re.compile(r"(?:when|what)\s+(?:is\s+)?(?:the\s+)?(?:next\s+)?maintenance", re.I),
                re.compile(r"(?:maintenance|service)\s+(?:due|schedule|needed|required)", re.I),
                re.compile(r"(?:need|require)s?\s+(?:service|repair|maintenance)", re.I),
                re.compile(r"remaining\s+(?:useful\s+)?life", re.I),
                re.compile(r"(?:rul|end\s+of\s+life)", re.I),
                re.compile(r"how\s+(?:long|much\s+longer).+?(?:last|run)", re.I),
                re.compile(r"should\s+(?:i|we)\s+(?:service|replace|repair)", re.I),
                re.compile(r"spare\s+parts?", re.I),
            ],
            0.85,
        ),
        # COMPARE_EQUIPMENT: Comparing multiple pieces of equipment
        (
            Intent.COMPARE_EQUIPMENT,
            [
                re.compile(r"compare\b", re.I),
                re.compile(r"(?:difference|comparison)\s+between", re.I),
                re.compile(r"versus|vs\.?\b", re.I),
                re.compile(r"which\s+.+?\s+(?:is\s+)?(?:better|worse|healthier|more reliable)", re.I),
                re.compile(r"side\s+by\s+side", re.I),
            ],
            0.85,
        ),
        # SHOW_TRENDS: Requesting trend or historical data
        (
            Intent.SHOW_TRENDS,
            [
                re.compile(r"(?:show|display|plot|graph)\s+(?:me\s+)?(?:the\s+)?trend", re.I),
                re.compile(r"(?:trend|history|historical)\s+(?:for|of|data)", re.I),
                re.compile(r"(?:over\s+)?(?:the\s+)?(?:last|past)\s+\d+\s+(?:day|week|month)", re.I),
                re.compile(r"how\s+has\s+.+?(?:changed|trended|performed)", re.I),
                re.compile(r"performance\s+(?:over\s+)?time", re.I),
                re.compile(r"degradation\s+(?:curve|trend|rate)", re.I),
            ],
            0.80,
        ),
        # EQUIPMENT_STATUS: Asking about current status/health
        (
            Intent.EQUIPMENT_STATUS,
            [
                re.compile(r"(?:what\s+is|what\'s)\s+(?:the\s+)?(?:status|health|condition)", re.I),
                re.compile(r"(?:status|health|condition)\s+(?:of|for)", re.I),
                re.compile(r"how\s+(?:is|are)\s+.+?(?:doing|performing|running)", re.I),
                re.compile(r"(?:is|are)\s+.+?(?:running|working|ok|healthy)", re.I),
                re.compile(r"(?:current|latest)\s+(?:reading|value|state)", re.I),
                re.compile(r"health\s+score", re.I),
            ],
            0.75,
        ),
    ]

    def classify(self, query: str) -> ClassifiedQuery:
        """Classify a user query into an intent with extracted entities.

        Args:
            query: Natural language query from user

        Returns:
            ClassifiedQuery with intent, confidence, and extracted entities
        """
        equipment_ids = self._extract_equipment_ids(query)
        equipment_type = self._extract_equipment_type(query)
        time_range = self._extract_time_range(query)

        # Try each intent pattern set in order
        for intent, patterns, base_confidence in self._INTENT_PATTERNS:
            for pattern in patterns:
                if pattern.search(query):
                    # Boost confidence if equipment context is present
                    confidence = base_confidence
                    if equipment_ids or equipment_type:
                        confidence = min(confidence + 0.10, 0.99)

                    return ClassifiedQuery(
                        intent=intent,
                        confidence=confidence,
                        equipment_ids=equipment_ids,
                        equipment_type=equipment_type,
                        time_range=time_range,
                        original_query=query,
                    )

        # Default to general query
        return ClassifiedQuery(
            intent=Intent.GENERAL_QUERY,
            confidence=0.50,
            equipment_ids=equipment_ids,
            equipment_type=equipment_type,
            time_range=time_range,
            original_query=query,
        )

    def _extract_equipment_ids(self, query: str) -> list[str]:
        """Extract equipment IDs (v2.0 format) from query."""
        return [m.upper() for m in _EQUIPMENT_ID_PATTERN.findall(query)]

    def _extract_equipment_type(self, query: str) -> Optional[str]:
        """Extract equipment type keyword from query."""
        query_lower = query.lower()
        # Check multi-word phrases first (longer match wins)
        for keyword in sorted(_EQUIPMENT_TYPES, key=len, reverse=True):
            if keyword in query_lower:
                return _EQUIPMENT_TYPES[keyword]
        return None

    def _extract_time_range(self, query: str) -> Optional[str]:
        """Extract time range from query."""
        for pattern_str, unit in _TIME_PATTERNS.items():
            match = re.search(pattern_str, query, re.IGNORECASE)
            if match:
                if match.groups():
                    return f"{match.group(1)}{unit[0]}"
                return unit
        return None
