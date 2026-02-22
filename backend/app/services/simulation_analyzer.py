"""Simulation analyzer - computes metrics and applies optimization profile weights."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from app.models.simulation_analytics import (
    OptimizationProfile,
    ProfileAnalysisResult,
    SimulationAnalysisReport,
    SimulationEvent,
    SimulationMetrics,
    SimulationRunRecord,
)

logger = logging.getLogger(__name__)

LOG_DIR = Path(__file__).parent.parent / "data" / "simulation_logs"
PROFILES_PATH = Path(__file__).parent.parent / "data" / "optimization_profiles.json"


def _load_profiles() -> Dict[str, OptimizationProfile]:
    """Load optimization profiles from config file."""
    if not PROFILES_PATH.exists():
        return {}
    data = json.loads(PROFILES_PATH.read_text())
    return {key: OptimizationProfile(**val) for key, val in data.get("profiles", {}).items()}


class SimulationAnalyzer:
    """Analyzes simulation run data against optimization profiles."""

    def __init__(self, log_dir: Path = LOG_DIR):
        self.log_dir = log_dir
        self.profiles = _load_profiles()

    def list_runs(self) -> List[SimulationRunRecord]:
        """List all simulation runs from metadata files."""
        runs = []
        for meta_file in sorted(self.log_dir.glob("*_meta.json"), reverse=True):
            try:
                data = json.loads(meta_file.read_text())
                runs.append(SimulationRunRecord(**data))
            except Exception as e:
                logger.warning(f"Skipping invalid meta file {meta_file}: {e}")
        return runs

    def get_run(self, run_id: str) -> Optional[SimulationRunRecord]:
        """Get metadata for a specific run."""
        meta_path = self.log_dir / f"{run_id}_meta.json"
        if not meta_path.exists():
            return None
        data = json.loads(meta_path.read_text())
        return SimulationRunRecord(**data)

    def get_events(
        self,
        run_id: str,
        event_type: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> List[SimulationEvent]:
        """Read events from JSONL file with optional filtering and pagination."""
        events_path = self.log_dir / f"{run_id}_events.jsonl"
        if not events_path.exists():
            return []

        events = []
        count = 0
        with open(events_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if event_type and evt.get("event_type") != event_type:
                    continue

                if count < offset:
                    count += 1
                    continue

                events.append(SimulationEvent(**evt))
                if len(events) >= limit:
                    break
                count += 1

        return events

    def compute_metrics(self, run_id: str) -> SimulationMetrics:
        """Compute aggregate metrics from simulation events."""
        events_path = self.log_dir / f"{run_id}_events.jsonl"
        if not events_path.exists():
            return SimulationMetrics()

        metrics = SimulationMetrics()
        fault_times: Dict[str, str] = {}  # equipment_id -> fault timestamp
        repair_durations: List[float] = []

        with open(events_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue

                metrics.total_events += 1
                etype = evt.get("event_type", "")
                hour = evt.get("simulated_hour", 0)
                equip_id = evt.get("equipment_id")

                # Count by hour
                metrics.events_by_hour[hour] = metrics.events_by_hour.get(hour, 0) + 1

                if etype == "equipment_fault":
                    metrics.total_faults += 1
                    fault_type = evt.get("details", {}).get("fault_type", "unknown")
                    metrics.fault_types[fault_type] = metrics.fault_types.get(fault_type, 0) + 1
                    if equip_id:
                        fault_times[equip_id] = evt.get("timestamp", "")

                elif etype == "repair_completed":
                    metrics.faults_repaired += 1
                    if equip_id and equip_id in fault_times:
                        try:
                            fault_t = datetime.fromisoformat(fault_times[equip_id])
                            repair_t = datetime.fromisoformat(evt.get("timestamp", ""))
                            duration_hours = (repair_t - fault_t).total_seconds() / 3600.0
                            repair_durations.append(duration_hours)
                        except (ValueError, TypeError):
                            pass

                elif etype == "alert_generated":
                    metrics.alerts_generated += 1

                elif etype == "work_order_created":
                    metrics.work_orders_created += 1

                elif etype == "ai_optimization":
                    # Count only summary events (no equipment_id) to avoid
                    # inflating the count with per-equipment detail events
                    if not equip_id:
                        metrics.ai_optimizations += 1

                elif etype == "setpoint_change":
                    metrics.setpoint_changes += 1
                    details = evt.get("details", {})
                    if "temperature" in details or "setpoint" in details:
                        metrics.comfort_deviations.append(
                            {
                                "hour": hour,
                                "equipment_id": equip_id,
                                "details": details,
                            }
                        )

                # Track equipment activity as proxy for runtime.
                # Only count events that carry an equipment_id.
                # Excluded: building_wake, peak_load, occupancy_increase
                # (building-level events that never have equipment_id).
                if equip_id and etype in (
                    "ai_optimization",
                    "setpoint_change",
                    "equipment_fault",
                    "repair_completed",
                ):
                    metrics.equipment_runtime_hours[equip_id] = metrics.equipment_runtime_hours.get(equip_id, 0) + 1

        if repair_durations:
            metrics.mean_time_to_repair_hours = round(sum(repair_durations) / len(repair_durations), 2)

        return metrics

    def score_profile(self, metrics: SimulationMetrics, profile: OptimizationProfile) -> ProfileAnalysisResult:
        """Score simulation metrics against an optimization profile."""
        weights = profile.weights
        thresholds = profile.thresholds
        scores: Dict[str, float] = {}
        flags: List[str] = []
        recommendations: List[str] = []

        # Runtime score (0-100): higher utilization = higher score
        total_equip = max(len(metrics.equipment_runtime_hours), 1)
        avg_runtime = (
            sum(metrics.equipment_runtime_hours.values()) / total_equip if metrics.equipment_runtime_hours else 0
        )
        runtime_score = min(100, (avg_runtime / 16.0) * 100)  # 16h as baseline
        scores["runtime"] = round(runtime_score, 1)

        if "min_runtime_utilization_pct" in thresholds:
            if runtime_score < thresholds["min_runtime_utilization_pct"]:
                flags.append(
                    f"Runtime utilization {runtime_score:.0f}% below "
                    f"threshold {thresholds['min_runtime_utilization_pct']}%"
                )
                recommendations.append("Increase equipment scheduling density")

        # Comfort score (0-100): fewer deviations = higher score
        deviation_count = len(metrics.comfort_deviations)
        comfort_score = max(0, 100 - deviation_count * 10)
        scores["comfort"] = round(comfort_score, 1)

        if "max_comfort_deviation_c" in thresholds and deviation_count > 0:
            flags.append(f"{deviation_count} comfort deviation events detected")
            recommendations.append("Tighten setpoint control and response time")

        # Cost score (0-100): more optimization actions = better cost management
        opt_actions = metrics.ai_optimizations + metrics.setpoint_changes
        cost_score = min(100, opt_actions * 15)  # Each action worth 15 points
        scores["cost"] = round(cost_score, 1)

        # Maintenance score (0-100): fast repair + low fault rate = high score
        mttr = metrics.mean_time_to_repair_hours or 0
        if metrics.total_faults == 0:
            maint_score = 100.0
        elif mttr > 0:
            maint_score = max(0, 100 - mttr * 20)  # Lose 20 pts per hour MTTR
        else:
            maint_score = max(0, 100 - metrics.total_faults * 15)
        scores["maintenance"] = round(maint_score, 1)

        if "max_acceptable_mttr_hours" in thresholds and mttr > thresholds["max_acceptable_mttr_hours"]:
            flags.append(f"MTTR {mttr:.1f}h exceeds threshold {thresholds['max_acceptable_mttr_hours']}h")
            recommendations.append("Improve technician response time or pre-position parts")

        # Energy score (0-100): optimization actions help, faults hurt
        energy_score = min(100, metrics.ai_optimizations * 20)
        if metrics.total_faults > 0:
            energy_score = max(0, energy_score - metrics.total_faults * 10)
        scores["energy"] = round(energy_score, 1)

        # Weighted overall score
        overall = sum(
            scores.get(dim, 0) * weights.get(dim, 0) for dim in ("runtime", "comfort", "cost", "maintenance", "energy")
        )

        return ProfileAnalysisResult(
            profile_name=profile.name,
            overall_score=round(overall, 1),
            component_scores=scores,
            recommendations=recommendations,
            flags=flags,
        )

    def analyze_run(
        self, run_id: str, custom_profiles: Optional[Dict[str, OptimizationProfile]] = None
    ) -> Optional[SimulationAnalysisReport]:
        """Generate full analysis report for a simulation run."""
        run = self.get_run(run_id)
        if not run:
            logger.warning(f"Run {run_id} not found")
            return None

        metrics = self.compute_metrics(run_id)
        profiles = custom_profiles or self.profiles
        profile_results = {}

        for key, profile in profiles.items():
            result = self.score_profile(metrics, profile)
            profile_results[key] = result

        report = SimulationAnalysisReport(
            run_id=run_id,
            scenario=run.scenario,
            building_code=run.building_code,
            analyzed_at=datetime.now().isoformat(),
            metrics=metrics,
            profile_results=profile_results,
        )

        # Save report to file
        report_path = self.log_dir / f"{run_id}_analysis.json"
        report_path.write_text(report.model_dump_json(indent=2))
        logger.info(f"Analysis report saved: {report_path}")

        return report

    def get_analysis(self, run_id: str) -> Optional[SimulationAnalysisReport]:
        """Get existing analysis report or generate one."""
        report_path = self.log_dir / f"{run_id}_analysis.json"
        if report_path.exists():
            data = json.loads(report_path.read_text())
            return SimulationAnalysisReport(**data)
        return self.analyze_run(run_id)

    def get_profiles(self) -> Dict[str, OptimizationProfile]:
        """Return loaded optimization profiles."""
        return self.profiles
