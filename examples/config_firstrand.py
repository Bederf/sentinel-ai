"""
SIMBIOT Concept Connector — Example Configuration
==================================================
Shows how to configure the connector for a FirstRand/REMS deployment.

In production, load from environment variables or SENTINEL admin UI.
This file serves as documentation and a starting template.
"""

from simbiot_concept.models.config import (
    ConceptConfig,
    SegmentConfig,
    SeverityMapping,
    TradeMapping,
    RateLimitConfig,
    PollingConfig,
    SyncConfig,
    Environment,
)


def create_firstrand_config() -> ConceptConfig:
    """
    Example configuration for FirstRand/REMS deployment.

    Site-specific IDs (priorities, trades, segments) must be obtained from
    the MRI Evolution administrator. The values below are illustrative.
    """
    return ConceptConfig(
        # ── FSI Public API Connection ──
        api_base_url="https://developer.fsiservices.com",
        subscription_key="your-ocp-apim-subscription-key-here",  # type: ignore
        api_username="sentinel_api",
        api_password="secure-password-from-vault",  # type: ignore
        customer_site_code="FIRSTRAND_REMS",

        # ── Token Management ──
        token_refresh_threshold=0.8,  # Refresh at 80% of 7-day expiry (day 5.6)

        # ── Facilities / Contracts ──
        segments=[
            SegmentConfig(
                segment_id="SEG-FAIRLANDS-001",
                site_name="Fairlands Campus",
                cost_center_id=10001,
                enabled=True,
            ),
            SegmentConfig(
                segment_id="SEG-FNB-BRANCHES-GP",
                site_name="FNB Branches — Gauteng",
                cost_center_id=10002,
                enabled=True,
            ),
            SegmentConfig(
                segment_id="SEG-FNB-BRANCHES-WC",
                site_name="FNB Branches — Western Cape",
                cost_center_id=10003,
                enabled=True,
            ),
            SegmentConfig(
                segment_id="SEG-FNB-BRANCHES-KZN",
                site_name="FNB Branches — KwaZulu-Natal",
                cost_center_id=10004,
                enabled=True,
            ),
        ],

        # ── Severity → Priority Mapping ──
        # MRI Evolution priority IDs are site-specific — get from admin
        severity_mapping=SeverityMapping(
            critical_threshold=0.9,
            high_threshold=0.7,
            medium_threshold=0.5,
            low_threshold=0.3,
            p1_priority_id=1,   # Critical / Emergency
            p2_priority_id=2,   # High / Urgent
            p3_priority_id=3,   # Medium / Standard
            p4_priority_id=4,   # Low / Planned
        ),

        # ── Asset Type → Trade Mapping ──
        # MRI Evolution trade IDs are site-specific — get from admin
        trade_mapping=TradeMapping(
            hvac=101,           # Mechanical / HVAC
            electrical=102,     # Electrical
            plumbing=103,       # Plumbing
            fire=104,           # Fire Systems
            lifts=105,          # Lifts / Vertical Transport
            building_fabric=106,  # Building Fabric
            cleaning=107,       # Cleaning / Soft Services
            security=108,       # Security Systems
            general=109,        # General / Unclassified
        ),

        # ── Rate Limiting ──
        rate_limit=RateLimitConfig(
            max_calls_per_minute=200,      # Below FSI's 250 limit
            burst_size=10,
            backoff_base_seconds=1.0,
            backoff_max_seconds=600.0,     # Max 10-minute backoff
            circuit_breaker_threshold=5,   # 5 consecutive failures → open
            circuit_breaker_recovery_seconds=60.0,
        ),

        # ── Polling ──
        polling=PollingConfig(
            active_interval_seconds=300,   # 5 min for active WOs
            stale_interval_seconds=900,    # 15 min for WOs > 48h old
            stale_threshold_hours=48,
            max_open_tracking=500,
        ),

        # ── Asset Sync ──
        sync=SyncConfig(
            full_sync_cron="0 2 * * *",       # Daily at 02:00
            delta_sync_interval_seconds=14400,  # Every 4 hours
            cache_ttl_seconds=86400,            # 24h cache TTL
        ),

        # ── Deduplication ──
        dedup_cooldown_minutes=30,

        # ── Environment ──
        environment=Environment.PRODUCTION,
        log_level="INFO",

        # ── SENTINEL Callback ──
        sentinel_callback_url="http://sentinel-core:8000/api/v1/integration/events",
    )


# ── Quick sanity check ──
if __name__ == "__main__":
    config = create_firstrand_config()
    print(f"Config created: {len(config.segments)} segments")
    print(f"Default segment: {config.get_default_segment().site_name}")

    # Test severity mapping
    for score in [0.95, 0.75, 0.55, 0.25]:
        label = config.severity_mapping.get_priority_label(score)
        pid = config.severity_mapping.get_priority_id(score)
        print(f"  Score {score:.2f} → {label} (MRI ID: {pid})")

    # Test trade mapping
    for asset_type in ["chiller", "generator", "fire_panel", "cctv", "unknown_thing"]:
        tid = config.trade_mapping.get_trade_id(asset_type)
        print(f"  Asset '{asset_type}' → Trade ID {tid}")
