"""Energy Centre Service for Complete Electrical Infrastructure Monitoring.

Combines MV/LV switchgear, ATS, transformers, power metering, PFC, and UPS
into a unified SCADA-style view for the energy centre.
"""

from typing import Dict, List, Optional
from datetime import datetime
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from app.models.energy_centre import (
    EnergyCentre,
    ATSUnit,
    MVIncomer,
    Transformer,
    LVSwitchboard,
    PowerMeter,
    PFCBank,
    UPSSystem,
)
from app.services.generator_service import get_generator_service


class EnergyCentreService:
    """Service for energy centre monitoring."""

    def __init__(self):
        self._centres: Dict[str, EnergyCentre] = {}
        self._mv_incomers: Dict[str, MVIncomer] = {}
        self._transformers: Dict[str, Transformer] = {}
        self._switchboards: Dict[str, LVSwitchboard] = {}
        self._ats_units: Dict[str, ATSUnit] = {}
        self._meters: Dict[str, PowerMeter] = {}
        self._pfc_banks: Dict[str, PFCBank] = {}
        self._ups_systems: Dict[str, UPSSystem] = {}
        self._feeders: Dict[str, dict] = {}
        self._scada_config: Dict = {}
        self._load_mock_data()

    def _load_mock_data(self):
        """Load energy centre data from JSON."""
        data_paths = [
            Path(__file__).parent.parent / "data" / "buildings" / "sandton" / "energy_centre.json",
        ]

        for data_path in data_paths:
            if data_path.exists():
                with open(data_path) as f:
                    data = json.load(f)

                # Parse energy centre
                if "energy_centre" in data:
                    ec = data["energy_centre"]
                    centre = EnergyCentre(
                        centre_id=ec.get("centre_id"),
                        name=ec.get("name"),
                        site_id=ec.get("site_id"),
                        building=ec.get("building"),
                        location=ec.get("location"),
                        mv_incomer_ids=ec.get("mv_incomer_ids", []),
                        transformer_ids=ec.get("transformer_ids", []),
                        lv_switchboard_ids=ec.get("lv_switchboard_ids", []),
                        ats_ids=ec.get("ats_ids", []),
                        generator_group_ids=ec.get("generator_group_ids", []),
                        pfc_ids=ec.get("pfc_ids", []),
                        ups_ids=ec.get("ups_ids", []),
                        meter_ids=ec.get("meter_ids", []),
                        mains_healthy=ec.get("mains_healthy", True),
                        on_generator=ec.get("on_generator", False),
                        total_load_kw=ec.get("total_load_kw", 0),
                        total_capacity_kw=ec.get("total_capacity_kw", 0),
                    )
                    self._centres[centre.centre_id] = centre

                # Parse MV incomers
                for mv in data.get("mv_incomers", []):
                    incomer = MVIncomer(**{k: v for k, v in mv.items() if k in MVIncomer.__dataclass_fields__})
                    self._mv_incomers[incomer.incomer_id] = incomer

                # Parse transformers
                for tx in data.get("transformers", []):
                    transformer = Transformer(**{k: v for k, v in tx.items() if k in Transformer.__dataclass_fields__})
                    self._transformers[transformer.transformer_id] = transformer

                # Parse LV switchboards
                for sb in data.get("lv_switchboards", []):
                    switchboard = LVSwitchboard(
                        **{k: v for k, v in sb.items() if k in LVSwitchboard.__dataclass_fields__}
                    )
                    self._switchboards[switchboard.switchboard_id] = switchboard

                # Parse ATS units
                for ats in data.get("ats_units", []):
                    ats_unit = ATSUnit(**{k: v for k, v in ats.items() if k in ATSUnit.__dataclass_fields__})
                    self._ats_units[ats_unit.ats_id] = ats_unit

                # Parse power meters
                for mtr in data.get("power_meters", []):
                    meter = PowerMeter(**{k: v for k, v in mtr.items() if k in PowerMeter.__dataclass_fields__})
                    self._meters[meter.meter_id] = meter

                # Parse PFC banks
                for pfc in data.get("pfc_banks", []):
                    bank = PFCBank(**{k: v for k, v in pfc.items() if k in PFCBank.__dataclass_fields__})
                    self._pfc_banks[bank.pfc_id] = bank

                # Parse UPS systems
                for ups in data.get("ups_systems", []):
                    system = UPSSystem(**{k: v for k, v in ups.items() if k in UPSSystem.__dataclass_fields__})
                    self._ups_systems[system.ups_id] = system

                # Parse feeders (simple dict)
                for fdr in data.get("feeders", []):
                    self._feeders[fdr["feeder_id"]] = fdr

                # SCADA config
                self._scada_config = data.get("scada_network", {})

                logger.info(f"Loaded energy centre data from {data_path}")

    # === Energy Centre ===

    def get_centres(self, site_id: Optional[str] = None) -> List[EnergyCentre]:
        """Get all energy centres."""
        centres = list(self._centres.values())
        if site_id:
            centres = [c for c in centres if c.site_id == site_id]
        return centres

    def get_centre(self, centre_id: str) -> Optional[EnergyCentre]:
        """Get single energy centre."""
        return self._centres.get(centre_id)

    # === ATS ===

    def get_ats_units(self, site_id: Optional[str] = None) -> List[ATSUnit]:
        """Get all ATS units."""
        units = list(self._ats_units.values())
        if site_id:
            units = [u for u in units if u.site_id == site_id]
        return units

    def get_ats(self, ats_id: str) -> Optional[ATSUnit]:
        """Get single ATS unit."""
        return self._ats_units.get(ats_id)

    def get_ats_status(self, ats_id: str) -> Optional[Dict]:
        """Get detailed ATS status with transfer history."""
        ats = self._ats_units.get(ats_id)
        if not ats:
            return None

        return {
            "ats_id": ats.ats_id,
            "name": ats.name,
            "timestamp": datetime.now().isoformat(),
            "position": ats.position,
            "type": ats.ats_type,
            "transfer_mode": ats.transfer_mode,
            "sources": {
                "mains": {
                    "available": ats.mains_available,
                    "breaker": ats.mains_breaker,
                },
                "generator": {
                    "available": ats.generator_available,
                    "breaker": ats.gen_breaker,
                },
            },
            "interlocks": {
                "mechanical_ok": ats.mechanical_interlock_ok,
                "electrical_ok": ats.electrical_interlock_ok,
            },
            "transfer_stats": {
                "total_transfers": ats.transfer_count,
                "last_transfer_time_ms": ats.last_transfer_time_ms,
                "last_transfer": ats.last_transfer_timestamp,
                "last_reason": ats.last_transfer_reason,
            },
        }

    # === MV Switchgear ===

    def get_mv_incomers(self, site_id: Optional[str] = None) -> List[MVIncomer]:
        """Get all MV incomers."""
        incomers = list(self._mv_incomers.values())
        if site_id:
            incomers = [i for i in incomers if i.site_id == site_id]
        return incomers

    def get_mv_incomer(self, incomer_id: str) -> Optional[MVIncomer]:
        """Get single MV incomer."""
        return self._mv_incomers.get(incomer_id)

    # === Transformers ===

    def get_transformers(self, site_id: Optional[str] = None) -> List[Transformer]:
        """Get all transformers."""
        transformers = list(self._transformers.values())
        if site_id:
            transformers = [t for t in transformers if t.site_id == site_id]
        return transformers

    def get_transformer(self, transformer_id: str) -> Optional[Transformer]:
        """Get single transformer."""
        return self._transformers.get(transformer_id)

    # === LV Switchboards ===

    def get_switchboards(self, site_id: Optional[str] = None) -> List[LVSwitchboard]:
        """Get all LV switchboards."""
        switchboards = list(self._switchboards.values())
        if site_id:
            switchboards = [s for s in switchboards if s.site_id == site_id]
        return switchboards

    def get_switchboard(self, switchboard_id: str) -> Optional[LVSwitchboard]:
        """Get single switchboard."""
        return self._switchboards.get(switchboard_id)

    # === Power Meters ===

    def get_meters(self, site_id: Optional[str] = None, meter_type: Optional[str] = None) -> List[PowerMeter]:
        """Get all power meters."""
        meters = list(self._meters.values())
        if site_id:
            meters = [m for m in meters if m.site_id == site_id]
        if meter_type:
            meters = [m for m in meters if m.meter_type == meter_type]
        return meters

    def get_meter(self, meter_id: str) -> Optional[PowerMeter]:
        """Get single power meter."""
        return self._meters.get(meter_id)

    def get_power_summary(self, site_id: str) -> Dict:
        """Get power summary from all meters at a site."""
        meters = self.get_meters(site_id=site_id)
        main_meter = next((m for m in meters if m.meter_type == "main"), None)

        return {
            "site_id": site_id,
            "timestamp": datetime.now().isoformat(),
            "main_incomer": main_meter.to_dict() if main_meter else None,
            "total_power_kw": sum(m.active_power_kw for m in meters if m.meter_type in ("main", "sub")),
            "total_kwh": sum(m.kwh_import for m in meters if m.meter_type == "main"),
            "power_factor": main_meter.power_factor if main_meter else 0,
            "tariff": {
                "type": main_meter.tariff_type if main_meter else None,
                "period": main_meter.tou_period if main_meter else None,
            },
            "meters": [m.to_dict() for m in meters],
        }

    # === PFC ===

    def get_pfc_banks(self, site_id: Optional[str] = None) -> List[PFCBank]:
        """Get all PFC banks."""
        banks = list(self._pfc_banks.values())
        if site_id:
            banks = [b for b in banks if b.site_id == site_id]
        return banks

    def get_pfc(self, pfc_id: str) -> Optional[PFCBank]:
        """Get single PFC bank."""
        return self._pfc_banks.get(pfc_id)

    # === UPS ===

    def get_ups_systems(self, site_id: Optional[str] = None) -> List[UPSSystem]:
        """Get all UPS systems."""
        systems = list(self._ups_systems.values())
        if site_id:
            systems = [s for s in systems if s.site_id == site_id]
        return systems

    def get_ups(self, ups_id: str) -> Optional[UPSSystem]:
        """Get single UPS system."""
        return self._ups_systems.get(ups_id)

    def get_ups_summary(self, site_id: str) -> Dict:
        """Get UPS summary for a site."""
        systems = self.get_ups_systems(site_id=site_id)

        return {
            "site_id": site_id,
            "timestamp": datetime.now().isoformat(),
            "total_capacity_kva": sum(s.rated_power_kva for s in systems),
            "total_load_kw": sum(s.load_kw for s in systems),
            "all_healthy": all(s.mode == "online" and not s.alarms for s in systems),
            "any_on_battery": any(s.on_battery for s in systems),
            "systems": [
                {
                    "ups_id": s.ups_id,
                    "name": s.name,
                    "mode": s.mode,
                    "load_percent": s.load_percent,
                    "battery_charge_pct": s.battery_charge_pct,
                    "runtime_min": s.battery_runtime_min,
                    "on_battery": s.on_battery,
                    "alarms": s.alarms,
                }
                for s in systems
            ],
        }

    # === Feeders ===

    def get_feeders(self, site_id: Optional[str] = None) -> List[Dict]:
        """Get all distribution feeders."""
        return list(self._feeders.values())

    # === SCADA Overview ===

    def get_scada_overview(self, site_id: str) -> Dict:
        """Get complete SCADA overview for energy centre."""
        centre = next((c for c in self._centres.values() if c.site_id == site_id), None)

        # Get generator status from generator service
        gen_service = get_generator_service()
        gen_overview = gen_service.get_scada_overview(site_id)

        # Get equipment status
        mv_incomers = self.get_mv_incomers(site_id=site_id)
        transformers = self.get_transformers(site_id=site_id)
        switchboards = self.get_switchboards(site_id=site_id)
        ats_units = self.get_ats_units(site_id=site_id)
        meters = self.get_meters(site_id=site_id)
        pfc_banks = self.get_pfc_banks(site_id=site_id)
        ups_systems = self.get_ups_systems(site_id=site_id)
        feeders = self.get_feeders(site_id=site_id)

        # Determine overall status
        mains_healthy = all(mv.healthy for mv in mv_incomers) if mv_incomers else True
        ats_on_gen = any(ats.position == "generator" for ats in ats_units)

        main_meter = next((m for m in meters if m.meter_type == "main"), None)

        return {
            "site_id": site_id,
            "centre": centre.to_dict() if centre else None,
            "timestamp": datetime.now().isoformat(),
            "status": {
                "mains_healthy": mains_healthy,
                "on_generator": ats_on_gen,
                "all_systems_normal": mains_healthy and not ats_on_gen,
            },
            "mv_supply": {
                "incomers": [mv.to_dict() for mv in mv_incomers],
                "voltage_kv": mv_incomers[0].voltage_kv if mv_incomers else 0,
                "healthy": mains_healthy,
            },
            "transformers": {
                "units": [tx.to_dict() for tx in transformers],
                "total_capacity_kva": sum(tx.rated_power_kva for tx in transformers),
                "total_load_kva": sum(tx.load_kva for tx in transformers),
                "avg_load_percent": (
                    sum(tx.load_percent for tx in transformers) / len(transformers) if transformers else 0
                ),
            },
            "ats": {
                "units": [self.get_ats_status(ats.ats_id) for ats in ats_units],
                "current_source": "generator" if ats_on_gen else "mains",
            },
            "generators": gen_overview,
            "lv_distribution": {
                "switchboards": [sb.to_dict() for sb in switchboards],
                "feeders": feeders,
                "total_power_kw": main_meter.active_power_kw if main_meter else 0,
            },
            "power_metering": {
                "main": main_meter.to_dict() if main_meter else None,
                "total_kwh": main_meter.kwh_import if main_meter else 0,
                "power_factor": main_meter.power_factor if main_meter else 0,
                "tariff": main_meter.tariff_type if main_meter else None,
                "tou_period": main_meter.tou_period if main_meter else None,
            },
            "power_factor_correction": {
                "banks": [pfc.to_dict() for pfc in pfc_banks],
                "total_kvar": sum(pfc.total_kvar for pfc in pfc_banks),
                "active_kvar": sum(pfc.active_kvar for pfc in pfc_banks),
                "current_pf": pfc_banks[0].current_power_factor if pfc_banks else 0,
            },
            "ups": self.get_ups_summary(site_id),
            "scada_network": self._scada_config,
        }

    # === Single-Line Diagram Data ===

    def get_sld_data(self, site_id: str) -> Dict:
        """Get data formatted for single-line diagram visualization."""
        overview = self.get_scada_overview(site_id)

        # Build simplified structure for SLD
        return {
            "site_id": site_id,
            "timestamp": datetime.now().isoformat(),
            "nodes": self._build_sld_nodes(site_id),
            "connections": self._build_sld_connections(site_id),
            "status": overview["status"],
        }

    def _build_sld_nodes(self, site_id: str) -> List[Dict]:
        """Build nodes for SLD visualization."""
        nodes = []

        # MV Incomer
        for mv in self.get_mv_incomers(site_id=site_id):
            nodes.append(
                {
                    "id": mv.incomer_id,
                    "type": "mv_incomer",
                    "label": f"Eskom {mv.nominal_voltage_kv}kV",
                    "status": "healthy" if mv.healthy else "fault",
                    "voltage": mv.voltage_kv,
                    "breaker": mv.breaker_state,
                }
            )

        # Transformers
        for tx in self.get_transformers(site_id=site_id):
            nodes.append(
                {
                    "id": tx.transformer_id,
                    "type": "transformer",
                    "label": f"TX {tx.rated_power_kva}kVA",
                    "status": "healthy" if tx.healthy else "fault",
                    "load_percent": tx.load_percent,
                    "temp_c": tx.winding_temp_c,
                }
            )

        # ATS
        for ats in self.get_ats_units(site_id=site_id):
            nodes.append(
                {
                    "id": ats.ats_id,
                    "type": "ats",
                    "label": "ATS",
                    "position": ats.position,
                    "mains_breaker": ats.mains_breaker,
                    "gen_breaker": ats.gen_breaker,
                }
            )

        # Generators
        gen_service = get_generator_service()
        for gen in gen_service.get_generators(site_id=site_id):
            nodes.append(
                {
                    "id": gen.generator_id,
                    "type": "generator",
                    "label": f"Gen {gen.rated_power_kw}kW",
                    "status": gen.status,
                    "running": gen.engine_running,
                    "on_load": gen.on_load,
                }
            )

        # Switchboard
        for sb in self.get_switchboards(site_id=site_id):
            nodes.append(
                {
                    "id": sb.switchboard_id,
                    "type": "switchboard",
                    "label": "MSB",
                    "voltage": sb.voltage_l1_l2,
                    "power_kw": sb.total_power_kw,
                }
            )

        # UPS
        for ups in self.get_ups_systems(site_id=site_id):
            nodes.append(
                {
                    "id": ups.ups_id,
                    "type": "ups",
                    "label": f"UPS {ups.rated_power_kva}kVA",
                    "mode": ups.mode,
                    "battery_pct": ups.battery_charge_pct,
                    "on_battery": ups.on_battery,
                }
            )

        return nodes

    def _build_sld_connections(self, site_id: str) -> List[Dict]:
        """Build connections for SLD visualization."""
        connections = []

        # MV → Transformer
        mv_incomers = self.get_mv_incomers(site_id=site_id)
        transformers = self.get_transformers(site_id=site_id)
        if mv_incomers and transformers:
            for tx in transformers:
                connections.append(
                    {
                        "from": mv_incomers[0].incomer_id,
                        "to": tx.transformer_id,
                        "type": "mv_cable",
                        "energized": mv_incomers[0].healthy,
                    }
                )

        # Transformer → ATS (mains side)
        ats_units = self.get_ats_units(site_id=site_id)
        if transformers and ats_units:
            connections.append(
                {
                    "from": transformers[0].transformer_id,
                    "to": ats_units[0].ats_id,
                    "type": "lv_cable",
                    "energized": ats_units[0].mains_breaker == "closed",
                    "port": "mains",
                }
            )

        # Generator → ATS (gen side)
        gen_service = get_generator_service()
        generators = gen_service.get_generators(site_id=site_id)
        if generators and ats_units:
            connections.append(
                {
                    "from": generators[0].generator_id,
                    "to": ats_units[0].ats_id,
                    "type": "lv_cable",
                    "energized": ats_units[0].gen_breaker == "closed",
                    "port": "generator",
                }
            )

        # ATS → Switchboard
        switchboards = self.get_switchboards(site_id=site_id)
        if ats_units and switchboards:
            connections.append(
                {
                    "from": ats_units[0].ats_id,
                    "to": switchboards[0].switchboard_id,
                    "type": "busbar",
                    "energized": True,
                }
            )

        return connections


# Singleton instance
_energy_centre_service: Optional[EnergyCentreService] = None


def get_energy_centre_service() -> EnergyCentreService:
    """Get the singleton energy centre service instance."""
    global _energy_centre_service
    if _energy_centre_service is None:
        _energy_centre_service = EnergyCentreService()
    return _energy_centre_service
