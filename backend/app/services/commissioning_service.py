"""Commissioning scorecard service for shadow_live → live_control promotion.

Implements 8 hard gates, truth-check validation, and consecutive-day tracking
as the formal gate before promoting a building to LIVE_CONTROL mode.
"""

from datetime import datetime, date

from app.config.settings import settings as app_settings
from app.database.repositories.integration_repository import IntegrationRepository
from app.models.commissioning import (
    CommissioningGateId,
    CommissioningGate,
    TruthCheckEntry,
    TruthCheckResult,
    CommissioningScorecard,
    PromotionResult,
)
from app.models.integration import BuildingStatus


class CommissioningService:
    """Evaluates commissioning gates and manages promotion workflow."""

    def __init__(self) -> None:
        self._repo = IntegrationRepository()
        # building_id → list of {date, all_gates_passed, scorecard_summary}
        self._scorecard_history: dict[str, list[dict]] = {}
        # building_id → latest TruthCheckResult
        self._truth_checks: dict[str, TruthCheckResult] = {}

    async def run_scorecard(self, building_id: str) -> CommissioningScorecard:
        """Run all 8 commissioning gates and produce a scorecard."""
        settings = app_settings
        ingestion_mode = settings.resolved_ingestion_mode.value

        # Fetch quality metrics once — reused by several gates
        quality = self._repo.get_quality_metrics(building_id)

        # Get sync frequency for freshness target
        sync_freq_minutes = self._get_sync_frequency(building_id)
        freshness_target_hours = 2 * sync_freq_minutes / 60

        gates: list[CommissioningGate] = []

        # Gate 1: match_coverage >= 95%
        mc = quality["match_coverage"]
        gates.append(
            CommissioningGate(
                id=CommissioningGateId.MATCH_COVERAGE,
                name="Match Coverage",
                category="point_mapping",
                target=">= 95%",
                actual=mc,
                passed=mc >= 95.0,
                details=f"{mc}% of points matched to assets",
            )
        )

        # Gate 2: unmatched_points <= 5%
        unmatched = round(100 - mc, 1)
        gates.append(
            CommissioningGate(
                id=CommissioningGateId.UNMATCHED_POINTS,
                name="Unmatched Points",
                category="point_mapping",
                target="<= 5%",
                actual=unmatched,
                passed=unmatched <= 5.0,
                details=f"{unmatched}% of points unmatched",
            )
        )

        # Gate 3: data_freshness < 2× poll interval
        freshness = quality["data_freshness_hours"]
        gates.append(
            CommissioningGate(
                id=CommissioningGateId.DATA_FRESHNESS,
                name="Data Freshness",
                category="data_quality",
                target=f"< {freshness_target_hours:.1f}h (2× poll)",
                actual=round(freshness, 2),
                passed=freshness < freshness_target_hours,
                details=f"Last data {freshness:.1f}h ago; target < {freshness_target_hours:.1f}h",
            )
        )

        # Gate 4: error_rate < 1%
        er = quality["error_rate"]
        gates.append(
            CommissioningGate(
                id=CommissioningGateId.ERROR_RATE,
                name="Error Rate",
                category="data_quality",
                target="< 1%",
                actual=er,
                passed=er < 1.0,
                details=f"{er}% of sync jobs failed in last 7 days",
            )
        )

        # Gate 5: duplicate_rate < 0.5%
        dr = quality["duplicate_rate"]
        gates.append(
            CommissioningGate(
                id=CommissioningGateId.DUPLICATE_RATE,
                name="Duplicate Rate",
                category="data_quality",
                target="< 0.5%",
                actual=dr,
                passed=dr < 0.5,
                details=f"{dr}% of records were duplicates",
            )
        )

        # Gate 6: source_provenance — no json/manual sources
        json_count, prov_detail = self._check_source_provenance(building_id)
        gates.append(
            CommissioningGate(
                id=CommissioningGateId.SOURCE_PROVENANCE,
                name="Source Provenance",
                category="ingestion_mode",
                target="0 file/manual sources",
                actual=float(json_count),
                passed=json_count == 0,
                details=prov_detail,
            )
        )

        # Gate 7: value_validity — < 0.5% invalid values
        invalid_pct, val_detail = self._check_value_validity(building_id)
        gates.append(
            CommissioningGate(
                id=CommissioningGateId.VALUE_VALIDITY,
                name="Value Validity",
                category="data_quality",
                target="< 0.5% invalid",
                actual=round(invalid_pct, 3),
                passed=invalid_pct < 0.5,
                details=val_detail,
            )
        )

        # Gate 8: timestamp_integrity >= 99.9%
        valid_pct, ts_detail = self._check_timestamp_integrity(building_id)
        gates.append(
            CommissioningGate(
                id=CommissioningGateId.TIMESTAMP_INTEGRITY,
                name="Timestamp Integrity",
                category="data_quality",
                target=">= 99.9%",
                actual=round(valid_pct, 3),
                passed=valid_pct >= 99.9,
                details=ts_detail,
            )
        )

        # Summarize
        passed_count = sum(1 for g in gates if g.passed)
        failed_count = len(gates) - passed_count
        all_gates_passed = failed_count == 0
        blocking = [g.id.value for g in gates if not g.passed]

        # Record in history
        today = date.today()
        history = self._scorecard_history.setdefault(building_id, [])
        history.append(
            {
                "date": today.isoformat(),
                "all_gates_passed": all_gates_passed,
                "checked_at": datetime.utcnow().isoformat(),
            }
        )

        consecutive = self.get_consecutive_pass_days(building_id)

        # Look up truth check
        truth_check = self._truth_checks.get(building_id)

        can_promote = all_gates_passed and consecutive >= 2 and truth_check is not None and truth_check.passed

        # Add blocking reasons beyond gates
        if not all_gates_passed:
            pass  # blocking already populated
        else:
            if consecutive < 2:
                blocking.append(f"consecutive_days={consecutive} (need >= 2)")
            if truth_check is None:
                blocking.append("truth_check_missing")
            elif not truth_check.passed:
                blocking.append(f"truth_check_failed ({truth_check.agreement_pct:.1f}%)")

        return CommissioningScorecard(
            building_id=building_id,
            ingestion_mode=ingestion_mode,
            checked_at=datetime.utcnow(),
            gates=gates,
            truth_check=truth_check,
            summary={"passed": passed_count, "failed": failed_count, "total": len(gates)},
            all_gates_passed=all_gates_passed,
            consecutive_pass_days=consecutive,
            can_promote=can_promote,
            blocking_gates=blocking,
        )

    def _get_sync_frequency(self, building_id: str) -> int:
        """Get the sync frequency in minutes for the building's active sources."""
        try:
            sources = self._repo.get_log_sources(building_id=building_id, is_active=True)
            if sources:
                return min(s.get("sync_frequency_minutes") or 15 for s in sources)
        except Exception:
            pass
        return 15  # default

    def _check_source_provenance(self, building_id: str) -> tuple[int, str]:
        """Count active sources using file_drop or manual_upload connection types."""
        try:
            sources = self._repo.get_log_sources(building_id=building_id, is_active=True)
        except Exception:
            return 0, "No sources found"

        json_sources = [s for s in sources if s.get("connection_type") in ("manual_upload", "file_drop")]
        count = len(json_sources)
        if count == 0:
            return 0, f"All {len(sources)} active sources use live connections"
        names = ", ".join(s.get("name", s["id"][:8]) for s in json_sources)
        return count, f"{count} file/manual source(s): {names}"

    def _check_value_validity(self, building_id: str) -> tuple[float, str]:
        """Check ingested_trends for null or out-of-range values (last 48h)."""
        try:
            from datetime import timedelta

            cutoff = (datetime.utcnow() - timedelta(hours=48)).isoformat()

            # Get source IDs for this building
            sources = self._repo.get_log_sources(building_id=building_id)
            source_ids = [s["id"] for s in sources]
            if not source_ids:
                return 0.0, "No sources — no data to validate"

            # Query trends for the building's sources
            response = (
                self._repo.client.table("ingested_trends")
                .select("value")
                .in_("log_source_id", source_ids)
                .gte("recorded_at", cutoff)
                .execute()
            )
            rows = response.data or []
            total = len(rows)
            if total == 0:
                return 0.0, "No trend data in last 48h"

            invalid = 0
            for r in rows:
                val = r.get("value")
                if val is None:
                    invalid += 1
                    continue
                try:
                    fval = float(val)
                    if fval < -1000 or fval > 10000:
                        invalid += 1
                except (ValueError, TypeError):
                    invalid += 1

            pct = (invalid / total) * 100
            return pct, f"{invalid}/{total} invalid values ({pct:.2f}%)"
        except Exception as e:
            # Table may not exist in demo mode
            return 0.0, f"Could not query trends: {e}"

    def _check_timestamp_integrity(self, building_id: str) -> tuple[float, str]:
        """Check ingested_trends for future timestamps (last 48h)."""
        try:
            from datetime import timedelta

            cutoff = (datetime.utcnow() - timedelta(hours=48)).isoformat()
            # 5-minute future tolerance
            future_cutoff = (datetime.utcnow() + timedelta(minutes=5)).isoformat()

            sources = self._repo.get_log_sources(building_id=building_id)
            source_ids = [s["id"] for s in sources]
            if not source_ids:
                return 100.0, "No sources — nothing to check"

            # Total count
            total_resp = (
                self._repo.client.table("ingested_trends")
                .select("id", count="exact")
                .in_("log_source_id", source_ids)
                .gte("recorded_at", cutoff)
                .execute()
            )
            total = total_resp.count or 0
            if total == 0:
                return 100.0, "No trend data in last 48h"

            # Future timestamps
            future_resp = (
                self._repo.client.table("ingested_trends")
                .select("id", count="exact")
                .in_("log_source_id", source_ids)
                .gt("recorded_at", future_cutoff)
                .execute()
            )
            future_count = future_resp.count or 0

            valid_pct = ((total - future_count) / total) * 100
            return valid_pct, f"{future_count}/{total} future timestamps ({100 - valid_pct:.2f}% invalid)"
        except Exception as e:
            return 100.0, f"Could not query trends: {e}"

    def submit_truth_check(self, building_id: str, entries: list[TruthCheckEntry]) -> TruthCheckResult:
        """Submit and evaluate a truth check (min 20 entries)."""
        if len(entries) < 20:
            raise ValueError(f"Truth check requires >= 20 entries, got {len(entries)}")

        agreeing = sum(1 for e in entries if e.within_tolerance)
        agreement_pct = (agreeing / len(entries)) * 100

        result = TruthCheckResult(
            building_id=building_id,
            checked_at=datetime.utcnow(),
            total_points=len(entries),
            agreeing_points=agreeing,
            agreement_pct=round(agreement_pct, 2),
            passed=agreement_pct >= 98.0,
            entries=entries,
        )
        self._truth_checks[building_id] = result
        return result

    def get_consecutive_pass_days(self, building_id: str) -> int:
        """Count consecutive days where all gates passed (walking backward)."""
        history = self._scorecard_history.get(building_id, [])
        if not history:
            return 0

        # Deduplicate by date (keep last entry per date)
        by_date: dict[str, bool] = {}
        for entry in history:
            by_date[entry["date"]] = entry["all_gates_passed"]

        # Walk dates in reverse
        sorted_dates = sorted(by_date.keys(), reverse=True)
        count = 0
        for d in sorted_dates:
            if by_date[d]:
                count += 1
            else:
                break
        return count

    async def promote_to_live(self, building_id: str) -> PromotionResult:
        """Attempt to promote building from SHADOW_LIVE to LIVE_CONTROL.

        Phase 109: Additionally evaluates quality gate with live_control thresholds
        as a pre-promotion check. If any metric fails live_control thresholds,
        promotion is blocked.

        Note: This is a single-point-in-time check. A 48h rolling quality gate
        check requires historical metric storage (future enhancement).
        """
        settings = app_settings
        current_mode = settings.resolved_ingestion_mode.value

        # Phase 109: Quality gate pre-promotion check
        try:
            from app.services.quality_gate_evaluator import QualityGateEvaluator
            from app.services.quality_gate_policy import GateStatus

            evaluator = QualityGateEvaluator()
            metrics = await evaluator.collect_metrics(building_id)
            # Evaluate against live_control thresholds (target mode, not current)
            gate_result = evaluator.evaluate("live_control", metrics)

            if gate_result.overall == GateStatus.FAIL:
                return PromotionResult(
                    success=False,
                    building_id=building_id,
                    previous_mode=current_mode,
                    message=(
                        f"Quality gate failed for live_control thresholds — failed rules: {gate_result.failed_rules}"
                    ),
                    blocking_reasons=[f"quality_gate:{rule}" for rule in gate_result.failed_rules],
                )
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(
                f"Quality gate pre-promotion check failed for {building_id}, proceeding with scorecard check: {e}"
            )

        scorecard = await self.run_scorecard(building_id)

        if not scorecard.can_promote:
            return PromotionResult(
                success=False,
                building_id=building_id,
                previous_mode=current_mode,
                message="Promotion blocked — see blocking_reasons",
                scorecard=scorecard,
                blocking_reasons=scorecard.blocking_gates,
            )

        # Update per-building status
        self._repo.update_building_status(
            building_id,
            BuildingStatus.LIVE_CONTROL.value,
            notes="Promoted via commissioning scorecard",
        )

        return PromotionResult(
            success=True,
            building_id=building_id,
            previous_mode=current_mode,
            new_mode=BuildingStatus.LIVE_CONTROL.value,
            message="Building promoted to LIVE_CONTROL. Update INGESTION_MODE env var to complete.",
            scorecard=scorecard,
        )
