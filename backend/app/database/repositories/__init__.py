"""Repository layer for database operations."""

from app.database.repositories.agent_memory_repository import (
    AgentMemoryRepository,
    get_agent_memory_repository,
)
from app.database.repositories.alert_repository import AlertRepository
from app.database.repositories.audit_repository import AuditRepository
from app.database.repositories.desk_repository import DeskRepository
from app.database.repositories.device_repository import DeviceRepository
from app.database.repositories.email_intake_repository import (
    EmailIntakeRepository,
    get_email_intake_repository,
)
from app.database.repositories.energy_centre_repository import EnergyCentreRepository
from app.database.repositories.equipment_repository import EquipmentRepository
from app.database.repositories.generator_repository import GeneratorRepository
from app.database.repositories.hvac_zone_repository import HVACZoneRepository
from app.database.repositories.integration_repository import IntegrationRepository
from app.database.repositories.lighting_repository import (
    LightingControllerRepository,
    LightingGroupRepository,
    LightingLuminaireRepository,
    LightingSensorRepository,
)
from app.database.repositories.prediction_repository import PredictionRepository
from app.database.repositories.recommendation_repository import (
    RecommendationRepository,
    get_recommendation_repository,
)
from app.database.repositories.reporter_location_repository import (
    ReporterLocationRepository,
    get_reporter_location_repository,
)
from app.database.repositories.safety_rules_repository import SafetyRulesRepository
from app.database.repositories.sensor_repository import SensorRepository
from app.database.repositories.service_record_repository import ServiceRecordRepository
from app.database.repositories.site_repository import SiteRepository
from app.database.repositories.sla_repository import SLARepository, get_sla_repository

__all__ = [
    "AgentMemoryRepository",
    "AlertRepository",
    "AuditRepository",
    "DeskRepository",
    "DeviceRepository",
    "EmailIntakeRepository",
    "EnergyCentreRepository",
    "EquipmentRepository",
    "GeneratorRepository",
    "HVACZoneRepository",
    "IntegrationRepository",
    "LightingControllerRepository",
    "LightingGroupRepository",
    "LightingLuminaireRepository",
    "LightingSensorRepository",
    "PredictionRepository",
    "RecommendationRepository",
    "ReporterLocationRepository",
    "SLARepository",
    "SafetyRulesRepository",
    "SensorRepository",
    "ServiceRecordRepository",
    "SiteRepository",
    "get_agent_memory_repository",
    "get_email_intake_repository",
    "get_recommendation_repository",
    "get_reporter_location_repository",
    "get_sla_repository",
]
