"""
Service Feedback Collection Service

Manages the collection of technician feedback after work order completion.
Equipment-type specific templates define what data is required.
Feedback is used to update equipment health scores.

Phase 59: Service Feedback & Health Score Integration
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from app.database.supabase_client import get_supabase_client
from app.database.repositories.service_record_repository import ServiceRecordRepository
from app.database.repositories.equipment_repository import EquipmentRepository
from app.database.repositories.baseline_repository import BaselineRepository

logger = logging.getLogger(__name__)

# Path to ML data templates
TEMPLATES_PATH = Path(__file__).parent.parent / "data" / "ml_data_templates.json"


class FeedbackItemType(str, Enum):
    """Types of feedback items."""
    READING = "reading"
    PHOTO = "photo"
    AUDIO = "audio"
    OBSERVATION = "observation"
    CHECKLIST = "checklist"


class HealthImpact(str, Enum):
    """Health score impact direction."""
    POSITIVE = "positive"  # Reading improved vs baseline
    NEUTRAL = "neutral"    # Reading within normal range
    NEGATIVE = "negative"  # Reading worse than baseline or out of range
    CRITICAL = "critical"  # Reading in critical range


@dataclass
class FeedbackItem:
    """A single feedback item submitted by technician."""
    item_type: FeedbackItemType
    item_key: str  # e.g., "vibration", "oil_level", "before_photo"
    value: Any
    unit: Optional[str] = None
    numeric_value: Optional[float] = None
    file_path: Optional[str] = None
    confidence: float = 1.0
    baseline_value: Optional[float] = None
    deviation_percent: Optional[float] = None
    health_impact: HealthImpact = HealthImpact.NEUTRAL
    notes: Optional[str] = None


@dataclass
class FeedbackTemplate:
    """Template defining required feedback for equipment type."""
    equipment_type: str
    service_type: str
    required_items: List[str]
    optional_items: List[str]
    prompts: Dict[str, str]
    validation_rules: Dict[str, Dict[str, Any]]
    audio_duration_seconds: int = 10


@dataclass
class FeedbackSession:
    """Active feedback collection session."""
    session_id: str
    work_order_id: str
    equipment_id: str
    equipment_code: str
    equipment_type: str
    service_type: str
    template: FeedbackTemplate
    items_collected: List[str] = field(default_factory=list)
    feedback_items: List[FeedbackItem] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    health_score_change: int = 0
    status: str = "in_progress"


class FeedbackCollectionService:
    """
    Service for collecting and processing technician feedback.

    Responsibilities:
    - Load equipment-type specific templates
    - Track feedback collection progress
    - Validate readings against baselines
    - Calculate health score impact
    - Update equipment health after completion
    """

    def __init__(self):
        self._templates: Dict[str, Dict[str, FeedbackTemplate]] = {}
        self._sessions: Dict[str, FeedbackSession] = {}
        self._load_templates()
        self.service_record_repo = ServiceRecordRepository()
        self.equipment_repo = EquipmentRepository()
        self.baseline_repo = BaselineRepository()

    def _load_templates(self) -> None:
        """Load feedback templates from JSON file."""
        try:
            if TEMPLATES_PATH.exists():
                with open(TEMPLATES_PATH) as f:
                    raw_templates = json.load(f)

                for eq_type, service_types in raw_templates.items():
                    self._templates[eq_type] = {}
                    for svc_type, template_data in service_types.items():
                        self._templates[eq_type][svc_type] = FeedbackTemplate(
                            equipment_type=eq_type,
                            service_type=svc_type,
                            required_items=template_data.get("required", []),
                            optional_items=template_data.get("optional", []),
                            prompts=template_data.get("prompts", {}),
                            validation_rules=template_data.get("validation_rules", {}),
                            audio_duration_seconds=template_data.get("audio_duration_seconds", 10)
                        )

                logger.info(f"Loaded feedback templates for {len(self._templates)} equipment types")
            else:
                logger.warning(f"Templates file not found: {TEMPLATES_PATH}")
        except Exception as e:
            logger.error(f"Failed to load feedback templates: {e}")

    def get_template(self, equipment_type: str, service_type: str) -> Optional[FeedbackTemplate]:
        """Get feedback template for equipment type and service type."""
        eq_templates = self._templates.get(equipment_type.lower())
        if not eq_templates:
            # Try to find partial match
            for key in self._templates:
                if key in equipment_type.lower() or equipment_type.lower() in key:
                    eq_templates = self._templates[key]
                    break

        if not eq_templates:
            logger.warning(f"No template found for equipment type: {equipment_type}")
            return self._get_default_template(equipment_type, service_type)

        template = eq_templates.get(service_type.lower())
        if not template:
            # Fall back to minor if specific type not found
            template = eq_templates.get("minor")

        return template

    def _get_default_template(self, equipment_type: str, service_type: str) -> FeedbackTemplate:
        """Return a default template for unknown equipment types."""
        return FeedbackTemplate(
            equipment_type=equipment_type,
            service_type=service_type,
            required_items=["service_sheet", "observation"],
            optional_items=["issue_photo", "before_photo", "after_photo"],
            prompts={
                "service_sheet": "Photo of completed service sheet with readings",
                "observation": "Describe the work performed and equipment condition",
                "issue_photo": "Photo of any issues found (optional)",
                "before_photo": "Before photo (optional)",
                "after_photo": "After photo (optional)"
            },
            validation_rules={}
        )

    def _parse_equipment_type(self, equipment_code: str) -> str:
        """
        Parse equipment type from equipment code.
        Format: {site}-{type}-{floor}-{zone}
        Example: S002-CHILLER-B1-001 -> chiller
        """
        parts = equipment_code.split("-")
        if len(parts) >= 2:
            eq_type = parts[1].lower()
            # Map common abbreviations
            type_mapping = {
                "ch": "chiller",
                "ahu": "ahu",
                "fcu": "fcu",
                "vav": "vav",
                "gen": "generator",
                "ups": "ups",
                "tx": "transformer",
                "ats": "ats",
                "dali": "dali_controller",
                "mtr": "power_meter",
                "pump": "pump",
                "ct": "cooling_tower",
            }
            return type_mapping.get(eq_type, eq_type)
        return "unknown"

    async def start_feedback_session(
        self,
        work_order_id: str,
        equipment_id: str,
        equipment_code: str,
        service_type: str = "minor"
    ) -> FeedbackSession:
        """
        Start a new feedback collection session for a work order.

        Args:
            work_order_id: Work order being completed
            equipment_id: Equipment UUID
            equipment_code: Equipment code (e.g., S002-CHILLER-B1-001)
            service_type: Type of service (minor, major, breakdown)

        Returns:
            FeedbackSession with template and tracking info
        """
        # Parse equipment type from code
        equipment_type = self._parse_equipment_type(equipment_code)

        # Get template for this equipment type
        template = self.get_template(equipment_type, service_type)
        if not template:
            template = self._get_default_template(equipment_type, service_type)

        # Create session
        session_id = f"fb-{work_order_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        session = FeedbackSession(
            session_id=session_id,
            work_order_id=work_order_id,
            equipment_id=equipment_id,
            equipment_code=equipment_code,
            equipment_type=equipment_type,
            service_type=service_type,
            template=template,
            started_at=datetime.now()
        )

        self._sessions[session_id] = session

        logger.info(
            f"Started feedback session {session_id} for {equipment_code} "
            f"({equipment_type}/{service_type}), {len(template.required_items)} required items"
        )

        return session

    def get_session(self, session_id: str) -> Optional[FeedbackSession]:
        """Get an active feedback session."""
        return self._sessions.get(session_id)

    def get_next_prompt(self, session_id: str) -> Optional[Tuple[str, str, bool]]:
        """
        Get the next item to collect and its prompt.

        Returns:
            Tuple of (item_key, prompt_text, is_required) or None if complete
        """
        session = self._sessions.get(session_id)
        if not session:
            return None

        # Check required items first
        for item in session.template.required_items:
            if item not in session.items_collected:
                prompt = session.template.prompts.get(item, f"Please provide: {item}")
                return (item, prompt, True)

        # Then optional items
        for item in session.template.optional_items:
            if item not in session.items_collected:
                prompt = session.template.prompts.get(item, f"Optional: {item}")
                return (item, prompt, False)

        return None  # All items collected

    async def submit_feedback_item(
        self,
        session_id: str,
        item_key: str,
        value: Any,
        item_type: FeedbackItemType = FeedbackItemType.READING,
        unit: Optional[str] = None,
        file_path: Optional[str] = None,
        notes: Optional[str] = None
    ) -> FeedbackItem:
        """
        Submit a feedback item for a session.

        Args:
            session_id: Active session ID
            item_key: Key of the item being submitted (e.g., "vibration")
            value: The value (numeric, text, or file reference)
            item_type: Type of feedback item
            unit: Unit of measurement
            file_path: Path to uploaded file (for photos/audio)
            notes: Additional notes

        Returns:
            FeedbackItem with validation and health impact calculated
        """
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        # Parse numeric value if applicable
        numeric_value = None
        if isinstance(value, (int, float)):
            numeric_value = float(value)
        elif isinstance(value, str):
            try:
                numeric_value = float(value.replace(",", "."))
            except ValueError:
                pass

        # Get validation rules for this item
        validation_rules = session.template.validation_rules.get(item_key, {})

        # Create feedback item
        feedback_item = FeedbackItem(
            item_type=item_type,
            item_key=item_key,
            value=value,
            unit=unit or validation_rules.get("unit"),
            numeric_value=numeric_value,
            file_path=file_path,
            notes=notes
        )

        # Validate against rules if numeric
        if numeric_value is not None and validation_rules:
            feedback_item = await self._validate_reading(
                session, feedback_item, validation_rules
            )

        # Add to session
        session.feedback_items.append(feedback_item)
        if item_key not in session.items_collected:
            session.items_collected.append(item_key)

        logger.info(
            f"Session {session_id}: Collected {item_key} = {value} "
            f"(impact: {feedback_item.health_impact.value})"
        )

        return feedback_item

    async def _validate_reading(
        self,
        session: FeedbackSession,
        item: FeedbackItem,
        rules: Dict[str, Any]
    ) -> FeedbackItem:
        """
        Validate a reading against rules and baseline.
        Calculate health impact.
        """
        value = item.numeric_value
        if value is None:
            return item

        # Check against validation rules (min/max)
        min_val = rules.get("min")
        max_val = rules.get("max")

        if min_val is not None and value < min_val:
            item.health_impact = HealthImpact.NEGATIVE
            item.notes = f"Below minimum ({min_val})"
        elif max_val is not None and value > max_val:
            item.health_impact = HealthImpact.NEGATIVE
            item.notes = f"Above maximum ({max_val})"
        else:
            item.health_impact = HealthImpact.NEUTRAL

        # Try to compare against baseline
        try:
            baseline = await self.baseline_repo.get_active_equipment_baseline(
                session.equipment_id
            )
            if baseline and baseline.baseline_values:
                baseline_value = baseline.baseline_values.get(item.item_key)
                if baseline_value is not None:
                    item.baseline_value = float(baseline_value)

                    # Calculate deviation
                    if item.baseline_value != 0:
                        deviation = ((value - item.baseline_value) / item.baseline_value) * 100
                        item.deviation_percent = round(deviation, 2)

                        # Determine health impact based on deviation
                        # For most readings, lower deviation is better
                        abs_deviation = abs(deviation)
                        if abs_deviation <= 5:
                            item.health_impact = HealthImpact.POSITIVE
                        elif abs_deviation <= 15:
                            item.health_impact = HealthImpact.NEUTRAL
                        elif abs_deviation <= 30:
                            item.health_impact = HealthImpact.NEGATIVE
                        else:
                            item.health_impact = HealthImpact.CRITICAL
        except Exception as e:
            logger.warning(f"Failed to compare against baseline: {e}")

        return item

    def calculate_health_score_change(self, session_id: str) -> int:
        """
        Calculate the overall health score change from feedback.

        Returns:
            Integer change to health score (-20 to +10)
        """
        session = self._sessions.get(session_id)
        if not session:
            return 0

        # Count impacts
        positive_count = 0
        neutral_count = 0
        negative_count = 0
        critical_count = 0

        for item in session.feedback_items:
            if item.health_impact == HealthImpact.POSITIVE:
                positive_count += 1
            elif item.health_impact == HealthImpact.NEUTRAL:
                neutral_count += 1
            elif item.health_impact == HealthImpact.NEGATIVE:
                negative_count += 1
            elif item.health_impact == HealthImpact.CRITICAL:
                critical_count += 1

        # Calculate score change
        # Positive readings: +2 each (max +10)
        # Negative readings: -3 each
        # Critical readings: -5 each
        score_change = (
            min(positive_count * 2, 10) +
            (negative_count * -3) +
            (critical_count * -5)
        )

        # Clamp to range
        score_change = max(-20, min(10, score_change))

        session.health_score_change = score_change
        return score_change

    async def complete_feedback_session(
        self,
        session_id: str,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Complete a feedback session and update equipment health.

        Args:
            session_id: Session to complete
            force: Complete even if required items missing

        Returns:
            Summary including health score change and any warnings
        """
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        # Check required items
        missing_required = []
        for item in session.template.required_items:
            if item not in session.items_collected:
                missing_required.append(item)

        if missing_required and not force:
            return {
                "success": False,
                "error": "missing_required_items",
                "missing_items": missing_required,
                "message": f"Missing required items: {', '.join(missing_required)}"
            }

        # Calculate health score change
        health_change = self.calculate_health_score_change(session_id)

        # Update equipment health in database
        try:
            equipment = self.equipment_repo.get_by_id(session.equipment_code)
            if equipment:
                current_health = equipment.get("health_score", 70)
                new_health = max(0, min(100, current_health + health_change))

                # Determine new status based on health
                if new_health >= 80:
                    new_status = "normal"
                elif new_health >= 60:
                    new_status = "warning"
                else:
                    new_status = "critical"

                self.equipment_repo.update(session.equipment_code, {
                    "health_score": new_health,
                    "status": new_status,
                    "last_service_date": datetime.now().isoformat()
                })

                logger.info(
                    f"Updated {session.equipment_code} health: {current_health} -> {new_health} "
                    f"(change: {health_change:+d})"
                )
        except Exception as e:
            logger.error(f"Failed to update equipment health: {e}")

        # Mark session complete
        session.completed_at = datetime.now()
        session.status = "completed"

        # Build summary
        summary = {
            "success": True,
            "session_id": session_id,
            "equipment_code": session.equipment_code,
            "equipment_type": session.equipment_type,
            "service_type": session.service_type,
            "items_collected": len(session.items_collected),
            "required_items": len(session.template.required_items),
            "optional_items": len(session.template.optional_items),
            "health_score_change": health_change,
            "feedback_summary": self._build_feedback_summary(session),
            "warnings": missing_required if missing_required else [],
            "completed_at": session.completed_at.isoformat()
        }

        return summary

    def _build_feedback_summary(self, session: FeedbackSession) -> Dict[str, Any]:
        """Build a summary of collected feedback."""
        readings = []
        attachments = []
        observations = []

        for item in session.feedback_items:
            if item.item_type == FeedbackItemType.READING:
                readings.append({
                    "key": item.item_key,
                    "value": item.value,
                    "unit": item.unit,
                    "baseline": item.baseline_value,
                    "deviation_percent": item.deviation_percent,
                    "health_impact": item.health_impact.value
                })
            elif item.item_type in (FeedbackItemType.PHOTO, FeedbackItemType.AUDIO):
                attachments.append({
                    "key": item.item_key,
                    "file_path": item.file_path,
                    "type": item.item_type.value
                })
            elif item.item_type == FeedbackItemType.OBSERVATION:
                observations.append({
                    "key": item.item_key,
                    "content": item.value,
                    "notes": item.notes
                })

        return {
            "readings": readings,
            "attachments": attachments,
            "observations": observations,
            "impact_counts": {
                "positive": sum(1 for i in session.feedback_items if i.health_impact == HealthImpact.POSITIVE),
                "neutral": sum(1 for i in session.feedback_items if i.health_impact == HealthImpact.NEUTRAL),
                "negative": sum(1 for i in session.feedback_items if i.health_impact == HealthImpact.NEGATIVE),
                "critical": sum(1 for i in session.feedback_items if i.health_impact == HealthImpact.CRITICAL)
            }
        }

    def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a feedback session."""
        session = self._sessions.get(session_id)
        if not session:
            return None

        # Calculate progress
        total_required = len(session.template.required_items)
        collected_required = sum(
            1 for item in session.template.required_items
            if item in session.items_collected
        )

        next_prompt = self.get_next_prompt(session_id)

        return {
            "session_id": session_id,
            "status": session.status,
            "equipment_code": session.equipment_code,
            "equipment_type": session.equipment_type,
            "service_type": session.service_type,
            "progress": {
                "required_collected": collected_required,
                "required_total": total_required,
                "optional_collected": len(session.items_collected) - collected_required,
                "optional_total": len(session.template.optional_items),
                "percent_complete": round((collected_required / total_required * 100) if total_required > 0 else 100)
            },
            "items_collected": session.items_collected,
            "next_item": {
                "key": next_prompt[0] if next_prompt else None,
                "prompt": next_prompt[1] if next_prompt else None,
                "required": next_prompt[2] if next_prompt else None
            } if next_prompt else None,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "completed_at": session.completed_at.isoformat() if session.completed_at else None
        }


# Singleton instance
_feedback_service: Optional[FeedbackCollectionService] = None


def get_feedback_collection_service() -> FeedbackCollectionService:
    """Get singleton feedback collection service."""
    global _feedback_service
    if _feedback_service is None:
        _feedback_service = FeedbackCollectionService()
    return _feedback_service
