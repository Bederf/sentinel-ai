"""
Complaint Handling Models
=========================
Pydantic models for desk-to-zone mapping and comfort complaint handling.
Enables intelligent complaint handling by linking desk locations to HVAC zones.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any, Literal
from pydantic import BaseModel, Field
import uuid


class Desk(BaseModel):
    """
    Desk location model - maps physical desk to HVAC zone and DALI lighting.

    Enables the killer feature: "Too hot at Desk 25" -> instant BMS diagnosis.

    Integrates:
    - HVAC zone (FCU, VAV, AHU)
    - DALI-2 lighting (Tridonic Scenecom)
    - Environmental context (window, orientation, heat sources)
    """
    desk_id: str  # e.g., "L2-D025" or "25"
    floor: str  # e.g., "Level 2"
    building: str = ""  # e.g., "Sandton" (can be inferred from folder)
    zone_id: str  # e.g., "Zone-L2-C"

    # Environmental context
    near_window: bool = False
    orientation: Optional[str] = None  # "N", "S", "E", "W", "NE", "NW", "SE", "SW" - for solar analysis
    near_diffuser: Optional[str] = None  # e.g., "DIFF-25" if under a supply diffuser
    near_printer: bool = False

    # Organizational
    department: Optional[str] = None
    occupant: Optional[str] = None  # Who sits here

    # Floor plan position
    x_coord: Optional[float] = None
    y_coord: Optional[float] = None

    # DALI-2 Scenecom integration (Tridonic)
    dali_zone: Optional[str] = None  # DALI zone/group (e.g., "Zone-L2-C" - often matches HVAC zone)
    sensor_id: Optional[str] = None  # PIR occupancy sensor (e.g., "S002-PIR-L2-C-001")
    luminaire_ids: Optional[List[str]] = None  # Luminaires serving this desk (e.g., ["S002-LUM-L2-001", "S002-LUM-L2-002"])
    dali_controller: Optional[str] = None  # Scenecom controller (e.g., "S002-DALI-L2-01")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "desk_id": self.desk_id,
            "floor": self.floor,
            "building": self.building,
            "zone_id": self.zone_id,
            "near_window": self.near_window,
            "orientation": self.orientation,
            "near_diffuser": self.near_diffuser,
            "near_printer": self.near_printer,
            "department": self.department,
            "occupant": self.occupant,
            "x_coord": self.x_coord,
            "y_coord": self.y_coord,
            "dali_zone": self.dali_zone,
            "sensor_id": self.sensor_id,
            "luminaire_ids": self.luminaire_ids,
            "dali_controller": self.dali_controller,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Desk":
        """Create instance from dictionary.

        Handles both JSON schema (near_diffuser as string ID) and
        Supabase schema (near_diffuser as bool, diffuser_id as string).
        """
        # Handle near_diffuser: Supabase has bool + diffuser_id, JSON has string
        near_diffuser_val = data.get("near_diffuser")
        if isinstance(near_diffuser_val, bool):
            # Supabase schema: use diffuser_id if near_diffuser is True
            near_diffuser = data.get("diffuser_id") if near_diffuser_val else None
        else:
            # JSON schema: near_diffuser is already the ID string
            near_diffuser = near_diffuser_val

        return cls(
            desk_id=data.get("desk_id", ""),
            floor=data.get("floor", ""),
            building=data.get("building", ""),
            zone_id=data.get("zone_id", ""),
            near_window=data.get("near_window", False),
            orientation=data.get("orientation") or data.get("window_facing"),
            near_diffuser=near_diffuser,
            near_printer=data.get("near_printer", False),
            department=data.get("department"),
            occupant=data.get("occupant") or data.get("assigned_to"),
            x_coord=data.get("x_coord"),
            y_coord=data.get("y_coord"),
            dali_zone=data.get("dali_zone"),
            sensor_id=data.get("sensor_id"),
            luminaire_ids=data.get("luminaire_ids"),
            dali_controller=data.get("dali_controller"),
        )


class HVACZone(BaseModel):
    """
    HVAC zone model - contains zone equipment and current status.

    Links to FCUs, VAVs, AHUs, and sensors for complete BMS context.
    """
    zone_id: str  # e.g., "Zone-L2-C"
    zone_name: Optional[str] = None  # e.g., "Level 2 Zone C"
    floor: Optional[str] = None
    fcu_id: Optional[str] = None  # e.g., "S002-FCU-L2-C"
    vav_id: Optional[str] = None
    ahu_id: Optional[str] = None
    temp_sensor: Optional[str] = None  # e.g., "S002-TS-L2-C"
    co2_sensor: Optional[str] = None
    typical_occupancy: Optional[int] = None
    area_sqm: Optional[float] = None
    setpoint: float = 22.0
    current_temp: float = 22.0
    status: str = "running"  # 'running', 'off', 'fault'

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "floor": self.floor,
            "fcu_id": self.fcu_id,
            "vav_id": self.vav_id,
            "ahu_id": self.ahu_id,
            "temp_sensor": self.temp_sensor,
            "co2_sensor": self.co2_sensor,
            "typical_occupancy": self.typical_occupancy,
            "area_sqm": self.area_sqm,
            "setpoint": self.setpoint,
            "current_temp": self.current_temp,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HVACZone":
        """Create instance from dictionary."""
        return cls(
            zone_id=data.get("zone_id", ""),
            zone_name=data.get("zone_name", ""),
            floor=data.get("floor", ""),
            fcu_id=data.get("fcu_id", ""),
            vav_id=data.get("vav_id"),
            ahu_id=data.get("ahu_id"),
            temp_sensor=data.get("temp_sensor", ""),
            co2_sensor=data.get("co2_sensor"),
            typical_occupancy=data.get("typical_occupancy", 0),
            area_sqm=data.get("area_sqm"),
            setpoint=data.get("setpoint", 22.0),
            current_temp=data.get("current_temp", 22.0),
            status=data.get("status", "running"),
        )


class ComfortComplaint(BaseModel):
    """
    Comfort complaint record - logged when user reports discomfort.

    Tracks complaints for pattern analysis and escalation.
    """
    complaint_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.now)
    desk_id: str
    user_name: Optional[str] = None
    complaint_type: Literal["too_hot", "too_cold", "stuffy", "drafty", "other"]
    description: Optional[str] = None
    status: Literal["open", "diagnosed", "resolved", "escalated"] = "open"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "complaint_id": self.complaint_id,
            "timestamp": self.timestamp.isoformat(),
            "desk_id": self.desk_id,
            "user_name": self.user_name,
            "complaint_type": self.complaint_type,
            "description": self.description,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ComfortComplaint":
        """Create instance from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now()

        return cls(
            complaint_id=data.get("complaint_id", str(uuid.uuid4())),
            timestamp=timestamp,
            desk_id=data.get("desk_id", ""),
            user_name=data.get("user_name"),
            complaint_type=data.get("complaint_type", "other"),
            description=data.get("description"),
            status=data.get("status", "open"),
        )


class ComplaintDiagnosis(BaseModel):
    """
    Diagnosis result from analyzing a comfort complaint.

    Combines desk context, zone context, and AI analysis for actionable insights.
    """
    complaint_id: str
    desk: Desk
    zone: HVACZone
    diagnosis: str  # From CrossSystemAnalyzer
    root_cause: str
    confidence: Literal["high", "medium", "low"]
    suggestions: List[str]
    auto_action_taken: Optional[str] = None
    needs_dispatch: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "complaint_id": self.complaint_id,
            "desk": self.desk.to_dict(),
            "zone": self.zone.to_dict(),
            "diagnosis": self.diagnosis,
            "root_cause": self.root_cause,
            "confidence": self.confidence,
            "suggestions": self.suggestions,
            "auto_action_taken": self.auto_action_taken,
            "needs_dispatch": self.needs_dispatch,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ComplaintDiagnosis":
        """Create instance from dictionary."""
        return cls(
            complaint_id=data.get("complaint_id", ""),
            desk=Desk.from_dict(data.get("desk", {})),
            zone=HVACZone.from_dict(data.get("zone", {})),
            diagnosis=data.get("diagnosis", ""),
            root_cause=data.get("root_cause", ""),
            confidence=data.get("confidence", "low"),
            suggestions=data.get("suggestions", []),
            auto_action_taken=data.get("auto_action_taken"),
            needs_dispatch=data.get("needs_dispatch", False),
        )
