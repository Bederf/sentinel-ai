"""Phase 188 report-only outcome validation foundation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.database.repositories.base import SupabaseRepository


EPOCH_PRE_CUTOVER = "pre_cutover_legacy"
EPOCH_POST_CUTOVER = "post_phase185_cutover"
EPOCH_EXCLUDED_UNKNOWN = "excluded_unknown"

GATE_NOT_ENOUGH_EVIDENCE = "not_enough_evidence"
GATE_OUTCOME_ELIGIBLE = "outcome_eligible"
GATE_ADVISORY_ONLY = "advisory_only"
GATE_SUPERVISED_ELIGIBLE = "supervised_eligible"
GATE_BLOCKED_QUALITY_FAILURE = "blocked_quality_failure"
GATE_BLOCKED_PRE_CUTOVER = "blocked_pre_cutover"
GATE_SAFETY_UNRESOLVED = "safety_class_unresolved"

SAFETY_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


@dataclass(frozen=True)
class SafetyProfile:
    equipment_type: str
    default_safety_class: str
    source: str = "equipment_type_profile"
    site_id: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class SafetyResolution:
    safety_class: str | None
    source: str
    reason: str

    @property
    def resolved(self) -> bool:
        return self.safety_class in SAFETY_ORDER


@dataclass(frozen=True)
class ThresholdConfig:
    equipment_type: str
    recommendation_type: str
    safety_class: str
    site_id: str | None = None
    min_validated_recommendations: int = 1
    min_measured_outcomes: int = 1
    min_fault_prediction_samples: int = 0
    max_false_positive_rate: float = 1.0
    max_false_negative_rate: float = 1.0
    min_positive_outcome_rate: float = 0.0
    min_energy_savings_confidence: float = 0.0
    promotion_mode: str = "blocked"


@dataclass
class EvidenceCounts:
    generated: int = 0
    measured_outcomes: int = 0
    positive: int = 0
    negative: int = 0
    false_positive: int = 0
    false_negative: int = 0
    inconclusive: int = 0

    @property
    def validated(self) -> int:
        return self.positive + self.negative + self.false_positive + self.false_negative


class Phase188OutcomeValidationService(SupabaseRepository):
    """Report-only Phase 188 evaluator.

    This service does not write routing decisions and deliberately excludes
    pre-cutover/unknown evidence from promotion math.
    """

    async def collect_report(
        self,
        *,
        site_id: str,
        limit: int = 5000,
    ) -> dict[str, Any]:
        """Collect a report from live Supabase data."""
        client = await self.get_client()
        rec_result = await (
            client.table("recommendations")
            .select(
                "id,site_id,action_type,target_equipment,action,expected_impact,status,"
                "outcome_validated,outcome_notes,actual_saving_kwh,actual_saving_zar,"
                "metadata,phase188_evidence_epoch"
            )
            .eq("site_id", site_id)
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )
        profiles = await self._load_safety_profiles(client, site_id)
        thresholds = await self._load_thresholds(client, site_id)
        return self.evaluate_rows(
            rec_result.data or [],
            safety_profiles=profiles,
            thresholds=thresholds,
            site_id=site_id,
        )

    async def _load_safety_profiles(self, client: Any, site_id: str) -> list[SafetyProfile]:
        result = await (
            client.table("phase188_equipment_safety_profiles")
            .select("site_id,equipment_type,default_safety_class,source,reason")
            .eq("enabled", True)
            .execute()
        )
        profiles: list[SafetyProfile] = []
        for row in result.data or []:
            row_site = row.get("site_id")
            if row_site not in (None, "", site_id):
                continue
            profiles.append(
                SafetyProfile(
                    site_id=row_site or None,
                    equipment_type=str(row.get("equipment_type") or "").lower(),
                    default_safety_class=normalise_safety_class(row.get("default_safety_class")) or "HIGH",
                    source=str(row.get("source") or "equipment_type_profile"),
                    reason=str(row.get("reason") or ""),
                )
            )
        return profiles

    async def _load_thresholds(self, client: Any, site_id: str) -> list[ThresholdConfig]:
        result = await client.table("phase188_outcome_thresholds").select("*").eq("enabled", True).execute()
        thresholds: list[ThresholdConfig] = []
        for row in result.data or []:
            row_site = row.get("site_id")
            if row_site not in (None, "", site_id):
                continue
            thresholds.append(threshold_from_row(row))
        return thresholds

    def evaluate_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        safety_profiles: list[SafetyProfile],
        thresholds: list[ThresholdConfig],
        site_id: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate recommendation rows in report-only mode."""
        summary: dict[str, Any] = {
            "site_id": site_id,
            "total_rows": len(rows),
            "eligible_rows": 0,
            "excluded_pre_cutover": 0,
            "excluded_unknown": 0,
            "safety_unresolved": 0,
            "groups": [],
            "overall_gate_result": GATE_NOT_ENOUGH_EVIDENCE,
        }
        grouped: dict[tuple[str, str, str], EvidenceCounts] = {}
        unresolved_groups: set[tuple[str, str]] = set()

        for row in rows:
            epoch = str(row.get("phase188_evidence_epoch") or EPOCH_EXCLUDED_UNKNOWN)
            if epoch == EPOCH_PRE_CUTOVER:
                summary["excluded_pre_cutover"] += 1
                continue
            if epoch != EPOCH_POST_CUTOVER:
                summary["excluded_unknown"] += 1
                continue

            equipment_type = resolve_equipment_type(row)
            recommendation_type = resolve_recommendation_type(row)
            safety = resolve_safety_class(row, safety_profiles=safety_profiles, equipment_type=equipment_type)
            if not safety.resolved:
                summary["safety_unresolved"] += 1
                unresolved_groups.add((equipment_type, recommendation_type))
                continue

            key = (equipment_type, recommendation_type, safety.safety_class or "HIGH")
            counts = grouped.setdefault(key, EvidenceCounts())
            counts.generated += 1
            apply_outcome(counts, row)
            summary["eligible_rows"] += 1

        for equipment_type, recommendation_type in sorted(unresolved_groups):
            summary["groups"].append(
                {
                    "equipment_type": equipment_type,
                    "recommendation_type": recommendation_type,
                    "safety_class": None,
                    "gate_result": GATE_SAFETY_UNRESOLVED,
                    "reason": "No point-level SafetyClass or equipment-type safety profile resolved",
                    "counts": {},
                }
            )

        for key, counts in sorted(grouped.items()):
            equipment_type, recommendation_type, safety_class = key
            threshold = resolve_threshold(
                thresholds,
                site_id=site_id,
                equipment_type=equipment_type,
                recommendation_type=recommendation_type,
                safety_class=safety_class,
            )
            gate_result, reason = evaluate_counts(counts, threshold, safety_class)
            summary["groups"].append(
                {
                    "equipment_type": equipment_type,
                    "recommendation_type": recommendation_type,
                    "safety_class": safety_class,
                    "gate_result": gate_result,
                    "reason": reason,
                    "threshold": threshold_to_dict(threshold) if threshold else None,
                    "counts": counts_to_dict(counts),
                }
            )

        summary["overall_gate_result"] = overall_gate_result(summary)
        return summary


def normalise_safety_class(value: Any) -> str | None:
    safety = str(value or "").strip().upper()
    if safety in SAFETY_ORDER:
        return safety
    return None


def resolve_equipment_type(row: dict[str, Any]) -> str:
    raw_metadata = row.get("metadata")
    raw_action = row.get("action")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    action: dict[str, Any] = raw_action if isinstance(raw_action, dict) else {}
    for value in (
        row.get("equipment_type"),
        metadata.get("equipment_type"),
        metadata.get("canonical_equipment_type"),
        action.get("equipment_type"),
    ):
        if value:
            return str(value).strip().lower()
    target = str(row.get("target_equipment") or "")
    parts = [part for part in target.replace("_", "-").split("-") if part]
    if len(parts) >= 2:
        return parts[1].lower()
    return "unknown"


def resolve_recommendation_type(row: dict[str, Any]) -> str:
    raw_metadata = row.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    for value in (
        row.get("recommendation_type"),
        metadata.get("recommendation_type"),
        metadata.get("recommendation_family"),
        row.get("action_type"),
    ):
        if value:
            return str(value).strip().lower()
    return "unknown"


def resolve_safety_class(
    row: dict[str, Any],
    *,
    safety_profiles: list[SafetyProfile],
    equipment_type: str,
) -> SafetyResolution:
    point_classes = extract_point_safety_classes(row)
    if point_classes:
        worst = max(point_classes, key=lambda item: SAFETY_ORDER[item])
        return SafetyResolution(
            safety_class=worst,
            source="point_worst_case",
            reason="Resolved from concrete point safety classes",
        )

    profile = resolve_safety_profile(safety_profiles, equipment_type=equipment_type, site_id=row.get("site_id"))
    if profile:
        return SafetyResolution(
            safety_class=profile.default_safety_class,
            source=profile.source,
            reason=profile.reason,
        )

    return SafetyResolution(
        safety_class=None,
        source="unresolved",
        reason="No concrete point safety class or equipment-type safety profile",
    )


def extract_point_safety_classes(row: dict[str, Any]) -> list[str]:
    raw_action = row.get("action")
    raw_metadata = row.get("metadata")
    action: dict[str, Any] = raw_action if isinstance(raw_action, dict) else {}
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    point_payloads = [
        action.get("points"),
        action.get("resolved_points"),
        action.get("point_safety_classes"),
        metadata.get("points"),
        metadata.get("resolved_points"),
        metadata.get("point_safety_classes"),
        metadata.get("point_resolution"),
    ]
    classes: list[str] = []
    for payload in point_payloads:
        classes.extend(_extract_safety_classes(payload))
    return classes


def _extract_safety_classes(value: Any) -> list[str]:
    safety = normalise_safety_class(value)
    if safety:
        return [safety]
    if isinstance(value, dict):
        found: list[str] = []
        direct = normalise_safety_class(value.get("safety_class") or value.get("highest_safety_class"))
        if direct:
            found.append(direct)
        for nested_key in ("points", "resolved_points", "children", "point_resolution"):
            found.extend(_extract_safety_classes(value.get(nested_key)))
        return found
    if isinstance(value, list):
        list_found: list[str] = []
        for item in value:
            list_found.extend(_extract_safety_classes(item))
        return list_found
    return []


def resolve_safety_profile(
    profiles: list[SafetyProfile],
    *,
    equipment_type: str,
    site_id: str | None,
) -> SafetyProfile | None:
    equipment_key = (equipment_type or "").lower()
    exact = next(
        (
            profile
            for profile in profiles
            if profile.equipment_type.lower() == equipment_key and profile.site_id == site_id
        ),
        None,
    )
    if exact:
        return exact
    return next(
        (
            profile
            for profile in profiles
            if profile.equipment_type.lower() == equipment_key and profile.site_id is None
        ),
        None,
    )


def threshold_from_row(row: dict[str, Any]) -> ThresholdConfig:
    return ThresholdConfig(
        site_id=row.get("site_id") or None,
        equipment_type=str(row.get("equipment_type") or "").lower(),
        recommendation_type=str(row.get("recommendation_type") or "").lower(),
        safety_class=normalise_safety_class(row.get("safety_class")) or "HIGH",
        min_validated_recommendations=int(row.get("min_validated_recommendations") or 0),
        min_measured_outcomes=int(row.get("min_measured_outcomes") or 0),
        min_fault_prediction_samples=int(row.get("min_fault_prediction_samples") or 0),
        max_false_positive_rate=float(row.get("max_false_positive_rate") or 0.0),
        max_false_negative_rate=float(row.get("max_false_negative_rate") or 0.0),
        min_positive_outcome_rate=float(row.get("min_positive_outcome_rate") or 0.0),
        min_energy_savings_confidence=float(row.get("min_energy_savings_confidence") or 0.0),
        promotion_mode=str(row.get("promotion_mode") or "blocked"),
    )


def resolve_threshold(
    thresholds: list[ThresholdConfig],
    *,
    site_id: str | None,
    equipment_type: str,
    recommendation_type: str,
    safety_class: str,
) -> ThresholdConfig | None:
    key = (equipment_type.lower(), recommendation_type.lower(), safety_class.upper())
    exact = next(
        (
            item
            for item in thresholds
            if (
                item.site_id == site_id
                and item.equipment_type.lower() == key[0]
                and item.recommendation_type.lower() == key[1]
                and item.safety_class.upper() == key[2]
            )
        ),
        None,
    )
    if exact:
        return exact
    return next(
        (
            item
            for item in thresholds
            if (
                item.site_id is None
                and item.equipment_type.lower() == key[0]
                and item.recommendation_type.lower() == key[1]
                and item.safety_class.upper() == key[2]
            )
        ),
        None,
    )


def apply_outcome(counts: EvidenceCounts, row: dict[str, Any]) -> None:
    status = str(row.get("outcome_status") or "").strip().lower()
    if not status:
        status = derive_outcome_status(row)
    if status == "positive":
        counts.positive += 1
        counts.measured_outcomes += 1
    elif status == "negative":
        counts.negative += 1
        counts.measured_outcomes += 1
    elif status == "false_positive":
        counts.false_positive += 1
        counts.measured_outcomes += 1
    elif status == "false_negative":
        counts.false_negative += 1
        counts.measured_outcomes += 1
    else:
        counts.inconclusive += 1


def derive_outcome_status(row: dict[str, Any]) -> str:
    if row.get("outcome_validated") is True:
        return "positive"
    if row.get("outcome_validated") is False and row.get("outcome_notes"):
        return "negative"
    if row.get("actual_saving_kwh") is not None or row.get("actual_saving_zar") is not None:
        return "positive"
    return "inconclusive"


def evaluate_counts(
    counts: EvidenceCounts,
    threshold: ThresholdConfig | None,
    safety_class: str,
) -> tuple[str, str]:
    if threshold is None:
        if safety_class == "HIGH":
            return GATE_BLOCKED_QUALITY_FAILURE, "Missing threshold config for HIGH safety class"
        return GATE_NOT_ENOUGH_EVIDENCE, "Missing threshold config"
    if counts.validated < threshold.min_validated_recommendations:
        return GATE_NOT_ENOUGH_EVIDENCE, "Validated recommendation sample floor not met"
    if counts.measured_outcomes < threshold.min_measured_outcomes:
        return GATE_NOT_ENOUGH_EVIDENCE, "Measured outcome sample floor not met"
    validated = max(counts.validated, 1)
    false_positive_rate = counts.false_positive / validated
    false_negative_rate = counts.false_negative / validated
    positive_rate = counts.positive / validated
    if false_positive_rate > threshold.max_false_positive_rate:
        return GATE_BLOCKED_QUALITY_FAILURE, "False-positive rate exceeds threshold"
    if false_negative_rate > threshold.max_false_negative_rate:
        return GATE_BLOCKED_QUALITY_FAILURE, "False-negative rate exceeds threshold"
    if positive_rate < threshold.min_positive_outcome_rate:
        return GATE_BLOCKED_QUALITY_FAILURE, "Positive outcome rate below threshold"
    if threshold.promotion_mode == "advisory_only":
        return GATE_ADVISORY_ONLY, "Evidence passes advisory-only threshold"
    if threshold.promotion_mode == "supervised_eligible":
        return GATE_SUPERVISED_ELIGIBLE, "Evidence passes supervised threshold"
    return GATE_OUTCOME_ELIGIBLE, "Evidence passes outcome threshold but promotion mode is blocked"


def overall_gate_result(summary: dict[str, Any]) -> str:
    groups = summary.get("groups") or []
    if any(group.get("gate_result") == GATE_SAFETY_UNRESOLVED for group in groups):
        return GATE_SAFETY_UNRESOLVED
    if groups:
        if any(group.get("gate_result") == GATE_BLOCKED_QUALITY_FAILURE for group in groups):
            return GATE_BLOCKED_QUALITY_FAILURE
        if any(group.get("gate_result") in {GATE_ADVISORY_ONLY, GATE_SUPERVISED_ELIGIBLE} for group in groups):
            return GATE_OUTCOME_ELIGIBLE
        return GATE_NOT_ENOUGH_EVIDENCE
    if summary.get("excluded_pre_cutover", 0) > 0:
        return GATE_BLOCKED_PRE_CUTOVER
    return GATE_NOT_ENOUGH_EVIDENCE


def counts_to_dict(counts: EvidenceCounts) -> dict[str, int]:
    return {
        "generated": counts.generated,
        "validated": counts.validated,
        "measured_outcomes": counts.measured_outcomes,
        "positive": counts.positive,
        "negative": counts.negative,
        "false_positive": counts.false_positive,
        "false_negative": counts.false_negative,
        "inconclusive": counts.inconclusive,
    }


def threshold_to_dict(threshold: ThresholdConfig) -> dict[str, Any]:
    return {
        "site_id": threshold.site_id,
        "equipment_type": threshold.equipment_type,
        "recommendation_type": threshold.recommendation_type,
        "safety_class": threshold.safety_class,
        "min_validated_recommendations": threshold.min_validated_recommendations,
        "min_measured_outcomes": threshold.min_measured_outcomes,
        "min_fault_prediction_samples": threshold.min_fault_prediction_samples,
        "max_false_positive_rate": threshold.max_false_positive_rate,
        "max_false_negative_rate": threshold.max_false_negative_rate,
        "min_positive_outcome_rate": threshold.min_positive_outcome_rate,
        "min_energy_savings_confidence": threshold.min_energy_savings_confidence,
        "promotion_mode": threshold.promotion_mode,
    }


def get_phase188_outcome_validation_service() -> Phase188OutcomeValidationService:
    return Phase188OutcomeValidationService()
