"""Deterministic, auditable rule-based point classifier.

Phase 162: Semantic Control Foundation — Plan 02.
Applies semantic dictionary rules with weighted evidence aggregation.
Every match is recorded in an EvidenceRecord for full auditability.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any

from app.models.point_classification import (
    BatchClassificationResult,
    EvidenceRecord,
    PointClassification,
)
from app.models.semantic_tag import ClassificationRule, EvidenceSource, SafetyClass, SemanticTag
from app.services.simbiot.classifiers.base_classifier import BasePointClassifier
from app.services.simbiot.classifiers.confidence_calculator import ConfidenceCalculator
from app.services.simbiot.semantic_dictionary import SemanticDictionaryService


class RuleBasedPointClassifier(BasePointClassifier):
    """Deterministic classifier using semantic dictionary rules.

    Decision flow for each point:
    1. Load candidate tags for the point's equipment type
    2. For each tag evaluate every classification rule
    3. Collect matching EvidenceRecords
    4. Calculate confidence via ConfidenceCalculator
    5. Return PointClassification with full evidence trail
    """

    def __init__(self, dictionary_service: SemanticDictionaryService | None = None) -> None:
        self._dict_service = dictionary_service or SemanticDictionaryService()
        self._dict_service.load()

    @property
    def classifier_id(self) -> str:
        return "rule_based_v1"

    # ------------------------------------------------------------------
    # Pattern matching helpers
    # ------------------------------------------------------------------

    def _match_glob(self, text: str, pattern: str) -> bool:
        """Match text against a glob pattern that supports ** and *.

        ** matches any sequence of characters (including path separators).
        * matches any sequence of non-star characters.
        """
        if not text or not pattern:
            return False
        # Convert glob to regex: ** → .*, * → [^*]*
        regex = re.escape(pattern)
        regex = regex.replace(r"\*\*", ".*")
        regex = regex.replace(r"\*", "[^*]*")
        return bool(re.match(regex, text.lower(), re.IGNORECASE))

    def _match_exact_or_contains(self, text: str, pattern: str) -> bool:
        """Match if text equals pattern (case-insensitive) or contains it as a token."""
        if not text or not pattern:
            return False
        text_up = text.upper()
        pattern_up = pattern.upper()
        # Exact match
        if text_up == pattern_up:
            return True
        # Glob pattern (contains wildcard characters)
        if "*" in pattern:
            return self._match_glob(text, pattern)
        # Token match: pattern appears as word-boundary substring
        return bool(re.search(rf"(?<![A-Z0-9]){re.escape(pattern_up)}(?![A-Z0-9])", text_up))

    # ------------------------------------------------------------------
    # Rule evaluation
    # ------------------------------------------------------------------

    def _evaluate_haystack_rule(self, rule: ClassificationRule, point_data: dict[str, Any]) -> EvidenceRecord | None:
        """Evaluate a haystack_id rule against point_data."""
        haystack_id: str = point_data.get("haystack_id") or ""
        if not haystack_id:
            return None
        pattern = rule.pattern or ""
        if not self._match_glob(haystack_id, pattern):
            return None
        return EvidenceRecord(
            source=EvidenceSource.HAYSTACK_ID,
            value_found=haystack_id,
            rule_matched=pattern,
            weight=rule.weight,
            contributed_confidence=rule.weight,
            evidence_description=rule.evidence,
        )

    def _evaluate_point_name_rule(self, rule: ClassificationRule, point_data: dict[str, Any]) -> EvidenceRecord | None:
        """Evaluate a point_name rule against point_data."""
        point_name: str = point_data.get("point_name") or ""
        if not point_name:
            return None
        patterns = rule.patterns or ([] if rule.pattern is None else [rule.pattern])
        matched_pattern: str | None = None
        for p in patterns:
            if self._match_exact_or_contains(point_name, p):
                matched_pattern = p
                break
        if matched_pattern is None:
            return None
        return EvidenceRecord(
            source=EvidenceSource.POINT_NAME,
            value_found=point_name,
            rule_matched=matched_pattern,
            weight=rule.weight,
            contributed_confidence=rule.weight,
            evidence_description=rule.evidence,
        )

    def _evaluate_equipment_type_rule(
        self, rule: ClassificationRule, point_data: dict[str, Any]
    ) -> EvidenceRecord | None:
        """Evaluate an equipment_type rule against point_data."""
        eq_type: str = point_data.get("equipment_type") or ""
        if not eq_type:
            return None
        must_be = rule.must_be or []
        if eq_type.lower() not in [m.lower() for m in must_be]:
            return None
        return EvidenceRecord(
            source=EvidenceSource.EQUIPMENT_TYPE,
            value_found=eq_type,
            rule_matched=",".join(must_be),
            weight=rule.weight,
            contributed_confidence=rule.weight,
            evidence_description=rule.evidence,
        )

    def _evaluate_metadata_rule(self, rule: ClassificationRule, point_data: dict[str, Any]) -> EvidenceRecord | None:
        """Evaluate a metadata rule against point_data['metadata']."""
        metadata: dict = point_data.get("metadata") or {}
        if not metadata or not rule.equipment_context:
            return None
        contains_keys: list[str] = rule.equipment_context.get("contains", [])
        metadata_str = " ".join(str(v) for v in metadata.values()).upper()
        matched = [k for k in contains_keys if k.upper() in metadata_str]
        if not matched:
            return None
        return EvidenceRecord(
            source=EvidenceSource.METADATA,
            value_found=str(matched),
            rule_matched=str(contains_keys),
            weight=rule.weight,
            contributed_confidence=rule.weight,
            evidence_description=rule.evidence,
        )

    def _evaluate_value_pattern_rule(
        self, rule: ClassificationRule, point_data: dict[str, Any]
    ) -> EvidenceRecord | None:
        """Evaluate a value_pattern rule against point_data['current_value']."""
        current_value = point_data.get("current_value")
        if current_value is None:
            return None
        pattern = rule.pattern or ""
        if not self._match_glob(str(current_value), pattern):
            return None
        return EvidenceRecord(
            source=EvidenceSource.VALUE_PATTERN,
            value_found=str(current_value),
            rule_matched=pattern,
            weight=rule.weight,
            contributed_confidence=rule.weight,
            evidence_description=rule.evidence,
        )

    def _evaluate_rule(self, rule: ClassificationRule, point_data: dict[str, Any]) -> EvidenceRecord | None:
        """Dispatch rule evaluation to the appropriate method by source."""
        if rule.source == EvidenceSource.HAYSTACK_ID:
            return self._evaluate_haystack_rule(rule, point_data)
        if rule.source == EvidenceSource.POINT_NAME:
            return self._evaluate_point_name_rule(rule, point_data)
        if rule.source == EvidenceSource.EQUIPMENT_TYPE:
            return self._evaluate_equipment_type_rule(rule, point_data)
        if rule.source == EvidenceSource.METADATA:
            return self._evaluate_metadata_rule(rule, point_data)
        if rule.source == EvidenceSource.VALUE_PATTERN:
            return self._evaluate_value_pattern_rule(rule, point_data)
        return None

    # ------------------------------------------------------------------
    # Negative sample check
    # ------------------------------------------------------------------

    def _fails_negative_check(self, tag: SemanticTag, point_data: dict[str, Any]) -> bool:
        """Return True if any negative sample is an exact match for the point name."""
        point_name: str = (point_data.get("point_name") or "").upper()
        return point_name in {s.upper() for s in tag.negative_samples}

    # ------------------------------------------------------------------
    # Safety class helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _highest_safety_class(
        classes: list[SafetyClass],
    ) -> SafetyClass | None:
        """Return the most restrictive safety class from a list."""
        priority = {SafetyClass.HIGH: 3, SafetyClass.MEDIUM: 2, SafetyClass.LOW: 1}
        if not classes:
            return None
        return max(classes, key=lambda c: priority.get(c, 0))

    # ------------------------------------------------------------------
    # Core classification
    # ------------------------------------------------------------------

    async def classify_point(self, point_data: dict[str, Any]) -> PointClassification:
        """Classify a single point and return a fully populated PointClassification."""
        point_id: str = point_data.get("point_id", "unknown")
        site_id: str = point_data.get("site_id", "")
        equipment_type: str = point_data.get("equipment_type", "")
        data_quality_score: float = float(point_data.get("data_quality_score", 1.0))

        # 1. Get all candidate tags (all tags when equipment_type is unknown; filtered otherwise)
        if equipment_type:
            candidate_tags = self._dict_service.find_by_equipment_type(equipment_type)
        else:
            all_tag_names = self._dict_service.list_tags()
            candidate_tags = [self._dict_service.get_tag(t) for t in all_tag_names]
            candidate_tags = [t for t in candidate_tags if t is not None]

        best_tag: str | None = None
        best_confidence: float = 0.0
        best_evidence: list[EvidenceRecord] = []
        best_safety_class: SafetyClass | None = None
        best_control_envelope: dict | None = None
        all_matched_tags: list[str] = []
        safety_classes: list[SafetyClass] = []

        for tag in candidate_tags:
            # Negative sample guard
            if self._fails_negative_check(tag, point_data):
                continue

            evidence: list[EvidenceRecord] = []
            for rule in tag.classification_rules:
                record = self._evaluate_rule(rule, point_data)
                if record is not None:
                    evidence.append(record)

            if not evidence:
                continue

            # 2. Calculate confidence
            required = tag.required_evidence if tag.required_evidence > 0 else 1
            confidence = ConfidenceCalculator.calculate_confidence(evidence, required)

            if confidence > 0.0:
                all_matched_tags.append(tag.tag)
                safety_classes.append(tag.safety_class)

            if confidence > best_confidence:
                best_confidence = confidence
                best_tag = tag.tag
                best_evidence = list(evidence)
                best_safety_class = tag.safety_class
                if tag.control_envelope:
                    best_control_envelope = tag.control_envelope.model_dump()

        matched_tags = [best_tag] if best_tag else []

        return PointClassification(
            point_id=point_id,
            device_id=point_data.get("device_id"),
            site_id=site_id,
            equipment_type=equipment_type,
            semantic_tags=matched_tags,
            confidence_score=best_confidence,
            data_quality_score=data_quality_score,
            classification_date=datetime.utcnow(),
            status="pending_review",
            evidence_records=best_evidence,
            highest_safety_class=best_safety_class,
            control_envelope=best_control_envelope,
            validation_passed=best_confidence >= 0.4,
            current_value=point_data.get("current_value"),
        )

    async def classify_equipment_batch(
        self,
        equipment_id: str,
        points: list[dict[str, Any]],
    ) -> BatchClassificationResult:
        """Classify all points for one equipment and aggregate statistics."""
        start_ms = int(time.monotonic() * 1000)

        # Ensure site_id is propagated to each point if missing
        site_id: str = ""
        for p in points:
            sid = p.get("site_id", "")
            if sid:
                site_id = sid
                break

        classified: list[PointClassification] = []
        for point_data in points:
            result = await self.classify_point(point_data)
            classified.append(result)

        # Statistics
        high = sum(1 for p in classified if p.confidence_score >= 0.7)
        medium = sum(1 for p in classified if 0.4 <= p.confidence_score < 0.7)
        low = sum(1 for p in classified if p.confidence_score < 0.4)
        review = sum(1 for p in classified if p.status == "pending_review")

        elapsed_ms = int(time.monotonic() * 1000) - start_ms

        return BatchClassificationResult(
            equipment_id=equipment_id,
            site_id=site_id,
            classified_points=classified,
            total_points=len(classified),
            high_confidence_count=high,
            medium_confidence_count=medium,
            low_confidence_count=low,
            requires_review_count=review,
            processing_time_ms=elapsed_ms,
        )
