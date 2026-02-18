"""
Module Registry Models - Bolt-on Module System

Defines the structure for modular building subsystems:
- HVAC module
- Energy module
- Security module

Each module operates standalone but integrates when multiple are activated.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class ModuleType(str, Enum):
    """Available module types."""
    # Core infrastructure (non-deactivatable)
    KPI = "kpi"
    ML = "ml"
    HVAC = "hvac"
    ENERGY = "energy"
    ASSETS = "assets"
    SIMBIOT = "simbiot"
    INTEGRATIONS = "integrations"
    NOTIFICATIONS = "notifications"

    # Paid add-ons
    CONTROL = "control"  # Gateway add-on — unlocks all automation
    MAINTENANCE = "maintenance"  # Work order and asset lifecycle management
    DIGITAL_TWIN = "digital_twin"  # 3D/2D building visualization

    # Building system add-ons (require CONTROL for automation)
    LIGHTING = "lighting"  # DALI lighting + occupancy-driven automation
    FIRE = "fire"
    ACCESS = "access"  # Access control integration
    SECURITY = "security"  # Includes access control data
    SOLAR = "solar"
    SUSTAINABILITY = "sustainability"
    WATER = "water"
    CONTRACTS = "contracts"


class ModuleStatus(str, Enum):
    """Module operational status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class RecommendationType(str, Enum):
    """AI recommendation types."""
    OPTIMIZATION = "optimization"
    MAINTENANCE = "maintenance"
    ALERT = "alert"
    CROSS_SYSTEM = "cross_system"
    PREDICTIVE = "predictive"


class RecommendationPriority(str, Enum):
    """Recommendation priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ModuleCapability:
    """Defines what a module can do."""
    capability_id: str
    name: str
    description: str
    requires_integration: List[str] = field(default_factory=list)  # Other modules needed


@dataclass
class ModuleDefinition:
    """Static definition of a module type."""
    module_type: ModuleType
    name: str
    version: str
    description: str
    capabilities: List[ModuleCapability] = field(default_factory=list)
    integrates_with: List[ModuleType] = field(default_factory=list)
    telemetry_points: List[str] = field(default_factory=list)
    ai_features: List[str] = field(default_factory=list)


@dataclass
class ModuleInstance:
    """Instance of a module activated for a specific site."""
    instance_id: str
    site_id: str
    module_type: ModuleType
    status: ModuleStatus
    activated_at: str
    config: Dict[str, Any] = field(default_factory=dict)
    health_score: float = 100.0
    last_telemetry: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class CrossModuleLink:
    """Defines integration between two modules."""
    link_id: str
    source_module: ModuleType
    target_module: ModuleType
    integration_type: str  # e.g., "load_shedding", "occupancy_sync", "alert_correlation"
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AIRecommendation:
    """AI-generated recommendation from telemetry analysis."""
    recommendation_id: str
    timestamp: str
    source_module: ModuleType
    recommendation_type: RecommendationType
    priority: RecommendationPriority
    title: str
    description: str
    confidence: float  # 0-1
    related_modules: List[ModuleType] = field(default_factory=list)
    telemetry_context: Dict[str, Any] = field(default_factory=dict)
    suggested_action: Optional[Dict[str, Any]] = None
    auto_actionable: bool = False
    acknowledged: bool = False
    resolved: bool = False


@dataclass
class ModuleIntegrationEvent:
    """Event when modules interact."""
    event_id: str
    timestamp: str
    source_module: ModuleType
    target_modules: List[ModuleType]
    event_type: str  # e.g., "data_share", "action_request", "alert_propagation"
    payload: Dict[str, Any] = field(default_factory=dict)
    result: Optional[str] = None


@dataclass
class SiteModuleConfig:
    """Complete module configuration for a site."""
    site_id: str
    site_name: str
    active_modules: List[ModuleInstance] = field(default_factory=list)
    cross_module_links: List[CrossModuleLink] = field(default_factory=list)
    ai_enabled: bool = True
    auto_integration: bool = True  # Auto-create links when modules added


# Pre-defined module definitions
MODULE_DEFINITIONS: Dict[ModuleType, ModuleDefinition] = {
    ModuleType.CONTROL: ModuleDefinition(
        module_type=ModuleType.CONTROL,
        name="Control & Automation",
        version="1.0.0",
        description="Core control system orchestration and automation rules",
        capabilities=[
            ModuleCapability("control_rules", "Control Rules", "Rule-based control logic for systems"),
            ModuleCapability("control_audit", "Control Audit Trail", "Audit log for control actions"),
        ],
        integrates_with=[ModuleType.HVAC, ModuleType.ENERGY, ModuleType.LIGHTING, ModuleType.SECURITY],
        telemetry_points=["control_events", "rules_active"],
        ai_features=["control_optimization"]
    ),
    ModuleType.ASSETS: ModuleDefinition(
        module_type=ModuleType.ASSETS,
        name="Asset Workflow",
        version="1.0.0",
        description="Lifecycle, maintenance workflows, and asset tracking",
        capabilities=[
            ModuleCapability("asset_registry", "Asset Registry", "Track assets and lifecycle state"),
            ModuleCapability("workflow", "Workflow Automation", "Automate maintenance workflows"),
        ],
        integrates_with=[ModuleType.HVAC, ModuleType.ENERGY, ModuleType.SOLAR],
        telemetry_points=["asset_status", "work_orders"],
        ai_features=["maintenance_planning"]
    ),
    ModuleType.SIMBIOT: ModuleDefinition(
        module_type=ModuleType.SIMBIOT,
        name="SIMBIOT",
        version="1.0.0",
        description="BMS connection wizard and integration bootstrap",
        capabilities=[
            ModuleCapability("connection_wizard", "Connection Wizard", "Guide BMS integration setup"),
            ModuleCapability("data_discovery", "Data Discovery", "Discover devices and points"),
        ],
        integrates_with=[ModuleType.INTEGRATIONS],
        telemetry_points=["connection_status"],
        ai_features=["integration_guidance"]
    ),
    ModuleType.INTEGRATIONS: ModuleDefinition(
        module_type=ModuleType.INTEGRATIONS,
        name="Integrations",
        version="1.0.0",
        description="Integration health and data quality monitoring",
        capabilities=[
            ModuleCapability("health_monitoring", "Integration Health", "Monitor integration uptime and latency"),
            ModuleCapability("data_quality", "Data Quality", "Detect data gaps and anomalies"),
        ],
        integrates_with=[ModuleType.CONTROL, ModuleType.ASSETS, ModuleType.HVAC, ModuleType.ENERGY],
        telemetry_points=["integration_health", "data_quality_score"],
        ai_features=["anomaly_detection"]
    ),
    ModuleType.NOTIFICATIONS: ModuleDefinition(
        module_type=ModuleType.NOTIFICATIONS,
        name="Notifications",
        version="1.0.0",
        description="Alerting and notification routing",
        capabilities=[
            ModuleCapability("alert_routing", "Alert Routing", "Route alerts to channels"),
            ModuleCapability("acknowledgement", "Acknowledgement", "Track alert acknowledgement"),
        ],
        integrates_with=[ModuleType.SECURITY, ModuleType.ENERGY, ModuleType.HVAC],
        telemetry_points=["alerts_sent", "alerts_acknowledged"],
        ai_features=["alert_prioritization"]
    ),
    ModuleType.HVAC: ModuleDefinition(
        module_type=ModuleType.HVAC,
        name="HVAC Control",
        version="1.0.0",
        description="Heating, ventilation, and air conditioning monitoring and control",
        capabilities=[
            ModuleCapability("zone_control", "Zone Temperature Control", "Control zone setpoints and modes"),
            ModuleCapability("ahu_monitoring", "AHU Monitoring", "Monitor air handling units"),
            ModuleCapability("chiller_control", "Chiller Control", "Monitor and control chillers"),
            ModuleCapability("comfort_analysis", "Comfort Analysis", "AI-based comfort optimization"),
        ],
        integrates_with=[ModuleType.ENERGY, ModuleType.SECURITY, ModuleType.LIGHTING],
        telemetry_points=["zone_temp", "zone_setpoint", "ahu_supply_temp", "chiller_kw", "occupancy"],
        ai_features=["predictive_comfort", "load_optimization", "fault_detection", "setpoint_tuning"]
    ),
    ModuleType.ENERGY: ModuleDefinition(
        module_type=ModuleType.ENERGY,
        name="Energy Centre",
        version="1.0.0",
        description="Generator, power metering, UPS, and electrical distribution monitoring",
        capabilities=[
            ModuleCapability("generator_scada", "Generator SCADA", "Monitor generator fleet with predictive maintenance"),
            ModuleCapability("ats_monitoring", "ATS Monitoring", "Transfer switch position and history"),
            ModuleCapability("power_metering", "Power Metering", "Real-time power consumption and quality"),
            ModuleCapability("ups_monitoring", "UPS Monitoring", "UPS status and battery health"),
            ModuleCapability("sld_visualization", "Single-Line Diagram", "Visual electrical distribution"),
        ],
        integrates_with=[ModuleType.HVAC, ModuleType.SECURITY, ModuleType.LIGHTING],
        telemetry_points=["gen_kw", "gen_fuel", "ats_position", "main_power_kw", "pf", "ups_battery", "tx_load"],
        ai_features=["generator_predictive", "load_shedding_optimization", "power_quality_analysis", "fuel_forecasting"]
    ),
    ModuleType.SECURITY: ModuleDefinition(
        module_type=ModuleType.SECURITY,
        name="Security & Access",
        version="1.0.0",
        description="Access control, CCTV, and intrusion detection integration",
        capabilities=[
            ModuleCapability("access_control", "Access Control", "Door access and badge management"),
            ModuleCapability("cctv_integration", "CCTV Integration", "Camera feeds and analytics"),
            ModuleCapability("intrusion_detection", "Intrusion Detection", "Alarm zone monitoring"),
            ModuleCapability("occupancy_tracking", "Occupancy Tracking", "Real-time building occupancy"),
        ],
        integrates_with=[ModuleType.HVAC, ModuleType.ENERGY, ModuleType.LIGHTING],
        telemetry_points=["door_status", "badge_events", "occupancy_count", "alarm_zones", "camera_status"],
        ai_features=["occupancy_prediction", "anomaly_detection", "access_pattern_analysis", "emergency_response"]
    ),
    ModuleType.LIGHTING: ModuleDefinition(
        module_type=ModuleType.LIGHTING,
        name="Lighting Control",
        version="1.0.0",
        description="DALI lighting control and daylight harvesting",
        capabilities=[
            ModuleCapability("dali_control", "DALI Control", "Individual luminaire control"),
            ModuleCapability("scene_management", "Scene Management", "Lighting scenes and schedules"),
            ModuleCapability("daylight_harvesting", "Daylight Harvesting", "Automatic dimming based on daylight"),
            ModuleCapability("emergency_lighting", "Emergency Lighting", "Emergency lighting status"),
        ],
        integrates_with=[ModuleType.HVAC, ModuleType.ENERGY, ModuleType.SECURITY],
        telemetry_points=["luminaire_level", "scene_active", "lux_level", "emergency_status", "power_consumption"],
        ai_features=["occupancy_based_control", "energy_optimization", "circadian_lighting", "fault_detection"]
    ),
    ModuleType.SOLAR: ModuleDefinition(
        module_type=ModuleType.SOLAR,
        name="Solar & BESS",
        version="1.0.0",
        description="Solar PV generation, battery storage, and grid-tied optimisation",
        capabilities=[
            ModuleCapability("pv_monitoring", "PV Monitoring", "Inverter fleet and string-level monitoring"),
            ModuleCapability("bess_management", "BESS Management", "Battery SOC, dispatch, and health tracking"),
            ModuleCapability("energy_arbitrage", "Energy Arbitrage", "TOU tariff-based charge/discharge optimisation"),
            ModuleCapability("grid_compliance", "Grid Compliance", "NRS 097-2-1 compliance monitoring"),
            ModuleCapability("performance_analytics", "Performance Analytics", "PR calculation and inverter peer comparison"),
        ],
        integrates_with=[ModuleType.ENERGY, ModuleType.HVAC],
        telemetry_points=["pv_power_kw", "bess_soc", "bess_mode", "grid_import_kw", "grid_export_kw", "inverter_status", "pr_ratio"],
        ai_features=["generation_forecast", "arbitrage_optimisation", "fault_detection", "self_consumption_maximisation"]
    ),
    ModuleType.WATER: ModuleDefinition(
        module_type=ModuleType.WATER,
        name="Water Meter",
        version="1.0.0",
        description="Water consumption monitoring, leak detection, and trending analysis",
        capabilities=[
            ModuleCapability("consumption_monitoring", "Consumption Monitoring", "Track water consumption and flow rates"),
            ModuleCapability("leak_detection", "Leak Detection", "Three-algorithm leak detection (continuous flow, Z-score, spike)"),
            ModuleCapability("trending_analysis", "Trending Analysis", "Period-over-period consumption comparison"),
            ModuleCapability("alert_management", "Alert Management", "Leak alert creation, resolution, and tracking"),
        ],
        integrates_with=[ModuleType.SUSTAINABILITY, ModuleType.ENERGY],
        telemetry_points=["flow_rate_lpm", "volume_liters", "pulse_count", "leak_alerts"],
        ai_features=["leak_detection", "consumption_forecasting", "pattern_anomaly_detection"]
    ),
    ModuleType.ML: ModuleDefinition(
        module_type=ModuleType.ML,
        name="Fleet ML",
        version="1.0.0",
        description="Cross-site machine learning insights, anomaly detection, and predictive maintenance",
        capabilities=[
            ModuleCapability("fleet_insights", "Fleet Insights", "Cross-site pattern recognition and benchmarking"),
            ModuleCapability("anomaly_detection", "Anomaly Detection", "LSTM/Autoencoder-based anomaly detection"),
            ModuleCapability("predictive_maintenance", "Predictive Maintenance", "Failure probability forecasting"),
            ModuleCapability("mlops_monitoring", "MLOps Monitoring", "Model performance tracking and drift detection"),
        ],
        integrates_with=[ModuleType.HVAC, ModuleType.ENERGY, ModuleType.SOLAR],
        telemetry_points=["model_accuracy", "inference_latency", "anomaly_score", "drift_metric"],
        ai_features=["cross_site_benchmarking", "model_retraining", "explainable_predictions", "fleet_health_scoring"]
    ),
    ModuleType.SUSTAINABILITY: ModuleDefinition(
        module_type=ModuleType.SUSTAINABILITY,
        name="Sustainability & ESG",
        version="1.0.0",
        description="Carbon tracking, ESG reporting, and sustainability compliance",
        capabilities=[
            ModuleCapability("carbon_tracking", "Carbon Tracking", "Scope 1/2/3 emissions monitoring"),
            ModuleCapability("esg_reporting", "ESG Reporting", "Automated sustainability report generation"),
            ModuleCapability("compliance_monitoring", "Compliance Monitoring", "Regulatory compliance tracking"),
            ModuleCapability("green_certification", "Green Certification", "GBCSA/LEED/WELL certification support"),
        ],
        integrates_with=[ModuleType.ENERGY, ModuleType.SOLAR, ModuleType.HVAC],
        telemetry_points=["carbon_emissions_kg", "energy_intensity", "water_usage", "waste_diversion_rate"],
        ai_features=["emissions_forecasting", "reduction_recommendations", "benchmark_comparison", "report_generation"]
    ),
    ModuleType.FIRE: ModuleDefinition(
        module_type=ModuleType.FIRE,
        name="Fire Safety",
        version="1.0.0",
        description="Fire detection and alarm system monitoring",
        capabilities=[
            ModuleCapability("alarm_monitoring", "Alarm Monitoring", "Monitor fire alarm status"),
            ModuleCapability("panel_integration", "Panel Integration", "Integrate fire panel signals"),
        ],
        integrates_with=[ModuleType.SECURITY],
        telemetry_points=["fire_alarm_status"],
        ai_features=["alarm_correlation"]
    ),
    ModuleType.ACCESS: ModuleDefinition(
        module_type=ModuleType.ACCESS,
        name="Access Control",
        version="1.0.0",
        description="Access control integration and badge management",
        capabilities=[
            ModuleCapability("door_access", "Door Access", "Monitor and control door access"),
            ModuleCapability("badge_events", "Badge Events", "Track badge use and anomalies"),
        ],
        integrates_with=[ModuleType.SECURITY],
        telemetry_points=["badge_events", "door_status"],
        ai_features=["access_anomaly_detection"]
    ),
    ModuleType.CONTRACTS: ModuleDefinition(
        module_type=ModuleType.CONTRACTS,
        name="Contracts",
        version="1.0.0",
        description="Contract and SLA management",
        capabilities=[
            ModuleCapability("sla_tracking", "SLA Tracking", "Track SLA compliance"),
            ModuleCapability("contract_reporting", "Contract Reporting", "Summarize contract performance"),
        ],
        integrates_with=[ModuleType.ASSETS, ModuleType.ENERGY],
        telemetry_points=["sla_status", "contract_margin"],
        ai_features=["risk_scoring"]
    ),
}


# Cross-module integration definitions
INTEGRATION_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "hvac_energy_loadshed": {
        "name": "HVAC Load Shedding",
        "description": "Reduce HVAC load when on generator power",
        "source": ModuleType.ENERGY,
        "target": ModuleType.HVAC,
        "trigger": "ats_position == 'generator'",
        "action": "increase_setpoints_by_2C",
    },
    "security_hvac_occupancy": {
        "name": "Occupancy-Based HVAC",
        "description": "Adjust HVAC based on access control occupancy",
        "source": ModuleType.SECURITY,
        "target": ModuleType.HVAC,
        "trigger": "zone_occupancy_change",
        "action": "adjust_zone_setpoint",
    },
    "security_lighting_occupancy": {
        "name": "Occupancy-Based Lighting",
        "description": "Control lighting based on occupancy",
        "source": ModuleType.SECURITY,
        "target": ModuleType.LIGHTING,
        "trigger": "zone_occupancy_change",
        "action": "adjust_lighting_level",
    },
    "energy_lighting_loadshed": {
        "name": "Lighting Load Shedding",
        "description": "Reduce lighting when on generator",
        "source": ModuleType.ENERGY,
        "target": ModuleType.LIGHTING,
        "trigger": "ats_position == 'generator'",
        "action": "reduce_lighting_50_percent",
    },
    "hvac_energy_demand": {
        "name": "Demand Response",
        "description": "Coordinate HVAC with demand management",
        "source": ModuleType.ENERGY,
        "target": ModuleType.HVAC,
        "trigger": "peak_demand_warning",
        "action": "pre_cool_then_reduce",
    },
    "energy_solar_generation": {
        "name": "Solar Generation Contribution",
        "description": "Include solar generation in total energy accounting",
        "source": ModuleType.SOLAR,
        "target": ModuleType.ENERGY,
        "trigger": "solar_generation_update",
        "action": "update_generation_contribution",
    },
    "solar_generator_coordination": {
        "name": "Solar-Generator Coordination",
        "description": "Avoid generator start when solar + BESS can serve load",
        "source": ModuleType.SOLAR,
        "target": ModuleType.ENERGY,
        "trigger": "generator_start_request",
        "action": "check_solar_bess_capacity",
    },
    "sustainability_water_monitoring": {
        "name": "Water Consumption for Sustainability",
        "description": "Track water consumption for sustainability reporting",
        "source": ModuleType.WATER,
        "target": ModuleType.SUSTAINABILITY,
        "trigger": "water_consumption_update",
        "action": "update_water_metrics",
    },
}
