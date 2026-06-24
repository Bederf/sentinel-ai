"""Tests for Phase 230: Fault Safety Gate — hard pre-generation block."""

from datetime import datetime
from typing import Any

import pytest

from app.models.device import (
    DeviceEquipment,
    DeviceLocation,
    DevicePoint,
    DeviceType,
    HVACDevice,
    PointType,
    ProtocolType,
)
from app.services.ai_optimizer import AIOptimizerService


def _optimizer() -> AIOptimizerService:
    optimizer = AIOptimizerService()
    optimizer._sites = [
        {
            "id": "site-002",
            "name": "S002",
            "operating_hours": {"start": "08:00", "end": "18:00"},
        }
    ]
    return optimizer


def _chiller(zone_key: str = "ROOF", metadata: dict | None = None) -> HVACDevice:
    base_meta = {
        "equipment_type": "chiller",
        "zone_key": zone_key,
    }
    if metadata:
        base_meta.update(metadata)
    return HVACDevice(
        id="S002-CHILLER-B01",
        name="S002 Chiller B01",
        device_type=DeviceType.HVAC,
        protocol=ProtocolType.MOCK,
        site_id="site-002",
        device_location=DeviceLocation(
            building="S002", floor="B1", zone="Plant", room="Chiller Plant", description="Basement chiller plant"
        ),
        equipment=DeviceEquipment(manufacturer="Test", model="CH-1"),
        hvac_type="chiller",
        metadata=base_meta,
        points={},
    )


def _ahu(zone_key: str = "ROOF", metadata: dict | None = None) -> HVACDevice:
    base_meta = {
        "equipment_type": "ahu",
        "zone_key": zone_key,
    }
    if metadata:
        base_meta.update(metadata)
    return HVACDevice(
        id="S002-AHU-B01",
        name="S002 AHU B01",
        device_type=DeviceType.HVAC,
        protocol=ProtocolType.MOCK,
        site_id="site-002",
        device_location=DeviceLocation(
            building="S002", floor="B1", zone="Plant", room="AHU Plant", description="Basement AHU plant"
        ),
        equipment=DeviceEquipment(manufacturer="Test", model="AHU-1"),
        hvac_type="ahu",
        metadata=base_meta,
        points={
            "fresh_air_damper": DevicePoint(
                name="fresh_air_damper",
                point_type=PointType.ANALOG_OUTPUT,
                unit="%",
                default_value=20.0,
                writable=True,
            ),
            "supply_air_temp_setpoint": DevicePoint(
                name="supply_air_temp_setpoint",
                point_type=PointType.ANALOG_OUTPUT,
                unit="°C",
                default_value=12.0,
                writable=True,
            ),
        },
    )


def _fcu() -> HVACDevice:
    return HVACDevice(
        id="S002-FCU-L2-A",
        name="S002 FCU Level 2 A",
        device_type=DeviceType.HVAC,
        protocol=ProtocolType.MOCK,
        site_id="site-002",
        device_location=DeviceLocation(
            building="S002", floor="L2", zone="Office", room="Open Plan", description="Level 2 open plan"
        ),
        equipment=DeviceEquipment(manufacturer="Test", model="FCU-1"),
        hvac_type="fcu",
        metadata={"equipment_type": "fcu"},
        points={
            "setpoint": DevicePoint(
                name="setpoint", point_type=PointType.ANALOG_OUTPUT, unit="°C", default_value=22.0, writable=True
            ),
        },
    )


def _inventory(
    chiller: HVACDevice | None = None, ahu: HVACDevice | None = None, fcu: HVACDevice | None = None
) -> dict[str, list]:
    inv: dict[str, list] = {"hvac": []}
    if chiller:
        inv["hvac"].append(chiller)
    if ahu:
        inv["hvac"].append(ahu)
    if fcu:
        inv["hvac"].append(fcu)
    return inv


def _conditions(critical_alerts: list[dict] | None = None, urgent_wos: list[dict] | None = None) -> dict[str, Any]:
    return {
        "timestamp": datetime(2026, 6, 24, 7, 0).isoformat(),
        "indoor_temp": 22.0,
        "outdoor_temp": 7.7,
        "humidity": 55.0,
        "active_critical_alerts": critical_alerts or [],
        "active_urgent_work_orders": urgent_wos or [],
    }


class TestFaultGateLoadContext:
    """Tests for _load_fault_gate_context — the core resolution logic."""

    @pytest.mark.asyncio
    async def test_no_alerts_no_wos_no_suppression(self):
        """Equipment with no alerts, no WOs, no faulted plant-group-mate -> not suppressed."""
        optimizer = _optimizer()
        inv = _inventory(chiller=_chiller(), ahu=_ahu(), fcu=_fcu())
        cond = _conditions()

        # Use a non-existent site so Supabase supplement doesn't inject live data
        context = await optimizer._load_fault_gate_context("site-999", cond, inv)
        decisions = context.get("decisions", {})

        assert decisions.get("S002-CHILLER-B01", {}).get("suppress") is False
        assert decisions.get("S002-AHU-B01", {}).get("suppress") is False
        assert decisions.get("S002-FCU-L2-A", {}).get("suppress") is False

    @pytest.mark.asyncio
    async def test_direct_critical_alert_suppresses_equipment(self):
        """Equipment with a direct active critical alert -> suppressed."""
        optimizer = _optimizer()
        chiller = _chiller()
        ahu = _ahu()
        inv = _inventory(chiller=chiller, ahu=ahu)
        cond = _conditions(
            critical_alerts=[
                {
                    "equipment_id": "S002-CHILLER-B01",
                    "severity": "critical",
                    "message": "CHILLER1.COMPCURRENT: Equipment operating outside normal range",
                    "created_at": "2026-06-24T06:00:00",
                },
            ]
        )

        context = await optimizer._load_fault_gate_context("site-002", cond, inv)
        decisions = context.get("decisions", {})

        # Critical alert on CHILLER-B01 -> suppressed
        assert decisions.get("S002-CHILLER-B01", {}).get("suppress") is True
        assert decisions.get("S002-CHILLER-B01", {}).get("fault_type") == "direct"

    @pytest.mark.asyncio
    async def test_urgent_wo_suppresses_equipment(self):
        """Equipment with open urgent work order -> suppressed."""
        optimizer = _optimizer()
        chiller = _chiller()
        inv = _inventory(chiller=chiller)
        cond = _conditions(
            urgent_wos=[
                {
                    "equipment_code": "S002-CHILLER-B01",
                    "title": "Compressor current fault",
                    "priority": "high",
                    "status": "open",
                },
            ]
        )

        context = await optimizer._load_fault_gate_context("site-002", cond, inv)
        decisions = context.get("decisions", {})

        assert decisions.get("S002-CHILLER-B01", {}).get("suppress") is True
        assert decisions.get("S002-CHILLER-B01", {}).get("fault_type") == "direct"

    @pytest.mark.asyncio
    async def test_coupled_plant_group_mate_suppresses_ahu(self):
        """AHU-B01 in same plant group as faulted CHILLER-B01 -> suppressed.

        This is the primary regression case from the morning digest:
        CHILLER-B01 has active COMPCURRENT fault + open WO,
        AHU-B01 is in the same plant group (roof).
        Previously: AHU-B01 was not blocked (prompt-only, no coupling).
        Now: AHU-B01 must be suppressed.
        """
        optimizer = _optimizer()
        chiller = _chiller(zone_key="ROOF")
        ahu = _ahu(zone_key="ROOF")
        fcu = _fcu()
        inv = _inventory(chiller=chiller, ahu=ahu, fcu=fcu)
        cond = _conditions(
            critical_alerts=[
                {
                    "equipment_id": "S002-CHILLER-B01",
                    "severity": "critical",
                    "message": "CHILLER1.COMPCURRENT: Equipment operating outside normal range",
                    "created_at": "2026-06-24T06:00:00",
                },
            ],
            urgent_wos=[
                {
                    "equipment_code": "S002-CHILLER-B01",
                    "title": "Compressor current fault",
                    "priority": "high",
                    "status": "open",
                },
            ],
        )

        context = await optimizer._load_fault_gate_context("site-002", cond, inv)
        decisions = context.get("decisions", {})

        # CHILLER-B01: direct fault -> suppressed
        assert decisions.get("S002-CHILLER-B01", {}).get("suppress") is True
        assert decisions.get("S002-CHILLER-B01", {}).get("fault_type") == "direct"

        # AHU-B01: plant-group-mate fault -> suppressed (COUPLED)
        ahu_decision = decisions.get("S002-AHU-B01", {})
        assert ahu_decision.get("suppress") is True, (
            f"AHU-B01 should be suppressed because CHILLER-B01 in same plant group has fault. Got: {ahu_decision}"
        )
        assert ahu_decision.get("fault_type") == "coupled"
        assert any("Coupled equipment" in r for r in ahu_decision.get("reason_codes", []))

        # FCU-L2-A: no zone_key, not in plant group -> NOT suppressed
        assert decisions.get("S002-FCU-L2-A", {}).get("suppress") is False

    @pytest.mark.asyncio
    async def test_different_plant_group_no_suppression(self):
        """Equipment in a different plant group from the faulted one -> not suppressed."""
        optimizer = _optimizer()
        chiller = _chiller(zone_key="BASEMENT")
        ahu = _ahu(zone_key="ROOF")
        inv = _inventory(chiller=chiller, ahu=ahu)
        cond = _conditions(
            critical_alerts=[
                {
                    "equipment_id": "S002-CHILLER-B01",
                    "severity": "critical",
                    "message": "CHILLER1.COMPCURRENT fault",
                    "created_at": "2026-06-24T06:00:00",
                },
            ]
        )

        context = await optimizer._load_fault_gate_context("site-002", cond, inv)
        decisions = context.get("decisions", {})

        # CHILLER-B01 (BASEMENT) -> suppressed (direct fault)
        assert decisions.get("S002-CHILLER-B01", {}).get("suppress") is True

        # AHU-B01 (ROOF) -> NOT suppressed (different plant group)
        assert decisions.get("S002-AHU-B01", {}).get("suppress") is False


class TestFaultGateFilterInventory:
    """Tests for _filter_equipment_inventory_by_fault_gate."""

    @pytest.mark.asyncio
    async def test_fault_gate_removes_suppressed_equipment(self):
        """Suppressed equipment is removed from the inventory."""
        optimizer = _optimizer()
        chiller = _chiller(zone_key="ROOF")
        ahu = _ahu(zone_key="ROOF")
        fcu = _fcu()
        inv = _inventory(chiller=chiller, ahu=ahu, fcu=fcu)
        cond = _conditions(
            critical_alerts=[
                {
                    "equipment_id": "S002-CHILLER-B01",
                    "severity": "critical",
                    "message": "CHILLER1.COMPCURRENT fault",
                    "created_at": "2026-06-24T06:00:00",
                },
            ],
        )

        context = await optimizer._load_fault_gate_context("site-002", cond, inv)
        cond["_fault_gate_context"] = context

        filtered = optimizer._filter_equipment_inventory_by_fault_gate(inv, cond)

        # CHILLER-B01 and AHU-B01 removed, FCU-L2-A kept
        hvac_codes = {d.id for d in filtered.get("hvac", [])}
        assert "S002-CHILLER-B01" not in hvac_codes
        assert "S002-AHU-B01" not in hvac_codes
        assert "S002-FCU-L2-A" in hvac_codes

    @pytest.mark.asyncio
    async def test_fault_gate_no_alerts_leaves_inventory_unchanged(self):
        """No alerts -> inventory unchanged."""
        optimizer = _optimizer()
        ahu = _ahu()
        fcu = _fcu()
        inv = _inventory(ahu=ahu, fcu=fcu)
        cond = _conditions()

        context = await optimizer._load_fault_gate_context("site-002", cond, inv)
        cond["_fault_gate_context"] = context

        filtered = optimizer._filter_equipment_inventory_by_fault_gate(inv, cond)

        hvac_codes = {d.id for d in filtered.get("hvac", [])}
        assert "S002-AHU-B01" in hvac_codes
        assert "S002-FCU-L2-A" in hvac_codes


class TestFaultGateAdvisory:
    """Tests for _fault_gate_advisory."""

    def test_advisory_contains_required_fields(self):
        """Advisory recommendation has correct fields for a direct fault."""
        optimizer = _optimizer()
        decision = {
            "equipment_code": "S002-CHILLER-B01",
            "suppress": True,
            "fault_type": "direct",
            "reason_codes": ["Active critical alert: CHILLER1.COMPCURRENT: Equipment operating outside normal range"],
        }

        advisory = optimizer._fault_gate_advisory("site-002", "S002-CHILLER-B01", decision)

        assert advisory["target_equipment"] == "S002-CHILLER-B01"
        assert advisory["status"] == "advisory_info"
        assert advisory["action"]["execution_blocked"] is True
        assert advisory["action"]["blocker"] == "active_fault_on_equipment_or_plant_group_mate"
        assert advisory["metadata"]["rule"] == AIOptimizerService.FAULT_GATE_RULE
        assert advisory["metadata"]["fault_type"] == "direct"
        assert "excluded" in advisory["reason"]
        assert "CHILLER1.COMPCURRENT" in advisory["reason"]

    def test_coupled_advisory_mentions_mate(self):
        """Coupled equipment advisory mentions the faulted mate."""
        optimizer = _optimizer()
        decision = {
            "equipment_code": "S002-AHU-B01",
            "suppress": True,
            "fault_type": "coupled",
            "reason_codes": [
                "Coupled equipment S002-CHILLER-B01 has active critical alert: CHILLER1.COMPCURRENT fault"
            ],
        }

        advisory = optimizer._fault_gate_advisory("site-002", "S002-AHU-B01", decision)

        assert advisory["status"] == "advisory_info"
        assert advisory["metadata"]["fault_type"] == "coupled"
        assert "S002-CHILLER-B01" in advisory["reason"]
        assert "excluded" in advisory["reason"]
