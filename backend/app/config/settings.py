"""Application settings and configuration."""

from enum import StrEnum

from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings


BACKGROUND_AI_MODEL = "claude-haiku-4-5-20251001"  # Cost-optimised for scheduled jobs
INTERACTIVE_AI_MODEL = "claude-sonnet-4-20250514"  # Full capability for chat


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
    ]

    # Backend URL (for external service health checks)
    backend_url: str = ""

    # Claude AI settings
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 1536
    ai_cloud_provider: str = "anthropic"  # anthropic|openai|zai
    zai_api_key: str = ""
    zai_model: str = "glm-4.7-flash"
    zai_base_url: str = "https://api.z.ai/api/paas/v4"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-nano"  # Tier 1: fast/cheap for routine queries
    openai_model_heavy: str = "gpt-4.1-mini"  # Tier 2: complex reasoning & diagnostics
    openai_base_url: str = "https://api.openai.com/v1"
    local_ai_only: bool = False  # Force local-only AI mode (no Anthropic/Claude calls)
    popia_require_cross_border_consent: bool = True  # Block cloud LLM without explicit cross-border consent
    popia_dsr_sla_days: int = 30  # POPIA response SLA for data subject requests
    popia_retention_enabled: bool = True  # Enable scheduled retention enforcement
    popia_retention_consent_days: int = 1825  # 5 years
    popia_retention_request_days: int = 1825  # 5 years
    popia_retention_audit_days: int = 1825  # 5 years
    popia_retention_job_interval_seconds: int = 86400  # Daily

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
    ingestion_mode: str = "simulation"  # env: INGESTION_MODE

    # Site-002 data source — enables the simulation engine as a BMS data source
    # When False: SENTINEL starts clean with zero telemetry (SBC deployment ready)
    # When True: Loads reference devices and auto-starts lifecycle simulation
    site002_source_enabled: bool = False  # env: ENABLE_SITE002_SOURCE

    # Encryption at rest (Phase 1b FSR Compliance - Cryptography)
    encryption_enabled: bool = True
    encryption_key: str = ""  # Base64-encoded Fernet key from cryptography.fernet.Fernet.generate_key()

    # JWT secret key (required when not in DEMO_MODE)
    jwt_secret_key: str = ""

    # JWT token expiration (Phase 58-04 M-3: reduced from 30 days to 8 hours)
    jwt_expiration_hours: int = 8  # DEPRECATED: Use jwt_access_token_ttl_minutes instead
    jwt_expiry_days: int = 30  # DEPRECATED: legacy compatibility only

    # JWT access token TTL (Phase 65-02: short-lived tokens with refresh)
    jwt_access_token_ttl_minutes: int = 15  # 15 minutes for access tokens

    # JWT refresh token TTL (Phase 65-02: long-lived refresh tokens)
    jwt_refresh_token_ttl_days: int = 7  # 7 days for refresh tokens

    # Sentry webhook secret (required for Telegram bot integration)
    sentry_webhook_secret: str = ""

    # Sentry bot API key (for authenticated access to /api/sites/* endpoints)
    sentry_bot_api_key: str = Field(default="", validation_alias="SENTRY_BOT_API_KEY")
    sentry_bot_cli: str = Field(default="sentry", validation_alias="SENTRY_BOT_CLI")

    # SIMBIOT Concept Evolution (FSI Public API) credentials
    simbiot_api_key: str = ""
    simbiot_api_url: str = ""
    simbiot_username: str = ""
    simbiot_password: str = ""

    # Notification service settings (email, Slack)
    notification_smtp_host: str = ""
    notification_smtp_port: int = 587
    notification_smtp_username: str = ""
    notification_smtp_password: str = ""
    notification_smtp_use_tls: bool = True
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

    # Solar connector mode (v27.0 — simulation | live)
    solar_connector_mode: str = "simulation"  # simulation = demo data, live = real Modbus TCP

    # Sprint 0 write test gating — requires BOTH this AND aegis_bess_writer_enabled
    allow_write_tests: bool = False  # Second gate: explicitly allow hardware write tests

    # Sprint 0 hard safety limits (enforced in code, not just config)
    sprint0_max_power_kw: float = 5.0  # Max power per command during Sprint 0
    sprint0_max_duration_min: int = 10  # Max duration per command during Sprint 0

    # Background optimization model (cheaper than interactive chat)
    # Empty = use claude_model; set to e.g. "claude-haiku-4-5-20251001" for cost savings
    optimization_model: str = ""
    optimization_max_tokens: int = 1536

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

    # Block Booking Detection
    block_booking_enabled: bool = False  # Master switch
    block_booking_min_rooms: int = 2  # Flag when same person holds N+ rooms
    block_booking_mailbox_email: str = ""  # IMAP mailbox for BCC'd confirmations
    block_booking_mailbox_password: str = ""
    block_booking_mailbox_host: str = ""  # e.g. outlook.office365.com
    block_booking_concierge_email: str = ""  # Notification target
    block_booking_concierge_whatsapp: str = ""  # E.164 format
    block_booking_concierge_telegram_id: str = ""  # Telegram chat ID

    # Ghost Booking & Right-Sizing Detection (Rev 1.2)
    ghost_booking_grace_minutes: int = 15  # Wait N min after booking start before flagging
    right_sizing_grace_minutes: int = 20  # Do not flag until meeting has been running this long
    early_vacate_threshold_minutes: int = 90  # Room empty with >N min of booking remaining
    sporadic_use_threshold_pct: int = 25  # Occupied < N% of total booking duration
    brief_occupation_threshold_min: int = 30  # Occupied < N min total in the whole booking

    # Focus Room Sessions (Phase 2)
    focus_min_session_seconds: int = 180  # Discard sessions shorter than 3 min (noise)
    focus_extended_use_seconds: int = 7200  # Flag sessions longer than 2 hours

    # Telegram alert delivery
    telegram_bot_token: str = ""  # Bot token from BotFather
    telegram_alert_chat_id: str = ""  # Default chat/group ID for plant alerts

    # Plant Room Alerts — Desigo email→WhatsApp pipeline (Phase 146)
    plant_alerts_enabled: bool = False  # Master switch for plant alert ingestion
    desigo_sender_email: str = "noreply@fnb.co.za"  # Authorised Desigo sender address
    plant_site_id: str = "FLN02"  # Default site identifier for alarms
    plant_building_name: str = "Fairland 2"  # Default building name for alarms

    # WhatsApp delivery — Twilio (primary) or n8n webhook (fallback)
    twilio_account_sid: str = ""  # Twilio Account SID (ACxxxx)
    twilio_auth_token: str = ""  # Twilio Auth Token
    twilio_whatsapp_from: str = ""  # e.g. whatsapp:+14155238886
    twilio_whatsapp_to: str = ""  # e.g. whatsapp:+27721234567
    whatsapp_webhook_url: str = ""  # n8n webhook fallback (used if Twilio not configured)
    whatsapp_group_id: str = ""  # Target WhatsApp group ID (webhook mode only)

    @property
    def resolved_ingestion_mode(self) -> IngestionMode:
        """Resolve ingestion mode based on data source config and safe fallback."""
        if self.site002_source_enabled:
            return IngestionMode.SIMULATION
        try:
            return IngestionMode(self.ingestion_mode)
        except ValueError:
            return IngestionMode.SIMULATION

    @property
    def is_live_mode(self) -> bool:
        """True when running in live-read modes."""
        return self.resolved_ingestion_mode in (IngestionMode.SHADOW_LIVE, IngestionMode.LIVE_CONTROL)

    @property
    def recommendation_interval(self) -> int:
        """Recommendation generation interval in seconds (600s = 10 minutes)."""
        return 600

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
        if provider not in {"anthropic", "openai", "zai"}:
            return "anthropic"
        return provider


settings = Settings()
