"""
Service Feedback Collection Service

Manages the collection of technician feedback after work order completion.
Equipment-type specific templates define what data is required.
Feedback is used to update equipment health scores.

Phase 59: Service Feedback & Health Score Integration
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from app.database.repositories.baseline_repository import BaselineRepository
from app.database.repositories.equipment_repository import EquipmentRepository
from app.database.repositories.service_record_repository import ServiceRecordRepository

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
    NEUTRAL = "neutral"  # Reading within normal range
    NEGATIVE = "negative"  # Reading worse than baseline or out of range
    CRITICAL = "critical"  # Reading in critical range


@dataclass
class FeedbackItem:
    """A single feedback item submitted by technician."""

    item_type: FeedbackItemType
    item_key: str  # e.g., "vibration", "oil_level", "before_photo"
    value: Any
    unit: str | None = None
    numeric_value: float | None = None
    file_path: str | None = None
    confidence: float = 1.0
    baseline_value: float | None = None
    deviation_percent: float | None = None
    health_impact: HealthImpact = HealthImpact.NEUTRAL
    notes: str | None = None


@dataclass
class FeedbackTemplate:
    """Template defining required feedback for equipment type."""

    equipment_type: str
    service_type: str
    required_items: list[str]
    optional_items: list[str]
    prompts: dict[str, str]
    validation_rules: dict[str, dict[str, Any]]
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
    items_collected: list[str] = field(default_factory=list)
    feedback_items: list[FeedbackItem] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    health_score_change: int = 0
    status: str = "in_progress"

    def to_dict(self) -> dict[str, Any]:
        """Serialize session for Redis persistence."""
        return {
            "session_id": self.session_id,
            "work_order_id": self.work_order_id,
            "equipment_id": self.equipment_id,
            "equipment_code": self.equipment_code,
            "equipment_type": self.equipment_type,
            "service_type": self.service_type,
            "template": {
                "equipment_type": self.template.equipment_type,
                "service_type": self.template.service_type,
                "required_items": self.template.required_items,
                "optional_items": self.template.optional_items,
                "prompts": self.template.prompts,
                "validation_rules": self.template.validation_rules,
                "audio_duration_seconds": self.template.audio_duration_seconds,
            },
            "items_collected": self.items_collected,
            "feedback_items": [
                {
                    "item_type": fi.item_type.value,
                    "item_key": fi.item_key,
                    "value": fi.value,
                    "unit": fi.unit,
                    "numeric_value": fi.numeric_value,
                    "file_path": fi.file_path,
                    "confidence": fi.confidence,
                    "baseline_value": fi.baseline_value,
                    "deviation_percent": fi.deviation_percent,
                    "health_impact": fi.health_impact.value,
                    "notes": fi.notes,
                }
                for fi in self.feedback_items
            ],
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "health_score_change": self.health_score_change,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeedbackSession":
        """Reconstruct FeedbackSession from serialized dict (Redis/JSON)."""
        tmpl_data = data.get("template", {})
        template = FeedbackTemplate(
            equipment_type=tmpl_data.get("equipment_type", ""),
            service_type=tmpl_data.get("service_type", ""),
            required_items=tmpl_data.get("required_items", []),
            optional_items=tmpl_data.get("optional_items", []),
            prompts=tmpl_data.get("prompts", {}),
            validation_rules=tmpl_data.get("validation_rules", {}),
            audio_duration_seconds=tmpl_data.get("audio_duration_seconds", 10),
        )

        feedback_items = []
        for fi_data in data.get("feedback_items", []):
            feedback_items.append(
                FeedbackItem(
                    item_type=FeedbackItemType(fi_data.get("item_type", "reading")),
                    item_key=fi_data.get("item_key", ""),
                    value=fi_data.get("value"),
                    unit=fi_data.get("unit"),
                    numeric_value=fi_data.get("numeric_value"),
                    file_path=fi_data.get("file_path"),
                    confidence=fi_data.get("confidence", 1.0),
                    baseline_value=fi_data.get("baseline_value"),
                    deviation_percent=fi_data.get("deviation_percent"),
                    health_impact=HealthImpact(fi_data.get("health_impact", "neutral")),
                    notes=fi_data.get("notes"),
                )
            )

        session = cls(
            session_id=data["session_id"],
            work_order_id=data.get("work_order_id", ""),
            equipment_id=data.get("equipment_id", ""),
            equipment_code=data.get("equipment_code", ""),
            equipment_type=data.get("equipment_type", ""),
            service_type=data.get("service_type", ""),
            template=template,
            items_collected=data.get("items_collected", []),
            feedback_items=feedback_items,
            health_score_change=data.get("health_score_change", 0),
            status=data.get("status", "in_progress"),
        )
        if data.get("started_at"):
            session.started_at = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at"):
            session.completed_at = datetime.fromisoformat(data["completed_at"])
        return session


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
        from app.services.redis_session_store import RedisSessionStore

        self._templates: dict[str, dict[str, FeedbackTemplate]] = {}
        self._store = RedisSessionStore(
            prefix="bms:feedback",
            ttl_seconds=14400,  # 4 hours
            deserializer=FeedbackSession.from_dict,
        )
        self._load_templates()
        self.service_record_repo = ServiceRecordRepository()
        self.equipment_repo = EquipmentRepository()
        self.baseline_repo = BaselineRepository()

    @property
    def _sessions(self) -> dict[str, FeedbackSession]:
        """Backward-compat: expose in-memory dict from store."""
        return self._store._memory

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
                            audio_duration_seconds=template_data.get("audio_duration_seconds", 10),
                        )

                logger.info(f"Loaded feedback templates for {len(self._templates)} equipment types")
            else:
                logger.warning(f"Templates file not found: {TEMPLATES_PATH}")
        except Exception as e:
            logger.error(f"Failed to load feedback templates: {e}")

    def get_template(self, equipment_type: str, service_type: str) -> FeedbackTemplate | None:
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
                "after_photo": "After photo (optional)",
            },
            validation_rules={},
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
        self, work_order_id: str, equipment_id: str, equipment_code: str, service_type: str = "minor"
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
            started_at=datetime.now(),
        )

        self._store.put(session_id, session)

        logger.info(
            f"Started feedback session {session_id} for {equipment_code} "
            f"({equipment_type}/{service_type}), {len(template.required_items)} required items"
        )

        return session

    def get_session(self, session_id: str) -> FeedbackSession | None:
        """Get an active feedback session."""
        return self._store.get(session_id)

    def get_next_prompt(self, session_id: str) -> tuple[str, str, bool] | None:
        """
        Get the next item to collect and its prompt.

        Returns:
            Tuple of (item_key, prompt_text, is_required) or None if complete
        """
        session = self._store.get(session_id)
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
        unit: str | None = None,
        file_path: str | None = None,
        notes: str | None = None,
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
        session = self._store.get(session_id)
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
            notes=notes,
        )

        # Validate against rules if numeric
        if numeric_value is not None and validation_rules:
            feedback_item = await self._validate_reading(session, feedback_item, validation_rules)

        # Add to session
        session.feedback_items.append(feedback_item)
        if item_key not in session.items_collected:
            session.items_collected.append(item_key)

        # Persist updated session
        self._store.put(session_id, session)

        logger.info(
            f"Session {session_id}: Collected {item_key} = {value} (impact: {feedback_item.health_impact.value})"
        )

        return feedback_item

    async def _validate_reading(
        self, session: FeedbackSession, item: FeedbackItem, rules: dict[str, Any]
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
            baseline = await self.baseline_repo.get_active_equipment_baseline(session.equipment_id)
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
        session = self._store.get(session_id)
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
        score_change = min(positive_count * 2, 10) + (negative_count * -3) + (critical_count * -5)

        # Clamp to range
        score_change = max(-20, min(10, score_change))

        session.health_score_change = score_change
        return score_change

    async def complete_feedback_session(self, session_id: str, force: bool = False) -> dict[str, Any]:
        """
        Complete a feedback session and update equipment health.

        Args:
            session_id: Session to complete
            force: Complete even if required items missing

        Returns:
            Summary including health score change and any warnings
        """
        session = self._store.get(session_id)
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
                "message": f"Missing required items: {', '.join(missing_required)}",
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

                self.equipment_repo.update(
                    session.equipment_code,
                    {"health_score": new_health, "status": new_status, "last_service_date": datetime.now().isoformat()},
                )

                logger.info(
                    f"Updated {session.equipment_code} health: {current_health} -> {new_health} "
                    f"(change: {health_change:+d})"
                )

                # Emit real-time SSE event for dashboard update
                try:
                    import asyncio

                    from app.services.event_emitter import get_event_emitter

                    emitter = get_event_emitter()
                    asyncio.create_task(
                        emitter.emit_health_changed(
                            equipment_id=equipment.get("id", session.equipment_code),
                            equipment_code=session.equipment_code,
                            equipment_name=equipment.get("name", session.equipment_code),
                            old_health_score=current_health,
                            new_health_score=new_health,
                            reason="service_feedback",
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to emit health_changed event: {e}")
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
            "completed_at": session.completed_at.isoformat(),
        }

        return summary

    def _build_feedback_summary(self, session: FeedbackSession) -> dict[str, Any]:
        """Build a summary of collected feedback."""
        readings = []
        attachments = []
        observations = []

        for item in session.feedback_items:
            if item.item_type == FeedbackItemType.READING:
                readings.append(
                    {
                        "key": item.item_key,
                        "value": item.value,
                        "unit": item.unit,
                        "baseline": item.baseline_value,
                        "deviation_percent": item.deviation_percent,
                        "health_impact": item.health_impact.value,
                    }
                )
            elif item.item_type in (FeedbackItemType.PHOTO, FeedbackItemType.AUDIO):
                attachments.append({"key": item.item_key, "file_path": item.file_path, "type": item.item_type.value})
            elif item.item_type == FeedbackItemType.OBSERVATION:
                observations.append({"key": item.item_key, "content": item.value, "notes": item.notes})

        return {
            "readings": readings,
            "attachments": attachments,
            "observations": observations,
            "impact_counts": {
                "positive": sum(1 for i in session.feedback_items if i.health_impact == HealthImpact.POSITIVE),
                "neutral": sum(1 for i in session.feedback_items if i.health_impact == HealthImpact.NEUTRAL),
                "negative": sum(1 for i in session.feedback_items if i.health_impact == HealthImpact.NEGATIVE),
                "critical": sum(1 for i in session.feedback_items if i.health_impact == HealthImpact.CRITICAL),
            },
        }

    def get_session_status(self, session_id: str) -> dict[str, Any] | None:
        """Get current status of a feedback session."""
        session = self._store.get(session_id)
        if not session:
            return None

        # Calculate progress
        total_required = len(session.template.required_items)
        collected_required = sum(1 for item in session.template.required_items if item in session.items_collected)

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
                "percent_complete": round((collected_required / total_required * 100) if total_required > 0 else 100),
            },
            "items_collected": session.items_collected,
            "next_item": {
                "key": next_prompt[0] if next_prompt else None,
                "prompt": next_prompt[1] if next_prompt else None,
                "required": next_prompt[2] if next_prompt else None,
            }
            if next_prompt
            else None,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        }

    def get_water_repair_template(self) -> dict[str, Any] | None:
        """Get water repair feedback template.

        Returns:
            Dictionary with water repair template data or None if not found
        """
        templates = self._templates.get("water_repair", {})
        if not templates:
            logger.warning("No water_repair templates found")
            return None

        # Return all water repair service types as a single template
        return {
            "equipment_type": "water_repair",
            "service_types": list(templates.keys()),
            "templates": templates,
        }

    async def process_water_repair_feedback(
        self,
        work_order_id: str,
        feedback: dict[str, Any],
        technician_id: str,
    ) -> dict[str, Any]:
        """Process water repair feedback and calculate health impact.

        Args:
            work_order_id: Work order ID for the repair
            feedback: Feedback dictionary with repair details
            technician_id: Technician who performed the repair

        Returns:
            Dictionary with work_order_id, health_impact, recorded_at, summary
        """
        try:
            recorded_at = datetime.now().isoformat()

            # Extract and validate feedback fields
            repair_method = feedback.get("repair_method", "unknown")
            service_quality = feedback.get("service_quality", "acceptable")
            customer_satisfaction = feedback.get("customer_satisfaction", 3)
            water_loss = feedback.get("water_loss_liters", 0)

            # Calculate health impact based on repair quality and outcomes
            health_impact = 0

            # Repair method impact: +2 for permanent fixes, 0 for temporary, -1 for partial
            if repair_method == "pipe_replacement":
                health_impact += 2  # Excellent permanent fix
            elif repair_method == "joint_resealing" or repair_method == "valve_replacement":
                health_impact += 2
            elif repair_method == "patching":
                health_impact += 0  # Neutral - acceptable fix
            elif repair_method == "temporary_fix":
                health_impact -= 1  # Needs follow-up

            # Service quality impact
            if service_quality == "excellent":
                health_impact += 1
            elif service_quality == "good" or service_quality == "acceptable":
                health_impact += 0
            elif service_quality == "poor":
                health_impact -= 3  # Reflects poorly on technician

            # Customer satisfaction impact
            if customer_satisfaction and customer_satisfaction < 3:
                health_impact -= 2  # Escalate low satisfaction
            elif customer_satisfaction >= 4:
                health_impact += 1  # Bonus for high satisfaction

            # Water loss severity - estimate equipment wear
            if water_loss > 10000:  # >10,000 liters lost
                health_impact -= 2  # Indicates serious leak, equipment damage
            elif water_loss > 1000:
                health_impact -= 1

            # Clamp health impact to range
            health_impact = max(-5, min(2, health_impact))

            result = {
                "work_order_id": work_order_id,
                "health_impact": health_impact,
                "recorded_at": recorded_at,
                "technician_id": technician_id,
                "repair_method": repair_method,
                "service_quality": service_quality,
                "water_loss_liters": water_loss,
                "customer_satisfaction": customer_satisfaction,
                "summary": self._build_water_feedback_summary(feedback, health_impact),
            }

            logger.info(
                f"Water repair feedback processed: WO {work_order_id}, "
                f"health_impact={health_impact:+d}, quality={service_quality}"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to process water repair feedback: {e}")
            return {
                "work_order_id": work_order_id,
                "status": "error",
                "message": str(e),
            }

    def _build_water_feedback_summary(self, feedback: dict[str, Any], health_impact: int) -> dict[str, Any]:
        """Build summary of water repair feedback."""
        return {
            "leak_type": feedback.get("leak_type", "unknown"),
            "repair_method": feedback.get("repair_method", "unknown"),
            "water_loss_liters": feedback.get("water_loss_liters", 0),
            "parts_replaced": feedback.get("parts_replaced", "none"),
            "service_quality": feedback.get("service_quality", "unknown"),
            "repair_time_hours": feedback.get("repair_time_hours", 0),
            "customer_satisfaction": feedback.get("customer_satisfaction", 0),
            "health_impact_rating": "positive"
            if health_impact > 0
            else ("neutral" if health_impact == 0 else "negative"),
            "follow_up_needed": "temporary_fix" in str(feedback.get("repair_method", "")).lower()
            or (feedback.get("customer_satisfaction", 5) < 3),
        }


# Singleton instance
_feedback_service: FeedbackCollectionService | None = None


def get_feedback_collection_service() -> FeedbackCollectionService:
    """Get singleton feedback collection service."""
    global _feedback_service
    if _feedback_service is None:
        _feedback_service = FeedbackCollectionService()
    return _feedback_service
