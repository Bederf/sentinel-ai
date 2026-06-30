"""Application settings and configuration."""

import base64
import hashlib
import json
import os
import re
from enum import StrEnum
from typing import Any

from pydantic import AliasChoices, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings

# 3-layer model routing (Phase 163)
# Layer 2 — Execution mode: api | cloud | local
# Layer 3 — Active routing profile name
SENTINEL_EXECUTION_MODE: str = os.getenv("SENTINEL_EXECUTION_MODE", "api")
SENTINEL_ROUTING_PROFILE: str = os.getenv("SENTINEL_ROUTING_PROFILE", "api_prod")

# Bot entry classes and escalation target
SENTINEL_BOT_DEFAULT_CLASS: str = "chat_ai"  # General occupant/facilities bot
SENTINEL_BOT_TECH_DEFAULT_CLASS: str = "chat_tech"  # Engineer/diagnostic bot
SENTINEL_BOT_ESCALATION_CLASS: str = "heavy"  # Escalation target for both bots


def apply_edge_mode_overrides() -> None:
    """Override routing profile for edge deployment.

    SENTINEL_ROUTING_PROFILE is read at import time and cannot be changed via
    environment variable after module load. This function must be called once at
    startup (before any model_gateway.call() invocations) to apply edge overrides.
    """
    import app.config.settings as _self

    if _self.settings.edge_mode and _self.SENTINEL_ROUTING_PROFILE != "local_full":
        _self.SENTINEL_ROUTING_PROFILE = "local_full"
        import logging

        logging.getLogger(__name__).info(
            "EDGE_MODE=true: SENTINEL_ROUTING_PROFILE overridden to 'local_full' "
            "(all LLM calls route through local Ollama; no cloud fallback)"
        )


def _parse_csv_list(value):
    if isinstance(value, list):
        return value
    if not value:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class IngestionMode(StrEnum):
    """Authoritative ingestion data provenance mode."""

    SIMULATION = "simulation"
    SHADOW_LIVE = "shadow_live"
    LIVE_CONTROL = "live_control"


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    app_name: str = "BMS Intelligence"
    app_version: str = "13.2"
    debug: bool = False

    # CORS settings (restrict to known frontend origins)
    # Development: localhost on ports 9096, 3000, 5173, 8080
    # Production: bms.aimthelaw.co.za via HTTPS
    cors_origins: list[str] = [
        "http://localhost:9096",
        "https://localhost:9096",
        "http://127.0.0.1:9096",
        "https://127.0.0.1:9096",
        "http://localhost:9097",
        "http://localhost:9098",
        "http://localhost:9099",
        "http://localhost:9100",
        "http://localhost:9101",
        "http://localhost:3000",
        "https://localhost:3000",
        "http://localhost:5173",
        "https://localhost:5173",
        "http://localhost:8080",
        "https://localhost:8080",
        "https://bms.aimthelaw.co.za",
        "https://sentinel-ai.co.za",
        "https://bms.sentinel-ai.co.za",
    ]

    # Backend URL (for external service health checks)
    backend_url: str = ""

    # Public URL for MCP/document links (must be externally accessible)
    # Example: https://bms.sentinel-ai.co.za
    sentinel_public_url: str = Field(default="", validation_alias="SENTINEL_PUBLIC_URL")

    # Internal service key for service-to-service API auth (X-Internal-Service header)
    internal_service_key: str = Field(default="sentinel-internal", validation_alias="INTERNAL_SERVICE_KEY")

    # DDMP / Demand Response thresholds (used by curtailable_load MCP tool).
    # ddmp_minimum_kw: Eskom DDMP programme minimum per site (0.2 MW = 200 kW).
    #   See demand_response_service._calculate_ddmp_eligible docstring.
    # ddmp_aggregation_cap_kw: Internal SENTINEL multi-site aggregation cap
    #   used to assess whether the fleet collectively clears the programme bar.
    ddmp_minimum_kw: float = 200.0
    ddmp_aggregation_cap_kw: float = 500.0

    # Claude AI settings
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 1536
    ai_cloud_provider: str = "anthropic"  # anthropic|openai|zai|xiaomi
    zai_api_key: str = ""
    zai_model: str = "glm-4.7-flash"
    zai_base_url: str = "https://api.z.ai/api/paas/v4"
    xiaomi_api_key: str = ""
    xiaomi_model: str = "mimo-v2-flash"
    xiaomi_base_url: str = "https://api.mimo.xiaomi.com/v1"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    minimax_api_key: str = ""
    minimax_model: str = "MiniMax-M2.7"
    minimax_base_url: str = "https://api.minimax.io/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-nano"  # Tier 1: fast/cheap for routine queries
    openai_model_heavy: str = "gpt-4.1-mini"  # Tier 2: complex reasoning & diagnostics
    openai_base_url: str = "https://api.openai.com/v1"
    # OpenAI Realtime-2 voice (Path C surgical — replaces ElevenLabs STT only)
    openai_realtime_api_key: str = ""
    realtime_voice_enabled: bool = False
    local_ai_only: bool = False  # Force local-only AI mode (no Anthropic/Claude calls)
    popia_require_cross_border_consent: bool = True  # Block cloud LLM without explicit cross-border consent
    popia_dsr_sla_days: int = 30  # POPIA response SLA for data subject requests
    popia_retention_enabled: bool = True  # Enable scheduled retention enforcement
    popia_retention_consent_days: int = 1825  # 5 years
    popia_retention_request_days: int = 1825  # 5 years
    popia_retention_audit_days: int = 1825  # 5 years
    popia_retention_job_interval_seconds: int = 86400  # Daily

    # Supabase SQL table retention (POPIA Section 14)
    popia_retention_ml_training_days: int = 7  # ML training data — 7-day window
    popia_retention_snapshot_days: int = 30  # Operational snapshots — 30-day window
    popia_retention_audit_trail_days: int = 1825  # 5 years

    # ElevenLabs TTS (Voice Chat)
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel
    elevenlabs_model_id: str = "eleven_monolingual_v1"
    elevenlabs_tts_enabled: bool = False

    # Environment (development, staging, production)
    environment: str = "development"

    # Demo mode — DEPRECATED: no longer grants auth bypasses.
    # Kept for backward compatibility with .env files.
    demo_mode: bool = False
    demo_allowed_origins: list[str] = []
    ingestion_mode: str = "shadow_live"  # env: INGESTION_MODE

    # Encryption at rest (Phase 1b FSR Compliance - Cryptography)
    encryption_enabled: bool = True
    encryption_key: str = ""  # Base64-encoded Fernet key from cryptography.fernet.Fernet.generate_key()

    # JWT secret key (required when not in DEMO_MODE)
    jwt_secret_key: str = ""

    # JWT token expiration (Phase 58-04 M-3: reduced from 30 days to 8 hours)
    jwt_expiration_hours: int = 8  # DEPRECATED: Use jwt_access_token_ttl_minutes instead
    jwt_expiry_days: int = 30  # DEPRECATED: legacy compatibility only

    # JWT access token TTL (Phase 193: short-lived tokens for XSS risk reduction)
    jwt_access_token_ttl_minutes: int = 480  # 8 hours — long enough for onboarding wizard sessions

    # JWT refresh token TTL (Phase 65-02: long-lived refresh tokens)
    jwt_refresh_token_ttl_days: int = 7  # 7 days for refresh tokens

    # Sentry webhook secret (required for Telegram bot integration)
    sentry_webhook_secret: str = ""

    # Home bot webhook secret (Phase 220 — Telegram sends this in X-Telegram-Bot-Api-Secret-Token)
    home_bot_webhook_secret: str = ""

    # Sentry operator password — required in request body for sensitive operations
    # (equipment resets, work order creation, inspection results, call log escalation)
    sentinel_operator_password: str = Field(default="", validation_alias="SENTINEL_OPERATOR_PASSWORD")

    # Sentry bot API key (for authenticated access to /api/sites/* endpoints)
    sentry_bot_api_key: str = Field(default="", validation_alias="SENTRY_BOT_API_KEY")
    sentry_bot_cli: str = Field(default="sentry", validation_alias="SENTRY_BOT_CLI")

    # Technician Telegram bot token (for direct work order notifications)
    sentry_client_bot_token: str = Field(default="", validation_alias="SENTRY_CLIENT_BOT_TOKEN")
    sentry_tech_bot_token: str = Field(default="", validation_alias="SENTRY_TECH_BOT_TOKEN")
    sentry_manager_bot_token: str = Field(default="", validation_alias="SENTRY_MANAGER_BOT_TOKEN")

    # Prometheus metrics bearer token (required for /metrics endpoint — no auth bypass)
    # Prometheus must send: Authorization: Bearer <token>
    metrics_bearer_token: str = Field(default="", validation_alias="METRICS_BEARER_TOKEN")

    # SIMBIOT Concept Evolution (FSI Public API) credentials
    simbiot_api_key: str = Field(default="", validation_alias=AliasChoices("SIMBIOT_API_KEY", "BRIDGE_API_TOKEN"))

    # OpenAI MCP endpoint API key (protects the read-only BMS intelligence endpoint)
    mcp_api_key: str = Field(default="", validation_alias="MCP_API_KEY")
    # Optional tenant-scoped MCP keys. JSON object keyed by bearer token:
    # {"token": {"tenant_id": "client-005", "allowed_sites": ["site-005"], "tools": ["ping", "get_site_status"]}}
    mcp_tenant_api_keys: str = Field(default="", validation_alias="MCP_TENANT_API_KEYS")
    simbiot_api_url: str = Field(default="", validation_alias=AliasChoices("SIMBIOT_API_URL", "BRIDGE_BASE_URL"))
    simbiot_username: str = ""
    simbiot_password: str = ""
    solarman_app_id: str = Field(default="", validation_alias="SOLARMAN_APP_ID")
    solarman_app_secret: str = Field(default="", validation_alias="SOLARMAN_APP_SECRET")

    # Notification service settings (email, Slack)
    notification_smtp_host: str = Field(
        default="", validation_alias=AliasChoices("NOTIFICATION_SMTP_HOST", "SMTP_HOST")
    )
    notification_smtp_port: int = Field(
        default=587, validation_alias=AliasChoices("NOTIFICATION_SMTP_PORT", "SMTP_PORT")
    )
    notification_smtp_username: str = Field(
        default="", validation_alias=AliasChoices("NOTIFICATION_SMTP_USERNAME", "SMTP_USER")
    )
    notification_smtp_password: str = Field(
        default="", validation_alias=AliasChoices("NOTIFICATION_SMTP_PASSWORD", "SMTP_PASSWORD")
    )
    notification_smtp_use_tls: bool = True

    # Rooms SMTP (ghost booking alerts — separate from work order email)
    rooms_smtp_host: str = ""
    rooms_smtp_port: int = 587
    rooms_smtp_username: str = ""
    rooms_smtp_password: str = ""
    rooms_smtp_from_name: str = "SENTINEL Room Alerts"

    notification_slack_webhook_critical: str = ""
    notification_slack_webhook_emergency: str = ""
    notification_email_recipients: list[str] = []  # Comma-separated email addresses

    # Supabase settings
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_role_key: str = ""
    use_json_storage: bool = False
    energy_allow_mock_fallback: bool = False  # If true, /api/energy may generate synthetic data when Supabase fails

    # Database URL (for direct PostgreSQL access if needed)
    database_url: str = ""

    # Redis cache settings
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True
    redis_default_ttl: int = 300  # 5 minutes default TTL

    # PARASITE Autonomous Control Configuration
    parasite_enabled: bool = False  # Master switch for PARASITE autonomous features
    parasite_tier3_enabled: bool = False  # Enable Tier 3 auto-execute (requires parasite_enabled)
    parasite_confidence_tier2_min: float = 0.70  # Min confidence for Tier 2 (supervised)
    parasite_confidence_tier3_min: float = 0.85  # Min confidence for Tier 3 (autonomous)
    parasite_cov_timeout_seconds: int = 30  # Max time to wait for COV verification
    parasite_outcome_window_minutes: int = 10  # Time to measure outcome after execution
    parasite_auto_rollback_enabled: bool = True  # Auto-rollback on COV failure
    parasite_max_auto_executions_per_hour: int = 10  # Rate limit for Tier 3 actions
    parasite_bacnet_priority: int = 8  # BACnet priority array slot (8 = PARASITE level)

    # AEGIS BESS Writer (Phase 0: disabled; Phase 1: enable after ops CONFIRM)
    aegis_bess_writer_enabled: bool = False

    # Load shedding — manual override takes priority over any API
    # Set to a stage number (1-8) to force load-shedding mode without an API.
    # Set to 0 (default) for no load shedding, or -1 to use EskomSePush API if configured.
    load_shedding_stage_override: int = 0

    # EskomSePush API (optional paid upgrade — not required for Sprint 0)
    # Free tier: 50 req/day. Business tier: R100+/month.
    # System works without it — uses load_shedding_stage_override instead.
    eskomsepush_api_token: str = ""
    eskomsepush_area_id: str = ""  # Area ID from EskomSePush (use /areas_search to find)
    eskomsepush_cache_seconds: int = 300  # Cache API responses for 5 minutes

    # Niagara oBIX connection
    niagara_obix_host: str = ""
    niagara_obix_port: int = 80
    niagara_obix_username: str = ""
    niagara_obix_password: str = ""
    niagara_obix_https: bool = False
    niagara_obix_timeout: int = 30
    niagara_obix_verify_ssl: bool = True

    # Niagara BACnet/IP
    niagara_bacnet_port: int = 47808
    niagara_bacnet_local_ip: str = ""  # blank = auto-detect

    # Document upload configuration (Phase X: Building-scoped RAG)
    max_document_upload_size_mb: int = 10
    allowed_document_types: list[str] = [".pdf", ".docx", ".txt"]
    supabase_storage_bucket: str = "building-documents"

    # Authentication Rate Limiting (Phase 58-04 M-5: FSR Domain 4.6 Brute-Force Protection)
    rate_limit_enabled: bool = True  # Master switch for rate limiting
    rate_limit_max_attempts: int = 5  # Max failed login attempts before lockout
    rate_limit_lockout_minutes: int = 15  # Lockout duration in minutes
    rate_limit_per_ip: bool = False  # If True, limit by IP; if False, limit by email (safer)
    rate_limit_default_rpm: int = 1000  # Default rate limit per minute (global default)
    rate_limit_login_rpm: int = 5  # Login endpoint: 5 per 15 minutes
    rate_limit_login_window_minutes: int = 15  # Login rate limit window

    # Optimization Tier Routing (Phase 82)
    optimization_routing_enforced: bool = False  # Phase A: shadow mode (log only). Phase B: enforce.
    optimization_tier_block_min: float = 0.30  # Below this -> blocked
    optimization_tier2_min: float = 0.60  # Below this -> tier1_advisory, above -> tier2_approval
    optimization_tier3_min: float = 0.85  # Above this -> tier3_auto_execute
    optimization_fcu_confidence_cap: float = 0.45  # FCU actions capped at this confidence
    recommendation_advisory_info_retention_days: int = 7
    after_hours_hvac_load_threshold_pct: float = 0.08
    after_hours_hvac_load_threshold_kw: float = 2.5
    after_hours_hvac_advisory_cooldown_hours: int = 2

    # MCP Authentication (Phase 81 - MCP SSE Security)
    mcp_auth_token: str = ""  # Shared MCP authentication token
    mcp_auth_token_previous: str = ""  # Previous token for rotation grace period
    mcp_auth_token_max_age_hours: int = 0  # 0 = no expiry; >0 = enforce max age

    # MCP Rate Limiting (Phase P4 - Abuse Prevention)
    mcp_read_rate_limit: int = 60  # Read tool calls per minute per identity
    mcp_mutate_rate_limit: int = 10  # Mutate tool calls per minute per identity
    mcp_tool_timeout_seconds: int = 30  # Default tool execution timeout

    # RLM Runner Integration (Phase 113 — see SENTINEL-RLM-ARCHITECTURE-SPEC-v1.0.md)
    rlm_runner_url: str = "http://127.0.0.1:8010"  # Runner binds localhost only
    rlm_runner_enabled: bool = False  # Disabled until runner is deployed
    rlm_timeout_seconds: int = 120  # Max time per HTTP request to runner

    # Solar connector mode (v27.0 — live only by default)
    solar_connector_mode: str = "live"  # live = real Modbus TCP; simulation is explicit only

    # Sprint 0 write test gating — requires BOTH this AND aegis_bess_writer_enabled
    allow_write_tests: bool = False  # Second gate: explicitly allow hardware write tests

    # Sprint 0 hard safety limits (enforced in code, not just config)
    sprint0_max_power_kw: float = 5.0  # Max power per command during Sprint 0
    sprint0_max_duration_min: int = 10  # Max duration per command during Sprint 0

    # Background optimization model (cheaper than interactive chat)
    # Empty = use claude_model; set to e.g. "claude-haiku-4-5-20251001" for cost savings
    optimization_model: str = ""
    optimization_max_tokens: int = 4096

    # Token budget enforcement (Phase 185 Wave 2)
    daily_token_budget_per_site: int = Field(default=200_000, validation_alias="DAILY_TOKEN_BUDGET_PER_SITE")
    token_budget_alert_threshold: float = Field(default=0.85, validation_alias="TOKEN_BUDGET_ALERT_THRESHOLD")
    token_budget_hard_limit: bool = Field(default=True, validation_alias="TOKEN_BUDGET_HARD_LIMIT")
    token_budget_exclude_interactive: bool = Field(default=True, validation_alias="TOKEN_BUDGET_EXCLUDE_INTERACTIVE")
    ai_alert_email: str = Field(default="info@sentinel-ai.co.za", validation_alias="AI_ALERT_EMAIL")
    overnight_advisory_email_recipient: str = Field(default="", validation_alias="OVERNIGHT_ADVISORY_EMAIL_RECIPIENT")
    overnight_advisory_fallback_hours: float = Field(default=2.0, validation_alias="OVERNIGHT_ADVISORY_FALLBACK_HOURS")

    # Lifecycle simulation optimization mode
    # IMPORTANT: Simulation MUST NOT consume LLM tokens. It uses rule-based
    # optimization only. SENTINEL's own background scheduler (every 15 min)
    # is the correct path for LLM-powered analysis — same as production.
    simulation_optimization_mode: str = "hardcoded"  # hardcoded | sentinel | hybrid
    simulation_llm_budget_max_calls: int = 0  # Simulation should not use LLM at all
    simulation_llm_model: str = ""  # Override model (empty = use claude_model)
    simulation_llm_temperature: float = 0.3  # Low temp for deterministic structured output

    # Modbus BESS Writer (v26.0 — Huawei LUNA2000 register writes)
    modbus_bess_ip: str = ""  # LUNA2000 Modbus TCP IP (empty = DEMO_MODE, no TCP)
    modbus_bess_port: int = 502  # Standard Modbus TCP port
    modbus_bess_unit_id: int = 1  # Modbus slave ID
    modbus_bess_timeout_s: int = 5  # TCP connection/response timeout
    modbus_write_verify: bool = True  # Read-back verification after write

    # JWT Token Claims (MCP SSE B1 - Issuer/Audience validation)
    jwt_issuer: str = "sentinel.bms"  # JWT iss claim
    jwt_audience: str = "sentinel.bms"  # JWT aud claim

    # Occupancy-driven control loop (Phase 130)
    occupancy_poll_enabled: bool = False  # Enable occupancy→HVAC/lighting control loop
    occupancy_poll_interval_seconds: int = 60  # Poll cycle interval
    occupancy_hvac_setback_c: float = 2.0  # Setpoint relaxation for empty zones (°C)
    occupancy_hvac_partial_setback_c: float = 1.0  # Setpoint relaxation for low zones (°C)
    occupancy_lighting_empty_pct: int = 20  # Brightness % for empty zones
    occupancy_lighting_low_pct: int = 50  # Brightness % for low-occupancy zones
    occupancy_empty_threshold: int = 0  # Occupancy count below which zone is "empty"
    occupancy_low_threshold: int = 3  # Occupancy count below which zone is "low"
    occupancy_restore_hysteresis_pct: float = 10.0  # % above threshold before restoring (anti-flap)

    # Email intake pipeline (Phase 131)
    email_intake_enabled: bool = False  # Master switch for email intake pipeline
    email_intake_auto_wo_enabled: bool = False  # Auto-create local WO-... work orders for high-confidence intakes
    email_intake_auto_wo_max_priority: int = 2  # Max urgency level for auto-WO (1=low, 4=critical)
    email_intake_duplicate_window_hours: int = 24  # Heuristic dedup window
    email_intake_agent_enabled: bool = True  # Phase 134: Use AI agent for classification + reply
    email_intake_agent_timeout_seconds: int = 30  # LLM call timeout

    # Email reply service (Phase 131.2b — backend SMTP threading)
    email_reply_enabled: bool = False  # Send threaded replies from backend instead of n8n
    email_reply_from_address: str = "workorder@sentinel-ai.co.za"
    email_reply_from_name: str = "SENTINEL Work Orders"

    # Intelligence intake mailbox (Phase 159 — signal emitter bridge source)
    # Separate from workorder@ — receives complaint threads, escalations, operational signals
    intelligence_intake_email: str = "intake@sentinel-ai.co.za"
    intelligence_intake_imap_host: str = ""
    intelligence_intake_imap_port: int = 993
    intelligence_intake_imap_username: str = ""
    intelligence_intake_imap_password: str = ""
    intelligence_intake_imap_folder: str = "INBOX"

    # Rooms mailbox IMAP (replaces n8n block-booking email ingest)
    rooms_imap_host: str = ""
    rooms_imap_port: int = 993
    rooms_imap_username: str = ""
    rooms_imap_password: str = ""
    rooms_imap_folder: str = "INBOX"

    # Edge mode: disables ML training, simulation queue, and AEGIS evidence jobs
    # for resource-constrained deployments (Jetson, lightweight VPS)
    edge_mode: bool = False

    # BMS source gate: enable simulator or live bridge polling for site-002 (ENABLE_SITE002_SOURCE env var)
    # DEPRECATED 2026-06: simulator removed. Always returns False.
    # The env var is still read but ignored — all sites route to live bridge/Supabase.
    @property
    def site002_source_enabled(self) -> bool:  # type: ignore[override]
        """Deprecated — simulator removed 2026-06. Always returns False."""
        return False

    # Advisory kernel routing switch for chat investigation mode
    sentinel_advisory_kernel_enabled: bool = Field(default=False, validation_alias="SENTINEL_ADVISORY_KERNEL_ENABLED")
    sentinel_advisory_model_router: str = Field(
        default="ByConfidenceModelRouter", validation_alias="SENTINEL_ADVISORY_MODEL_ROUTER"
    )

    # ML Background Training (retraining, drift detection, feedback retraining)
    # Disable on resource-constrained VPS — models are pre-trained and stable
    ml_background_training_enabled: bool = True

    # Block Booking Detection
    block_booking_enabled: bool = False  # Master switch
    block_booking_min_rooms: int = 3  # Flag when same person holds N+ rooms
    block_booking_mailbox_email: str = ""  # IMAP mailbox for BCC'd confirmations
    block_booking_mailbox_password: str = ""
    block_booking_mailbox_host: str = ""  # e.g. outlook.office365.com
    block_booking_concierge_email: str = ""  # Notification target
    block_booking_concierge_whatsapp: str = ""  # E.164 format
    block_booking_concierge_telegram_id: str = ""  # Telegram chat ID

    # Ghost Booking & Right-Sizing Detection (Rev 1.2)
    ghost_booking_grace_minutes: int = 5  # Wait N min after booking start before flagging
    right_sizing_grace_minutes: int = 20  # Do not flag until meeting has been running this long
    early_vacate_threshold_minutes: int = 90  # Room empty with >N min of booking remaining
    sporadic_use_threshold_pct: int = 25  # Occupied < N% of total booking duration
    brief_occupation_threshold_min: int = 30  # Occupied < N min total in the whole booking
    concierge_response_window_minutes: int = 15  # How long concierge has to respond before reminder
    sensor_silence_threshold_minutes: int = 30  # Sensor silent > N min = connectivity fault, not ghost
    space_mqtt_enabled: bool = True
    space_mqtt_broker: str = ""
    space_mqtt_port: int = 1883
    space_mqtt_username: str = ""
    space_mqtt_password: str = ""
    space_mqtt_client_id: str = "sentinel-space-backend"
    space_mqtt_topic: str = "sentinel/nodes/+/presence"
    space_mqtt_radar_topic: str = "sentinel/node/+/radar"  # LD2410C extended payload topic
    space_default_site_id: str = Field(default="", validation_alias="SITE_ID")  # Required env var

    # Graph / Azure AD email integration (Phase 184)
    graph_integration_enabled: bool = Field(default=False)  # Kill-switch without redeployment

    # LD2410C Radar Distance Filtering
    # Firmware: v2.44.25070917 | Resolution: 0.75 m | Effective range: 3.0 m
    # Mounting: ceiling, downward | Unmanned duration: 15 s
    # Per-room override: FR-L1 (Fairlands staging, 2m x 2m) -> max 1.0 m
    radar_distance_filter_enabled: bool = True  # Reject readings outside valid range
    radar_distance_min_m: float = 0.2  # Ignore very close readings (noise)
    radar_distance_max_m: float = 3.0  # Max effective range (gate 4 @ 0.75 m resolution)
    # Per-room max distances (room_code → max_m), applied on top of global max
    # Any detection beyond a room's physical dimensions = adjacent-space bleed
    radar_room_max_distance_m: dict[str, float] = {
        # FR-L1 (2m x 2m): 1.3m stationary readings in an "empty" room were confirmed
        # adjacent-room bleed (LD2410C detects through thin walls). Cap at 1.0m
        # so only genuine in-room presence (<1m from ceiling sensor) registers.
        "FR-L1": 1.0,
        "FR-L0": 1.0,
        "FR-L2": 1.0,
    }

    # Focus Room Sessions (Phase 2)
    focus_min_session_seconds: int = 180  # Discard sessions shorter than 3 min (noise)
    focus_extended_use_seconds: int = 7200  # Flag sessions longer than 2 hours
    focus_red_light_cooldown_seconds: int = 300  # Keep red light on for 5 minutes after overstay ends
    focus_relay_enabled: bool = True  # Publish relay/light control for focus room overstay
    focus_relay_topic_template: str = "sentinel/node/{node_id}/relay"
    focus_vacancy_grace_seconds: int = 300  # 5 min gap = same session (coffee / restroom)

    # Cost alert threshold — sends Telegram alert when daily spend exceeds this (ZAR)
    cost_alert_daily_threshold_zar: float = 100.0
    cost_alert_telegram_chat_id: str = ""  # Falls back to telegram_alert_chat_id if empty

    # Telegram alert delivery
    telegram_bot_token: str = Field(default="", validation_alias=AliasChoices("SENTRY_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"))
    telegram_alert_chat_id: str = Field(
        default="", validation_alias=AliasChoices("SENTRY_FM_CHAT_ID", "TELEGRAM_ALERT_CHAT_ID")
    )
    telegram_secret_token: str = Field(default="", validation_alias="TELEGRAM_SECRET_TOKEN")

    # Residential home bot Telegram token (Phase 214 — distinct from SENTRY_BOT_TOKEN)
    sentinel_home_bot_token: str = Field(default="", validation_alias="SENTINEL_HOME_BOT_TOKEN")

    # Residential Cloud-to-MQTT Bridge (Phase 210)
    residential_mqtt_broker: str = Field(default="127.0.0.1", validation_alias="RESIDENTIAL_MQTT_BROKER")
    residential_mqtt_port: int = Field(default=1883, validation_alias="RESIDENTIAL_MQTT_PORT")
    residential_mqtt_username: str = Field(default="", validation_alias="RESIDENTIAL_MQTT_USERNAME")
    residential_mqtt_password: str = Field(default="", validation_alias="RESIDENTIAL_MQTT_PASSWORD")

    # WireGuard VPN — Home Assistant gateway peer lifecycle (Phase 215)
    # VPS-side values: operator populates wg0.conf on the VPS with these
    wireguard_vpn_subnet: str = Field(default="", validation_alias="WIREGUARD_VPN_SUBNET")
    wireguard_vps_public_key: str = Field(default="", validation_alias="WIREGUARD_VPS_PUBLIC_KEY")
    wireguard_vps_endpoint: str = Field(
        default="", validation_alias="WIREGUARD_VPS_ENDPOINT"
    )  # e.g. "144.91.122.235:51820"

    # Fuel Tank MQTT Ingestion (Phase 148)
    fuel_mqtt_enabled: bool = False
    fuel_mqtt_broker: str = ""
    fuel_mqtt_port: int = 1883
    fuel_mqtt_username: str = ""
    fuel_mqtt_password: str = ""
    fuel_mqtt_client_id: str = "sentinel-fuel-backend"
    fuel_mqtt_topic_level: str = "sentinel/fuel/+/level"
    fuel_mqtt_topic_events: str = "sentinel/fuel/+/events"
    fuel_mqtt_topic_status: str = "sentinel/fuel/+/status"

    # Fuel Monitoring Module (Phase 150)
    fuel_monitoring_enabled: bool = True  # Enable fuel API endpoints + module

    # Fuel Event Processor (Phase 149)
    fuel_event_processor_enabled: bool = False
    fuel_low_alert_pct_1: float = 30.0  # Primary low fuel warning
    fuel_low_alert_pct_2: float = 15.0  # Critical low fuel
    fuel_theft_rate_threshold_lpm: float = 2.0  # Litres per minute loss rate
    fuel_consumption_anomaly_pct: float = 20.0  # Deviation from spec %
    fuel_temp_min_c: float = 5.0
    fuel_temp_max_c: float = 40.0
    fuel_refill_jump_pct: float = 10.0  # Minimum level jump to detect refill
    fuel_leak_sustained_minutes: int = 30  # Sustained slow loss duration

    # ODA File Converter path (DWG→DXF conversion, Phase 157)
    oda_converter_path: str = ""  # Path to ODAFileConverter binary (empty = default /usr/local/bin/ODAFileConverter)

    # Plant Room Alerts — Desigo email→WhatsApp pipeline (Phase 146)
    plant_alerts_enabled: bool = False  # Master switch for plant alert ingestion
    desigo_sender_email: str = "noreply@fnb.co.za"  # Authorised Desigo sender address
    plant_site_id: str = Field(default="", validation_alias="PLANT_SITE_ID")  # Required env var
    plant_building_name: str = Field(default="", validation_alias="BUILDING_NAME")  # Required env var

    # Fleet ML cross-portfolio analytics (Phase 45)
    # False by default — synthetic benchmark data must not be shown
    # as real portfolio analysis. Enable when 2+ sites reach advisory.
    fleet_ml_enabled: bool = False

    # MRI Evolution Connector (Phase 178)
    mri_evolution_base_url: str = Field(default="", validation_alias="MRI_EVOLUTION_BASE_URL")
    mri_evolution_api_key: str = Field(default="", validation_alias="MRI_EVOLUTION_API_KEY")
    mri_evolution_username: str = ""
    mri_evolution_password: str = ""
    mri_poll_interval_minutes: int = Field(default=15, validation_alias="MRI_POLL_INTERVAL_MINUTES")

    # Alarm ingestion — recency filter (Phase 187)
    # Alarms older than this are stale and dropped at ingest time.
    # Mirrors operator workflow: 48h-old unacknowledged alarms are operator backlog,
    # not SENTINEL intelligence input.
    alarm_recency_window_minutes: int = Field(default=30, validation_alias="ALARM_RECENCY_WINDOW_MINUTES")

    # MRI Document Client — Concept API for service reports and documents (Phase 179)
    mri_document_base_url: str = Field(default="", validation_alias="MRI_DOCUMENT_BASE_URL")
    mri_document_api_key: str = Field(default="", validation_alias="MRI_DOCUMENT_API_KEY")
    document_sync_interval_hours: int = Field(default=4, validation_alias="DOCUMENT_SYNC_INTERVAL_HOURS")

    # WhatsApp delivery — Twilio (primary) or n8n webhook (fallback)
    twilio_account_sid: str = ""  # Twilio Account SID (ACxxxx)
    twilio_auth_token: str = ""  # Twilio Auth Token
    twilio_whatsapp_from: str = ""  # e.g. whatsapp:+14155238886
    twilio_whatsapp_to: str = ""  # e.g. whatsapp:+27721234567
    whatsapp_webhook_url: str = ""  # n8n webhook fallback (used if Twilio not configured)
    whatsapp_group_id: str = ""  # Target WhatsApp group ID (webhook mode only)
    # Meta Cloud API WhatsApp (Phase 178)
    whatsapp_provider: str = ""  # "meta" or "twilio"
    whatsapp_phone_id: str = ""  # Meta Cloud API phone ID
    whatsapp_api_token: str = ""  # Meta Cloud API access token
    whatsapp_business_id: str = ""  # Meta Business ID
    whatsapp_enabled: bool = False

    # Residential VPS MQTT broker (public)
    mqtt_broker_public_host: str = Field(default="", validation_alias="MQTT_BROKER_PUBLIC_HOST")
    mqtt_broker_port: int = Field(default=1883, validation_alias="MQTT_BROKER_PORT")
    residential_tariff_zar: float = Field(default=3.50, validation_alias="RESIDENTIAL_TARIFF_ZAR")

    @property
    def resolved_ingestion_mode(self) -> IngestionMode:
        """Resolve ingestion mode from configured value with safe fallback."""
        try:
            return IngestionMode(self.ingestion_mode)
        except ValueError:
            return IngestionMode.SHADOW_LIVE

    @property
    def is_live_mode(self) -> bool:
        """True when running in live-read modes."""
        return self.resolved_ingestion_mode in (IngestionMode.SHADOW_LIVE, IngestionMode.LIVE_CONTROL)

    @property
    def recommendation_interval(self) -> int:
        """Recommendation generation interval in seconds (600s = 10 minutes)."""
        return 600

    @property
    def config_checksum_payload(self) -> dict[str, Any]:
        """Return a stable, non-secret payload representing runtime config."""
        payload = self.model_dump(mode="json")
        payload["resolved_ingestion_mode"] = self.resolved_ingestion_mode.value
        payload["is_live_mode"] = self.is_live_mode
        return {key: self._normalize_config_value(key, value) for key, value in sorted(payload.items())}

    @property
    def config_checksum(self) -> str:
        """Return a stable checksum for the effective non-secret configuration."""
        serialized = json.dumps(
            self.config_checksum_payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("cors_origins", "demo_allowed_origins", mode="before")
    @classmethod
    def _validate_list_fields(cls, value):
        return _parse_csv_list(value)

    @field_validator("debug", mode="before")
    @classmethod
    def _validate_debug(cls, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes")
        return False

    @field_validator("ai_cloud_provider", mode="before")
    @classmethod
    def _validate_ai_cloud_provider(cls, value):
        provider = (value or "anthropic").strip().lower()
        if provider not in {"anthropic", "openai", "zai", "xiaomi"}:
            return "anthropic"
        return provider

    @field_validator("jwt_secret_key", mode="after")
    @classmethod
    def _validate_jwt_secret_key(cls, value):
        """Validate JWT secret key strength."""
        if not value:
            # Empty is allowed if using Supabase auth
            return value
        if len(value) < 32:
            raise ValueError(
                f"JWT_SECRET_KEY must be at least 32 characters for security, got {len(value)}. "
                'Generate a secure key: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return value

    @field_validator("supabase_url", mode="after")
    @classmethod
    def _validate_supabase_url(cls, value):
        """Validate Supabase URL format."""
        if not value:
            # Empty is allowed if using JSON storage
            return value
        # Basic URL validation - must start with http:// or https://
        if not re.match(r"^https?://", value, re.IGNORECASE):
            raise ValueError(f"SUPABASE_URL must be a valid URL starting with http:// or https://, got: {value}")
        return value

    @field_validator("supabase_service_role_key", mode="after")
    @classmethod
    def _validate_supabase_service_role_key(cls, value):
        """Validate Supabase service role key."""
        if not value:
            # Empty is allowed if not using Supabase
            return value
        # Allow short keys in test environments (e.g., pytest)
        # In production, service role keys are typically 50+ characters
        if len(value) < 16:
            raise ValueError(
                f"SUPABASE_SERVICE_ROLE_KEY must be at least 16 characters, got {len(value)}. "
                "This is a critical security credential - ensure it's kept secret."
            )
        return value

    @field_validator("anthropic_api_key", "openai_api_key", "zai_api_key", mode="after")
    @classmethod
    def _validate_ai_api_keys(cls, value):
        """Validate AI API key format."""
        if not value:
            # Empty is allowed if not using the respective AI provider
            return value
        # AI API keys should be reasonable length (typically 30+ characters)
        # This catches common errors like typos or placeholder values
        # Allow shorter keys in test environments (e.g., pytest)
        if len(value) < 15:
            raise ValueError(
                f"AI_API_KEY must be at least 15 characters for security, got {len(value)}. "
                "This suggests an invalid or placeholder API key."
            )
        # Check for common placeholder patterns (only for very short keys to avoid false positives)
        if len(value) < 25 and any(
            placeholder in value.lower() for placeholder in ["placeholder", "your_key_here", "change_me", "fake_key"]
        ):
            raise ValueError(
                f"AI_API_KEY contains placeholder text: {value}. "
                "Please replace with a valid API key from your AI provider."
            )
        return value

    @field_validator("encryption_key", mode="after")
    @classmethod
    def _validate_encryption_key(cls, value):
        """Validate Fernet encryption key format."""
        if not value:
            # Empty is allowed if encryption is disabled
            return value
        # Fernet keys are base64-encoded and should be 44 characters
        if len(value) != 44:
            raise ValueError(
                f"ENCRYPTION_KEY must be a valid Fernet key (44 characters), got {len(value)}. "
                "Generate with: "
                'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
        try:
            # Verify it's valid base64
            decoded = base64.urlsafe_b64decode(value.encode())
            if len(decoded) != 32:
                raise ValueError(
                    f"ENCRYPTION_KEY must decode to 32 bytes (256 bits), got {len(decoded)}. "
                    "This suggests an invalid Fernet key format."
                )
        except (base64.binascii.Error, UnicodeDecodeError) as e:
            raise ValueError(f"ENCRYPTION_KEY must be valid base64-encoded data: {e}") from e
        return value

    @field_validator("space_default_site_id", "plant_site_id", "plant_building_name", mode="after")
    @classmethod
    def _validate_required_site_config(cls, value, info):
        """Ensure required site config fields are set."""
        if not value:
            # Map Pydantic field name → env var alias
            field_to_env = {
                "space_default_site_id": "SITE_ID",
                "plant_site_id": "PLANT_SITE_ID",
                "plant_building_name": "BUILDING_NAME",
            }
            env_var = field_to_env.get(info.field_name, info.field_name.upper())
            raise ValueError(
                f"REQUIRED env var not set: {env_var}. "
                "Deployment cannot start without site configuration. "
                "Set SITE_ID, PLANT_SITE_ID, and BUILDING_NAME env vars."
            )
        return value

    @classmethod
    def _normalize_config_value(cls, field_name: str, value: Any) -> Any:
        """Normalize config values for checksum generation without exposing secrets."""
        if cls._is_sensitive_field(field_name):
            return cls._sensitive_value_marker(value)
        if isinstance(value, dict):
            return {
                str(key): cls._normalize_config_value(f"{field_name}.{key}", nested_value)
                for key, nested_value in sorted(value.items())
            }
        if isinstance(value, list):
            return [cls._normalize_config_value(field_name, item) for item in value]
        return value

    @staticmethod
    def _is_sensitive_field(field_name: str) -> bool:
        """Return True when a field likely contains credential material."""
        sensitive_markers = (
            "secret",
            "password",
            "token",
            "api_key",
            "service_role_key",
            "webhook",
            "sid",
            "dsn",
        )
        normalized = field_name.lower()
        return any(marker in normalized for marker in sensitive_markers)

    # Google Custom Search for building photo scraping
    google_cse_api_key: str = ""
    google_cse_engine_id: str = ""

    @staticmethod
    def _sensitive_value_marker(value: Any) -> str:
        """Collapse secret values to a stable presence marker."""
        if value in (None, "", [], {}, False):
            return "__empty__"
        return "__set__"


settings = Settings()
