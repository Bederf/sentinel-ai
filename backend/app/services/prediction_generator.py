"""
Prediction Generator Service

Automatically generates predictions for equipment with health scores below threshold.
Runs as a background job to detect at-risk equipment and create predictions.

Phase: Automatic Prediction Generation
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from app.database.repositories.prediction_repository import PredictionRepository
from app.database.supabase_client import get_supabase_client
from app.services.health_threshold_service import get_health_status, get_health_thresholds
from app.services.prediction_taxonomy import (
    FORMULA_VERSION_STATIC,
    confidence_from_probability,
    normalize_prediction_urgency,
    urgency_from_severity,
)
from app.services.workflow_triggers import get_trigger_engine
from app.services.equipment_alert_service import EquipmentAlertService
from app.services.notification_service import NotificationService
from app.config.settings import settings

logger = logging.getLogger(__name__)

# Minimum probability threshold for creating predictions.
# Aligned with _calculate_prediction_from_health() minimum (50%).
MIN_PROBABILITY_THRESHOLD = 50


def _health_score_to_base_probability(health_score: float) -> float:
    """
    Pure rule-based probability derivation from health score.
    No ML signals involved — fallback when no anomaly scores available.
    Aligned with _calculate_prediction_from_health() in prediction_calculator.py.
    """
    thresholds = get_health_thresholds()

    if health_score >= thresholds["healthy"]:
        return 0.0

    if health_score < thresholds["critical"]:
        # Critical band: 75 - health * 0.3
        base = 75 - (health_score * 0.3)
    elif health_score < thresholds["warning"]:
        # Warning band: 65 - (health - critical_threshold) * 0.5
        base = 65 - ((health_score - thresholds["critical"]) * 0.5)
    else:
        # Moderate band: 55 - (health - warning_threshold) * 0.5
        base = 55 - ((health_score - thresholds["warning"]) * 0.5)

    return max(50, min(95, base))


def health_to_probability(
    health_score: float,
    anomaly_score: float | None = None,
    lstm_anomaly_score: float | None = None,
    ml_hours_ingested: float = 0.0,
) -> float:
    """
    Maps health score to failure probability.

    Combines rule-based health score mapping with ML anomaly signals when available.
    LSTM and IF scores are blended with trust_weight governance.

    Args:
        health_score: Equipment health score (0-100)
        anomaly_score: Isolation Forest anomaly score [0, 1] or None
        lstm_anomaly_score: LSTM anomaly score [0, 1] or None
        ml_hours_ingested: ML training hours for trust_weight calculation

    Returns:
        Failure probability percentage [0, 100]
    """
    from app.services.ml_config import get_ml_trust_weight

    # Rule-based base probability
    base_prob = _health_score_to_base_probability(health_score)

    # No ML signals available — return pure rule-based
    if anomaly_score is None and lstm_anomaly_score is None:
        return base_prob

    # Trust weight for ML blending
    trust_weight = get_ml_trust_weight(ml_hours_ingested)

    # Collect ML signals
    ml_signals = []
    if anomaly_score is not None:
        ml_signals.append(("if", anomaly_score))
    if lstm_anomaly_score is not None:
        ml_signals.append(("lstm", lstm_anomaly_score))

    # Blend ML signals (simple average of available signals)
    ml_avg = sum(s for _, s in ml_signals) / len(ml_signals)

    # ML contribution: (ml_avg - 0.5) * 2 maps [0,1] → [-1, 1] range
    # Weighted by trust_weight and capped
    ml_contribution = (ml_avg - 0.5) * 2 * trust_weight  # ∈ [-trust_weight, +trust_weight]

    # Combine: base_prob is the anchor, ML tilts it up/down
    final_prob = base_prob + ml_contribution

    return max(0, min(100, final_prob))


class PredictionGeneratorService:
    """Service for automatic prediction generation based on equipment health."""

    def __init__(self, site_id: str | None = None):
        """Initialize the prediction generator service."""
        self.supabase = get_supabase_client()
        self.prediction_repo = PredictionRepository()
        self.site_id = site_id  # Optional: if set, used for ML hours lookup

    async def _calculate_probability(
        self,
        equipment_id: str,
        health_score: float,
        operating_data: dict,
        site_id: str,
    ) -> float:
        """Calculate failure probability from health + ML signals.

        Pulls anomaly_score and lstm_anomaly_score from operating_data,
        fetches ml_hours for trust_weight, then calls health_to_probability.
        """
        from app.services.ml_config import get_ml_trust_weight

        anomaly_score = operating_data.get("anomaly_score")
        lstm_anomaly_score = operating_data.get("lstm_anomaly_score")

        ml_hours = await self._get_ml_hours_for_site(site_id)

        probability = health_to_probability(
            health_score=health_score,
            anomaly_score=anomaly_score,
            lstm_anomaly_score=lstm_anomaly_score,
            ml_hours_ingested=ml_hours,
        )
        trust_weight = get_ml_trust_weight(ml_hours)
        logger.info(
            "probability_calculated: equipment_id=%s health_score=%s anomaly_score=%s "
            "lstm_anomaly_score=%s ml_hours=%s trust_weight=%s final_probability=%s",
            equipment_id,
            health_score,
            anomaly_score,
            lstm_anomaly_score,
            ml_hours,
            trust_weight,
            probability,
        )
        return probability

    async def _get_ml_hours_for_site(self, site_id: str) -> float:
        """Fetch ml_hours_ingested for a site from the sites table."""
        try:
            result = self.supabase.table("sites").select("ml_hours_ingested").eq("id", site_id).execute()
            if result.data:
                return float(result.data[0].get("ml_hours_ingested", 0.0))
        except Exception:
            pass
        return 0.0

    async def _trigger_prediction_work_order(
        self, equipment: dict[str, Any], prediction: dict[str, Any]
    ) -> bool:
        """
        Trigger a PREDICTION_CRITICAL work order if conditions are met.

        Conditions:
          - failure_probability >= 65  OR  health_score < 50

        Returns True if a work order was created/triggered, False otherwise.
        """
        try:
            engine = get_trigger_engine()
            result = await engine.on_prediction_critical(
                equipment_id=equipment.get("id", ""),
                prediction_id=str(prediction.get("id")),
                prediction_code=prediction.get("code", ""),
                health_score=equipment.get("health_score", 50),
                probability_percent=prediction.get("probability_percent", 0),
                equipment_code=equipment.get("code"),
            )
            logger.info(
                f"Prediction critical trigger result for {equipment.get('id')}: "
                f"success={result.success} action={result.action_taken}"
            )
            return result.success
        except Exception as e:
            logger.error(f"Prediction work order trigger failed: {e}")
            return False

    def _get_prediction_severity(self, health_score: float, probability_percent: float) -> str:
        """Derive severity from health score and probability."""
        if health_score < 50 or probability_percent >= 65:
            return "critical"
        if health_score < 70 or probability_percent >= 50:
            return "warning"
        return "info"

    def _get_site_code(self, site_id: str | None) -> str:
        """Convert site UUID to site code."""
        if not site_id:
            return "UNKNOWN"
        try:
            sb = get_supabase_client()
            result = sb.table("sites").select("code").eq("id", site_id).limit(1).execute()
            if result.data:
                return result.data[0].get("code", "UNKNOWN")
        except Exception:
            pass
        return site_id or "UNKNOWN"

    def _should_notify_prediction(
        self,
        equipment_id: str,
        site_id: str,
        severity: str,
    ) -> bool:
        """
        Dedup: only notify once per severity level per equipment per 24h.
        Critical: once per 8h (more urgent).
        """
        from datetime import timedelta

        window_hours = 8 if severity == "critical" else 24
        cutoff = datetime.utcnow() - timedelta(hours=window_hours)

        try:
            sb = get_supabase_client()
            result = sb.table("notification_delivery_log").select("id").eq("site_id", site_id).eq(
                "reference_type", "prediction"
            ).eq("severity", severity).gt("sent_at", cutoff.isoformat()).limit(1).execute()
            return len(result.data or []) == 0
        except Exception:
            return True  # Allow notification if check fails

    def _format_prediction_telegram(
        self,
        prediction: dict[str, Any],
        equipment: dict[str, Any],
        severity: str,
        site_code: str,
    ) -> str:
        """Format prediction as HTML-safe Telegram message."""
        emoji = "🔴" if severity == "critical" else "🟡"
        prob = prediction.get("probability_percent", 0) / 100
        health = equipment.get("health_score", 0)
        repair_cost = prediction.get("repair_cost_zar", 0)
        potential_loss = prediction.get("potential_loss_zar", 0)
        factors = prediction.get("contributing_factors", []) or []

        lines = [
            f"{emoji} <b>SENTINEL {severity.upper()} — {site_code.upper()}</b>",
            "",
            f"<b>Equipment:</b> {equipment.get('code', 'UNKNOWN')}",
            f"<b>Type:</b> {equipment.get('type', 'equipment')}",
            f"<b>Health Score:</b> {health:.0f}%",
            f"<b>Failure Probability:</b> {prob:.0%}",
            f"<b>Repair Cost:</b> R{repair_cost:,.0f}",
            f"<b>Risk Exposure:</b> R{potential_loss:,.0f}",
            "",
            f"<b>Recommended Action:</b>",
            f"{prediction.get('recommended_action', 'Inspect equipment')}",
        ]
        if factors:
            lines.extend(["", "<b>Contributing Factors:</b>"])
            for f in factors[:3]:
                if isinstance(f, dict):
                    lines.append(f"• {f.get('factor', 'Unknown')}: {f.get('value', 'Unknown')}")
        lines.extend(["", "-> Acknowledge to confirm review"])
        return "\n".join(lines)

    async def _notify_prediction(
        self,
        prediction: dict[str, Any],
        equipment: dict[str, Any],
        site_id: str,
    ) -> None:
        """
        Route prediction notifications based on severity.

        Info (health 70-89%): Dashboard bell only (via alerts table)
        Warning (health 50-69%): Bell + Telegram
        Critical (health <50%): Bell + Telegram + Email + Auto work order
        """
        probability = prediction.get("probability_percent", 0)
        health_score = equipment.get("health_score", 50)
        severity = self._get_prediction_severity(health_score, probability)
        site_code = self._get_site_code(site_id)
        equipment_code = equipment.get("code", "UNKNOWN")

        # Dedup check
        if not self._should_notify_prediction(equipment.get("id"), site_id, severity):
            logger.info(f"[PRED-NOTIFY] Skipping duplicate notification for {equipment_code} ({severity})")
            return

        # Always create dashboard alert (bell)
        try:
            alert_svc = EquipmentAlertService()
            prob_pct = prediction.get("probability_percent", 0)
            message = (
                f"Health score {health_score:.0f}%. "
                f"Failure probability {prob_pct:.0%}. "
                f"{prediction.get('recommended_action', 'Inspect equipment.')}"
            )
            result = alert_svc.create_alert_for_equipment(
                equipment_id=equipment.get("id", equipment_code),
                site_id=site_id,
                severity=severity,
                message=message,
                alert_type="prediction",
                notify_telegram=False,  # We handle Telegram below with our own format
            )
            if result.get("error"):
                logger.warning(f"[PRED-NOTIFY] Alert creation failed: {result['error']}")
            else:
                logger.info(f"[PRED-NOTIFY] Dashboard alert created for {equipment_code}")
        except Exception as e:
            logger.warning(f"[PRED-NOTIFY] Alert creation error: {e}")

        # Telegram for warning and critical
        if severity in ("warning", "critical"):
            try:
                from app.config.settings import settings as _app_settings
                from app.services.telegram_message_sender import get_telegram_sender, InlineButton, InlineKeyboard

                chat_id = getattr(_app_settings, "telegram_alert_chat_id", None) or getattr(
                    _app_settings, "sentry_fm_chat_id", None
                )
                if chat_id:
                    msg = self._format_prediction_telegram(prediction, equipment, severity, site_code)
                    sender = get_telegram_sender()
                    keyboard = InlineKeyboard(
                        rows=[
                            [InlineButton(label="✅ Acknowledge", callback_data=f"pred_ack:{prediction['id']}")],
                            [InlineButton(label="🛠 Create Work Order", callback_data=f"pred_wo:{prediction['id']}")],
                        ]
                    )
                    await sender.send_text(str(chat_id), msg, keyboard=keyboard)
                    logger.info(f"[PRED-NOTIFY] Telegram sent for {equipment_code} ({severity})")

                    # Log delivery for dedup tracking
                    try:
                        sb = get_supabase_client()
                        sb.table("notification_delivery_log").insert({
                            "id": str(uuid.uuid4()),
                            "site_id": site_id,
                            "notification_type": "prediction",
                            "severity": severity,
                            "reference_type": "prediction",
                            "equipment_id": equipment.get("id"),
                            "channel_type": "telegram",
                            "status": "sent",
                            "provider": "telegram",
                            "sent_at": datetime.utcnow().isoformat(),
                        }).execute()
                    except Exception as log_err:
                        logger.warning(f"[PRED-NOTIFY] Failed to log delivery: {log_err}")
            except Exception as e:
                logger.warning(f"[PRED-NOTIFY] Telegram send failed: {e}")

        # Email escalation for critical only
        if severity == "critical":
            try:
                self._send_prediction_email(equipment, prediction, severity, site_code)
            except Exception as e:
                logger.warning(f"[PRED-NOTIFY] Email send failed: {e}")

    def _send_prediction_email(
        self,
        equipment: dict[str, Any],
        prediction: dict[str, Any],
        severity: str,
        site_code: str,
    ) -> None:
        """Send email escalation for critical predictions."""
        from app.services.visitor_email_service import _smtp_config
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        smtp = _smtp_config()
        if not smtp.get("host"):
            logger.warning("[PRED-EMAIL] SMTP not configured, skipping email")
            return

        prob = prediction.get("probability_percent", 0) / 100
        health = equipment.get("health_score", 0)
        repair_cost = prediction.get("repair_cost_zar", 0)
        potential_loss = prediction.get("potential_loss_zar", 0)
        factors = prediction.get("contributing_factors", []) or []

        body_html = f"""
        <html><body>
        <h2 style="color:{'#dc2626' if severity == 'critical' else '#d97706'}">
            SENTINEL {severity.upper()} Prediction — {site_code.upper()}
        </h2>
        <table style="border-collapse:collapse;width:100%">
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Equipment</b></td>
            <td style="padding:8px;border:1px solid #ddd">{equipment.get('code','UNKNOWN')}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Type</b></td>
            <td style="padding:8px;border:1px solid #ddd">{equipment.get('type','equipment')}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Health Score</b></td>
            <td style="padding:8px;border:1px solid #ddd">{health:.0f}%</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Failure Probability</b></td>
            <td style="padding:8px;border:1px solid #ddd">{prob:.0%}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Repair Cost</b></td>
            <td style="padding:8px;border:1px solid #ddd">R{repair_cost:,.0f}</td></tr>
        <tr><td style="padding:8px;border:1px solid #ddd"><b>Risk Exposure</b></td>
            <td style="padding:8px;border:1px solid #ddd">R{potential_loss:,.0f}</td></tr>
        </table>
        <h3>Recommended Action</h3>
        <p>{prediction.get('recommended_action', 'Inspect equipment.')}</p>
        {'<h3>Contributing Factors</h3><ul>' + ''.join(f"<li>{f.get('factor','Unknown')}: {f.get('value','Unknown')}" for f in factors[:3]) + '</ul>' if factors else ''}
        </body></html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[{severity.upper()}] SENTINEL Prediction — {equipment.get('code')} at {site_code.upper()}"
        msg["From"] = smtp["from_email"]
        msg["To"] = smtp.get("to_email", "operations@sentinel-ai.co.za")

        part = MIMEText(body_html, "html")
        msg.attach(part)

        with smtplib.SMTP(smtp["host"], smtp.get("port", 587)) as server:
            server.starttls()
            server.login(smtp["username"], smtp["password"])
            server.send_message(msg)

        logger.info(f"[PRED-EMAIL] Email sent for {equipment.get('code')} ({severity})")

    def _is_maintenance_module_active(self, site_id: str | None) -> bool:
        """Return True only when phase and module gates permit maintenance workflows."""
        if not site_id:
            return False
        try:
            from app.database.supabase_client import get_supabase_client
            from app.models.onboarding_phase import phase_allows
            from app.models.module_registry import ModuleType
            from app.services.module_registry_service import module_registry

            try:
                sb = get_supabase_client()
                result = sb.table("sites").select("onboarding_phase").eq("code", site_id).limit(1).execute()
                site_phase = (result.data[0].get("onboarding_phase") or "commissioning") if result.data else "commissioning"
            except Exception:
                site_phase = "commissioning"

            return (
                phase_allows(site_phase, "recommendations_ui")
                and module_registry.is_module_active(site_id, ModuleType.MAINTENANCE)
            )
        except Exception as e:
            logger.warning("Maintenance module gate check failed for %s: %s", site_id, e)
            return False

    async def generate_predictions_for_all_sites(self) -> dict[str, Any]:
        """
        Generate predictions for all equipment with health below threshold.

        Main entry point for prediction generation. Called by background scheduler.

        Returns:
            Dict with generation results including counts and any errors
        """
        results = {
            "generated": 0,
            "skipped_duplicate": 0,
            "skipped_low_probability": 0,
            "resolved": 0,
            "errors": [],
            "timestamp": datetime.now().isoformat(),
        }

        try:
            # Get health thresholds
            thresholds = get_health_thresholds()
            healthy_threshold = thresholds.get("healthy", 90)

            logger.info(f"Starting prediction generation (health threshold: {healthy_threshold})")

            # Get equipment with health below threshold
            at_risk_equipment = self._get_at_risk_equipment(healthy_threshold)
            logger.info(f"Found {len(at_risk_equipment)} equipment below health threshold")

            # Get equipment IDs with existing active predictions
            active_prediction_ids = set(self.prediction_repo.get_active_equipment_ids())

            # Generate predictions for at-risk equipment
            for equipment in at_risk_equipment:
                try:
                    equipment_id = equipment.get("id")

                    # Check for duplicate
                    if equipment_id in active_prediction_ids:
                        results["skipped_duplicate"] += 1
                        continue

                    # Generate prediction (async for ML signal integration)
                    prediction = await self._generate_prediction_async(equipment, equipment.get("site_id", ""))

                    # Check probability threshold
                    if prediction["probability_percent"] < MIN_PROBABILITY_THRESHOLD:
                        results["skipped_low_probability"] += 1
                        continue

                    # Store prediction
                    self.prediction_repo.create(prediction)
                    results["generated"] += 1
                    logger.info(
                        f"Generated prediction for {equipment.get('name')} (health: {equipment.get('health_score')}%)"
                    )

                    # Notify based on severity (all predictions, not just critical)
                    equipment_site_id = equipment.get("site_id")
                    await self._notify_prediction(prediction, equipment, equipment_site_id)

                    # Auto-create work order for critical predictions
                    probability = prediction.get("probability_percent", 0)
                    health_score = equipment.get("health_score", 50)
                    if probability >= 65 or health_score < 50:
                        if self._is_maintenance_module_active(equipment_site_id):
                            await self._trigger_prediction_work_order(equipment, prediction)
                        else:
                            logger.info(
                                "Prediction work-order trigger gated off for site=%s equipment=%s "
                                "(maintenance module inactive)",
                                site_id,
                                equipment.get("code") or equipment.get("id"),
                            )

                except Exception as e:
                    error_msg = f"Error generating prediction for {equipment.get('id')}: {e!s}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)

            # Auto-resolve predictions for improved equipment
            resolved_count = await self.auto_resolve_improved_equipment(healthy_threshold)
            results["resolved"] = resolved_count

            logger.info(
                f"Prediction generation complete: {results['generated']} generated, "
                f"{results['skipped_duplicate']} skipped (duplicate), "
                f"{results['resolved']} resolved"
            )

        except Exception as e:
            error_msg = f"Prediction generation failed: {e!s}"
            logger.error(error_msg)
            results["errors"].append(error_msg)

        return results

    def _get_at_risk_equipment(self, threshold: int) -> list[dict[str, Any]]:
        """
        Query equipment with health score below threshold.

        Args:
            threshold: Health score threshold (equipment below this is at-risk)

        Returns:
            List of equipment records with health below threshold
        """
        try:
            response = (
                self.supabase.table("equipment")
                .select("*, building:buildings(id, name, code)")
                .lt("health_score", threshold)
                .execute()
            )

            return response.data or []

        except Exception as e:
            logger.error(f"Failed to query at-risk equipment: {e}")
            return []

    # Keep sync version for backward compatibility (used by tests)
    # Does NOT use ML signals — use _generate_prediction_async for ML-aware predictions.
    def _generate_prediction(self, equipment: dict[str, Any]) -> dict[str, Any]:
        """
        Generate a prediction record for equipment (sync, no ML signals).

        Args:
            equipment: Equipment record from database

        Returns:
            Prediction record ready for insertion
        """
        health_score = equipment.get("health_score", 50)
        equipment_type = equipment.get("type", "unknown")

        # Calculate probability based on health (inverse relationship)
        probability = health_to_probability(health_score)

        # Determine severity based on health status - aligned with database constraint
        health_status = get_health_status(health_score)
        if health_status == "critical":
            severity = "critical"
            timeframe_days = 7
            urgency = "critical"
        elif health_status == "warning":
            severity = "warning"
            timeframe_days = 14
            urgency = "warning"
        else:
            severity = "healthy"
            timeframe_days = 30
            urgency = "healthy"

        predicted_date = datetime.now() + timedelta(days=timeframe_days)
        code = f"pred-auto-{uuid.uuid4().hex[:8]}"
        prediction_type = self._determine_prediction_type(equipment_type, health_score)
        evidence = self._build_evidence(equipment)
        financial_impact = self._calculate_financial_impact(equipment_type, severity)
        contributing_factors = self._get_contributing_factors(equipment)
        recommended_action = self._get_recommended_action(equipment_type, severity, prediction_type)

        return {
            "code": code,
            "site_id": equipment.get("site_id"),
            "equipment_id": equipment.get("id"),
            "prediction_type": prediction_type,
            "probability_percent": probability,
            "confidence": confidence_from_probability(probability, high_threshold=80, medium_threshold=65),
            "predicted_failure_date": predicted_date.isoformat(),
            "timeframe_days": timeframe_days,
            "severity": severity,
            "status": "active",
            "evidence": evidence,
            "contributing_factors": contributing_factors,
            "similar_failures": [],
            "repair_cost_zar": financial_impact["repair_cost"],
            "replacement_cost_zar": financial_impact["replacement_cost"],
            "downtime_cost_per_hour_zar": financial_impact["downtime_cost_per_hour"],
            "potential_loss_zar": financial_impact["potential_loss"],
            "recommended_action": recommended_action,
            "urgency": normalize_prediction_urgency(urgency) or urgency_from_severity(severity),
        }

    async def _generate_prediction_async(self, equipment: dict[str, Any], site_id: str) -> dict[str, Any]:
        """
        Generate a prediction record for equipment asynchronously.

        Args:
            equipment: Equipment record from database
            site_id: Site ID for ML hours lookup

        Returns:
            Prediction record ready for insertion
        """
        health_score = equipment.get("health_score", 50)
        equipment_type = equipment.get("type", "unknown")
        operating_data = equipment.get("operating_data") or {}

        # Calculate probability with ML signals (async, uses trust_weight)
        probability = await self._calculate_probability(
            equipment_id=equipment.get("id", ""),
            health_score=health_score,
            operating_data=operating_data,
            site_id=site_id,
        )

        # Determine severity based on health status - aligned with database constraint
        # Database allows: critical, warning, healthy (NOT high, medium, low)
        health_status = get_health_status(health_score)
        if health_status == "critical":
            severity = "critical"
            timeframe_days = 7
            urgency = "critical"
        elif health_status == "warning":
            severity = "warning"  # Use 'warning' not 'high' (DB constraint)
            timeframe_days = 14
            urgency = "warning"
        else:
            # Healthy equipment shouldn't reach here (only generate for health < 90)
            # But if it does, use 'healthy' not 'low'
            severity = "healthy"
            timeframe_days = 30
            urgency = "healthy"

        # Calculate predicted failure date
        predicted_date = datetime.now() + timedelta(days=timeframe_days)

        # Generate prediction code
        code = f"pred-auto-{uuid.uuid4().hex[:8]}"

        # Determine prediction type based on equipment type
        prediction_type = self._determine_prediction_type(equipment_type, health_score)

        # Build evidence from available data
        evidence = self._build_evidence(equipment)

        # Calculate financial impact
        financial_impact = self._calculate_financial_impact(equipment_type, severity)

        # Get contributing factors
        contributing_factors = self._get_contributing_factors(equipment)

        # Generate recommended action
        recommended_action = self._get_recommended_action(equipment_type, severity, prediction_type)

        return {
            "code": code,
            "site_id": equipment.get("site_id"),
            "equipment_id": equipment.get("id"),
            "prediction_type": prediction_type,
            "probability_percent": probability,
            "confidence": confidence_from_probability(probability, high_threshold=80, medium_threshold=65),
            "predicted_failure_date": predicted_date.isoformat(),
            "timeframe_days": timeframe_days,
            "severity": severity,
            "status": "active",
            "evidence": evidence,
            "contributing_factors": contributing_factors,
            "similar_failures": [],
            "repair_cost_zar": financial_impact["repair_cost"],
            "replacement_cost_zar": financial_impact["replacement_cost"],
            "downtime_cost_per_hour_zar": financial_impact["downtime_cost_per_hour"],
            "potential_loss_zar": financial_impact["potential_loss"],
            "recommended_action": recommended_action,
            "urgency": normalize_prediction_urgency(urgency) or urgency_from_severity(severity),
        }

    def _determine_prediction_type(self, equipment_type: str, health_score: float) -> str:
        """Determine the type of failure prediction based on equipment."""
        type_lower = equipment_type.lower()

        if "chiller" in type_lower:
            if health_score < 50:
                return "compressor_failure"
            return "refrigerant_leak"
        elif "ahu" in type_lower:
            if health_score < 50:
                return "motor_failure"
            return "belt_wear"
        elif "pump" in type_lower:
            return "bearing_failure"
        elif "boiler" in type_lower:
            return "heat_exchanger_fouling"
        elif "ups" in type_lower:
            return "battery_degradation"
        elif "generator" in type_lower:
            return "fuel_system_issue"
        else:
            return "component_degradation"

    def _build_evidence(self, equipment: dict[str, Any]) -> dict[str, Any]:
        """Build evidence data for prediction."""
        thresholds = get_health_thresholds()
        health_score = equipment.get("health_score", 50)

        evidence = {
            "health_score": health_score,
            "health_trend": "declining" if health_score < thresholds["warning"] else "stable",
            "formula_version": FORMULA_VERSION_STATIC,
            "data_source": "automatic_health_monitoring",
            "last_reading": {
                "parameter": "health_score",
                "value": health_score,
                "baseline": thresholds["healthy"],
                "threshold": thresholds["warning"],
                "trend": "declining",
            },
        }

        # Add asset age if install_date available
        install_date = equipment.get("install_date")
        if install_date:
            try:
                age = (
                    datetime.now() - datetime.fromisoformat(install_date.replace("Z", "+00:00").replace("+00:00", ""))
                ).days / 365.25
                evidence["asset_age_years"] = round(age, 1)
            except Exception:
                pass

        # Query fault events for alarm frequency (last 60 days)
        eq_code = equipment.get("code", "")
        site_id_val = equipment.get("site_id", "")
        if eq_code or site_id_val:
            try:
                from app.database.supabase_client import get_supabase_client

                supabase = get_supabase_client()
                lookback = (datetime.now() - timedelta(days=60)).isoformat()

                faults = None
                # Try exact match on equipment_code
                if eq_code:
                    faults = (
                        supabase.table("equipment_fault_events")
                        .select("alarm_code")
                        .eq("equipment_code", eq_code)
                        .gte("recorded_at", lookback)
                        .limit(100)
                        .execute()
                    )
                # Fallback: site-level top alarms (bridge codes differ from catalog)
                if not faults or not faults.data:
                    if site_id_val:
                        # Fault events use S002 format (not site-002), alarm_code is always null
                        bridge_site_id = site_id_val.replace("site-", "S").upper()
                        faults = (
                            supabase.table("equipment_fault_events")
                            .select("event_type")
                            .eq("site_id", bridge_site_id)
                            .gte("recorded_at", lookback)
                            .limit(100)
                            .execute()
                        )

                if faults and faults.data:
                    from collections import Counter

                    key = "alarm_code" if faults.data[0].get("alarm_code") else "event_type"
                    freq = Counter(f[key] for f in faults.data)
                    evidence["alarm_frequency"] = dict(freq.most_common(10))
            except Exception:
                pass
            except Exception:
                pass

        return evidence

    def _calculate_financial_impact(self, equipment_type: str, severity: str) -> dict[str, int]:
        """Calculate estimated financial impact."""
        # Base costs by equipment type (ZAR)
        base_costs = {
            "chiller": {"repair": 85000, "replacement": 2500000, "downtime": 15000},
            "ahu": {"repair": 25000, "replacement": 450000, "downtime": 8000},
            "pump": {"repair": 15000, "replacement": 120000, "downtime": 5000},
            "boiler": {"repair": 45000, "replacement": 800000, "downtime": 12000},
            "ups": {"repair": 35000, "replacement": 650000, "downtime": 25000},
            "generator": {"repair": 75000, "replacement": 1500000, "downtime": 30000},
            "default": {"repair": 20000, "replacement": 200000, "downtime": 5000},
        }

        # Severity multipliers (normalized severity states only)
        severity_multipliers = {
            "critical": 1.5,
            "warning": 1.0,
            "healthy": 0.8,
        }

        # Get costs for equipment type
        type_lower = equipment_type.lower()
        costs = base_costs.get("default", base_costs["default"])
        for key in base_costs:
            if key in type_lower:
                costs = base_costs[key]
                break

        multiplier = severity_multipliers.get(severity, 1.0)

        repair_cost = int(costs["repair"] * multiplier)
        replacement_cost = costs["replacement"]
        downtime_cost = int(costs["downtime"] * multiplier)

        # Estimate potential loss (downtime * estimated hours)
        estimated_hours = {"critical": 48, "warning": 8, "healthy": 4}.get(severity, 8)
        potential_loss = downtime_cost * estimated_hours + repair_cost

        return {
            "repair_cost": repair_cost,
            "replacement_cost": replacement_cost,
            "downtime_cost_per_hour": downtime_cost,
            "potential_loss": potential_loss,
        }

    def _get_contributing_factors(self, equipment: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Get contributing factors for the prediction, keyed by equipment type
        using health_calculation_config.json thresholds.
        """
        health_score = equipment.get("health_score", 50)
        equipment_type = equipment.get("type", "unknown")
        operating_data = equipment.get("operating_data") or {}

        factors: list[dict[str, Any]] = []

        # ── 1. Health Score Factor (always present if below threshold) ─────────
        if health_score < 70:
            factors.append({
                "factor": "Low Health Score",
                "weight": 0.4,
                "description": f"Equipment health at {health_score}%, below acceptable threshold",
            })

        # ── 2. Equipment Age Factor ──────────────────────────────────────────
        # Use config expected_life_years (critical threshold = 80% of expected life)
        try:
            from app.api.health_config import load_config
            config = load_config()
            type_config = config.get(equipment_type.lower(), {})
            expected_life_years = float(type_config.get("expected_life_years", 15))
        except Exception:
            expected_life_years = 15.0
        age_critical_years = expected_life_years * 0.8

        install_date = equipment.get("install_date")
        if install_date:
            try:
                install_str = install_date.replace("Z", "+00:00").replace("+00:00", "")
                age_years = (datetime.now() - datetime.fromisoformat(install_str)).days / 365.25
                if age_years > age_critical_years:
                    factors.append({
                        "factor": "Equipment Age",
                        "weight": 0.3,
                        "description": f"Equipment is {age_years:.1f} years old (expected life: {expected_life_years:.0f} years)",
                    })
            except Exception:
                pass

        # ── 3. High Runtime Factor ───────────────────────────────────────────
        try:
            from app.api.health_config import load_config
            config = load_config()
            type_config = config.get(equipment_type.lower(), {})
            runtime_thresholds = type_config.get("thresholds", {})
            runtime_critical = runtime_thresholds.get("runtime_hours_critical", 40000)
        except Exception:
            runtime_critical = 40000

        runtime = operating_data.get("total_runtime_hours", 0)
        if runtime > runtime_critical:
            factors.append({
                "factor": "High Runtime",
                "weight": 0.2,
                "description": f"Equipment has {runtime:,} operating hours (critical threshold: {runtime_critical:,})",
            })

        # ── 4. Service Overdue Factor ────────────────────────────────────────
        try:
            from app.api.health_config import load_config
            config = load_config()
            type_config = config.get(equipment_type.lower(), {})
            service_interval_days = type_config.get("service_interval_days", 90)
        except Exception:
            service_interval_days = 90
        overdue_critical_days = service_interval_days  # use interval as the overdue threshold

        last_service = equipment.get("last_service") or equipment.get("last_service_date")
        if last_service:
            try:
                last_service_str = last_service.replace("Z", "+00:00").replace("+00:00", "")
                days_since_service = (datetime.now() - datetime.fromisoformat(last_service_str)).days
                if days_since_service > overdue_critical_days:
                    factors.append({
                        "factor": "Service Overdue",
                        "weight": 0.25,
                        "description": (
                            f"Last service {days_since_service} days ago "
                            f"(critical threshold: {overdue_critical_days} days, "
                            f"interval: {service_interval_days} days)"
                        ),
                    })
                elif days_since_service > service_interval_days * 0.8:
                    factors.append({
                        "factor": "Service Approaching Overdue",
                        "weight": 0.15,
                        "description": (
                            f"Last service {days_since_service} days ago "
                            f"(warning threshold: {int(service_interval_days * 0.8)} days)"
                        ),
                    })
            except Exception:
                pass

        # ── 5. Supply Temperature Deviation (HVAC equipment) ──────────────────
        hvac_types = {"chiller", "ahu", "fcu", "vav", "cooling_tower", "ct"}
        if equipment_type.lower() in hvac_types:
            supply_temp = operating_data.get("supply_temp") or operating_data.get("chw_supply_temp")
            setpoint = operating_data.get("setpoint") or operating_data.get("cooling_setpoint")

            if supply_temp is not None and setpoint is not None:
                try:
                    deviation = abs(float(supply_temp) - float(setpoint))
                    if deviation > 5.0:
                        factors.append({
                            "factor": "Supply Temperature Deviation",
                            "weight": 0.3,
                            "description": (
                                f"Supply temperature {float(supply_temp):.1f}°C deviates "
                                f"{deviation:.1f}°C from setpoint {float(setpoint):.1f}°C"
                            ),
                        })
                    elif deviation > 2.0:
                        factors.append({
                            "factor": "Supply Temperature Deviation",
                            "weight": 0.2,
                            "description": (
                                f"Supply temperature {float(supply_temp):.1f}°C deviates "
                                f"{deviation:.1f}°C from setpoint {float(setpoint):.1f}°C"
                            ),
                        })
                except (ValueError, TypeError):
                    pass

            # Low delta-T check for chillers / cooling towers
            return_temp = operating_data.get("return_temp") or operating_data.get("chw_return_temp")
            if return_temp is not None and supply_temp is not None:
                try:
                    delta_t = float(return_temp) - float(supply_temp)
                    if delta_t < 4.0 and equipment_type.lower() in {"chiller", "ct", "cooling_tower"}:
                        factors.append({
                            "factor": "Low Temperature Differential",
                            "weight": 0.25,
                            "description": (
                                f"Return-supply delta-T is {delta_t:.1f}°C "
                                f"(expected ≥ 5°C). Possible heat exchanger issue."
                            ),
                        })
                except (ValueError, TypeError):
                    pass

        # ── Default factor if none found ──────────────────────────────────────
        if not factors:
            factors.append({
                "factor": "Health Monitoring",
                "weight": 0.5,
                "description": "Detected through automated health monitoring",
            })

        return factors

    def _get_recommended_action(self, equipment_type: str, severity: str, prediction_type: str) -> str:
        """Generate recommended action based on prediction."""
        actions = {
            "compressor_failure": "Schedule compressor inspection and vibration analysis",
            "refrigerant_leak": "Perform leak detection and refrigerant level check",
            "motor_failure": "Inspect motor bearings and windings, check amperage draw",
            "belt_wear": "Replace drive belts and check pulley alignment",
            "bearing_failure": "Replace bearings and check lubrication system",
            "heat_exchanger_fouling": "Schedule chemical cleaning of heat exchanger",
            "battery_degradation": "Test battery cells and schedule replacement",
            "fuel_system_issue": "Inspect fuel filters, injectors, and tank condition",
            "component_degradation": "Schedule comprehensive equipment inspection",
        }

        base_action = actions.get(prediction_type, "Schedule maintenance inspection")

        if severity == "critical":
            return f"URGENT: {base_action}. Immediate attention required."
        elif severity == "warning":
            return f"{base_action}. Schedule within 7 days."
        else:
            return f"{base_action}. Schedule at next maintenance window."

    async def auto_resolve_improved_equipment(self, threshold: int) -> int:
        """
        Auto-resolve predictions for equipment that has improved above threshold.

        Args:
            threshold: Health score threshold

        Returns:
            Number of predictions resolved
        """
        resolved_count = 0

        try:
            # Get equipment IDs with active predictions
            active_ids = self.prediction_repo.get_active_equipment_ids()

            if not active_ids:
                return 0

            # Check which have improved
            response = (
                self.supabase.table("equipment")
                .select("id, health_score")
                .in_("id", active_ids)
                .gte("health_score", threshold)
                .execute()
            )

            improved_equipment = response.data or []

            # Resolve predictions for improved equipment
            for equipment in improved_equipment:
                equipment_id = equipment.get("id")
                count = self.prediction_repo.resolve_by_equipment(equipment_id)
                resolved_count += count
                if count > 0:
                    logger.info(
                        f"Auto-resolved {count} prediction(s) for equipment {equipment_id} "
                        f"(health improved to {equipment.get('health_score')}%)"
                    )

        except Exception as e:
            logger.error(f"Failed to auto-resolve predictions: {e}")

        return resolved_count


# Singleton instance
_generator_instance: PredictionGeneratorService | None = None


def get_prediction_generator() -> PredictionGeneratorService:
    """Get singleton prediction generator instance."""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = PredictionGeneratorService()
    return _generator_instance
