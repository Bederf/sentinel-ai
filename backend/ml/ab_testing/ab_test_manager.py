"""
A/B Test Manager for ML Models

Manages controlled experiments between model versions:
- Creates tests (candidate vs control/current active)
- Hash-based traffic splitting (10% to candidate)
- Evaluates test results and promotes winners
"""

import hashlib
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

CANDIDATE_TRAFFIC_PCT = 10  # 10% traffic to candidate model


class TestStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    PROMOTED = "promoted"
    CANCELLED = "cancelled"


@dataclass
class ABTest:
    """An A/B test between two model versions."""
    test_id: str
    model_type: str
    equipment_type: str
    control_model_id: str
    candidate_model_id: str
    status: TestStatus = TestStatus.RUNNING
    created_at: str = ""
    completed_at: Optional[str] = None
    control_metrics: Dict[str, float] = field(default_factory=dict)
    candidate_metrics: Dict[str, float] = field(default_factory=dict)
    control_assignments: int = 0
    candidate_assignments: int = 0
    winner: Optional[str] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class ABTestManager:
    """Manages A/B tests between ML model versions."""

    def __init__(self):
        self._tests: Dict[str, ABTest] = {}
        self._next_id = 1

    def create_test(
        self,
        model_type: str,
        equipment_type: str,
        candidate_model_id: str,
    ) -> Dict[str, Any]:
        """Create a new A/B test.

        The control model is the current active model from the registry.
        The candidate is the new model to evaluate.

        Args:
            model_type: e.g. "lstm", "autoencoder"
            equipment_type: e.g. "chiller", "ahu"
            candidate_model_id: ID of the candidate model to test

        Returns:
            Test details dict
        """
        from ml.registry import get_model_registry
        registry = get_model_registry()

        # Get current active as control
        active = registry.get_active_model(model_type, equipment_type)
        if not active:
            return {
                "success": False,
                "error": f"No active model found for {model_type}/{equipment_type}",
            }

        control_id = active["model_id"]

        # Verify candidate exists
        candidate = registry.get_model(candidate_model_id)
        if not candidate:
            return {
                "success": False,
                "error": f"Candidate model {candidate_model_id} not found",
            }

        test_id = f"ab_{self._next_id:04d}"
        self._next_id += 1

        test = ABTest(
            test_id=test_id,
            model_type=model_type,
            equipment_type=equipment_type,
            control_model_id=control_id,
            candidate_model_id=candidate_model_id,
        )
        self._tests[test_id] = test

        logger.info(
            f"A/B test created: {test_id} - {control_id} vs {candidate_model_id}"
        )

        return {
            "success": True,
            "test_id": test_id,
            "control_model_id": control_id,
            "candidate_model_id": candidate_model_id,
            "traffic_split": f"{100 - CANDIDATE_TRAFFIC_PCT}% control / {CANDIDATE_TRAFFIC_PCT}% candidate",
        }

    def assign_model(self, test_id: str, equipment_id: str) -> str:
        """Determine which model to use for a given equipment_id.

        Uses hash-based bucketing for consistent assignment:
        - Same equipment_id always gets same model within a test
        - ~10% of equipment goes to candidate

        Args:
            test_id: The A/B test ID
            equipment_id: Equipment code (e.g. S002-CHILLER-B1-001)

        Returns:
            Model ID to use (control or candidate)
        """
        test = self._tests.get(test_id)
        if not test or test.status != TestStatus.RUNNING:
            # Default to control
            return test.control_model_id if test else ""

        # Hash-based bucket assignment
        hash_input = f"{test_id}:{equipment_id}"
        hash_val = int(hashlib.sha256(hash_input.encode()).hexdigest(), 16)
        bucket = hash_val % 100

        if bucket < CANDIDATE_TRAFFIC_PCT:
            test.candidate_assignments += 1
            return test.candidate_model_id
        else:
            test.control_assignments += 1
            return test.control_model_id

    def record_outcome(
        self,
        test_id: str,
        model_id: str,
        metric_name: str,
        metric_value: float,
    ):
        """Record an outcome metric for a model in a test.

        Args:
            test_id: The A/B test ID
            model_id: Which model produced this outcome
            metric_name: e.g. "accuracy", "mae", "f1"
            metric_value: The metric value
        """
        test = self._tests.get(test_id)
        if not test:
            return

        if model_id == test.control_model_id:
            if metric_name not in test.control_metrics:
                test.control_metrics[metric_name] = 0.0
            # Running average
            n = test.control_assignments or 1
            test.control_metrics[metric_name] = (
                test.control_metrics[metric_name] * (n - 1) + metric_value
            ) / n
        elif model_id == test.candidate_model_id:
            if metric_name not in test.candidate_metrics:
                test.candidate_metrics[metric_name] = 0.0
            n = test.candidate_assignments or 1
            test.candidate_metrics[metric_name] = (
                test.candidate_metrics[metric_name] * (n - 1) + metric_value
            ) / n

    def evaluate_test(self, test_id: str) -> Dict[str, Any]:
        """Evaluate A/B test results.

        Returns comparison of control vs candidate metrics.
        """
        test = self._tests.get(test_id)
        if not test:
            return {"error": f"Test {test_id} not found"}

        # Determine winner based on primary metric (accuracy or f1_score)
        winner = None
        primary_metric = "accuracy"

        control_val = test.control_metrics.get(primary_metric, 0)
        candidate_val = test.candidate_metrics.get(primary_metric, 0)

        if candidate_val > control_val * 1.05:  # 5% improvement threshold
            winner = "candidate"
        elif control_val >= candidate_val:
            winner = "control"
        else:
            winner = "inconclusive"

        test.winner = winner

        return {
            "test_id": test.test_id,
            "status": test.status.value,
            "model_type": test.model_type,
            "equipment_type": test.equipment_type,
            "control": {
                "model_id": test.control_model_id,
                "assignments": test.control_assignments,
                "metrics": test.control_metrics,
            },
            "candidate": {
                "model_id": test.candidate_model_id,
                "assignments": test.candidate_assignments,
                "metrics": test.candidate_metrics,
            },
            "winner": winner,
            "created_at": test.created_at,
        }

    def promote_candidate(self, test_id: str) -> Dict[str, Any]:
        """Promote the candidate model to active in the registry.

        Args:
            test_id: The A/B test to promote

        Returns:
            Result dict with success status
        """
        test = self._tests.get(test_id)
        if not test:
            return {"success": False, "error": f"Test {test_id} not found"}

        if test.status != TestStatus.RUNNING:
            return {"success": False, "error": f"Test is {test.status.value}, not running"}

        try:
            from ml.registry import get_model_registry
            registry = get_model_registry()

            # Promote candidate to active
            registry.set_active(test.candidate_model_id)

            test.status = TestStatus.PROMOTED
            test.completed_at = datetime.now().isoformat()

            logger.info(
                f"A/B test {test_id}: promoted {test.candidate_model_id} to active"
            )

            return {
                "success": True,
                "test_id": test_id,
                "promoted_model_id": test.candidate_model_id,
                "previous_model_id": test.control_model_id,
            }

        except Exception as e:
            logger.error(f"Promotion failed for test {test_id}: {e}")
            return {"success": False, "error": str(e)}

    def cancel_test(self, test_id: str) -> Dict[str, Any]:
        """Cancel a running test."""
        test = self._tests.get(test_id)
        if not test:
            return {"success": False, "error": f"Test {test_id} not found"}

        test.status = TestStatus.CANCELLED
        test.completed_at = datetime.now().isoformat()
        return {"success": True, "test_id": test_id}

    def list_tests(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all A/B tests, optionally filtered by status."""
        tests = list(self._tests.values())
        if status:
            tests = [t for t in tests if t.status.value == status]

        return [
            {
                "test_id": t.test_id,
                "model_type": t.model_type,
                "equipment_type": t.equipment_type,
                "control_model_id": t.control_model_id,
                "candidate_model_id": t.candidate_model_id,
                "status": t.status.value,
                "created_at": t.created_at,
                "completed_at": t.completed_at,
                "control_assignments": t.control_assignments,
                "candidate_assignments": t.candidate_assignments,
                "winner": t.winner,
            }
            for t in tests
        ]


# Singleton
_manager: Optional[ABTestManager] = None


def get_ab_test_manager() -> ABTestManager:
    """Get singleton ABTestManager instance."""
    global _manager
    if _manager is None:
        _manager = ABTestManager()
    return _manager
