"""Shared prediction taxonomy and formula metadata."""

SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"
SEVERITY_HEALTHY = "healthy"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

# Freeze current deterministic rule-based formulas before ML rollout.
FORMULA_VERSION_STATIC = "v1.0-static"


def normalize_prediction_severity(value: str | None) -> str | None:
    """Normalize severity to canonical states."""
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in ("high", "medium"):
        return SEVERITY_WARNING
    if normalized == "low":
        return SEVERITY_HEALTHY
    if normalized in (SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_HEALTHY):
        return normalized
    return None


def normalize_prediction_confidence(value: str | None) -> str | None:
    """Normalize confidence to canonical states."""
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in (CONFIDENCE_LOW, CONFIDENCE_MEDIUM, CONFIDENCE_HIGH):
        return normalized
    return None


def normalize_prediction_urgency(value: str | None) -> str | None:
    """Normalize urgency to canonical states."""
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in ("immediate", "high"):
        return SEVERITY_CRITICAL
    if normalized in ("soon", "medium", "warning"):
        return SEVERITY_WARNING
    if normalized in ("scheduled", "low", "healthy"):
        return SEVERITY_HEALTHY
    if normalized in (SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_HEALTHY):
        return normalized
    return None


def severity_from_probability(probability: float) -> str:
    """Map probability to canonical severity."""
    if probability >= 85:
        return SEVERITY_CRITICAL
    if probability >= 65:
        return SEVERITY_WARNING
    return SEVERITY_HEALTHY


def confidence_from_probability(
    probability: float,
    high_threshold: int = 80,
    medium_threshold: int = 65,
) -> str:
    """Map probability to confidence."""
    if probability >= high_threshold:
        return CONFIDENCE_HIGH
    if probability >= medium_threshold:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def urgency_from_severity(severity: str) -> str:
    """Map canonical severity to canonical urgency."""
    normalized = normalize_prediction_severity(severity)
    if normalized == SEVERITY_CRITICAL:
        return SEVERITY_CRITICAL
    if normalized == SEVERITY_WARNING:
        return SEVERITY_WARNING
    return SEVERITY_HEALTHY
