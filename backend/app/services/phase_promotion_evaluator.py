"""Trust Ladder phase readiness evaluator.

Evaluates whether a site meets all gates for its next onboarding phase
and surfaces readiness to human operators. Never calls the promotion API
itself — operators make the final decision and flip the phase manually.
"""

import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta, timezone

logger = logging.getLogger("sentinel.phase_promotion")


@dataclass
class GateResult:
    gate: str
    passed: bool
    value: float | int | bool | str | None = None
    threshold: float | int | None = None
    reason: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PromotionResult:
    eligible: bool
    promoted: bool = False
    from_phase: str | None = None
    to_phase: str | None = None
    reason: str | None = None
    gates: list[GateResult] = field(default_factory=list)
    computed_at: str | None = None
    trust_confidence: float | None = None
    trust_breakdown: dict | None = None
    equipment_findings: list[dict] = field(default_factory=list)

    def to_readiness_dict(self) -> dict:
        """Structured, explainable readiness breakdown (AC-1).

        Never a bare eligible flag — every result carries satisfied /
        not_satisfied lists with values, thresholds, and reasons.
        """
        result: dict = {
            "eligible": self.eligible,
            "current_mode": self.from_phase,
            "eligible_mode": self.to_phase if self.eligible else None,
            "recommended_next_mode": self.to_phase,
            "reason": self.reason,
            "computed_at": self.computed_at,
            "satisfied": [g.to_dict() for g in self.gates if g.passed],
            "not_satisfied": [g.to_dict() for g in self.gates if not g.passed],
        }

        # Add trust metrics if available (Phase 240 M2.3 drift integration)
        if self.trust_confidence is not None:
            result["trust_confidence"] = self.trust_confidence
        if self.trust_breakdown is not None:
            result["trust_breakdown"] = self.trust_breakdown
        if self.equipment_findings:
            result["equipment_findings"] = self.equipment_findings

        return result


class PhasePromotionEvaluator:
    """Evaluates Trust Ladder gates and surfaces readiness to operators.

    The evaluator assesses whether a site has met all gates for its next
    onboarding phase and sets a readiness flag. Human operators make the
    final decision and flip the phase manually — this class never calls
    the promotion API.
    """

    PROMOTION_GATES: dict[str, dict] = {
        "commissioning": {
            "target": "shadow_live",
            "gates": [
                "hours_since_created >= 24",
                "bridge_polls_successful >= 50",
                "data_quality_score >= 0.7",
            ],
        },
        "shadow_live": {
            "target": "advisory",
            "gates": [
                "ml_hours_ingested >= 72",
                "anomaly_scores_writing",
                "bridge_connected",
            ],
        },
        "advisory": {
            "target": "supervised",
            "gates": [
                "ml_hours_ingested >= 500",
                "recommendations_acknowledged >= 3",
                "control_modules_active_for_controllable_equipment",
                "write_capable_adapter_configured",
                "bridge_write_endpoint_available",
                "verified_writable_control_points >= 10",
                "controllable_equipment_control_coverage >= 0.75",
                "no_safety_violations_30d",
            ],
        },
        "supervised": {
            "target": "automatic",
            "gates": [
                "ml_hours_ingested >= 2000",
                "approval_accuracy >= 0.85",
                "false_positive_rate <= 0.10",
                "recommendations_approved >= 30",
                "no_safety_violations_7d",
                "write_capable_adapter_enabled",
                "human_approved_autonomous",
            ],
        },
    }

    def __init__(self):
        self._internal_key: str | None = None
        self._backend_url: str | None = None

    async def _ensure_config(self) -> None:
        """Load internal service key and backend URL from settings (idempotent)."""
        if self._internal_key and self._backend_url:
            return
        from app.config.settings import settings

        self._internal_key = getattr(settings, "internal_service_key", "") or ""
        self._backend_url = getattr(settings, "backend_base_url", "http://127.0.0.1:9095") or "http://127.0.0.1:9095"

    async def evaluate_all_sites(self) -> list[PromotionResult]:
        """Evaluate every site for promotion eligibility. Called by scheduler."""
        from app.config.settings import settings
        from supabase import create_client

        client = create_client(settings.supabase_url, settings.supabase_service_role_key)
        # Invariant I-2 scope: commercial sites only. res-* sites are a separate
        # residential product line governed by residential onboarding.
        rows = client.table("sites").select("code, onboarding_phase").like("code", "site-%").execute()
        if not rows.data:
            logger.warning("No sites found for promotion evaluation")
            return []

        results: list[PromotionResult] = []
        for site in rows.data:
            code = site["code"]
            phase = site.get("onboarding_phase", "commissioning")
            normalised = phase.lower().replace(" ", "_")
            if normalised == "auto":
                normalised = "automatic"
            if normalised not in self.PROMOTION_GATES:
                continue
            try:
                result = await self.evaluate_site(code, normalised)
                results.append(result)
            except Exception as e:
                logger.error("Promotion evaluation failed for %s: %s", code, e, exc_info=True)
                results.append(PromotionResult(eligible=False, reason=str(e)))

        # AC-7: Check for critical safety violations and demote if needed
        # (runs after readiness evaluation, within the same cycle)
        try:
            await self.check_and_apply_demotions()
        except Exception as e:
            logger.error("Demotion check failed: %s", e, exc_info=True)

        return results

    async def evaluate_site(self, site_id: str, current_phase: str) -> PromotionResult:
        """Check all gates and surface readiness for manual operator promotion."""

        sast = timezone(timedelta(hours=2))  # South Africa Standard Time
        computed_at = datetime.now(tz=sast).isoformat()
        gates_config = self.PROMOTION_GATES.get(current_phase)
        if not gates_config:
            return PromotionResult(
                eligible=False,
                from_phase=current_phase,
                reason=f"no_promotion_gates_defined_for_{current_phase}",
                computed_at=computed_at,
            )

        gate_results = await self._evaluate_gates(site_id, gates_config["gates"])
        all_passed = all(g.passed for g in gate_results)
        target = gates_config["target"]

        # Phase 240 M2.3: Compute trust confidence from drift verdicts
        trust_confidence, trust_breakdown, equipment_findings = await self._compute_trust_metrics(site_id, gate_results)

        if all_passed:
            await self._set_ready_flag(site_id, current_phase, target, gate_results)
            return PromotionResult(
                eligible=True,
                promoted=False,
                from_phase=current_phase,
                to_phase=target,
                reason="ready_for_manual_promotion",
                gates=gate_results,
                computed_at=computed_at,
                trust_confidence=trust_confidence,
                trust_breakdown=trust_breakdown,
                equipment_findings=equipment_findings,
            )

        await self._clear_stale_ready_flag(site_id, current_phase, target, gate_results)
        return PromotionResult(
            eligible=False,
            from_phase=current_phase,
            to_phase=target,
            reason="eligibility_requirements_not_met",
            gates=gate_results,
            computed_at=computed_at,
            trust_confidence=trust_confidence,
            trust_breakdown=trust_breakdown,
            equipment_findings=equipment_findings,
        )

    async def _clear_stale_ready_flag(
        self,
        site_id: str,
        from_phase: str,
        to_phase: str,
        gate_results: list[GateResult],
    ) -> None:
        """Clear a previously-set ready flag when eligibility regresses.

        A stale ready flag is a dishonest eligibility claim — readiness must
        track the evidence in both directions.
        """
        from app.config.settings import settings
        from supabase import create_client

        try:
            client = create_client(settings.supabase_url, settings.supabase_service_role_key)
            existing = (
                client.table("sites")
                .select("phase_promotion_ready, phase_promotion_target")
                .eq("code", site_id)
                .limit(1)
                .execute()
            )
            if not existing.data or not existing.data[0].get("phase_promotion_ready"):
                return

            sast = timezone(timedelta(hours=2))  # South Africa Standard Time
            met_at = datetime.now(tz=sast).isoformat()
            client.table("sites").update(
                {
                    "phase_promotion_ready": False,
                    "phase_promotion_readiness": {
                        "event": "phase_promotion_readiness",
                        "ready": False,
                        "from_phase": from_phase,
                        "to_phase": to_phase,
                        "met_at": met_at,
                        "gate_results": [g.to_dict() for g in gate_results],
                    },
                }
            ).eq("code", site_id).execute()

            client.table("phase_promotion_readiness_log").insert(
                {
                    "site_id": site_id,
                    "from_phase": from_phase,
                    "to_phase": to_phase,
                    "met": False,
                    "met_at": met_at,
                    "gate_results": [g.to_dict() for g in gate_results],
                    "recorded_by": "phase_promotion_evaluator",
                }
            ).execute()
            logger.info("Phase readiness cleared for %s (%s → %s eligibility regressed)", site_id, from_phase, to_phase)
        except Exception as e:
            logger.warning("Failed to clear stale readiness flag for %s: %s", site_id, e)

    async def _set_ready_flag(
        self,
        site_id: str,
        from_phase: str,
        to_phase: str,
        gate_results: list[GateResult],
    ) -> None:
        """Set phase_promotion_ready flag on the site and notify operators.

        The evaluator surfaces readiness only — it never calls the promotion
        API. Human operators make the final decision and flip the phase.
        """
        from app.config.settings import settings
        from supabase import create_client

        sast = timezone(timedelta(hours=2))  # South Africa Standard Time
        met_at = datetime.now(tz=sast).isoformat()
        readiness = {
            "event": "phase_promotion_readiness",
            "ready": True,
            "from_phase": from_phase,
            "to_phase": to_phase,
            "met_at": met_at,
            "gate_results": [g.to_dict() for g in gate_results],
            "current_progress": {
                g.gate: {
                    "met": g.passed,
                    "value": g.value,
                    "threshold": g.threshold,
                }
                for g in gate_results
            },
        }

        logger.info(
            "Phase readiness set: %s %s → %s (%d/%d gates passed)",
            site_id,
            from_phase,
            to_phase,
            sum(1 for g in gate_results if g.passed),
            len(gate_results),
        )

        client = create_client(settings.supabase_url, settings.supabase_service_role_key)
        previous_ready = False
        try:
            existing = client.table("sites").select("phase_promotion_readiness").eq("code", site_id).limit(1).execute()
            if existing.data:
                previous = existing.data[0].get("phase_promotion_readiness") or {}
                previous_ready = (
                    bool(previous.get("ready"))
                    and previous.get("from_phase") == from_phase
                    and previous.get("to_phase") == to_phase
                )
        except Exception as e:
            logger.debug("Could not read previous phase readiness for %s: %s", site_id, e)

        client.table("sites").update(
            {
                "phase_promotion_ready": True,
                "phase_promotion_ready_since": met_at,
                "phase_promotion_target": to_phase,
                "phase_promotion_readiness": readiness,
            }
        ).eq("code", site_id).execute()

        # Once-per-eligibility-edge semantics: log + notify only on the flip,
        # not on every hourly evaluation while the site remains eligible.
        if not previous_ready:
            await self._log_readiness_flip(client, site_id, from_phase, to_phase, readiness)
            await self._notify_ready(site_id, from_phase, to_phase, gate_results)

    async def _log_readiness_flip(
        self,
        client,
        site_id: str,
        from_phase: str,
        to_phase: str,
        readiness: dict,
    ) -> None:
        """Record a readiness event distinct from a phase transition."""
        try:
            client.table("phase_promotion_readiness_log").insert(
                {
                    "site_id": site_id,
                    "from_phase": from_phase,
                    "to_phase": to_phase,
                    "met": True,
                    "met_at": readiness["met_at"],
                    "current_progress": readiness["current_progress"],
                    "gate_results": readiness["gate_results"],
                    "recorded_by": "phase_promotion_evaluator",
                }
            ).execute()
        except Exception as e:
            logger.warning("Failed to write phase readiness audit log for %s: %s", site_id, e)

    async def _notify_ready(
        self,
        site_id: str,
        from_phase: str,
        to_phase: str,
        gate_results: list[GateResult],
    ) -> None:
        """Send Telegram alert that a site is ready for manual promotion."""
        ml_hours = 0.0
        for g in gate_results:
            if g.gate.startswith("ml_hours_ingested") and isinstance(g.value, (int, float)):
                ml_hours = float(g.value)
                break

        try:
            from app.models.notification import AlertLevel
            from app.services.notification_service import notification_service

            title = f"SENTINEL Phase Readiness — {site_id.upper()}"
            body = (
                f"Ready for operator review: {from_phase} → {to_phase}\n"
                f"All Trust Ladder gates passed.\n"
                f"ML hours ingested: {ml_hours:.0f}h\n"
                f"No phase change was applied automatically."
            )
            await notification_service.send_alert_direct(
                title=title,
                body=body,
                alert_level=AlertLevel.INFO,
            )
            logger.info("Phase readiness notification sent for %s", site_id)
        except Exception as e:
            logger.warning("Phase readiness notification failed for %s: %s", site_id, e)

    async def check_and_apply_demotions(self) -> None:
        """AC-7: Check for critical safety violations and demote sites.

        Runs as part of the readiness evaluation cycle. If a site in supervised
        or automatic mode has a safety_block, immediately demote to advisory
        (the safe mode). Demotion is never gated on human availability.
        """
        from app.config.settings import settings
        from supabase import create_client

        client = create_client(settings.supabase_url, settings.supabase_service_role_key)

        # Get all commercial sites currently in supervised or automatic
        try:
            sites = (
                client.table("sites")
                .select("code, id, onboarding_phase")
                .like("code", "site-%")
                .in_("onboarding_phase", ["supervised", "automatic"])
                .execute()
            )
        except Exception as e:
            logger.warning("Failed to fetch sites for demotion check: %s", e)
            return

        for site in sites.data or []:
            site_id = site["code"]
            current_phase = site["onboarding_phase"]

            # Check for recent safety violations (critical-failure signal: safety_block in last 7 days)
            try:
                safety_rows = (
                    client.table("parasite_decisions")
                    .select("id", count="exact")
                    .eq("site_id", site_id)
                    .eq("decision_type", "safety_block")
                    .gte("created_at", (datetime.now(tz=UTC) - timedelta(days=7)).isoformat())
                    .execute()
                )
                violation_count = safety_rows.count if hasattr(safety_rows, "count") else len(safety_rows.data or [])

                if violation_count > 0:
                    # Critical failure: demote to advisory immediately
                    # Persist demotion to phase_transition_log
                    client.table("phase_transition_log").insert(
                        {
                            "site_id": site_id,
                            "from_phase": current_phase,
                            "to_phase": "advisory",
                            "changed_by": "system",
                            "reason": f"auto_demotion safety_violations:{violation_count}_in_7d",
                        }
                    ).execute()

                    # Update phase
                    client.table("sites").update({"onboarding_phase": "advisory"}).eq("code", site_id).execute()

                    # Notify operator
                    try:
                        from app.models.notification import AlertLevel
                        from app.services.notification_service import notification_service

                        title = f"SENTINEL Safety Demotion — {site_id.upper()}"
                        body = (
                            f"Site demoted to advisory: critical safety violations detected.\n"
                            f"Safety blocks in last 7 days: {violation_count}\n"
                            f"Current mode revoked: {current_phase} → advisory\n"
                            f"Action required: investigate violations before re-promotion."
                        )
                        await notification_service.send_alert_direct(
                            title=title,
                            body=body,
                            alert_level=AlertLevel.CRITICAL,
                        )
                        logger.warning("Safety demotion executed for %s (%d violations)", site_id, violation_count)
                    except Exception as notify_err:
                        logger.warning("Demotion notification failed for %s: %s", site_id, notify_err)

            except Exception as e:
                logger.debug("Demotion check failed for %s: %s", site_id, e)

    async def _compute_trust_metrics(
        self,
        site_id: str,
        gate_results: list[GateResult],
    ) -> tuple[float, dict, list[dict]]:
        """Compute trust confidence from gates and drift verdicts (Phase 240 M2.3).

        Returns:
            (trust_confidence, trust_breakdown, equipment_findings)
        """
        from app.ml.models.drift_trust_integration import (
            compute_drift_penalty_for_site,
            compute_trust_confidence,
            create_findings_from_drift,
            extract_equipment_verdicts_from_db,
        )

        # Base trust from gates
        total_gates = len(gate_results)
        gates_passed = sum(1 for g in gate_results if g.passed)
        base_trust = gates_passed / total_gates if total_gates > 0 else 0.0

        # Extract drift verdicts from database
        equipment_verdicts = extract_equipment_verdicts_from_db(site_id)

        # Compute drift penalty (max across equipment)
        drift_penalty = compute_drift_penalty_for_site(site_id, {k: v[0] for k, v in equipment_verdicts.items()})

        # Compute trust confidence
        trust_confidence = compute_trust_confidence(base_trust, drift_penalty)

        # Trust breakdown for operator visibility
        trust_breakdown = {
            "base_trust": round(base_trust, 4),
            "drift_penalty": round(drift_penalty, 4),
            "formula": "base_trust * (1.0 - drift_penalty)",
        }

        # Equipment findings
        equipment_findings_list = create_findings_from_drift(site_id, equipment_verdicts)

        # Phase 241 M2.4 (AC-6): surface retraining queue state on findings —
        # operators see "drift detected AND repair is pending/running/escalated"
        try:
            from app.ml.models.retraining_queue import get_active_statuses_for_site

            retrain_statuses = get_active_statuses_for_site(site_id)
        except Exception:
            retrain_statuses = {}

        # Convert findings to response format
        equipment_findings = []
        for f in equipment_findings_list:
            eq_type = f.get("equipment_type", "unknown")
            verdict_tuple = equipment_verdicts.get(eq_type, ("UNEVALUABLE", None))
            finding = {
                "equipment_id": f.get("equipment_id", "unknown"),
                "equipment_type": eq_type,
                "drift_verdict": verdict_tuple[0],
                "finding_type": f.get("finding_type"),
                "severity": f.get("severity", "low"),
            }
            if eq_type in retrain_statuses:
                finding["retraining"] = retrain_statuses[eq_type]
            equipment_findings.append(finding)

        logger.debug(
            "[READINESS] Site %s: trust_confidence=%.4f, base_trust=%.4f, drift_penalty=%.4f",
            site_id,
            trust_confidence,
            base_trust,
            drift_penalty,
        )

        return trust_confidence, trust_breakdown, equipment_findings

    async def _evaluate_gates(
        self,
        site_id: str,
        gates: list[str],
    ) -> list[GateResult]:
        """Evaluate all promotion gates for a site."""
        from app.config.settings import settings
        from supabase import create_client

        client = create_client(settings.supabase_url, settings.supabase_service_role_key)

        # Fetch site UUID once
        site_row = client.table("sites").select("id").eq("code", site_id).limit(1).execute()
        site_uuid = site_row.data[0]["id"] if site_row.data else None

        # Fetch ML hours once
        ml_hours_raw = None
        if site_uuid:
            ml_row = client.table("sites").select("ml_hours_ingested").eq("id", site_uuid).limit(1).execute()
            ml_hours_raw = ml_row.data[0].get("ml_hours_ingested", 0.0) if ml_row.data else 0.0
        ml_hours = float(ml_hours_raw or 0.0)
        now = datetime.now(tz=UTC)

        results: list[GateResult] = []
        for gate in gates:
            result = await self._evaluate_single_gate(client, site_id, site_uuid, site_id, gate, ml_hours, now)
            results.append(result)

        return results

    async def _evaluate_single_gate(
        self,
        client,
        site_id: str,
        site_uuid: str | None,
        site_id_for_queries: str,
        gate: str,
        ml_hours: float,
        now: datetime,
    ) -> GateResult:
        """Evaluate a single gate expression."""

        # ── ml_hours_ingested >= X ──────────────────────────────────────
        if gate.startswith("ml_hours_ingested >="):
            threshold = float(gate.split(">=")[1].strip())
            passed = ml_hours >= threshold
            reason = (
                f"{round(ml_hours, 1)}h {'≥' if passed else '<'} {threshold}h minimum"
                if passed
                else f"insufficient evidence: {round(ml_hours, 1)}h / {threshold}h"
            )
            return GateResult(
                gate=gate,
                passed=passed,
                value=round(ml_hours, 1),
                threshold=threshold,
                reason=reason,
            )

        # ── hours_since_created >= X (commissioning gate) ──────────────
        if gate.startswith("hours_since_created >="):
            threshold = int(gate.split(">=")[1].strip())
            try:
                created_row = client.table("sites").select("created_at").eq("code", site_id).limit(1).execute()
                if created_row.data and created_row.data[0].get("created_at"):
                    created = datetime.fromisoformat(created_row.data[0]["created_at"].replace("Z", "+00:00"))
                    hours = (datetime.now(tz=UTC) - created).total_seconds() / 3600
                    return GateResult(gate=gate, passed=hours >= threshold, value=round(hours, 1), threshold=threshold)
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=str(e), threshold=threshold)
            return GateResult(gate=gate, passed=False, value=0, threshold=threshold)

        # ── bridge_polls_successful >= X (commissioning gate) ─────────
        if gate.startswith("bridge_polls_successful >="):
            threshold = int(gate.split(">=")[1].strip())
            try:
                polls_row = (
                    client.table("site_polling_state").select("poll_count").eq("site_id", site_id).limit(1).execute()
                )
                if polls_row.data and polls_row.data[0].get("poll_count") is not None:
                    count = int(polls_row.data[0]["poll_count"])
                    return GateResult(gate=gate, passed=count >= threshold, value=count, threshold=threshold)
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
            # Fallback: count from equipment_sensor_readings as polling proxy
            try:
                readings = (
                    client.table("equipment_sensor_readings")
                    .select("id", count="exact")
                    .eq("site_id", site_id)
                    .execute()
                )
                count = readings.count if hasattr(readings, "count") else len(readings.data or [])
                passed = count >= 50  # At least 50 sensor readings = bridge is working
                return GateResult(gate=gate, passed=passed, value=count, threshold=threshold)
            except Exception as e:
                logger.debug("Gate '%s' fallback failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=str(e), threshold=threshold)

        # ── data_quality_score >= X (commissioning gate) ──────────────
        if gate.startswith("data_quality_score >="):
            threshold = float(gate.split(">=")[1].strip())
            try:
                # Check fault-to-normal ratio from equipment_sensor_readings
                # Good quality = most readings are normal, few are faults/alarms
                readings = (
                    client.table("equipment_sensor_readings")
                    .select("sensor_type", count="exact")
                    .eq("site_id", site_id)
                    .execute()
                )
                total = readings.count if hasattr(readings, "count") else len(readings.data or [])
                if total < 10:
                    return GateResult(gate=gate, passed=False, value=0.0, threshold=threshold)
                # Count anomaly-related sensor types as potential fault indicators
                fault_types = (
                    client.table("equipment_sensor_readings")
                    .select("sensor_type", count="exact")
                    .eq("site_id", site_id)
                    .in_("sensor_type", ["anomaly_score", "fault_code", "alarm_status"])
                    .execute()
                )
                fault_count = fault_types.count if hasattr(fault_types, "count") else len(fault_types.data or [])
                # Also check equipment_fault_events
                try:
                    fault_events = (
                        client.table("equipment_fault_events")
                        .select("id", count="exact")
                        .eq("site_id", site_id)
                        .eq("is_synthetic", False)
                        .execute()
                    )
                    fault_count += (
                        fault_events.count if hasattr(fault_events, "count") else len(fault_events.data or [])
                    )
                except Exception:
                    pass
                quality = max(0.0, min(1.0, 1.0 - (fault_count / max(total, 1))))
                return GateResult(gate=gate, passed=quality >= threshold, value=round(quality, 2), threshold=threshold)
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=str(e), threshold=threshold)

        # ── anomaly_scores_writing ──────────────────────────────────────
        # equipment_analytics: ML anomaly scores written by sentinel_data_sync.
        # Pass if any equipment has a score written in the last 30 minutes.
        if gate == "anomaly_scores_writing":
            if not site_uuid:
                return GateResult(gate=gate, passed=False, value=None)
            try:
                rows = (
                    client.table("equipment_analytics")
                    .select("id", count="exact")
                    .eq("site_id", site_uuid)
                    .not_.is_("anomaly_score", "null")
                    .gte("scored_at", (now - timedelta(minutes=30)).isoformat())
                    .execute()
                )
                count = rows.count if hasattr(rows, "count") else len(rows.data or [])
                return GateResult(gate=gate, passed=count > 0, value=count)
            except Exception as e:
                # Fail closed (AC-2): an unevaluable gate must never pass silently.
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=None, reason=f"check_error: {e}")

        # ── bridge_connected ────────────────────────────────────────────
        # BridgeBMSAdapter.get_status() contract:
        #   status: "connected" | "disconnected" | "error"
        #   connection: bool (True = connected)
        # Also accept legacy "ok" and string "online" for forward compat.
        if gate == "bridge_connected":
            import httpx

            try:
                # Use per-site bridge token from site_adapter_config
                cfg_rows = (
                    client.table("site_adapter_config")
                    .select("connection_config")
                    .eq("site_id", site_id)
                    .ilike("protocol", "%bridge%")
                    .eq("enabled", True)
                    .limit(1)
                    .execute()
                )
                if cfg_rows.data:
                    cc = cfg_rows.data[0]["connection_config"]
                    base_url = cc.get("base_url", "")
                    from app.services.shadow_mode_polling import resolve_site_bridge_token

                    token = resolve_site_bridge_token(site_id, cc)
                    if not token:
                        return GateResult(
                            gate=gate, passed=False, value=None, reason="check_error: no bridge token resolved"
                        )
                    resp = httpx.get(
                        f"{base_url}/api/sites/{site_id}/health",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=15,
                    )
                    resp.raise_for_status()
                    status = resp.json()
                else:
                    from app.services.simbiot_service import simbiot_service

                    status = await simbiot_service.get_site_status(site_id)

                connected = status.get("status") in ("connected", "ok") or status.get("site_available") is True
                return GateResult(gate=gate, passed=connected, value=connected)
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=str(e))

        # ── write_capable_adapter_enabled ──────────────────────────────
        if gate == "write_capable_adapter_enabled":
            try:
                rows = (
                    client.table("site_adapter_config")
                    .select("protocol,connection_config")
                    .eq("site_id", site_id)
                    .eq("enabled", True)
                    .execute()
                )
                write_ready = False
                protocols: list[str] = []
                for row in rows.data or []:
                    protocol = str(row.get("protocol") or "").strip().lower()
                    config = row.get("connection_config") or {}
                    protocols.append(protocol)
                    if protocol in {"bacnet", "knx", "modbus", "obix"} or (
                        protocol == "bridge"
                        and config.get("supports_writes") is True
                        and config.get("write_enabled") is True
                    ):
                        write_ready = True
                return GateResult(gate=gate, passed=write_ready, value=",".join(protocols) or None)
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=str(e))

        # ── write_capable_adapter_configured ───────────────────────────
        # Advisory mode keeps bridge writes disabled, but promotion to
        # supervised still requires proof that a write-capable transport is
        # configured and ready to be enabled at promotion time.
        if gate == "write_capable_adapter_configured":
            try:
                rows = (
                    client.table("site_adapter_config")
                    .select("protocol,connection_config")
                    .eq("site_id", site_id)
                    .eq("enabled", True)
                    .execute()
                )
                configured = False
                protocols: list[str] = []
                for row in rows.data or []:
                    protocol = str(row.get("protocol") or "").strip().lower()
                    config = row.get("connection_config") or {}
                    protocols.append(protocol)
                    if protocol in {"bacnet", "knx", "modbus", "obix"} or (
                        protocol == "bridge" and config.get("supports_writes") is True
                    ):
                        configured = True
                return GateResult(gate=gate, passed=configured, value=",".join(protocols) or None)
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=str(e))

        # ── control_modules_active_for_controllable_equipment ─────────
        # Advisory is where the site proves it is ready for supervised
        # control. If controllable equipment exists, the matching control
        # add-on must already be licensed/active before promotion.
        if gate == "control_modules_active_for_controllable_equipment":
            if not site_uuid:
                return GateResult(gate=gate, passed=False, value=None)
            try:
                equipment_rows = client.table("equipment").select("type").eq("site_id", site_uuid).execute()
                equipment_types = {
                    str(row.get("type") or "").strip().lower() for row in (equipment_rows.data or []) if row.get("type")
                }
                required_modules: set[str] = set()
                if equipment_types & {"ahu", "fcu", "vav", "chiller", "cooling_tower", "pump"}:
                    required_modules.add("hvac_control")
                if equipment_types & {"meter", "power_meter", "bess", "generator", "ups", "inverter"}:
                    required_modules.add("energy_control")
                if equipment_types & {"lighting", "dali", "luminaire"}:
                    required_modules.add("lighting_control")
                if equipment_types & {"solar", "pv", "inverter"}:
                    required_modules.add("solar_control")
                if not required_modules:
                    return GateResult(gate=gate, passed=True, value="none_required")

                module_rows = (
                    client.table("site_modules")
                    .select("module_type,status,licensed")
                    .eq("site_id", site_id)
                    .in_("module_type", sorted(required_modules))
                    .execute()
                )
                active_modules = {
                    str(row.get("module_type") or "")
                    for row in (module_rows.data or [])
                    if row.get("status") == "active" and row.get("licensed") is True
                }
                missing = sorted(required_modules - active_modules)
                return GateResult(
                    gate=gate,
                    passed=not missing,
                    value="ok" if not missing else ",".join(missing),
                )
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=str(e))

        # ── bridge_write_endpoint_available ───────────────────────────
        # In advisory, bridge writes remain disabled locally. This gate only
        # verifies that the upstream bridge exposes the supervised write API
        # that will be enabled when the site is promoted.
        if gate == "bridge_write_endpoint_available":
            import httpx

            try:
                rows = (
                    client.table("site_adapter_config")
                    .select("protocol,connection_config")
                    .eq("site_id", site_id)
                    .eq("enabled", True)
                    .execute()
                )
                checked: list[str] = []
                for row in rows.data or []:
                    protocol = str(row.get("protocol") or "").strip().lower()
                    config = row.get("connection_config") or {}
                    if protocol in {"bacnet", "knx", "modbus", "obix"}:
                        return GateResult(gate=gate, passed=True, value=protocol)
                    if protocol != "bridge" or config.get("supports_writes") is not True:
                        continue
                    base_url = str(config.get("base_url") or "").rstrip("/")
                    if not base_url:
                        continue
                    checked.append("bridge")
                    from app.services.shadow_mode_polling import resolve_site_bridge_token

                    token = resolve_site_bridge_token(site_id, config)
                    headers = {"Authorization": f"Bearer {token}"} if token else {}
                    resp = httpx.options(
                        f"{base_url}/api/sites/{site_id}/write",
                        headers=headers,
                        timeout=10,
                    )
                    allow = resp.headers.get("allow", "")
                    if resp.status_code in (200, 204) or "POST" in allow.upper():
                        return GateResult(gate=gate, passed=True, value="bridge")
                    if resp.status_code == 405 and "GET" in allow.upper() and "POST" not in allow.upper():
                        return GateResult(gate=gate, passed=False, value="bridge_write_endpoint_get_only")
                return GateResult(gate=gate, passed=False, value=",".join(checked) or None)
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=str(e))

        # ── recommendations_generated >= X (all-time count) ──────────
        if gate.startswith("recommendations_generated >="):
            threshold = int(gate.split(">=")[1].strip())
            if not site_uuid:
                return GateResult(
                    gate=gate, passed=False, value=None, threshold=threshold, reason="site_uuid_not_found"
                )
            try:
                rows = (
                    client.table("recommendations")
                    .select("id", count="exact")
                    .eq("site_id", site_id)
                    .eq("source", "ai_optimizer")
                    .eq("shadow_mode", False)
                    .execute()
                )
                count = rows.count if hasattr(rows, "count") else len(rows.data or [])
                passed = count >= threshold
                reason = (
                    f"{count} recs {'≥' if passed else '<'} {threshold} minimum"
                    if passed
                    else f"insufficient recommendations: {count} / {threshold}"
                )
                return GateResult(gate=gate, passed=passed, value=count, threshold=threshold, reason=reason)
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(
                    gate=gate, passed=False, value=str(e), threshold=threshold, reason=f"check_error: {e}"
                )

        # ── recommendations_acknowledged >= X ────────────────────────────
        if gate.startswith("recommendations_acknowledged >="):
            threshold = int(gate.split(">=")[1].strip())
            if not site_uuid:
                return GateResult(gate=gate, passed=False, value=None, threshold=threshold)
            try:
                rows = (
                    client.table("recommendations")
                    .select("id", count="exact")
                    .eq("site_id", site_id)
                    .neq("status", "pending")
                    .eq("shadow_mode", False)
                    .execute()
                )
                count = rows.count if hasattr(rows, "count") else len(rows.data or [])
                return GateResult(gate=gate, passed=count >= threshold, value=count, threshold=threshold)
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=str(e), threshold=threshold)

        # ── time_in_advisory_days >= X ────────────────────────────────
        if gate.startswith("time_in_advisory_days >="):
            threshold = int(gate.split(">=")[1].strip())
            if not site_uuid:
                return GateResult(
                    gate=gate, passed=False, value=None, threshold=threshold, reason="site_uuid_not_found"
                )
            try:
                row = client.table("sites").select("advisory_started_at").eq("id", site_uuid).limit(1).execute()
                advisory_start = row.data[0].get("advisory_started_at") if row.data else None
                if not advisory_start:
                    return GateResult(
                        gate=gate, passed=False, value=None, threshold=threshold, reason="advisory_started_at_not_set"
                    )
                start = datetime.fromisoformat(advisory_start.replace("Z", "+00:00"))
                days = (now - start).days
                passed = days >= threshold
                reason = (
                    f"{days}d in advisory {'≥' if passed else '<'} {threshold}d minimum"
                    if passed
                    else f"insufficient time: {days}d / {threshold}d"
                )
                return GateResult(gate=gate, passed=passed, value=days, threshold=threshold, reason=reason)
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(
                    gate=gate, passed=False, value=str(e), threshold=threshold, reason=f"check_error: {e}"
                )

        # ── recommendation_acceptance_rate >= X ──────────────────────
        if gate.startswith("recommendation_acceptance_rate >="):
            threshold = float(gate.split(">=")[1].strip())
            if not site_uuid:
                return GateResult(gate=gate, passed=False, value=None, threshold=threshold)
            try:
                rows_accepted = (
                    client.table("recommendations")
                    .select("id", count="exact")
                    .eq("site_id", site_id)
                    .eq("acknowledgement_type", "accepted")
                    .eq("shadow_mode", False)
                    .execute()
                )
                rows_dismissed = (
                    client.table("recommendations")
                    .select("id", count="exact")
                    .eq("site_id", site_id)
                    .eq("acknowledgement_type", "dismissed")
                    .eq("shadow_mode", False)
                    .execute()
                )
                accepted_c = rows_accepted.count if hasattr(rows_accepted, "count") else len(rows_accepted.data or [])
                dismissed_c = (
                    rows_dismissed.count if hasattr(rows_dismissed, "count") else len(rows_dismissed.data or [])
                )
                total = accepted_c + dismissed_c
                rate = accepted_c / total if total > 0 else 0.0
                return GateResult(gate=gate, passed=rate >= threshold, value=round(rate, 4), threshold=threshold)
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=str(e), threshold=threshold)

        # ── no_safety_violations_30d ──────────────────────────────────
        if gate == "no_safety_violations_30d":
            if not site_uuid:
                return GateResult(gate=gate, passed=False, value=None)
            try:
                rows_obj = (
                    client.table("parasite_decisions")
                    .select("id", count="exact")
                    .eq("site_id", site_id)
                    .eq("decision_type", "safety_block")
                    .gte("created_at", (now - timedelta(days=30)).isoformat())
                    .execute()
                )
                count = rows_obj.count if hasattr(rows_obj, "count") else len(rows_obj.data or [])
                return GateResult(gate=gate, passed=count == 0, value=count)
            except Exception as e:
                # Fail closed (AC-2): an unevaluable safety gate must never pass silently.
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=None, reason=f"check_error: {e}")

        # ── verified_writable_control_points >= X ──────────────────────
        if gate.startswith("verified_writable_control_points >="):
            threshold = int(gate.split(">=")[1].strip())
            if not site_uuid:
                return GateResult(gate=gate, passed=False, value=None, threshold=threshold)
            try:
                rows = (
                    client.table("point_asset_mappings")
                    .select("id", count="exact")
                    .eq("site_id", site_uuid)
                    .eq("is_verified", True)
                    .or_(
                        "parameter_type.ilike.command:%,"
                        "parameter_type.ilike.setpoint:%,"
                        "parameter_type.ilike.writable:%,"
                        "parameter_type.eq.command,"
                        "parameter_type.eq.setpoint,"
                        "parameter_type.eq.writable,"
                        "parameter_type.ilike.%analogOutput%,"
                        "parameter_type.ilike.%binaryOutput%,"
                        "parameter_type.ilike.%multiStateOutput%"
                    )
                    .execute()
                )
                count = rows.count if hasattr(rows, "count") else len(rows.data or [])
                return GateResult(gate=gate, passed=count >= threshold, value=count, threshold=threshold)
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=str(e), threshold=threshold)

        # ── controllable_equipment_control_coverage >= X ───────────────
        if gate.startswith("controllable_equipment_control_coverage >="):
            threshold = float(gate.split(">=")[1].strip())
            if not site_uuid:
                return GateResult(gate=gate, passed=False, value=None, threshold=threshold)
            controllable_types = [
                "ahu",
                "fcu",
                "vav",
                "chiller",
                "cooling_tower",
                "pump",
                "bess",
                "generator",
                "inverter",
            ]
            try:
                equipment_rows = (
                    client.table("equipment")
                    .select("code,type")
                    .eq("site_id", site_uuid)
                    .in_("type", controllable_types)
                    .execute()
                )
                controllable_codes = {
                    str(row.get("code") or "").strip() for row in (equipment_rows.data or []) if row.get("code")
                }
                if not controllable_codes:
                    return GateResult(gate=gate, passed=False, value=0.0, threshold=threshold)

                mapping_rows = (
                    client.table("point_asset_mappings")
                    .select("extracted_asset_id")
                    .eq("site_id", site_uuid)
                    .eq("is_verified", True)
                    .or_(
                        "parameter_type.ilike.command:%,"
                        "parameter_type.ilike.setpoint:%,"
                        "parameter_type.ilike.writable:%,"
                        "parameter_type.eq.command,"
                        "parameter_type.eq.setpoint,"
                        "parameter_type.eq.writable,"
                        "parameter_type.ilike.%analogOutput%,"
                        "parameter_type.ilike.%binaryOutput%,"
                        "parameter_type.ilike.%multiStateOutput%"
                    )
                    .execute()
                )
                equipment_with_control = {
                    str(row.get("extracted_asset_id") or "").strip()
                    for row in (mapping_rows.data or [])
                    if row.get("extracted_asset_id")
                }
                covered = len(controllable_codes & equipment_with_control)
                coverage = covered / max(len(controllable_codes), 1)
                return GateResult(
                    gate=gate,
                    passed=coverage >= threshold,
                    value=round(coverage, 3),
                    threshold=threshold,
                )
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=str(e), threshold=threshold)

        # ── bridge_connected_uptime_pct >= X ─────────────────────────
        if gate.startswith("bridge_connected_uptime_pct >="):
            threshold = float(gate.split(">=")[1].strip())
            if not site_uuid:
                return GateResult(gate=gate, passed=False, value=None, threshold=threshold)
            try:
                # Read bridge adapter uptime from adapter_health_current (24h rolling)
                row = (
                    client.table("adapter_health_current")
                    .select("uptime_24h_percent")
                    .eq("site_id", site_id_for_queries)
                    .eq("adapter_type", "shadow_bridge")
                    .limit(1)
                    .execute()
                )
                uptime = float(row.data[0].get("uptime_24h_percent", 0.0)) if row.data else 0.0
                # Fall back to live WireGuard ping if uptime is stale (< 1%)
                # Use per-site bridge IP from site_adapter_config, not hardcoded address
                if uptime < 1.0:
                    import subprocess

                    bridge_ip = "10.99.0.1"  # S002 default
                    try:
                        config_rows = (
                            client.table("site_adapter_config")
                            .select("connection_config")
                            .eq("site_id", site_id)
                            .eq("protocol", "bridge")
                            .eq("enabled", True)
                            .limit(1)
                            .execute()
                        )
                        if config_rows.data:
                            cfg = config_rows.data[0].get("connection_config", {})
                            if cfg.get("base_url"):
                                import re

                                m = re.match(r"http://([^:]+):\d+", cfg["base_url"])
                                if m:
                                    bridge_ip = m.group(1)
                    except Exception:
                        pass

                    try:
                        result = subprocess.run(
                            ["ping", "-c", "2", "-W", "3", bridge_ip],
                            capture_output=True,
                            timeout=5,
                        )
                        if result.returncode == 0:
                            uptime = 100.0
                    except Exception:
                        pass
                return GateResult(gate=gate, passed=uptime >= threshold, value=round(uptime, 4), threshold=threshold)
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=str(e), threshold=threshold)

        # ── recommendations_approved >= X ───────────────────────────────
        if gate.startswith("recommendations_approved >="):
            threshold = int(gate.split(">=")[1].strip())
            if not site_uuid:
                return GateResult(gate=gate, passed=False, value=None, threshold=threshold)
            try:
                rows = (
                    client.table("recommendations")
                    .select("id", count="exact")
                    .eq("site_id", site_id)
                    .eq("status", "approved")
                    .eq("shadow_mode", False)
                    .execute()
                )
                count = rows.count if hasattr(rows, "count") else len(rows.data or [])
                return GateResult(gate=gate, passed=count >= threshold, value=count, threshold=threshold)
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=str(e), threshold=threshold)

        # ── no_critical_ml_errors_24h ───────────────────────────────────
        if gate == "no_critical_ml_errors_24h":
            if not site_uuid:
                return GateResult(gate=gate, passed=False, value=None)
            try:
                rows_obj = (
                    client.table("audit_log")
                    .select("id", count="exact")
                    .eq("action", "ml_scoring_failed")
                    .gte("timestamp", (now - timedelta(hours=24)).isoformat())
                    .execute()
                )
                count = rows_obj.count if hasattr(rows_obj, "count") else len(rows_obj.data or [])
                return GateResult(gate=gate, passed=count == 0, value=count)
            except Exception as e:
                # Fail closed (AC-2): an unevaluable gate must never pass silently.
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=None, reason=f"check_error: {e}")

        # ── no_safety_violations_7d ────────────────────────────────────
        if gate == "no_safety_violations_7d":
            if not site_uuid:
                return GateResult(gate=gate, passed=False, value=None)
            try:
                rows_obj = (
                    client.table("parasite_decisions")
                    .select("id", count="exact")
                    .eq("site_id", site_id)
                    .eq("decision_type", "safety_block")
                    .gte("created_at", (now - timedelta(days=7)).isoformat())
                    .execute()
                )
                count = rows_obj.count if hasattr(rows_obj, "count") else len(rows_obj.data or [])
                return GateResult(gate=gate, passed=count == 0, value=count)
            except Exception as e:
                # Fail closed (AC-2): an unevaluable safety gate must never pass silently.
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=None, reason=f"check_error: {e}")

        # ── approval_accuracy >= X ──────────────────────────────────────
        if gate.startswith("approval_accuracy >="):
            threshold = float(gate.split(">=")[1].strip())
            if not site_uuid:
                return GateResult(gate=gate, passed=False, value=None, threshold=threshold)
            try:
                total = (
                    client.table("recommendations")
                    .select("id", count="exact")
                    .eq("site_id", site_id)
                    .neq("status", "pending")
                    .eq("shadow_mode", False)
                    .execute()
                )
                approved = (
                    client.table("recommendations")
                    .select("id", count="exact")
                    .eq("site_id", site_id)
                    .eq("status", "approved")
                    .eq("shadow_mode", False)
                    .execute()
                )
                total_c = total.count if hasattr(total, "count") else len(total.data or [])
                approved_c = approved.count if hasattr(approved, "count") else len(approved.data or [])
                accuracy = approved_c / total_c if total_c > 0 else 0.0
                return GateResult(
                    gate=gate,
                    passed=accuracy >= threshold,
                    value=round(accuracy, 4),
                    threshold=threshold,
                )
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=str(e), threshold=threshold)

        # ── false_positive_rate <= X ────────────────────────────────────
        if gate.startswith("false_positive_rate <="):
            threshold = float(gate.split("<=")[1].strip())
            if not site_uuid:
                return GateResult(gate=gate, passed=False, value=None, threshold=threshold)
            try:
                rejected = (
                    client.table("recommendations")
                    .select("id", count="exact")
                    .eq("site_id", site_id)
                    .eq("status", "rejected")
                    .eq("shadow_mode", False)
                    .execute()
                )
                non_pending = (
                    client.table("recommendations")
                    .select("id", count="exact")
                    .eq("site_id", site_id)
                    .neq("status", "pending")
                    .eq("shadow_mode", False)
                    .execute()
                )
                rejected_c = rejected.count if hasattr(rejected, "count") else len(rejected.data or [])
                total_c = non_pending.count if hasattr(non_pending, "count") else len(non_pending.data or [])
                fpr = rejected_c / total_c if total_c > 0 else 0.0
                return GateResult(gate=gate, passed=fpr <= threshold, value=round(fpr, 4), threshold=threshold)
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(gate=gate, passed=False, value=str(e), threshold=threshold)

        # ── human_approved_autonomous ───────────────────────────────────
        if gate == "human_approved_autonomous":
            if not site_uuid:
                return GateResult(gate=gate, passed=False, value=None)
            try:
                row = client.table("sites").select("human_approved_autonomous").eq("id", site_uuid).limit(1).execute()
                approved = bool(row.data[0].get("human_approved_autonomous", False)) if row.data else False
                return GateResult(gate=gate, passed=approved, value=approved)
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                if "human_approved_autonomous" in str(e):
                    return GateResult(gate=gate, passed=False, value=None)
                return GateResult(gate=gate, passed=False, value=str(e))

        # ── drift_verdict(equipment_type) != VERDICT ─────────────────────
        # Phase 240 M2.3: Gate on drift verdicts
        # Pattern: drift_verdict(chiller) != DRIFT_DETECTED
        if gate.startswith("drift_verdict("):
            try:
                from app.ml.models.drift_trust_integration import extract_equipment_verdicts_from_db

                # Parse gate expression
                # Format: drift_verdict(equipment_type) != EXPECTED_VERDICT
                import re

                match = re.match(r"drift_verdict\(([^)]+)\)\s*(!?=)\s*(.+)", gate)
                if not match:
                    return GateResult(
                        gate=gate,
                        passed=False,
                        value=None,
                        reason="Invalid drift_verdict gate expression",
                    )

                equipment_type = match.group(1).strip()
                operator = match.group(2)  # "=" or "!="
                expected_verdict = match.group(3).strip()

                # Get actual verdict from database
                verdicts = extract_equipment_verdicts_from_db(site_id, [equipment_type])
                actual_verdict, equipment_id = verdicts.get(equipment_type, ("UNEVALUABLE", None))

                # Evaluate gate
                if operator == "!=":
                    passed = actual_verdict != expected_verdict
                else:
                    passed = actual_verdict == expected_verdict

                reason = f"{equipment_type} drift verdict: {actual_verdict} (expected: {operator} {expected_verdict})"

                return GateResult(
                    gate=gate,
                    passed=passed,
                    value=f"actual={actual_verdict}, expected={operator}{expected_verdict}",
                    threshold=None,
                    reason=reason,
                )
            except Exception as e:
                logger.debug("Gate '%s' check failed: %s", gate, e)
                return GateResult(
                    gate=gate,
                    passed=False,
                    value=None,
                    reason=f"drift_verdict_check_error: {e}",
                )

        # Unknown gate — log and skip
        logger.warning("Unknown promotion gate: %s", gate)
        return GateResult(gate=gate, passed=False, value=None)


# Singleton
_phase_promotion_evaluator: PhasePromotionEvaluator | None = None


def get_phase_promotion_evaluator() -> PhasePromotionEvaluator:
    global _phase_promotion_evaluator
    if _phase_promotion_evaluator is None:
        _phase_promotion_evaluator = PhasePromotionEvaluator()
    return _phase_promotion_evaluator
