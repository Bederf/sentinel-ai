from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.module_registry import ModuleType
from app.services.demand_aware_coordinator import DemandAwareCoordinator


def _make_coordinator(ai_optimizer: object) -> DemandAwareCoordinator:
    coordinator = DemandAwareCoordinator.__new__(DemandAwareCoordinator)
    coordinator.ai_optimizer = ai_optimizer
    return coordinator


@pytest.mark.asyncio
async def test_generate_coordinated_shaving_plan_falls_back_when_optimizer_has_no_legacy_method():
    coordinator = _make_coordinator(SimpleNamespace())

    result = await coordinator._generate_coordinated_shaving_plan(
        site_id="site-002",
        active_module_types=[ModuleType.SOLAR, ModuleType.HVAC],
        required_reduction_kw=120.0,
        ai_context={"required_reduction_kw": 120.0},
    )

    assert result["total_reduction_kw"] >= 120.0
    assert [action["module"] for action in result["module_actions"]] == ["solar"]


@pytest.mark.asyncio
async def test_generate_coordinated_shaving_plan_uses_optimizer_when_shape_matches():
    expected = {
        "module_actions": [{"module": "hvac", "action": "increase_setpoint_2c", "reduction_kw": 60}],
        "total_reduction_kw": 60,
        "total_savings_r": 1500,
    }
    optimizer = SimpleNamespace(generate_recommendations=AsyncMock(return_value=expected))
    coordinator = _make_coordinator(optimizer)

    result = await coordinator._generate_coordinated_shaving_plan(
        site_id="site-002",
        active_module_types=[ModuleType.HVAC],
        required_reduction_kw=60.0,
        ai_context={"required_reduction_kw": 60.0},
    )

    assert result == expected
    optimizer.generate_recommendations.assert_awaited_once()
