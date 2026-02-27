"""Repository layer for database operations."""

from app.database.repositories.building_repository import BuildingRepository
from app.database.repositories.equipment_repository import EquipmentRepository
from app.database.repositories.sensor_repository import SensorRepository
from app.database.repositories.alert_repository import AlertRepository
from app.database.repositories.audit_repository import AuditRepository
from app.database.repositories.prediction_repository import PredictionRepository
from app.database.repositories.safety_rules_repository import SafetyRulesRepository
from app.database.repositories.integration_repository import IntegrationRepository
from app.database.repositories.hvac_zone_repository import HVACZoneRepository
from app.database.repositories.desk_repository import DeskRepository
from app.database.repositories.generator_repository import GeneratorRepository
from app.database.repositories.energy_centre_repository import EnergyCentreRepository
from app.database.repositories.service_record_repository import ServiceRecordRepository
from app.database.repositories.device_repository import DeviceRepository
from app.database.repositories.lighting_repository import (
    LightingControllerRepository,
    LightingLuminaireRepository,
    LightingSensorRepository,
    LightingGroupRepository,
)
from app.database.repositories.sla_repository import SLARepository, get_sla_repository
from app.database.repositories.recommendation_repository import (
    RecommendationRepository,
    get_recommendation_repository,
)
from app.database.repositories.agent_memory_repository import (
    AgentMemoryRepository,
    get_agent_memory_repository,
)
from app.database.repositories.email_intake_repository import (
    EmailIntakeRepository,
    get_email_intake_repository,
)

__all__ = [
    "BuildingRepository",
    "EquipmentRepository",
    "SensorRepository",
    "AlertRepository",
    "AuditRepository",
    "PredictionRepository",
    "SafetyRulesRepository",
    "IntegrationRepository",
    "HVACZoneRepository",
    "DeskRepository",
    "GeneratorRepository",
    "EnergyCentreRepository",
    "ServiceRecordRepository",
    "DeviceRepository",
    "LightingControllerRepository",
    "LightingLuminaireRepository",
    "LightingSensorRepository",
    "LightingGroupRepository",
    "SLARepository",
    "get_sla_repository",
    "RecommendationRepository",
    "get_recommendation_repository",
    "AgentMemoryRepository",
    "get_agent_memory_repository",
    "EmailIntakeRepository",
    "get_email_intake_repository",
]
