"""Tests for control tier behavior in recommendation workflow.

Tests the three control tiers:
- Tier 1 (Monitor): Display only, no execution
- Tier 2 (Human-in-Loop): All recommendations pending until approved
- Tier 3 (Auto-Execute): Low-risk auto-executed, high-risk pending
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.optimization import SiteProfileConfig
from app.models.recommendation import (
    ActionRiskLevel,
    Recommendation,
    RecommendationStatus,
)
from app.services.recommendation_service import RecommendationService


@pytest.mark.asyncio
class TestControlTierBehavior:
    """Test suite for control tier behavior."""

    @pytest.fixture
    def service(self):
        """Create a RecommendationService instance."""
        return RecommendationService()

    @pytest.fixture
    def mock_profile_config(self):
        """Create a mock SiteProfileConfig."""
        return SiteProfileConfig(
            site_id="site-002",
            active_profile="cost",
            control_tier="human_in_loop",  # Default
        )

    # =========================================================================
    # Tier 1: Monitor (Display Only)
    # =========================================================================

    async def test_tier1_monitor_only(self, service):
        """Tier 1: Display only, no execution."""
        with patch.object(service.profile_service, "load_site_profile_config") as mock_load:
            config = SiteProfileConfig(
                site_id="site-002",
                active_profile="cost",
                control_tier="monitor",
            )
            mock_load.return_value = config

            rec_data = {
                "site_id": "site-002",
                "action_type": "hvac_setpoint_change",
                "target_equipment": "S002-CHILLER-B1-001",
                "action": {"point": "supply_setpoint", "value": 18},
                "reason": "Reduce energy consumption",
                "confidence": "high",
            }

            rec = await service.create_recommendation(rec_data)

            # Tier 1: Should always require approval (display only)
            assert rec.requires_approval is True
            assert rec.status == RecommendationStatus.PENDING

    async def test_tier1_all_risk_levels_pending(self, service):
        """Tier 1: All risk levels pending (including low-risk)."""
        with patch.object(service.profile_service, "load_site_profile_config") as mock_load:
            config = SiteProfileConfig(
                site_id="site-002",
                active_profile="cost",
                control_tier="monitor",
            )
            mock_load.return_value = config

            risk_levels = [
                ("hvac_setpoint_change", ActionRiskLevel.LOW),
                ("equipment_staging", ActionRiskLevel.MEDIUM),
                ("generator_start", ActionRiskLevel.HIGH),
            ]

            for action_type, expected_risk in risk_levels:
                rec_data = {
                    "site_id": "site-002",
                    "action_type": action_type,
                    "target_equipment": "S002-CHILLER-B1-001",
                    "action": {"point": "test", "value": 1},
                    "reason": "Test",
                }

                rec = await service.create_recommendation(rec_data)

                # All require approval in Tier 1
                assert rec.requires_approval is True
                assert rec.status == RecommendationStatus.PENDING
                assert rec.risk_level == expected_risk

    # =========================================================================
    # Tier 2: Human-in-Loop (Always Approve)
    # =========================================================================

    async def test_tier2_all_pending_until_approved(self, service):
        """Tier 2: All recommendations pending until approved."""
        with patch.object(service.profile_service, "load_site_profile_config") as mock_load:
            config = SiteProfileConfig(
                site_id="site-002",
                active_profile="cost",
                control_tier="human_in_loop",
            )
            mock_load.return_value = config

            rec_data = {
                "site_id": "site-002",
                "action_type": "hvac_setpoint_change",
                "target_equipment": "S002-CHILLER-B1-001",
                "action": {"point": "supply_setpoint", "value": 18},
                "reason": "Test",
            }

            rec = await service.create_recommendation(rec_data)

            # Tier 2: Should require approval
            assert rec.requires_approval is True
            assert rec.status == RecommendationStatus.PENDING

    async def test_tier2_low_risk_also_requires_approval(self, service):
        """Tier 2: Even low-risk actions require approval."""
        with patch.object(service.profile_service, "load_site_profile_config") as mock_load:
            config = SiteProfileConfig(
                site_id="site-002",
                active_profile="cost",
                control_tier="human_in_loop",
            )
            mock_load.return_value = config

            rec_data = {
                "site_id": "site-002",
                "action_type": "lighting_dim",  # LOW risk
                "target_equipment": "S002-DALI-L2-01",
                "action": {"point": "brightness", "value": 50},
                "reason": "Test",
            }

            rec = await service.create_recommendation(rec_data)

            # Even low-risk requires approval in Tier 2
            assert rec.requires_approval is True
            assert rec.status == RecommendationStatus.PENDING
            assert rec.risk_level == ActionRiskLevel.LOW

    async def test_tier2_high_risk_also_requires_approval(self, service):
        """Tier 2: High-risk actions also require approval (same as low-risk)."""
        with patch.object(service.profile_service, "load_site_profile_config") as mock_load:
            config = SiteProfileConfig(
                site_id="site-002",
                active_profile="cost",
                control_tier="human_in_loop",
            )
            mock_load.return_value = config

            rec_data = {
                "site_id": "site-002",
                "action_type": "generator_start",  # HIGH risk
                "target_equipment": "S002-GEN-B1-001",
                "action": {"point": "run_command", "value": 1},
                "reason": "Test",
            }

            rec = await service.create_recommendation(rec_data)

            # High-risk also requires approval in Tier 2
            assert rec.requires_approval is True
            assert rec.status == RecommendationStatus.PENDING
            assert rec.risk_level == ActionRiskLevel.HIGH

    # =========================================================================
    # Tier 3: Auto-Execute
    # =========================================================================

    async def test_tier3_low_risk_auto_execute(self, service):
        """Tier 3: Low-risk auto-executed."""
        with patch.object(service.profile_service, "load_site_profile_config") as mock_load:
            config = SiteProfileConfig(
                site_id="site-002",
                active_profile="cost",
                control_tier="auto_execute",
            )
            mock_load.return_value = config

            with patch.object(service, "execute_recommendation", new_callable=AsyncMock) as mock_execute:
                rec_data = {
                    "site_id": "site-002",
                    "action_type": "hvac_setpoint_change",  # LOW risk
                    "target_equipment": "S002-CHILLER-B1-001",
                    "action": {"point": "supply_setpoint", "value": 18},
                    "reason": "Test",
                }

                rec = await service.create_recommendation(rec_data)

                # Low-risk: Should NOT require approval
                assert rec.requires_approval is False
                assert rec.status == RecommendationStatus.AUTO_EXECUTED

                # Should have called execute_recommendation
                mock_execute.assert_called_once()

    async def test_tier3_medium_risk_auto_execute(self, service):
        """Tier 3: Medium-risk auto-executed."""
        with patch.object(service.profile_service, "load_site_profile_config") as mock_load:
            config = SiteProfileConfig(
                site_id="site-002",
                active_profile="cost",
                control_tier="auto_execute",
            )
            mock_load.return_value = config

            with patch.object(service, "execute_recommendation", new_callable=AsyncMock) as mock_execute:
                rec_data = {
                    "site_id": "site-002",
                    "action_type": "equipment_staging",  # MEDIUM risk
                    "target_equipment": "S002-CHILLER-B1-001",
                    "action": {"point": "stage", "value": 1},
                    "reason": "Test",
                }

                rec = await service.create_recommendation(rec_data)

                # Medium-risk: Should NOT require approval
                assert rec.requires_approval is False
                assert rec.status == RecommendationStatus.AUTO_EXECUTED

                # Should have called execute_recommendation
                mock_execute.assert_called_once()

    async def test_tier3_high_risk_requires_approval(self, service):
        """Tier 3: High-risk actions require approval."""
        with patch.object(service.profile_service, "load_site_profile_config") as mock_load:
            config = SiteProfileConfig(
                site_id="site-002",
                active_profile="cost",
                control_tier="auto_execute",
            )
            mock_load.return_value = config

            rec_data = {
                "site_id": "site-002",
                "action_type": "generator_start",  # HIGH risk
                "target_equipment": "S002-GEN-B1-001",
                "action": {"point": "run_command", "value": 1},
                "reason": "Test",
            }

            rec = await service.create_recommendation(rec_data)

            # High-risk: Should require approval in Tier 3
            assert rec.requires_approval is True
            assert rec.status == RecommendationStatus.PENDING

    async def test_tier3_critical_risk_requires_approval(self, service):
        """Tier 3: Critical-risk actions require approval."""
        with patch.object(service.profile_service, "load_site_profile_config") as mock_load:
            config = SiteProfileConfig(
                site_id="site-002",
                active_profile="cost",
                control_tier="auto_execute",
            )
            mock_load.return_value = config

            rec_data = {
                "site_id": "site-002",
                "action_type": "fire_override",  # CRITICAL risk
                "target_equipment": "S002-FIRE-B1-001",
                "action": {"point": "override", "value": 1},
                "reason": "Test",
            }

            rec = await service.create_recommendation(rec_data)

            # Critical: Should require approval in Tier 3
            assert rec.requires_approval is True
            assert rec.status == RecommendationStatus.PENDING

    # =========================================================================
    # Risk Classification
    # =========================================================================

    async def test_risk_classification_low(self, service):
        """Risk classification: LOW actions."""
        risk_actions = [
            "hvac_setpoint_change",
            "zone_override",
            "lighting_dim",
            "schedule_shift",
        ]

        for action_type in risk_actions:
            risk = service._classify_risk(action_type)
            assert risk == ActionRiskLevel.LOW, f"{action_type} should be LOW"

    async def test_risk_classification_high(self, service):
        """Risk classification: HIGH actions."""
        risk_actions = [
            "generator_start",
            "bess_dispatch",
            "chiller_bypass",
            "equipment_shutdown",
        ]

        for action_type in risk_actions:
            risk = service._classify_risk(action_type)
            assert risk == ActionRiskLevel.HIGH, f"{action_type} should be HIGH"

    async def test_risk_classification_critical(self, service):
        """Risk classification: CRITICAL actions."""
        risk_actions = [
            "fire_override",
            "access_control",
            "emergency_shutdown",
        ]

        for action_type in risk_actions:
            risk = service._classify_risk(action_type)
            assert risk == ActionRiskLevel.CRITICAL, f"{action_type} should be CRITICAL"

    async def test_risk_classification_medium(self, service):
        """Risk classification: MEDIUM actions (default)."""
        risk = service._classify_risk("unknown_action")
        assert risk == ActionRiskLevel.MEDIUM

    # =========================================================================
    # Approval Logic
    # =========================================================================

    async def test_requires_approval_monitor(self, service):
        """Approval logic: Monitor tier always requires approval."""
        result = service._requires_approval("monitor", ActionRiskLevel.LOW)
        assert result is True

        result = service._requires_approval("monitor", ActionRiskLevel.CRITICAL)
        assert result is True

    async def test_requires_approval_human_in_loop(self, service):
        """Approval logic: Human-in-loop always requires approval."""
        result = service._requires_approval("human_in_loop", ActionRiskLevel.LOW)
        assert result is True

        result = service._requires_approval("human_in_loop", ActionRiskLevel.CRITICAL)
        assert result is True

    async def test_requires_approval_auto_execute_low(self, service):
        """Approval logic: Auto-execute, low-risk doesn't require approval."""
        result = service._requires_approval("auto_execute", ActionRiskLevel.LOW)
        assert result is False

    async def test_requires_approval_auto_execute_medium(self, service):
        """Approval logic: Auto-execute, medium-risk doesn't require approval."""
        result = service._requires_approval("auto_execute", ActionRiskLevel.MEDIUM)
        assert result is False

    async def test_requires_approval_auto_execute_high(self, service):
        """Approval logic: Auto-execute, high-risk requires approval."""
        result = service._requires_approval("auto_execute", ActionRiskLevel.HIGH)
        assert result is True

    async def test_requires_approval_auto_execute_critical(self, service):
        """Approval logic: Auto-execute, critical-risk requires approval."""
        result = service._requires_approval("auto_execute", ActionRiskLevel.CRITICAL)
        assert result is True

    async def test_requires_approval_default(self, service):
        """Approval logic: Unknown tier defaults to require approval."""
        result = service._requires_approval("unknown_tier", ActionRiskLevel.LOW)
        assert result is True


@pytest.mark.asyncio
class TestRecommendationExecution:
    """Test recommendation execution and error handling."""

    @pytest.fixture
    def service(self):
        """Create a RecommendationService instance."""
        return RecommendationService()

    async def test_execute_recommendation_success(self, service):
        """Execute recommendation successfully."""
        rec = Recommendation(
            site_id="site-002",
            action_type="hvac_setpoint_change",
            target_equipment="S002-CHILLER-B1-001",
            action={"point": "supply_setpoint", "value": 18},
        )

        with patch("app.services.recommendation_service.device_manager") as mock_dm:
            mock_dm.apply_action = AsyncMock(return_value={"success": True, "point": "supply_setpoint"})

            result = await service.execute_recommendation(rec.id, rec)

            assert result is not None
            assert rec.status == RecommendationStatus.EXECUTED
            assert rec.executed_at is not None
            assert rec.execution_result is not None

    async def test_execute_recommendation_failure(self, service):
        """Execute recommendation fails."""
        rec = Recommendation(
            site_id="site-002",
            action_type="hvac_setpoint_change",
            target_equipment="S002-CHILLER-B1-001",
            action={"point": "supply_setpoint", "value": 18},
        )

        with patch("app.services.recommendation_service.device_manager") as mock_dm:
            mock_dm.apply_action = AsyncMock(side_effect=Exception("Device offline"))

            with pytest.raises(Exception):
                await service.execute_recommendation(rec.id, rec)

            assert rec.status == RecommendationStatus.FAILED
            assert "Device offline" in rec.execution_result["error"]
