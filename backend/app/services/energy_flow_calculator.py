"""Energy Flow Calculator Service.

Infers HVAC and electrical distribution chains from equipment types
and calculates real-time energy flow between connected equipment.
Used by the Digital Twin 3D visualisation for animated flow paths.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# ── Flow type colours ────────────────────────────────────────────────
FLOW_COLORS = {
    "chilled_water_supply": "#2563eb",  # blue
    "chilled_water_return": "#ef4444",  # red
    "electrical": "#f59e0b",  # amber
    "condensate": "#06b6d4",  # cyan
}

# ── HVAC equipment hierarchy ────────────────────────────────────────
HVAC_TERMINAL_TYPES = {"fcu", "vav", "split", "crac"}
HVAC_AHU_TYPES = {"ahu"}
HVAC_PLANT_TYPES = {"chiller", "ct"}

# ── Electrical hierarchy ────────────────────────────────────────────
ELECTRICAL_SOURCE_TYPES = {"gen", "generator", "tx", "transformer"}
ELECTRICAL_DIST_TYPES = {"msb", "db", "distribution_board", "mcc", "ats"}


@dataclass
class EnergyFlow:
    """A single energy flow connection between two equipment items."""

    from_equipment: str
    to_equipment: str
    flow_type: str
    power_kw: float
    direction: str  # "forward" or "reverse"
    color: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_equipment": self.from_equipment,
            "to_equipment": self.to_equipment,
            "flow_type": self.flow_type,
            "power_kw": self.power_kw,
            "direction": self.direction,
            "color": self.color,
        }


def _extract_type(equipment: dict[str, Any]) -> str:
    """Extract normalised equipment type from an equipment dict."""
    raw = equipment.get("equipment_type") or equipment.get("type") or equipment.get("device_type") or "unknown"
    return raw.lower().strip()


def _extract_zone(equipment: dict[str, Any]) -> str:
    """Extract a zone/floor identifier from equipment code or metadata."""
    code = equipment.get("code") or equipment.get("id") or ""
    # Pattern: S002-FCU-L2-B  →  L2
    m = re.search(r"-(B\d|G|L\d+)-", code, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # Fallback: check floor metadata
    return (equipment.get("floor") or equipment.get("zone") or "").upper()


def _get_power_kw(equipment: dict[str, Any]) -> float:
    """Best-effort extraction of current power draw in kW."""
    # Check points dict for power-related readings
    points = equipment.get("points") or {}
    for key in ("power", "power_kw", "load", "demand"):
        pt = points.get(key)
        if isinstance(pt, dict):
            val = pt.get("value") or pt.get("default_value")
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass

    # Check direct attributes
    for key in ("power_kw", "rated_power_kw", "load_kw"):
        val = equipment.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass

    # Estimate from equipment type
    etype = _extract_type(equipment)
    defaults: dict[str, float] = {
        "chiller": 120.0,
        "ahu": 22.0,
        "fcu": 3.5,
        "vav": 1.2,
        "split": 5.0,
        "crac": 15.0,
        "gen": 250.0,
        "generator": 250.0,
        "tx": 500.0,
        "transformer": 500.0,
        "msb": 400.0,
        "db": 80.0,
        "ct": 18.0,
    }
    return defaults.get(etype, 5.0)


class EnergyFlowCalculator:
    """Calculates energy flow connections between equipment for 3D visualisation."""

    def get_hvac_chain(self, equipment_list: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
        """Infer HVAC connections from equipment types and zones.

        Returns list of (from_id, to_id, flow_type) tuples.
        """
        connections: list[tuple[str, str, str]] = []

        # Group by type
        chillers = [e for e in equipment_list if _extract_type(e) in HVAC_PLANT_TYPES]
        ahus = [e for e in equipment_list if _extract_type(e) in HVAC_AHU_TYPES]
        terminals = [e for e in equipment_list if _extract_type(e) in HVAC_TERMINAL_TYPES]

        # Chiller → AHU (all AHUs connect to nearest/first chiller)
        for ahu in ahus:
            ahu_id = ahu.get("code") or ahu.get("id") or ""
            if chillers:
                chiller_id = chillers[0].get("code") or chillers[0].get("id") or ""
                connections.append((chiller_id, ahu_id, "chilled_water_supply"))
                connections.append((ahu_id, chiller_id, "chilled_water_return"))

        # AHU → terminals (same zone/floor proximity)
        for terminal in terminals:
            terminal_id = terminal.get("code") or terminal.get("id") or ""
            terminal_zone = _extract_zone(terminal)

            # Find the best AHU match by zone proximity
            best_ahu = None
            for ahu in ahus:
                ahu_zone = _extract_zone(ahu)
                # Exact match or same floor prefix
                if ahu_zone == terminal_zone or (terminal_zone and ahu_zone and terminal_zone[0] == ahu_zone[0]):
                    best_ahu = ahu
                    break

            # Fallback: connect to first AHU
            if best_ahu is None and ahus:
                best_ahu = ahus[0]

            if best_ahu:
                ahu_id = best_ahu.get("code") or best_ahu.get("id") or ""
                connections.append((ahu_id, terminal_id, "chilled_water_supply"))

        return connections

    def get_electrical_chain(self, equipment_list: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
        """Infer electrical distribution connections.

        Returns list of (from_id, to_id, flow_type) tuples.
        """
        connections: list[tuple[str, str, str]] = []

        sources = [e for e in equipment_list if _extract_type(e) in ELECTRICAL_SOURCE_TYPES]
        distributors = [e for e in equipment_list if _extract_type(e) in ELECTRICAL_DIST_TYPES]
        consumers = [
            e
            for e in equipment_list
            if _extract_type(e) not in ELECTRICAL_SOURCE_TYPES
            and _extract_type(e) not in ELECTRICAL_DIST_TYPES
            and _extract_type(e) not in {"meter", "mtr", "sensor"}
        ]

        # Source → MSB/first distributor
        msbs = [d for d in distributors if _extract_type(d) in {"msb", "ats"}]
        dbs = [d for d in distributors if _extract_type(d) not in {"msb", "ats"}]

        for source in sources:
            source_id = source.get("code") or source.get("id") or ""
            if msbs:
                msb_id = msbs[0].get("code") or msbs[0].get("id") or ""
                connections.append((source_id, msb_id, "electrical"))
            elif dbs:
                db_id = dbs[0].get("code") or dbs[0].get("id") or ""
                connections.append((source_id, db_id, "electrical"))

        # MSB → DB
        for msb in msbs:
            msb_id = msb.get("code") or msb.get("id") or ""
            for db in dbs:
                db_id = db.get("code") or db.get("id") or ""
                connections.append((msb_id, db_id, "electrical"))

        # DB → major consumers (limit to HVAC plant to keep graph manageable)
        major_consumers = [
            e for e in consumers if _extract_type(e) in HVAC_PLANT_TYPES | HVAC_AHU_TYPES | {"ups", "bess"}
        ]
        target_dists = dbs if dbs else msbs
        for consumer in major_consumers:
            consumer_id = consumer.get("code") or consumer.get("id") or ""
            if target_dists:
                dist_id = target_dists[0].get("code") or target_dists[0].get("id") or ""
                connections.append((dist_id, consumer_id, "electrical"))

        return connections

    async def calculate_flows(
        self,
        site_id: str,
        equipment_list: list[dict[str, Any]] | None = None,
        timestamp: str | None = None,
    ) -> list[EnergyFlow]:
        """Calculate all energy flows for a site.

        Args:
            site_id: Site identifier (UUID or code).
            equipment_list: Pre-fetched equipment list (if None, loads from repo).
            timestamp: ISO timestamp for historical query (None = current).

        Returns:
            List of EnergyFlow objects representing connections.
        """
        if equipment_list is None:
            equipment_list = await self._load_equipment(site_id)

        if not equipment_list:
            return []

        flows: list[EnergyFlow] = []

        # HVAC chain
        hvac_connections = self.get_hvac_chain(equipment_list)
        eq_map = {(e.get("code") or e.get("id") or ""): e for e in equipment_list}

        for from_id, to_id, flow_type in hvac_connections:
            from_eq = eq_map.get(from_id, {})
            to_eq = eq_map.get(to_id, {})
            power = _get_power_kw(to_eq) if flow_type == "chilled_water_supply" else _get_power_kw(from_eq)
            flows.append(
                EnergyFlow(
                    from_equipment=from_id,
                    to_equipment=to_id,
                    flow_type=flow_type,
                    power_kw=round(power, 1),
                    direction="forward",
                    color=FLOW_COLORS.get(flow_type, "#94a3b8"),
                )
            )

        # Electrical chain
        elec_connections = self.get_electrical_chain(equipment_list)
        for from_id, to_id, flow_type in elec_connections:
            to_eq = eq_map.get(to_id, {})
            power = _get_power_kw(to_eq)
            flows.append(
                EnergyFlow(
                    from_equipment=from_id,
                    to_equipment=to_id,
                    flow_type=flow_type,
                    power_kw=round(power, 1),
                    direction="forward",
                    color=FLOW_COLORS.get(flow_type, "#94a3b8"),
                )
            )

        return flows

    async def _load_equipment(self, site_id: str) -> list[dict[str, Any]]:
        """Load equipment from repository with 3-tier fallback."""
        try:
            from app.database.repositories.equipment_repository import EquipmentRepository

            repo = EquipmentRepository()
            return repo.get_all(site_id=site_id)
        except Exception as e:
            logger.warning(f"Supabase equipment load failed, trying JSON fallback: {e}")

        # JSON fallback
        try:
            return self._load_equipment_json(site_id)
        except Exception as e2:
            logger.error(f"JSON equipment fallback also failed: {e2}")
            return []

    def _load_equipment_json(self, site_id: str) -> list[dict[str, Any]]:
        """Load equipment from JSON fallback files."""
        import json
        from pathlib import Path

        data_dir = Path(__file__).parent.parent / "data" / "sites" / site_id / "equipment"
        if not data_dir.exists():
            # Try site-002 as default seeded site
            data_dir = Path(__file__).parent.parent / "data" / "sites" / "site-002" / "equipment"

        if not data_dir.exists():
            return []

        equipment = []
        for f in data_dir.glob("*.json"):
            try:
                with open(f) as fh:
                    eq = json.load(fh)
                    if not eq.get("code"):
                        eq["code"] = eq.get("id", f.stem)
                    equipment.append(eq)
            except Exception:
                logger.warning(f"Failed to load equipment JSON {f}")
        return equipment

    async def get_historical_state(
        self,
        site_id: str,
        timestamp: str,
    ) -> list[dict[str, Any]]:
        """Get equipment state at a specific historical timestamp.

        Uses live telemetry rows only. If no rows exist at or before the
        requested timestamp, returns an empty list.

        Args:
            site_id: Site identifier.
            timestamp: ISO format timestamp.

        Returns:
            List of equipment dicts with health/status/power at that timestamp.
        """
        requested_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        client = get_supabase_client()
        response = (
            client.table("equipment_sensor_readings")
            .select("equipment_id,sensor_type,value,unit,recorded_at,metadata")
            .eq("site_id", site_id)
            .lte("recorded_at", requested_at.isoformat())
            .order("recorded_at", desc=True)
            .limit(2000)
            .execute()
        )

        latest_by_equipment: dict[str, dict[str, Any]] = {}
        for row in response.data or []:
            equipment_id = row.get("equipment_id")
            sensor_type = row.get("sensor_type")
            if not equipment_id or not sensor_type:
                continue
            equipment_state = latest_by_equipment.setdefault(
                equipment_id,
                {
                    "code": equipment_id,
                    "type": (row.get("metadata") or {}).get("equipment_type", "unknown")
                    if isinstance(row.get("metadata"), dict)
                    else "unknown",
                    "timestamp": timestamp,
                    "data_source": "equipment_sensor_readings",
                    "points": {},
                },
            )
            if sensor_type not in equipment_state["points"]:
                equipment_state["points"][sensor_type] = {
                    "value": row.get("value"),
                    "unit": row.get("unit"),
                    "recorded_at": row.get("recorded_at"),
                }

        return list(latest_by_equipment.values())


# ── Singleton ───────────────────────────────────────────────────────
_instance: EnergyFlowCalculator | None = None


def get_energy_flow_calculator() -> EnergyFlowCalculator:
    """Get or create the singleton EnergyFlowCalculator."""
    global _instance
    if _instance is None:
        _instance = EnergyFlowCalculator()
    return _instance
