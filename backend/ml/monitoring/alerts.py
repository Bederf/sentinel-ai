"""
ML System Alerting

Generates alerts for ML system issues: drift, performance degradation,
model staleness, and data quality problems.

Phase 45-03: MLOps Monitoring and Success Metrics.
"""

import logging
from datetime import datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class MLAlertSeverity(StrEnum):
    """Severity levels for ML system alerts."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class MLAlertType(StrEnum):
    """Types of ML system alerts."""

    FEATURE_DRIFT = "feature_drift"
    MODEL_DRIFT = "model_drift"
    MODEL_STALE = "model_stale"
    MODEL_UNDERPERFORMING = "model_underperforming"
    DATA_QUALITY = "data_quality"
    RETRAINING_FAILED = "retraining_failed"
    RETRAINING_NEEDED = "retraining_needed"
    AB_TEST_COMPLETE = "ab_test_complete"


class MLAlert:
    """An ML system alert."""

    def __init__(
        self,
        alert_type: MLAlertType,
        severity: MLAlertSeverity,
        title: str,
        message: str,
        source: str = "",
        metadata: dict[str, Any] | None = None,
    ):
        self.id = f"mla-{int(datetime.now().timestamp() * 1000)}"
        self.alert_type = alert_type
        self.severity = severity
        self.title = title
        self.message = message
        self.source = source
        self.metadata = metadata or {}
        self.created_at = datetime.now().isoformat()
        self.acknowledged = False
        self.acknowledged_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize alert to dict."""
        return {
            "id": self.id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "source": self.source,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at,
        }


class MLAlertManager:
    """Manages ML system alerts.

    Generates alerts based on drift detection, model health checks,
    and data quality assessments.
    """

    def __init__(self):
        self._alerts: list[MLAlert] = []
        self._max_alerts = 500

    def check_and_alert(self) -> list[dict[str, Any]]:
        """Run all alert checks and return new alerts generated.

        Checks drift detection, model staleness, and performance.
        """
        new_alerts: list[MLAlert] = []

        # Check feature drift
        new_alerts.extend(self._check_feature_drift())

        # Check model drift
        new_alerts.extend(self._check_model_drift())

        # Check model staleness
        new_alerts.extend(self._check_model_staleness())

        # Store alerts
        for alert in new_alerts:
            self._add_alert(alert)

        return [a.to_dict() for a in new_alerts]

    def get_alerts(
        self,
        severity: str | None = None,
        alert_type: str | None = None,
        acknowledged: bool | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get alerts with optional filters.

        Args:
            severity: Filter by severity level.
            alert_type: Filter by alert type.
            acknowledged: Filter by acknowledgement status.
            limit: Maximum alerts to return.

        Returns:
            List of alert dicts.
        """
        filtered = self._alerts

        if severity:
            filtered = [a for a in filtered if a.severity.value == severity]
        if alert_type:
            filtered = [a for a in filtered if a.alert_type.value == alert_type]
        if acknowledged is not None:
            filtered = [a for a in filtered if a.acknowledged == acknowledged]

        # Most recent first
        filtered = sorted(filtered, key=lambda a: a.created_at, reverse=True)
        return [a.to_dict() for a in filtered[:limit]]

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert.

        Args:
            alert_id: ID of the alert to acknowledge.

        Returns:
            True if alert was found and acknowledged.
        """
        for alert in self._alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                alert.acknowledged_at = datetime.now().isoformat()
                return True
        return False

    def get_alert_summary(self) -> dict[str, Any]:
        """Get summary of current alert status."""
        total = len(self._alerts)
        unacknowledged = sum(1 for a in self._alerts if not a.acknowledged)

        by_severity = {}
        for sev in MLAlertSeverity:
            count = sum(1 for a in self._alerts if a.severity == sev and not a.acknowledged)
            by_severity[sev.value] = count

        by_type = {}
        for atype in MLAlertType:
            count = sum(1 for a in self._alerts if a.alert_type == atype and not a.acknowledged)
            if count > 0:
                by_type[atype.value] = count

        return {
            "total_alerts": total,
            "unacknowledged": unacknowledged,
            "by_severity": by_severity,
            "by_type": by_type,
            "checked_at": datetime.now().isoformat(),
        }

    def _add_alert(self, alert: MLAlert) -> None:
        """Add alert and enforce max limit."""
        self._alerts.append(alert)
        if len(self._alerts) > self._max_alerts:
            # Remove oldest acknowledged first, then oldest overall
            ack = [a for a in self._alerts if a.acknowledged]
            if ack:
                self._alerts.remove(ack[0])
            else:
                self._alerts.pop(0)

    def _check_feature_drift(self) -> list[MLAlert]:
        """Check for feature drift across equipment types."""
        alerts: list[MLAlert] = []
        try:
            from ml.monitoring.drift import get_drift_detector

            detector = get_drift_detector()

            from ml.monitoring.drift import EQUIPMENT_TYPES

            for eq_type in EQUIPMENT_TYPES:
                result = detector.detect_feature_drift(eq_type)
                if result["drift_detected"]:
                    drifted = result["drifted_features"]
                    severity = MLAlertSeverity.CRITICAL if len(drifted) >= 3 else MLAlertSeverity.WARNING
                    alerts.append(
                        MLAlert(
                            alert_type=MLAlertType.FEATURE_DRIFT,
                            severity=severity,
                            title=f"Feature drift detected: {eq_type}",
                            message=(f"{len(drifted)} feature(s) drifted for {eq_type}: {', '.join(drifted[:5])}"),
                            source=eq_type,
                            metadata={
                                "equipment_type": eq_type,
                                "drifted_features": drifted,
                                "scores": result["feature_drift_scores"],
                            },
                        )
                    )
        except Exception as e:
            logger.error(f"Feature drift check failed: {e}")

        return alerts

    def _check_model_drift(self) -> list[MLAlert]:
        """Check for model prediction drift."""
        alerts: list[MLAlert] = []
        try:
            from ml.monitoring.drift import get_drift_detector

            detector = get_drift_detector()

            from ml.monitoring.drift import MODEL_TYPES

            for model_type in MODEL_TYPES:
                result = detector.detect_model_drift(model_type)
                if result["drift_detected"]:
                    alerts.append(
                        MLAlert(
                            alert_type=MLAlertType.MODEL_DRIFT,
                            severity=MLAlertSeverity.CRITICAL,
                            title=f"Model drift detected: {model_type}",
                            message=(
                                f"{model_type} accuracy degraded by "
                                f"{result['degradation_pct']}% "
                                f"(recent: {result['recent_accuracy']:.1%}, "
                                f"historical: {result['historical_accuracy']:.1%})"
                            ),
                            source=model_type,
                            metadata=result,
                        )
                    )
        except Exception as e:
            logger.error(f"Model drift check failed: {e}")

        return alerts

    def _check_model_staleness(self) -> list[MLAlert]:
        """Check for stale or underperforming models."""
        alerts: list[MLAlert] = []
        try:
            from ml.training.retraining_scheduler import get_retraining_scheduler

            scheduler = get_retraining_scheduler()
            checks = scheduler.check_all_models()

            for model in checks:
                if model["status"] == "stale":
                    alerts.append(
                        MLAlert(
                            alert_type=MLAlertType.MODEL_STALE,
                            severity=MLAlertSeverity.WARNING,
                            title=(f"Stale model: {model['model_type']}/{model['equipment_type']}"),
                            message=(
                                f"Model is {model.get('age_days', '?')} days old. "
                                "Consider retraining for optimal performance."
                            ),
                            source=f"{model['model_type']}/{model['equipment_type']}",
                            metadata=model,
                        )
                    )
                elif model["status"] == "underperforming":
                    alerts.append(
                        MLAlert(
                            alert_type=MLAlertType.MODEL_UNDERPERFORMING,
                            severity=MLAlertSeverity.CRITICAL,
                            title=(f"Underperforming: {model['model_type']}/{model['equipment_type']}"),
                            message=(
                                f"R2 score {model.get('r2_score', '?')} is below "
                                "minimum threshold. Retraining recommended."
                            ),
                            source=f"{model['model_type']}/{model['equipment_type']}",
                            metadata=model,
                        )
                    )
        except Exception as e:
            logger.error(f"Model staleness check failed: {e}")

        return alerts


# Singleton
_manager: MLAlertManager | None = None


def get_ml_alert_manager() -> MLAlertManager:
    """Get singleton MLAlertManager instance."""
    global _manager
    if _manager is None:
        _manager = MLAlertManager()
    return _manager
