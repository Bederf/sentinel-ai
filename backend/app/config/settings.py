"""Application settings and configuration."""

from pydantic import field_validator, ConfigDict
from pydantic_settings import BaseSettings


def _parse_csv_list(value):
    if isinstance(value, list):
        return value
    if not value:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    app_name: str = "BMS Intelligence"
    app_version: str = "13.2"
    debug: bool = False

    # CORS settings (restrict to known frontend origins)
    cors_origins: list[str] = ["http://localhost:9096"]

    # Claude AI settings
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 4096

    # Environment (development, staging, production)
    environment: str = "development"

    # Demo mode for pre-seeded responses
    demo_mode: bool = False
    demo_allowed_origins: list[str] = []

    # JWT secret key (required when not in DEMO_MODE)
    jwt_secret_key: str = ""

    # JWT token expiration (Phase 58-04 M-3: reduced from 30 days to 8 hours)
    jwt_expiration_hours: int = 8  # DEPRECATED: Use jwt_access_token_ttl_minutes instead

    # JWT access token TTL (Phase 65-02: short-lived tokens with refresh)
    jwt_access_token_ttl_minutes: int = 15  # 15 minutes for access tokens

    # JWT refresh token TTL (Phase 65-02: long-lived refresh tokens)
    jwt_refresh_token_ttl_days: int = 7  # 7 days for refresh tokens

    # Clawd webhook secret (required for Telegram bot integration)
    clawd_webhook_secret: str = ""

    # SIMBIOT Concept Evolution (FSI Public API) credentials
    simbiot_api_key: str = ""
    simbiot_api_url: str = ""
    simbiot_username: str = ""
    simbiot_password: str = ""

    # Supabase settings
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_role_key: str = ""
    use_json_storage: bool = False

    # Database URL (for direct PostgreSQL access if needed)
    database_url: str = ""

    # Redis cache settings
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True
    redis_default_ttl: int = 300  # 5 minutes default TTL

    # EskomSePush API (load shedding data)
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

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("cors_origins", "demo_allowed_origins", mode="before")
    @classmethod
    def _validate_list_fields(cls, value):
        return _parse_csv_list(value)


settings = Settings()
