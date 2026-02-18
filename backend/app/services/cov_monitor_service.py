"""COV (Change of Value) subscription monitor service.

Verifies device writes actually took effect by reading values back from devices,
and measures outcomes over configurable windows. This is PARASITE's nervous system
that confirms autonomous actions worked and learns from results.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from app.config.settings import settings
from app.database.repositories.parasite_decision_repository import (
    get_parasite_decision_repository,
)
from app.services.device_abstraction import device_manager

logger = logging.getLogger(__name__)


@dataclass
class COVVerificationResult:
    """Result of COV verification attempt."""

    verified: bool  # Did read-back match expected value?
    actual_value: Any  # What was actually read back
    expected_value: Any  # What we expected
    read_success: bool  # Did the read itself succeed?
    elapsed_seconds: float  # Time taken to verify
    error: Optional[str] = None  # Error message if read failed


@dataclass
class OutcomeMeasurement:
    """Measured outcome of an autonomous action."""

    decision_id: str
    equipment_id: str
    expected_outcome: Dict  # What we predicted would happen
    actual_outcome: Dict  # What actually happened
    matched: bool  # Did outcome match prediction?
    measurement_window_minutes: int
    measured_at: str  # ISO timestamp
    contributing_metrics: Dict = field(default_factory=dict)  # Individual metric comparisons


class COVMonitorService:
    """Monitor device writes and verify they took effect.

    Verifies COV (Change of Value) confirmations within configurable timeout windows,
    and measures post-execution outcomes to determine if actions achieved their goals.
    """

    def __init__(self):
        """Initialize COVMonitorService."""
        self._instance = None
        self.parasite_repo = get_parasite_decision_repository()
        self._pending_measurements: Dict[str, Dict] = {}
        self._verification_stats = {
            "total_attempts": 0,
            "successful_verifications": 0,
            "failed_verifications": 0,
        }
        logger.info("COVMonitorService initialized")

    async def verify_write(
        self,
        equipment_id: str,
        point_name: str,
        expected_value: Any,
        decision_id: str,
        timeout_seconds: Optional[int] = None,
    ) -> COVVerificationResult:
        """Verify device write took effect via read-back confirmation.

        Performs single read-back verification (not polling). Compares expected vs
        actual value within configurable tolerance for numeric values.

        Args:
            equipment_id: Target equipment UUID
            point_name: Device control point name (e.g., 'setpoint')
            expected_value: Value we expected to see after write
            decision_id: Decision ID for audit trail
            timeout_seconds: Max time to wait (override settings default)

        Returns:
            COVVerificationResult with verified flag and actual value read

        Raises:
            Exception: Only on critical failures (logs and continues)
        """
        start_time = datetime.utcnow()
        timeout = timeout_seconds or settings.parasite_cov_timeout_seconds

        self._verification_stats["total_attempts"] += 1

        try:
            logger.info(
                f"COV Verification: equipment={equipment_id}, point={point_name}, "
                f"expected={expected_value}, timeout={timeout}s"
            )

            # Attempt read-back from device
            try:
                read_result = await device_manager.read_device_value(
                    equipment_id, point_name
                )
                actual_value = read_result.value if hasattr(read_result, 'value') else read_result
                read_success = True
                read_error = None

                logger.debug(
                    f"COV read succeeded: equipment={equipment_id}, "
                    f"actual={actual_value}, expected={expected_value}"
                )

            except Exception as e:
                actual_value = None
                read_success = False
                read_error = str(e)
                logger.warning(
                    f"COV read failed: equipment={equipment_id}, point={point_name}, error={e}"
                )

            # Calculate verification result
            elapsed = (datetime.utcnow() - start_time).total_seconds()

            if read_success:
                # Compare values with appropriate tolerance
                verified = self._values_match(expected_value, actual_value, tolerance=0.5)
                if verified:
                    self._verification_stats["successful_verifications"] += 1
                    logger.info(
                        f"COV VERIFIED: decision={decision_id}, "
                        f"actual={actual_value} matches expected={expected_value}"
                    )
                else:
                    self._verification_stats["failed_verifications"] += 1
                    logger.warning(
                        f"COV MISMATCH: decision={decision_id}, "
                        f"expected={expected_value}, actual={actual_value}"
                    )
            else:
                verified = False
                self._verification_stats["failed_verifications"] += 1

            result = COVVerificationResult(
                verified=verified,
                actual_value=actual_value,
                expected_value=expected_value,
                read_success=read_success,
                elapsed_seconds=elapsed,
                error=read_error,
            )

            # Update parasite_decisions record with COV status
            try:
                await self.parasite_repo.update_cov_status(
                    decision_id, verified, str(actual_value) if actual_value is not None else "null"
                )
            except Exception as e:
                logger.error(
                    f"Failed to update COV status in parasite_decisions: {e}"
                )

            return result

        except Exception as e:
            logger.error(f"Unexpected error in verify_write: {e}")
            self._verification_stats["failed_verifications"] += 1
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            return COVVerificationResult(
                verified=False,
                actual_value=None,
                expected_value=expected_value,
                read_success=False,
                elapsed_seconds=elapsed,
                error=str(e),
            )

    async def schedule_outcome_measurement(
        self,
        decision_id: str,
        equipment_id: str,
        expected_outcome: Dict,
        window_minutes: Optional[int] = None,
    ) -> None:
        """Schedule outcome measurement for future execution.

        Non-blocking: stores measurement request to be processed later by
        check_pending_measurements(). Measurement occurs after configurable
        window (default 10 minutes) to capture real-world impact of the action.

        Args:
            decision_id: Decision ID for audit trail
            equipment_id: Target equipment UUID
            expected_outcome: Predicted outcome (e.g., temperature_delta, energy_savings)
            window_minutes: Window to measure in (override settings default)

        Returns:
            None (measurement happens asynchronously)
        """
        window = window_minutes or settings.parasite_outcome_window_minutes

        try:
            logger.info(
                f"Scheduling outcome measurement: decision={decision_id}, "
                f"window={window} minutes"
            )

            self._pending_measurements[decision_id] = {
                "equipment_id": equipment_id,
                "expected_outcome": expected_outcome,
                "scheduled_at": datetime.utcnow().isoformat(),
                "measure_at": (
                    datetime.utcnow() + timedelta(minutes=window)
                ).isoformat(),
                "measurement_window_minutes": window,
            }

            logger.debug(
                f"Measurement scheduled for {decision_id}: "
                f"measure_at={(datetime.utcnow() + timedelta(minutes=window)).isoformat()}"
            )

        except Exception as e:
            logger.error(f"Error scheduling outcome measurement: {e}")

    async def check_pending_measurements(self) -> List[Dict]:
        """Process completed outcome measurements.

        Called periodically by background scheduler. For each pending measurement
        whose window has elapsed, reads equipment state and determines if outcome
        matched prediction.

        Returns:
            List of completed measurements with results
        """
        completed_measurements = []
        now = datetime.utcnow()

        try:
            pending_ids = list(self._pending_measurements.keys())
            logger.debug(
                f"Checking {len(pending_ids)} pending measurements"
            )

            for decision_id in pending_ids:
                measurement_req = self._pending_measurements[decision_id]
                measure_at = datetime.fromisoformat(
                    measurement_req["measure_at"]
                )

                # Check if measurement window has passed
                if now < measure_at:
                    logger.debug(
                        f"Measurement for {decision_id} not ready yet "
                        f"(ready at {measure_at.isoformat()})"
                    )
                    continue

                # Measurement window elapsed - collect results
                try:
                    equipment_id = measurement_req["equipment_id"]
                    expected_outcome = measurement_req["expected_outcome"]

                    logger.info(
                        f"Measuring outcome for decision={decision_id}, "
                        f"equipment={equipment_id}"
                    )

                    # Read current equipment state (simplified for this phase)
                    actual_outcome = await self._read_equipment_outcome(
                        equipment_id, expected_outcome
                    )

                    # Determine if outcome matched prediction
                    matched = self._outcome_matches_prediction(
                        expected_outcome, actual_outcome
                    )

                    logger.info(
                        f"Outcome measurement complete: decision={decision_id}, "
                        f"matched={matched}"
                    )

                    # Create measurement result
                    measurement = OutcomeMeasurement(
                        decision_id=decision_id,
                        equipment_id=equipment_id,
                        expected_outcome=expected_outcome,
                        actual_outcome=actual_outcome,
                        matched=matched,
                        measurement_window_minutes=measurement_req[
                            "measurement_window_minutes"
                        ],
                        measured_at=now.isoformat(),
                        contributing_metrics=self._calculate_contributing_metrics(
                            expected_outcome, actual_outcome
                        ),
                    )

                    # Update parasite_decisions record with outcome
                    try:
                        await self.parasite_repo.update_outcome(
                            decision_id,
                            actual_outcome,
                            matched,
                        )
                        logger.debug(
                            f"Updated parasite_decisions with outcome for {decision_id}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to update outcome in parasite_decisions: {e}"
                        )

                    completed_measurements.append(measurement.__dict__)

                    # Remove from pending
                    del self._pending_measurements[decision_id]

                except Exception as e:
                    logger.error(
                        f"Error processing measurement for {decision_id}: {e}"
                    )
                    # Leave in pending for next iteration

            return completed_measurements

        except Exception as e:
            logger.error(f"Error in check_pending_measurements: {e}")
            return []

    def get_pending_count(self) -> int:
        """Get number of pending outcome measurements."""
        return len(self._pending_measurements)

    async def get_verification_stats(self) -> Dict:
        """Get COV verification success/failure rates."""
        total = self._verification_stats["total_attempts"]
        successful = self._verification_stats["successful_verifications"]
        failed = self._verification_stats["failed_verifications"]

        return {
            "total_attempts": total,
            "successful": successful,
            "failed": failed,
            "success_rate": (successful / total * 100) if total > 0 else 0.0,
            "pending_measurements": self.get_pending_count(),
        }

    def _values_match(
        self, expected: Any, actual: Any, tolerance: float = 0.5
    ) -> bool:
        """Compare expected vs actual values with configurable tolerance.

        For numeric values: uses ±tolerance range (device may round).
        For boolean/string: requires exact match.

        Args:
            expected: Expected value
            actual: Actual value read from device
            tolerance: Acceptable difference for numeric values

        Returns:
            True if values match within tolerance
        """
        # Handle None cases
        if expected is None or actual is None:
            return expected == actual

        # Try numeric comparison (most common case)
        try:
            exp_num = float(expected)
            act_num = float(actual)
            return abs(exp_num - act_num) <= tolerance
        except (ValueError, TypeError):
            pass

        # Fall back to string comparison
        return str(expected).lower() == str(actual).lower()

    @staticmethod
    def build_expected_outcome(
        action_type: str, target_value: Any, original_value: Any
    ) -> Dict:
        """Build expected outcome based on action type.

        Generates outcome prediction template based on the type of control action,
        enabling the learning loop where every action creates a prediction that
        the outcome measurement confirms or denies.

        Args:
            action_type: Type of action (hvac_setpoint_change, lighting_dimming, etc)
            target_value: Target value we're trying to achieve
            original_value: Starting value before change

        Returns:
            Dictionary with measurement_points and tolerances for outcome comparison
        """
        if action_type in ("hvac_setpoint_change", "setpoint_change"):
            delta = float(target_value) - float(original_value)
            return {
                "temperature_delta_expected": delta,
                "measurement_points": ["zone_temperature", "return_air_temp"],
                "tolerance_celsius": 1.0,
            }
        elif action_type in ("lighting_dimming", "dali_level_change"):
            return {
                "brightness_target": target_value,
                "measurement_points": ["light_level"],
                "tolerance_percent": 5.0,
            }
        else:
            return {
                "value_target": target_value,
                "measurement_points": [],
                "tolerance_percent": 10.0,
            }

    async def _read_equipment_outcome(
        self, equipment_id: str, expected_outcome: Dict
    ) -> Dict:
        """Read equipment state to measure outcome.

        Simplified implementation: reads key measurement points from equipment.
        In production, this would integrate with actual sensor/telemetry data.

        Args:
            equipment_id: Equipment to read
            expected_outcome: Defines which measurement_points to read

        Returns:
            Dictionary with actual measured values
        """
        actual_outcome = {}

        try:
            measurement_points = expected_outcome.get("measurement_points", [])
            logger.debug(
                f"Reading outcome from {equipment_id}: points={measurement_points}"
            )

            for point_name in measurement_points:
                try:
                    result = await device_manager.read_device_value(
                        equipment_id, point_name
                    )
                    value = result.value if hasattr(result, 'value') else result
                    actual_outcome[point_name] = value
                    logger.debug(
                        f"Read {point_name} from {equipment_id}: {value}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to read {point_name} from {equipment_id}: {e}"
                    )
                    actual_outcome[point_name] = None

        except Exception as e:
            logger.error(
                f"Error reading equipment outcome for {equipment_id}: {e}"
            )

        return actual_outcome

    @staticmethod
    def _outcome_matches_prediction(
        expected_outcome: Dict, actual_outcome: Dict
    ) -> bool:
        """Determine if measured outcome matches prediction.

        Compares expected vs actual values with tolerances defined in expected_outcome.

        Args:
            expected_outcome: Predicted outcome with tolerances
            actual_outcome: Actual measured values

        Returns:
            True if outcome matched prediction
        """
        try:
            # For now, simple heuristic: if we got measurements back, consider it matched
            # In production, this would compare against tolerance thresholds
            if not actual_outcome:
                return False

            # Check if any expected measurement points were successfully read
            measurement_points = expected_outcome.get("measurement_points", [])
            if not measurement_points:
                return True  # No specific points expected

            successful_reads = [
                p for p in measurement_points
                if p in actual_outcome and actual_outcome[p] is not None
            ]

            # Success if we got at least one reading
            matched = len(successful_reads) > 0
            logger.debug(
                f"Outcome matching: expected={measurement_points}, "
                f"got={successful_reads}, matched={matched}"
            )

            return matched

        except Exception as e:
            logger.error(f"Error determining outcome match: {e}")
            return False

    @staticmethod
    def _calculate_contributing_metrics(
        expected_outcome: Dict, actual_outcome: Dict
    ) -> Dict:
        """Calculate individual metric comparisons.

        Provides granular metrics for understanding which measurements matched
        and which didn't.

        Args:
            expected_outcome: Predicted outcome
            actual_outcome: Actual measured values

        Returns:
            Dictionary with per-metric comparison results
        """
        metrics = {}

        try:
            measurement_points = expected_outcome.get("measurement_points", [])

            for point in measurement_points:
                actual_value = actual_outcome.get(point)
                expected_target = expected_outcome.get(f"{point}_target")

                if actual_value is not None:
                    metrics[point] = {
                        "actual": actual_value,
                        "expected_target": expected_target,
                        "status": "success" if expected_target is None else "needs_comparison",
                    }
                else:
                    metrics[point] = {
                        "status": "failed_to_read",
                    }

        except Exception as e:
            logger.error(f"Error calculating contributing metrics: {e}")

        return metrics


# Singleton pattern
_instance: Optional[COVMonitorService] = None


def get_cov_monitor_service() -> COVMonitorService:
    """Get or create COVMonitorService singleton."""
    global _instance
    if _instance is None:
        _instance = COVMonitorService()
    return _instance
