"""Progression Engine Service — Trust Ladder Foundation.

Tracks recommendation outcomes and computes per-class trust readiness.
Phases A (schema+service), B (tier routing), and C (demotion detection).

Core responsibilities:
  1. Record every recommendation's predicted vs actual outcome (recommendation_validations)
  2. Compute per-class rolling accuracy (recommendation_class_readiness)
  3. Surface readiness for trust-level gates (Phase B+)
  4. Detect demotion conditions and apply demotions (Phase C+)
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# Validation class mapping: action_type → canonical class name
_VALIDATION_CLASS_MAP: dict[str, str] = {
    "hvac_setpoint_change": "hvac_setpoint_change",
    "setpoint_adjust": "hvac_setpoint_change",
    "cooling_setpoint_adjust": "hvac_setpoint_change",
    "heating_setpoint_adjust": "hvac_setpoint_change",
    "hvac_schedule_correction": "hvac_schedule_correction",
    "schedule_correction": "hvac_schedule_correction",
    "zone_shutdown": "zone_shutdown",
    "hvac_zone_shutdown": "zone_shutdown",
    "lighting_dim": "lighting_dim",
    "dali_level_change": "lighting_dim",
    "chiller_setpoint_adjust": "chiller_setpoint_adjust",
    "chiller_setpoint_change": "chiller_setpoint_adjust",
    "maintenance_inspection": "maintenance_inspection",
    "maintenance_check": "maintenance_inspection",
    "energy_optimization": "energy_optimization",
    "demand_response": "demand_response",
    "load_shedding": "demand_response",
    "peak_shaving": "demand_response",
    "bess_dispatch": "bess_dispatch",
    "hvac_mode_change": "hvac_mode_change",
    "fan_speed_change": "fan_speed_change",
    "valve_adjust": "valve_adjust",
    "coordinated_optimization": "coordinated_optimization",
}

# Default class for unmapped action_types
_DEFAULT_CLASS = "other"

# Rolling accuracy windows
_ACCURACY_WINDOW_7D_DAYS = 7
_ACCURACY_WINDOW_30D_DAYS = 30
_MAX_VALIDATIONS_FOR_WINDOW = 100

# Accuracy category thresholds
_ACCURACY_CORRECT = 0.85
_ACCURACY_CLOSE = 0.70
_ACCURACY_THRESHOLD = 0.50


class ProgressionEngineService:
    """Tracks recommendation outcomes and computes per-class trust readiness.

    Singleton accessed via get_progression_engine_service().
    """

    _instance: "ProgressionEngineService | None" = None

    def __new__(cls) -> "ProgressionEngineService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ------------------------------------------------------------------
    # Public API — 5 core methods
    # ------------------------------------------------------------------

    async def record_validation(
        self,
        recommendation_id: str,
        operator_feedback: str | None = None,
        operator_note: str | None = None,
        actual_delta: dict[str, Any] | None = None,
        outcome_status: str | None = None,
    ) -> dict[str, Any]:
        """Record a recommendation validation outcome.

        Called when:
        - Recommendation is approved/rejected (operator_feedback set, actual_delta=None)
        - Recommendation is verified post-execution (actual_delta set from M&V)

        Creates or updates a recommendation_validations row, computes outcome_accuracy,
        and updates recommendation_class_readiness for the validation_class.

        Args:
            recommendation_id: UUID of the recommendation.
            operator_feedback: "accepted", "rejected", or None.
            operator_note: Free-text note from operator.
            actual_delta: Dict of measured deltas from M&V (e.g., {"temp_c": -1.8}).
            outcome_status: Outcome status from recommendation lifecycle.

        Returns:
            Validation record as dict with outcome_accuracy.
        """
        sb = get_supabase_client()

        # Fetch recommendation metadata
        rec_resp = (
            sb.table("recommendations")
            .select(
                "site_id, action_type, target_equipment, expected_impact, predicted_delta, confidence_score, status"
            )
            .eq("id", recommendation_id)
            .limit(1)
            .execute()
        )
        if not rec_resp.data:
            logger.warning("record_validation: recommendation %s not found", recommendation_id)
            return {"error": "recommendation_not_found"}

        rec = rec_resp.data[0]
        site_id = rec.get("site_id", "")
        action_type = rec.get("action_type", "")
        equipment_code = rec.get("target_equipment", "")
        predicted_delta = rec.get("predicted_delta") or rec.get("expected_impact") or {}
        predicted_confidence = rec.get("confidence_score")
        rec_status = rec.get("status", "")

        outcome_status = outcome_status or rec_status or "unknown"
        validation_class = self._compute_validation_class(action_type)

        # Check if a validation row already exists (idempotency)
        existing_resp = (
            sb.table("recommendation_validations")
            .select("id, outcome_accuracy, validation_status")
            .eq("recommendation_id", recommendation_id)
            .limit(1)
            .execute()
        )

        outcome_accuracy = None
        accuracy_category = None
        validated_at = None

        # Compute accuracy if we have actual_delta (M&V verify path)
        if actual_delta is not None:
            outcome_accuracy = self._compute_outcome_accuracy(_safe_dict(predicted_delta), _safe_dict(actual_delta))
            accuracy_category = self._accuracy_category(outcome_accuracy) if outcome_accuracy is not None else None
            validated_at = datetime.now(UTC).isoformat()

        validation_data = {
            "recommendation_id": recommendation_id,
            "site_id": site_id,
            "action_type": action_type,
            "equipment_code": equipment_code,
            "predicted_delta": predicted_delta,
            "predicted_confidence": predicted_confidence,
            "actual_delta": actual_delta,
            "outcome_accuracy": outcome_accuracy,
            "operator_feedback": operator_feedback,
            "operator_note": operator_note,
            "validation_class": validation_class,
            "outcome_status": outcome_status,
            "accuracy_category": accuracy_category,
            "validated_at": validated_at,
            "validation_status": self._resolve_validation_status(operator_feedback, actual_delta),
        }

        if existing_resp.data:
            # Update existing validation row
            existing_id = existing_resp.data[0]["id"]
            # Don't overwrite earlier data with None
            update = {k: v for k, v in validation_data.items() if v is not None}
            update["validation_status"] = validation_data["validation_status"]
            if actual_delta is not None:
                update["actual_delta"] = actual_delta
                update["outcome_accuracy"] = outcome_accuracy
                update["accuracy_category"] = accuracy_category
                update["validated_at"] = validated_at
            sb.table("recommendation_validations").update(update).eq("id", existing_id).execute()
            validation_data["id"] = existing_id
        else:
            # Insert new validation row
            insert_resp = sb.table("recommendation_validations").insert(validation_data).execute()
            if insert_resp.data:
                validation_data["id"] = insert_resp.data[0]["id"]

        # Recompute class readiness
        await self._recompute_class_readiness(site_id, validation_class)

        logger.info(
            "record_validation: %s class=%s acc=%s feedback=%s",
            recommendation_id,
            validation_class,
            outcome_accuracy,
            operator_feedback,
        )

        return {
            "validation_class": validation_class,
            "outcome_accuracy": outcome_accuracy,
            "accuracy_category": accuracy_category,
            "operator_feedback": operator_feedback,
        }

    async def get_class_readiness(self, site_id: str, class_name: str) -> dict[str, Any]:
        """Return current readiness for a single recommendation class.

        Args:
            site_id: Site identifier (e.g., "site-002").
            class_name: Recommendation class name (e.g., "hvac_setpoint_change").

        Returns:
            Dict with class readiness fields, or empty defaults if no data.
        """
        sb = get_supabase_client()
        resp = (
            sb.table("recommendation_class_readiness")
            .select("*")
            .eq("site_id", site_id)
            .eq("class_name", class_name)
            .limit(1)
            .execute()
        )
        if resp.data:
            row = resp.data[0]
            return {
                "site_id": row["site_id"],
                "class_name": row["class_name"],
                "current_trust_level": row.get("current_trust_level", 1),
                "evidence_count": row.get("evidence_count", 0),
                "accuracy_pct_7d": row.get("accuracy_pct_7d"),
                "accuracy_pct_30d": row.get("accuracy_pct_30d"),
                "consecutive_successes": row.get("consecutive_successes", 0),
                "consecutive_failures": row.get("consecutive_failures", 0),
                "last_validation_at": row.get("last_validation_at"),
                "last_demotion_at": row.get("last_demotion_at"),
                "demotion_reason": row.get("demotion_reason"),
                "operator_hold_until": row.get("operator_hold_until"),
                "operator_override_level": row.get("operator_override_level"),
            }

        # Empty defaults for a class with zero evidence
        return {
            "site_id": site_id,
            "class_name": class_name,
            "current_trust_level": 1,
            "evidence_count": 0,
            "accuracy_pct_7d": None,
            "accuracy_pct_30d": None,
            "consecutive_successes": 0,
            "consecutive_failures": 0,
            "last_validation_at": None,
            "last_demotion_at": None,
            "demotion_reason": None,
            "operator_hold_until": None,
            "operator_override_level": None,
        }

    async def get_site_trust_summary(self, site_id: str) -> dict[str, Any]:
        """Return full site trust dashboard data with readiness gates.

        Aggregates all class readiness rows for a site, computes
        the effective site-level trust level, and evaluates gates
        for progression to the next level.

        Args:
            site_id: Site identifier.

        Returns:
            Dict with site-level summary, per-class readiness list,
            readiness score, and gates for next level.
        """
        sb = get_supabase_client()
        resp = sb.table("recommendation_class_readiness").select("*").eq("site_id", site_id).execute()

        now = datetime.now(UTC)

        classes = []
        total_evidence = 0
        accuracy_values_7d: list[float] = []
        accuracy_values_30d: list[float] = []
        min_trust_level = 3
        any_recent_demotion = False

        for row in resp.data or []:
            level = row.get("current_trust_level", 1)
            acc_7d = row.get("accuracy_pct_7d")
            acc_30d = row.get("accuracy_pct_30d")
            evidence = row.get("evidence_count", 0)
            last_demotion_at = row.get("last_demotion_at")

            # Detect recent demotion (within last 7 days)
            if last_demotion_at:
                try:
                    ld = last_demotion_at
                    if isinstance(ld, str):
                        ld = datetime.fromisoformat(ld.replace("Z", "+00:00"))
                    if (now - ld).total_seconds() < 7 * 86400:
                        any_recent_demotion = True
                except (ValueError, TypeError):
                    pass

            classes.append(
                {
                    "class_name": row["class_name"],
                    "current_trust_level": level,
                    "evidence_count": evidence,
                    "accuracy_pct_7d": acc_7d,
                    "accuracy_pct_30d": acc_30d,
                    "consecutive_successes": row.get("consecutive_successes", 0),
                    "consecutive_failures": row.get("consecutive_failures", 0),
                    "last_validation_at": row.get("last_validation_at"),
                    "last_demotion_at": last_demotion_at,
                    "demotion_reason": row.get("demotion_reason"),
                }
            )
            total_evidence += evidence
            if acc_7d is not None:
                accuracy_values_7d.append(acc_7d)
            if acc_30d is not None:
                accuracy_values_30d.append(acc_30d)
            if level < min_trust_level:
                min_trust_level = level

        # Site-level trust level = minimum of all class levels
        site_trust_level = min_trust_level if classes else 1
        next_level = min(site_trust_level + 1, 3)

        # Weighted readiness score = average of 30d accuracies
        readiness_score = _safe_mean(accuracy_values_30d) if accuracy_values_30d else 0.0

        # Evaluate gates for next level
        gates: dict[str, dict[str, Any]] = {}
        gate_defs = {
            1: {"recs": 200, "acc": 85.0, "classes": 5},
            2: {"recs": 500, "acc": 90.0, "classes": 8},
        }

        if site_trust_level in gate_defs:
            g = gate_defs[site_trust_level]
            gates["cumulative_validated_recs"] = {
                "required": g["recs"],
                "current": total_evidence,
                "pass": total_evidence >= g["recs"],
            }
            readiness = readiness_score or 0.0
            gates["accuracy_30d_weighted"] = {
                "required": g["acc"],
                "current": round(readiness, 1),
                "pass": readiness >= g["acc"],
            }
            gates["distinct_classes"] = {
                "required": g["classes"],
                "current": len(classes),
                "pass": len(classes) >= g["classes"],
            }
            gates["no_recent_demotions"] = {
                "required": True,
                "current": not any_recent_demotion,
                "pass": not any_recent_demotion,
            }
            gates["operator_approval"] = {
                "required": True,
                "current": None,
                "pass": False,
            }

        return {
            "site_id": site_id,
            "current_level": site_trust_level,
            "next_level": next_level,
            "readiness_score": round(readiness_score / 100.0, 3) if readiness_score else 0.0,
            "total_evidence_count": total_evidence,
            "accuracy_pct_7d_weighted": _safe_mean(accuracy_values_7d),
            "accuracy_pct_30d_weighted": round(readiness_score, 1) if readiness_score else None,
            "class_count": len(classes),
            "gates_for_next_level": gates if gates else None,
            "classes": classes,
            "evaluated_at": now.isoformat(),
        }

    async def apply_overrides(self, site_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
        """Apply operator overrides with audit logging.

        Supported overrides:
            hold_until: ISO date string to hold site at current level.
            class_overrides: dict of {class_name: override_level}.

        Args:
            site_id: Site identifier.
            overrides: Dict with override fields.

        Returns:
            Dict listing applied overrides.
        """
        sb = get_supabase_client()
        applied = []

        hold_until = overrides.get("hold_until")
        if hold_until:
            sb.table("recommendation_class_readiness").update(
                {
                    "operator_hold_until": hold_until,
                }
            ).eq("site_id", site_id).execute()
            applied.append({"type": "site_hold_until", "value": hold_until})

        class_overrides = overrides.get("class_overrides", {})
        for class_name, override_level in class_overrides.items():
            # Upsert — ensure the row exists first
            existing = (
                sb.table("recommendation_class_readiness")
                .select("id")
                .eq("site_id", site_id)
                .eq("class_name", class_name)
                .limit(1)
                .execute()
            )
            if existing.data:
                sb.table("recommendation_class_readiness").update(
                    {
                        "operator_override_level": override_level,
                    }
                ).eq("site_id", site_id).eq("class_name", class_name).execute()
            else:
                sb.table("recommendation_class_readiness").insert(
                    {
                        "site_id": site_id,
                        "class_name": class_name,
                        "operator_override_level": override_level,
                    }
                ).execute()
            applied.append({"type": "class_override", "class_name": class_name, "level": override_level})

        logger.info("apply_overrides: site=%s applied=%s", site_id, applied)
        return {"site_id": site_id, "applied": applied}

    async def check_demotion_triggers(self, site_id: str) -> list[dict[str, Any]]:
        """Check all classes for demotion conditions.

        Phase C: Full demotion detection with 4 trigger types.

        Trigger 1 — Accuracy drop:
          Level 3 class with accuracy_pct_30d < 0.90 → Level 2
          Level 2 class with accuracy_pct_30d < 0.85 → Level 1

        Trigger 2 — Consecutive failures:
          3+ consecutive wrong_direction/no_impact validations → Level 1

        Trigger 3 — Equipment damage (site-wide):
          Any quality_exception with outcome_status='equipment_damage' in last 7 days
          → All classes demoted to Level 1

        Trigger 4 — Comfort violation (class-specific):
          Any validation with outcome_status='comfort_violation' in last 24h
          → That class demoted to Level 1

        Demotion cool-off: classes demoted within the last 7 days are skipped.

        Args:
            site_id: Site identifier.

        Returns:
            List of demotion events with class_name, current_level, new_level,
            trigger, and evidence. Empty list if no demotions needed.
        """
        sb = get_supabase_client()
        now = datetime.now(UTC)

        # Fetch all classes at this site
        resp = sb.table("recommendation_class_readiness").select("*").eq("site_id", site_id).execute()

        demotions: list[dict[str, Any]] = []

        # Pre-fetch site-wide equipment damage count (7d window)
        damage_count_resp = (
            sb.table("recommendation_validations")
            .select("id", count="exact")
            .eq("site_id", site_id)
            .eq("outcome_status", "equipment_damage")
            .gte("created_at", (now - timedelta(days=7)).isoformat())
            .execute()
        )
        site_damage_count = damage_count_resp.count or 0

        for row in resp.data or []:
            class_name = row["class_name"]
            current_level = row.get("current_trust_level", 1)
            accuracy_pct_30d = row.get("accuracy_pct_30d")
            consecutive_failures = row.get("consecutive_failures", 0)
            last_demotion_at = row.get("last_demotion_at")

            # Cool-off: skip if demoted within last 7 days
            if last_demotion_at:
                try:
                    last_dt = last_demotion_at
                    if isinstance(last_dt, str):
                        last_dt = datetime.fromisoformat(last_dt.replace("Z", "+00:00"))
                    days_since = (now - last_dt).total_seconds() / 86400
                    if days_since < 7:
                        continue
                except (ValueError, TypeError):
                    pass

            trigger_result = None

            # Trigger 1: Accuracy drop
            if accuracy_pct_30d is not None:
                if current_level >= 3 and accuracy_pct_30d < 90.0:
                    trigger_result = ("accuracy_drop_l3", f"accuracy {accuracy_pct_30d:.1f}% < 90%")
                elif current_level >= 2 and accuracy_pct_30d < 85.0:
                    trigger_result = ("accuracy_drop_l2", f"accuracy {accuracy_pct_30d:.1f}% < 85%")

            # Trigger 2: Consecutive failures (overrides accuracy drop check)
            if consecutive_failures >= 3:
                trigger_result = ("consecutive_failures", f"{consecutive_failures} consecutive failures")

            # Trigger 3: Equipment damage (site-wide)
            if site_damage_count > 0:
                trigger_result = ("equipment_damage", f"{site_damage_count} equipment damage reports in last 7 days")

            # Trigger 4: Comfort violations for this class (24h window)
            comfort_resp = (
                sb.table("recommendation_validations")
                .select("id", count="exact")
                .eq("site_id", site_id)
                .eq("validation_class", class_name)
                .eq("outcome_status", "comfort_violation")
                .gte("created_at", (now - timedelta(hours=24)).isoformat())
                .execute()
            )
            comfort_count = comfort_resp.count or 0
            if comfort_count > 0:
                trigger_result = ("comfort_violation", f"{comfort_count} comfort violations in last 24h")

            if trigger_result:
                trigger_type, evidence = trigger_result
                # Equipment damage and comfort violations drop directly to Level 1
                if trigger_type in ("equipment_damage", "comfort_violation", "consecutive_failures"):
                    new_level = 1
                else:
                    new_level = max(1, current_level - 1)

                demotions.append(
                    {
                        "class_name": class_name,
                        "current_level": current_level,
                        "new_level": new_level,
                        "trigger": trigger_type,
                        "evidence": evidence,
                    }
                )

        if demotions:
            logger.warning(
                "check_demotion_triggers: site=%s demotions=%s",
                site_id,
                [d["class_name"] for d in demotions],
            )

        return demotions

    async def apply_demotions(self, site_id: str, demotions: list[dict[str, Any]]) -> list[str]:
        """Apply a list of demotion decisions.

        For each demotion:
        1. Updates current_trust_level in recommendation_class_readiness
        2. Sets last_demotion_at and demotion_reason
        3. Resets consecutive_failures
        4. Records audit event
        5. Sends Telegram alert

        Args:
            site_id: Site identifier.
            demotions: List of demotion dicts from check_demotion_triggers().

        Returns:
            List of Telegram message IDs sent (empty if no alerts configured).
        """
        sb = get_supabase_client()
        now = datetime.now(UTC).isoformat()
        alert_ids: list[str] = []

        for demotion in demotions:
            class_name = demotion["class_name"]
            new_level = demotion["new_level"]
            trigger = demotion.get("trigger", "unknown")
            evidence = demotion.get("evidence", "")

            # 1. Update class readiness
            sb.table("recommendation_class_readiness").update(
                {
                    "current_trust_level": new_level,
                    "last_demotion_at": now,
                    "demotion_reason": f"{trigger}: {evidence}",
                    "consecutive_failures": 0,
                    "updated_at": now,
                }
            ).eq("site_id", site_id).eq("class_name", class_name).execute()

            # 2. Record audit event — write to phase_transition_log
            try:
                sb.table("phase_transition_log").insert(
                    {
                        "site_id": site_id,
                        "from_phase": f"level_{demotion['current_level']}",
                        "to_phase": f"level_{new_level}",
                        "changed_by": "system",
                        "reason": f"auto_demotion class:{class_name} trigger:{trigger} {evidence}",
                    }
                ).execute()
            except Exception as audit_err:
                logger.warning("apply_demotions: audit logging failed for %s: %s", class_name, audit_err)

            # 3. Send Telegram alert (best-effort)
            try:
                from app.services.notification_service import NotificationService

                notification = NotificationService()
                alert_text = (
                    f"🚨 SENTINEL: {site_id} — {class_name} demoted to Level {new_level}\n"
                    f"Trigger: {trigger}\n"
                    f"Evidence: {evidence}\n"
                    f"Action: Pending {class_name} recommendations re-routed to approval queue."
                )
                await notification.send_alert_direct(
                    title=f"SENTINEL Class Demoted: {class_name}",
                    body=alert_text,
                    alert_level="warning",
                )
                alert_ids.append(alert_text[:40])  # best-effort tracking id
            except Exception as alert_err:
                logger.warning("apply_demotions: Telegram alert failed for %s: %s", class_name, alert_err)

            logger.info(
                "apply_demotions: %s %s level %s→%s (%s)",
                site_id,
                class_name,
                demotion["current_level"],
                new_level,
                trigger,
            )

        return alert_ids

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_validation_class(self, action_type: str) -> str:
        """Derive canonical validation_class from action_type.

        Normalizes varied action_type values into standard class names
        for consistent per-class readiness tracking.
        """
        normalized = action_type.strip().lower()
        return _VALIDATION_CLASS_MAP.get(normalized, _DEFAULT_CLASS)

    def _compute_outcome_accuracy(
        self,
        predicted_delta: dict[str, Any],
        actual_delta: dict[str, Any],
        epsilon: float = 0.01,
    ) -> float | None:
        """Compute outcome accuracy from predicted vs actual deltas.

        Formula: 1 - abs(pred - actual) / max(abs(pred), abs(actual), epsilon)
        Clipped to [0, 1].

        For non-quantitative recs (no matching keys), returns None.
        Operator satisfaction is used instead when applicable.
        """
        if not predicted_delta or not actual_delta:
            return None

        diffs: list[float] = []
        for key in predicted_delta:
            if key not in actual_delta:
                continue
            pred_val = predicted_delta[key]
            actual_val = actual_delta[key]
            if not isinstance(pred_val, (int, float)) or not isinstance(actual_val, (int, float)):
                continue
            if pred_val == 0 and actual_val == 0:
                diffs.append(1.0)
            else:
                denominator = max(abs(pred_val), abs(actual_val), epsilon)
                diff = 1.0 - (abs(pred_val - actual_val) / denominator)
                diffs.append(max(0.0, min(1.0, diff)))

        return sum(diffs) / len(diffs) if diffs else None

    def _accuracy_category(self, accuracy: float) -> str:
        """Classify an accuracy score into a human-readable category.

        Thresholds:
            > 0.85  → "correct"
            0.70-0.85 → "close"
            0.50-0.70 → "under_predicted"
            < 0.50  → "wrong_direction"
            None    → "unscored"
        """
        if accuracy is None:
            return "unscored"
        if accuracy > _ACCURACY_CORRECT:
            return "correct"
        if accuracy >= _ACCURACY_CLOSE:
            return "close"
        if accuracy >= _ACCURACY_THRESHOLD:
            return "under_predicted"
        return "wrong_direction"

    async def _recompute_class_readiness(self, site_id: str, class_name: str) -> None:
        """Recalculate rolling accuracy and evidence count for a class.

        Queries recent validated recommendations for the class and
        recomputes 7-day and 30-day rolling accuracy windows.

        Args:
            site_id: Site identifier.
            class_name: Class to recompute.
        """
        sb = get_supabase_client()
        now = datetime.now(UTC)

        # Fetch recent validations for this site+class
        resp = (
            sb.table("recommendation_validations")
            .select("outcome_accuracy, operator_feedback, validated_at, created_at")
            .eq("site_id", site_id)
            .eq("validation_class", class_name)
            .order("validated_at", desc=True)
            .limit(_MAX_VALIDATIONS_FOR_WINDOW)
            .execute()
        )

        rows = resp.data or []
        if not rows:
            # No validations yet — class exists but has zero evidence
            self._upsert_class_readiness(
                sb,
                site_id,
                class_name,
                {
                    "evidence_count": 0,
                    "accuracy_pct_7d": None,
                    "accuracy_pct_30d": None,
                    "consecutive_successes": 0,
                    "consecutive_failures": 0,
                    "last_validation_at": None,
                },
            )
            return

        # Compute evidence count (valid rows with outcome_accuracy)
        evidence_rows = [r for r in rows if r.get("outcome_accuracy") is not None]
        evidence_count = len(evidence_rows)

        # Seven-day window
        cutoff_7d = (now - timedelta(days=_ACCURACY_WINDOW_7D_DAYS)).isoformat()
        window_7d = [
            r["outcome_accuracy"]
            for r in evidence_rows
            if (r.get("validated_at") or r.get("created_at") or "") >= cutoff_7d
        ]
        accuracy_pct_7d = (_safe_mean(window_7d) or 0.0) * 100 if window_7d else None

        # Thirty-day window
        cutoff_30d = (now - timedelta(days=_ACCURACY_WINDOW_30D_DAYS)).isoformat()
        window_30d = [
            r["outcome_accuracy"]
            for r in evidence_rows
            if (r.get("validated_at") or r.get("created_at") or "") >= cutoff_30d
        ]
        accuracy_pct_30d = (_safe_mean(window_30d) or 0.0) * 100 if window_30d else None

        # Consecutive tracking: count trailing successes/failures from most recent rows
        consecutive_successes = 0
        consecutive_failures = 0
        in_run = None
        for r in rows:
            acc = r.get("outcome_accuracy")
            if acc is None:
                continue
            cat = self._accuracy_category(acc)
            is_success = cat in ("correct", "close")
            if in_run is None:
                in_run = is_success
            if is_success == in_run:
                if is_success:
                    consecutive_successes += 1
                else:
                    consecutive_failures += 1
            else:
                break  # Run ended

        # Last validation timestamp
        last_validation_at = None
        for r in rows:
            ts = r.get("validated_at") or r.get("created_at")
            if ts:
                last_validation_at = ts
                break

        self._upsert_class_readiness(
            sb,
            site_id,
            class_name,
            {
                "evidence_count": evidence_count,
                "accuracy_pct_7d": accuracy_pct_7d,
                "accuracy_pct_30d": accuracy_pct_30d,
                "consecutive_successes": consecutive_successes,
                "consecutive_failures": consecutive_failures,
                "last_validation_at": last_validation_at,
            },
        )

    @staticmethod
    def _resolve_validation_status(
        operator_feedback: str | None,
        actual_delta: dict | None,
    ) -> str:
        """Determine validation_status from available data."""
        if actual_delta is not None and operator_feedback is not None:
            return "validated"
        if actual_delta is not None:
            return "pending_operator"
        if operator_feedback is not None:
            return "pending_telemetry"
        return "pending_operator"

    @staticmethod
    def _upsert_class_readiness(sb, site_id: str, class_name: str, data: dict[str, Any]) -> None:
        """Insert or update a recommendation_class_readiness row."""
        now_val = datetime.now(UTC).isoformat()
        data["site_id"] = site_id
        data["class_name"] = class_name
        data["updated_at"] = now_val

        existing = (
            sb.table("recommendation_class_readiness")
            .select("id")
            .eq("site_id", site_id)
            .eq("class_name", class_name)
            .limit(1)
            .execute()
        )

        if existing.data:
            data.pop("site_id", None)
            data.pop("class_name", None)
            data.pop("created_at", None)
            sb.table("recommendation_class_readiness").update(data).eq("id", existing.data[0]["id"]).execute()
        else:
            data["created_at"] = now_val
            sb.table("recommendation_class_readiness").insert(data).execute()


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_service: ProgressionEngineService | None = None


def get_progression_engine_service() -> ProgressionEngineService:
    """Get or create the ProgressionEngineService singleton."""
    global _service
    if _service is None:
        _service = ProgressionEngineService()
    return _service


# ------------------------------------------------------------------
# Utility helpers
# ------------------------------------------------------------------


def _safe_dict(value: Any) -> dict[str, Any]:
    """Coerce a value to a dict, safely handling None and non-dict types."""
    if isinstance(value, dict):
        return value
    return {}


def _safe_mean(values: list[float]) -> float | None:
    """Compute mean of a list, returning None for empty lists."""
    if not values:
        return None
    return sum(values) / len(values)
