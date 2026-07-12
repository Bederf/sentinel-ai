"""Prometheus-format /metrics endpoint for AI governance observability.

Exposes SENTINEL AI control metrics in Prometheus text exposition format
for scraping by Prometheus/Victoria Metrics.

Phase 114-05: Creates the endpoint structure with static baseline values.
Real metric collection hooks into existing services will be wired in
Phase 2 (Control Implementation) per compliance.md roadmap.
"""

from __future__ import annotations

import contextlib
import ipaddress
import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)

from app.config.settings import settings
from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext, AuthLevel, SentinelRole

router = APIRouter()

# ---------------------------------------------------------------------------
# Dedicated registry (avoids polluting the default process-level registry
# which ships with python GC / platform metrics we don't want exposed).
# ---------------------------------------------------------------------------
REGISTRY = CollectorRegistry()

# ---------------------------------------------------------------------------
# Metric definitions — 8 AI governance metrics
# ---------------------------------------------------------------------------

# 1. Quality gate evaluations
sentinel_quality_gate_evaluations_total = Counter(
    "sentinel_quality_gate_evaluations_total",
    "Total quality-gate evaluations by site and outcome",
    labelnames=["site_id", "status"],
    registry=REGISTRY,
)

# 2. Quality gate enforcement level (current state gauge)
sentinel_quality_gate_enforcement = Gauge(
    "sentinel_quality_gate_enforcement",
    "Current enforcement level per site (1 = active for that enforcement level)",
    labelnames=["site_id", "enforcement"],
    registry=REGISTRY,
)

# 3. Recommendations generated
sentinel_recommendations_total = Counter(
    "sentinel_recommendations_total",
    "Total recommendations by site, tier, and action disposition",
    labelnames=["site_id", "tier", "action"],
    registry=REGISTRY,
)

# 4. Approval decisions
sentinel_approval_decisions_total = Counter(
    "sentinel_approval_decisions_total",
    "Total approval workflow decisions by site and outcome",
    labelnames=["site_id", "decision"],
    registry=REGISTRY,
)

# 5. Safety violations
sentinel_safety_violations_total = Counter(
    "sentinel_safety_violations_total",
    "Total safety boundary violations by site and severity",
    labelnames=["site_id", "severity"],
    registry=REGISTRY,
)

# 5b. Data freshness violations (Phase 188-01 — stale telemetry blocked before ML inference)
sentinel_data_freshness_violations_total = Counter(
    "sentinel_data_freshness_violations_total",
    "Number of times stale telemetry was rejected before ML inference",
    labelnames=["site_id"],
    registry=REGISTRY,
)

# 6. Model drift alerts (gauge — current active alert count)
sentinel_model_drift_alerts = Gauge(
    "sentinel_model_drift_alerts",
    "Active model drift alerts by site and model type",
    labelnames=["site_id", "model_type", "source", "data_sufficient"],
    registry=REGISTRY,
)

# 6b. Model drift score (gauge — current drift ratio per model)
sentinel_model_drift_score = Gauge(
    "sentinel_model_drift_score",
    "Model drift score (features_drifted / features_checked) per model",
    labelnames=["model_id", "model_type", "source", "data_sufficient", "data_quality"],
    registry=REGISTRY,
)

# 7. Rollback events
sentinel_rollback_total = Counter(
    "sentinel_rollback_total",
    "Total automated rollback events by site and equipment type",
    labelnames=["site_id", "equipment_type"],
    registry=REGISTRY,
)

# 8. Build / version info
sentinel_info = Info(
    "sentinel",
    "SENTINEL build and configuration metadata",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# HTTP request metrics (Phase 127 — RequestMetricsMiddleware)
# ---------------------------------------------------------------------------

# 9. HTTP request counter
sentinel_http_requests_total = Counter(
    "sentinel_http_requests_total",
    "Total HTTP requests by method, path pattern, and status code",
    labelnames=["method", "path", "status_code"],
    registry=REGISTRY,
)

# 10. HTTP request duration histogram
sentinel_http_request_duration_seconds = Histogram(
    "sentinel_http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "path"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=REGISTRY,
)

# 11. HTTP requests in progress
sentinel_http_requests_in_progress = Gauge(
    "sentinel_http_requests_in_progress",
    "Number of HTTP requests currently being processed",
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Tool-call metrics (Phase 127 — chat pipeline instrumentation)
# ---------------------------------------------------------------------------

# 12. Tool call counter
sentinel_tool_calls_total = Counter(
    "sentinel_tool_calls_total",
    "Total tool calls by tool name and outcome",
    labelnames=["tool_name", "outcome"],
    registry=REGISTRY,
)

# 13. Tool call duration histogram
sentinel_tool_call_duration_seconds = Histogram(
    "sentinel_tool_call_duration_seconds",
    "Tool call execution duration in seconds",
    labelnames=["tool_name"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Database & cache metrics (Phase 125 — Supabase Performance Completion)
# ---------------------------------------------------------------------------

# 14. Supabase query duration
sentinel_db_query_duration_seconds = Histogram(
    "sentinel_db_query_duration_seconds",
    "Supabase PostgREST query duration in seconds",
    labelnames=["repository", "method"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
    registry=REGISTRY,
)

# 15. Cache operations counter
sentinel_cache_operations_total = Counter(
    "sentinel_cache_operations_total",
    "Cache operations by type (hit, miss, error)",
    labelnames=["operation"],
    registry=REGISTRY,
)

# 16. Cache hit rate gauge
sentinel_cache_hit_rate_percent = Gauge(
    "sentinel_cache_hit_rate_percent",
    "Current cache hit rate percentage",
    registry=REGISTRY,
)

# 16b. Backend uptime indicator (1 = up, 0 = down)
# Updated by the metrics endpoint handler on every scrape
sentinel_backend_up = Gauge(
    "sentinel_backend_up",
    "Backend API health indicator: 1 = up, 0 = down",
    registry=REGISTRY,
)

# 16c. Metrics last updated timestamp (epoch seconds)
sentinel_metrics_last_updated_timestamp = Gauge(
    "sentinel_metrics_last_updated_timestamp",
    "Unix timestamp of the last metrics collection, used for scrape age tracking",
    labelnames=["job"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Scheduler job observability (Phase 226.1.3 — unknown scheduler risk)
# ---------------------------------------------------------------------------

# 16d. Scheduler job duration histogram
sentinel_scheduler_job_duration_seconds = Histogram(
    "sentinel_scheduler_job_duration_seconds",
    "Duration of background scheduler job execution",
    labelnames=["job_name"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
    registry=REGISTRY,
)

# 16e. Scheduler job error counter
sentinel_scheduler_job_errors_total = Counter(
    "sentinel_scheduler_job_errors_total",
    "Total scheduler job errors",
    labelnames=["job_name"],
    registry=REGISTRY,
)

# 16f. Supabase call duration histogram (feeds async-blocking risk signal)
sentinel_supabase_call_duration_seconds = Histogram(
    "sentinel_supabase_call_duration_seconds",
    "Duration of Supabase client calls",
    labelnames=["table", "op"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
    registry=REGISTRY,
)

# Short aliases for internal use (e.g. decorators, tests)
SCHEDULER_JOB_DURATION = sentinel_scheduler_job_duration_seconds
SCHEDULER_JOB_ERRORS = sentinel_scheduler_job_errors_total
SUPABASE_CALL_DURATION = sentinel_supabase_call_duration_seconds

# ---------------------------------------------------------------------------
# FM / Media Wall metrics (Phase 144 — Building Intelligence Dashboard)
# ---------------------------------------------------------------------------

# 17. Active alerts by severity and building
sentinel_alerts = Gauge(
    "sentinel_alerts",
    "Active alerts by severity and building",
    labelnames=["severity", "building", "status"],
    registry=REGISTRY,
)

# 18. Job cards by status and outcome
sentinel_job_cards = Gauge(
    "sentinel_job_cards",
    "Job card records by building, status, and outcome",
    labelnames=["building", "status", "outcome"],
    registry=REGISTRY,
)

# 19. Job cards created total (counter for rate calculations)
sentinel_job_cards_created_total = Counter(
    "sentinel_job_cards_created_total",
    "Total job cards created by building",
    labelnames=["building"],
    registry=REGISTRY,
)

# 20. SLA met count
sentinel_sla_met = Gauge(
    "sentinel_sla_met",
    "Count of SLA-compliant completed jobs by building",
    labelnames=["building"],
    registry=REGISTRY,
)

# 21. Critical response time
sentinel_critical_response_time_seconds = Gauge(
    "sentinel_critical_response_time_seconds",
    "Average response time for critical alerts in seconds",
    labelnames=["severity", "building"],
    registry=REGISTRY,
)

# 22. Equipment health status
sentinel_equipment_health = Gauge(
    "sentinel_equipment_health",
    "Equipment health status gauge (0-100 score)",
    labelnames=["building", "equipment", "health"],
    registry=REGISTRY,
)

# 23. Equipment issues (for table panel)
sentinel_equipment_issues = Gauge(
    "sentinel_equipment_issues",
    "Active equipment issues with details",
    labelnames=["building", "equipment", "issue", "severity"],
    registry=REGISTRY,
)

# 24. Maintenance backlog in days
sentinel_maintenance_backlog_days = Gauge(
    "sentinel_maintenance_backlog_days",
    "Days of pending maintenance work per building",
    labelnames=["building"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Phase 160 — AI Governance Metrics (5 new families)
# ---------------------------------------------------------------------------

# 25. Quality gate pass/fail per rule (supplements #1 which tracks by site/status)
sentinel_quality_gate_rule_evaluations_total = Counter(
    "sentinel_quality_gate_rule_evaluations_total",
    "Quality gate evaluations by individual rule and outcome",
    labelnames=["rule_name", "status"],
    registry=REGISTRY,
)

# Drift detection gates
MIN_BASELINE_HOURS = 72  # Absolute minimum — below this, don't run at all
MIN_BASELINE_AGE_HOURS = 168  # 7 days for production-grade signal


def _assess_drift_data_sufficiency(
    baseline_span_seconds: float,
    features_checked: int,
) -> tuple[str, str]:
    """
    Two-tier gate for drift detection data quality.

    Returns (data_quality, data_sufficient).
    data_quality drives Grafana styling and alert filtering.
    data_sufficient is the legacy label kept for alert backward compatibility.
    """
    hours_of_data = baseline_span_seconds / 3600

    if features_checked < 30:
        return "insufficient_samples", "false"

    if hours_of_data < MIN_BASELINE_HOURS:
        return "insufficient_timespan", "false"

    if hours_of_data < MIN_BASELINE_AGE_HOURS:
        return "provisional", "true"

    return "sufficient", "true"


# 5b. Drift baseline temporal span (hours of data available for comparison)
sentinel_drift_baseline_hours = Gauge(
    "sentinel_drift_baseline_hours",
    "Hours of baseline data available for drift detection",
    ["model_id", "site_id", "data_quality"],
    registry=REGISTRY,
)

# 27. Tool-call errors by error type (supplements #12 which tracks by outcome)
sentinel_tool_call_errors_total = Counter(
    "sentinel_tool_call_errors_total",
    "Tool call errors by tool name and error classification",
    labelnames=["tool_name", "error_type"],
    registry=REGISTRY,
)

# 28. Approval latency histogram
sentinel_approval_latency_seconds = Histogram(
    "sentinel_approval_latency_seconds",
    "Time from approval request to decision in seconds",
    labelnames=["site_id", "tier"],
    buckets=[1, 5, 15, 30, 60, 120, 300, 600, 1800],
    registry=REGISTRY,
)

# 29. (Removed — rejection rate computed from sentinel_approval_decisions_total counter)

# ---------------------------------------------------------------------------
# Phase 211 — Demand Response / DDMP Metrics (IES/LTM Integration)
# ---------------------------------------------------------------------------

# 30. Curtailable HVAC load (kW) - the core metric for DDMP
sentinel_curtailable_load_kw = Gauge(
    "sentinel_curtailable_load_kw",
    "Current curtailable HVAC load in kW per site",
    labelnames=["site_id", "customer"],
    registry=REGISTRY,
)

# 31. Safe duration for curtailment (minutes)
sentinel_safe_duration_minutes = Gauge(
    "sentinel_safe_duration_minutes",
    "Minutes until comfort breach if curtailed",
    labelnames=["site_id"],
    registry=REGISTRY,
)

# 32. Confidence score for curtailment prediction (0.0-0.95)
sentinel_confidence_score = Gauge(
    "sentinel_confidence_score",
    "Confidence in curtailment prediction (0.0-0.95)",
    labelnames=["site_id"],
    registry=REGISTRY,
)

# 33. DDMP eligibility status (1 = eligible, 0 = not eligible)
sentinel_ddmp_eligible = Gauge(
    "sentinel_ddmp_eligible",
    "DDMP eligibility status per site (1 = eligible)",
    labelnames=["site_id"],
    registry=REGISTRY,
)

# 34. Data freshness in seconds (for 503 logic visibility)
sentinel_data_freshness_seconds = Gauge(
    "sentinel_data_freshness_seconds",
    "Seconds since last sensor reading",
    labelnames=["site_id"],
    registry=REGISTRY,
)

# 35. Thermal runway in minutes (comfort countdown)
sentinel_thermal_runway_minutes = Gauge(
    "sentinel_thermal_runway_minutes",
    "Minutes until thermal comfort boundary breached",
    labelnames=["site_id"],
    registry=REGISTRY,
)

# 36. Zone coverage ratio (0.0-1.0)
sentinel_zone_coverage_percent = Gauge(
    "sentinel_zone_coverage_percent",
    "Percentage of zones reporting data",
    labelnames=["site_id"],
    registry=REGISTRY,
)

# 37. BESS SOC percentage (if BESS present)
sentinel_bess_soc_percent = Gauge(
    "sentinel_bess_soc_percent",
    "BESS State of Charge percentage (0-100)",
    labelnames=["site_id", "battery_id"],
    registry=REGISTRY,
)

# 38. DDMP event tracking
ddmp_event_active = Gauge(
    "sentinel_ddmp_event_active",
    "DDMP curtailment event active per site (1 = active)",
    labelnames=["site_id", "event_id"],
    registry=REGISTRY,
)

# 39. API request metrics for demand response endpoint
sentinel_demand_response_requests_total = Counter(
    "sentinel_demand_response_requests_total",
    "Total demand response API requests",
    labelnames=["site_id", "status_code"],
    registry=REGISTRY,
)

# 40. Demand response calculation duration
sentinel_demand_response_duration_seconds = Histogram(
    "sentinel_demand_response_duration_seconds",
    "Demand response calculation duration",
    labelnames=["site_id"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    registry=REGISTRY,
)

# 30. Token usage by route and site
sentinel_ai_tokens_by_route_total = Counter(
    "sentinel_ai_tokens_by_route_total",
    "AI tokens consumed by route, site, provider, and model",
    labelnames=["route", "site_id", "provider", "model"],
    registry=REGISTRY,
)

# 31. Cost by route, site, model, and task class
sentinel_ai_cost_by_route_total = Counter(
    "sentinel_ai_cost_by_route_total",
    "AI cost in USD by route, site, model, and task class",
    labelnames=["route", "site_id", "model", "task_class"],
    registry=REGISTRY,
)

# 32. Retrieval latency histogram (canonical/hybrid retrieval paths)
sentinel_retrieval_latency_seconds = Histogram(
    "sentinel_retrieval_latency_seconds",
    "Retrieval query latency by retrieval path and fallback mode",
    labelnames=["retrieval_path", "fallback"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    registry=REGISTRY,
)

# 33. Retrieval hit counter
sentinel_retrieval_hits_total = Counter(
    "sentinel_retrieval_hits_total",
    "Total retrieval hits returned by retrieval path and fallback mode",
    labelnames=["retrieval_path", "fallback"],
    registry=REGISTRY,
)

# 34. Retrieval fallback usage counter
sentinel_retrieval_fallbacks_total = Counter(
    "sentinel_retrieval_fallbacks_total",
    "Total retrieval fallback activations by fallback type",
    labelnames=["fallback"],
    registry=REGISTRY,
)

# ---------------------------------------------------------------------------
# Phase 189 — LLM Judge Loop (INTERIM)
# ---------------------------------------------------------------------------

sentinel_llm_judge_score = Gauge(
    "sentinel_llm_judge_score",
    "LLM judge evaluation score for recent AI explanations (0-1, higher is better)",
    ["score_type"],  # actionability, factuality, completeness, conciseness
    registry=REGISTRY,
)


# ---------------------------------------------------------------------------
# Phase 212 — Discipline Metrics (HVAC, Energy, Lighting, Solar, Water, Fire, Security, Space, Fuel, ESG)
# ---------------------------------------------------------------------------

# HVAC — zone temperature
sentinel_hvac_zone_temp_celsius = Gauge(
    "sentinel_hvac_zone_temp_celsius",
    "Zone actual temperature in Celsius",
    labelnames=["site_id", "zone_id"],
    registry=REGISTRY,
)

sentinel_hvac_zone_temp_deviation_celsius = Gauge(
    "sentinel_hvac_zone_temp_deviation_celsius",
    "Zone temperature deviation from setpoint in Celsius",
    labelnames=["site_id", "zone_id"],
    registry=REGISTRY,
)

sentinel_hvac_ahu_status = Gauge(
    "sentinel_hvac_ahu_status",
    "AHU operational status (1=running, 0=off)",
    labelnames=["site_id", "ahu_id"],
    registry=REGISTRY,
)

sentinel_hvac_savings_zar = Gauge(
    "sentinel_hvac_savings_zar",
    "HVAC energy cost savings in ZAR",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_hvac_thermal_runway_warnings = Gauge(
    "sentinel_hvac_thermal_runway_warnings",
    "Count of zones approaching thermal runway",
    labelnames=["site_id"],
    registry=REGISTRY,
)

# Energy — aggregate
sentinel_energy_total_kwh = Gauge(
    "sentinel_energy_total_kwh",
    "Total site energy consumption in kWh",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_energy_demand_kw = Gauge(
    "sentinel_energy_demand_kw",
    "Current site demand in kW",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_energy_cost_zar = Gauge(
    "sentinel_energy_cost_zar",
    "Total energy cost in ZAR",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_energy_peak_demand_kw = Gauge(
    "sentinel_energy_peak_demand_kw",
    "Peak demand in kW this billing period",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_energy_lighting_kwh = Gauge(
    "sentinel_energy_lighting_kwh",
    "Lighting energy in kWh",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_energy_carbon_kg = Gauge(
    "sentinel_energy_carbon_kg",
    "Carbon emissions in kg CO2",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_equipment_baseline_coverage_percent = Gauge(
    "sentinel_equipment_baseline_coverage_percent",
    "Percent of site equipment with an active onboarding/shadow baseline record",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_equipment_phase_health_score_avg = Gauge(
    "sentinel_equipment_phase_health_score_avg",
    "Average equipment health score observed during each onboarding/control phase",
    labelnames=["site_id", "phase"],
    registry=REGISTRY,
)

sentinel_equipment_phase_health_delta_from_shadow = Gauge(
    "sentinel_equipment_phase_health_delta_from_shadow",
    "Average equipment health score delta from shadow or shadow_live baseline",
    labelnames=["site_id", "phase"],
    registry=REGISTRY,
)

sentinel_energy_phase_avg_daily_kwh = Gauge(
    "sentinel_energy_phase_avg_daily_kwh",
    "Average daily site energy kWh observed during each onboarding/control phase",
    labelnames=["site_id", "phase"],
    registry=REGISTRY,
)

sentinel_energy_phase_delta_from_shadow_kwh = Gauge(
    "sentinel_energy_phase_delta_from_shadow_kwh",
    "Average daily site energy kWh delta from shadow or shadow_live baseline",
    labelnames=["site_id", "phase"],
    registry=REGISTRY,
)

sentinel_recommendation_baseline_energy_kwh = Gauge(
    "sentinel_recommendation_baseline_energy_kwh",
    "Measured baseline energy before recommendation execution in kWh",
    labelnames=["site_id", "recommendation_id", "equipment_id"],
    registry=REGISTRY,
)

sentinel_recommendation_actual_energy_kwh = Gauge(
    "sentinel_recommendation_actual_energy_kwh",
    "Measured energy after recommendation execution in kWh",
    labelnames=["site_id", "recommendation_id", "equipment_id"],
    registry=REGISTRY,
)

sentinel_recommendation_actual_saving_kwh = Gauge(
    "sentinel_recommendation_actual_saving_kwh",
    "Measured recommendation energy saving in kWh; negative values mean increased consumption",
    labelnames=["site_id", "recommendation_id", "equipment_id"],
    registry=REGISTRY,
)

sentinel_recommendation_actual_saving_zar = Gauge(
    "sentinel_recommendation_actual_saving_zar",
    "Measured recommendation Rand saving; negative values mean increased cost",
    labelnames=["site_id", "recommendation_id", "equipment_id"],
    registry=REGISTRY,
)

# Lighting — per zone
sentinel_lighting_zone_lux = Gauge(
    "sentinel_lighting_zone_lux",
    "Zone lighting level in lux",
    labelnames=["site_id", "zone_id"],
    registry=REGISTRY,
)

sentinel_lighting_fixtures_on = Gauge(
    "sentinel_lighting_fixtures_on",
    "Number of lighting fixtures currently on",
    labelnames=["site_id", "zone_id"],
    registry=REGISTRY,
)

sentinel_lighting_fixtures_total = Gauge(
    "sentinel_lighting_fixtures_total",
    "Total number of lighting fixtures",
    labelnames=["site_id", "zone_id"],
    registry=REGISTRY,
)

sentinel_lighting_energy_kwh_total = Counter(
    "sentinel_lighting_energy_kwh_total",
    "Total lighting energy consumed in kWh",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_lighting_occupancy_percent = Gauge(
    "sentinel_lighting_occupancy_percent",
    "Zone occupancy percentage for lighting control",
    labelnames=["site_id", "zone_id"],
    registry=REGISTRY,
)

# Solar / BESS
sentinel_solar_pv_generation_kw = Gauge(
    "sentinel_solar_pv_generation_kw",
    "Current solar PV generation in kW",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_bess_current_charge_kw = Gauge(
    "sentinel_bess_current_charge_kw",
    "BESS current charge (positive) or discharge (negative) in kW",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_solar_total_generation_kwh_total = Counter(
    "sentinel_solar_total_generation_kwh_total",
    "Total solar generation in kWh",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_solar_export_kwh_total = Counter(
    "sentinel_solar_export_kwh_total",
    "Total solar export to grid in kWh",
    labelnames=["site_id"],
    registry=REGISTRY,
)

# Water
sentinel_water_consumption_kl_total = Counter(
    "sentinel_water_consumption_kl_total",
    "Total water consumption in kL",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_water_flow_rate_lph = Gauge(
    "sentinel_water_flow_rate_lph",
    "Water flow rate in liters per hour",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_water_tank_level_percent = Gauge(
    "sentinel_water_tank_level_percent",
    "Water tank level percentage",
    labelnames=["site_id", "tank_id"],
    registry=REGISTRY,
)

sentinel_water_cost_zar = Gauge(
    "sentinel_water_cost_zar",
    "Total water cost in ZAR",
    labelnames=["site_id"],
    registry=REGISTRY,
)

# Fire
sentinel_fire_panel_status = Gauge(
    "sentinel_fire_panel_status",
    "Fire panel status (0=normal, 1=alarm, 2=fault)",
    labelnames=["site_id", "panel_id"],
    registry=REGISTRY,
)

sentinel_fire_detector_faults = Gauge(
    "sentinel_fire_detector_faults",
    "Number of fire detector faults per panel",
    labelnames=["site_id", "panel_id"],
    registry=REGISTRY,
)

sentinel_fire_extinguisher_expiry_days = Gauge(
    "sentinel_fire_extinguisher_expiry_days",
    "Days until extinguisher expiry",
    labelnames=["site_id", "extinguisher_id"],
    registry=REGISTRY,
)

sentinel_fire_evacuation_status = Gauge(
    "sentinel_fire_evacuation_status",
    "Evacuation status (0=safe, 1=evacuate)",
    labelnames=["site_id"],
    registry=REGISTRY,
)

# Security
sentinel_security_zone_breaches = Gauge(
    "sentinel_security_zone_breaches",
    "Security breaches by zone",
    labelnames=["site_id", "zone_id"],
    registry=REGISTRY,
)

sentinel_security_camera_uptime_percent = Gauge(
    "sentinel_security_camera_uptime_percent",
    "Security camera uptime percentage",
    labelnames=["site_id", "camera_id"],
    registry=REGISTRY,
)

sentinel_security_access_events_total = Counter(
    "sentinel_security_access_events_total",
    "Total access events by type",
    labelnames=["site_id", "event_type"],
    registry=REGISTRY,
)

sentinel_security_alarm_status = Gauge(
    "sentinel_security_alarm_status",
    "Alarm status by zone (0=normal, 1=alarm)",
    labelnames=["site_id", "zone_id"],
    registry=REGISTRY,
)

# Space
sentinel_space_occupancy_percent = Gauge(
    "sentinel_space_occupancy_percent",
    "Space occupancy percentage",
    labelnames=["site_id", "zone_id"],
    registry=REGISTRY,
)

sentinel_space_utilization_percent = Gauge(
    "sentinel_space_utilization_percent",
    "Space utilization percentage",
    labelnames=["site_id", "zone_id"],
    registry=REGISTRY,
)

sentinel_space_bookable_desks = Gauge(
    "sentinel_space_bookable_desks",
    "Number of bookable desks",
    labelnames=["site_id", "floor_id"],
    registry=REGISTRY,
)

sentinel_space_occupied_desks = Gauge(
    "sentinel_space_occupied_desks",
    "Number of occupied desks",
    labelnames=["site_id", "floor_id"],
    registry=REGISTRY,
)

# Fuel
sentinel_fuel_generator_runtime_hours = Gauge(
    "sentinel_fuel_generator_runtime_hours",
    "Generator runtime in hours",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_fuel_level_percent = Gauge(
    "sentinel_fuel_level_percent",
    "Fuel tank level percentage",
    labelnames=["site_id", "tank_id"],
    registry=REGISTRY,
)

sentinel_fuel_consumption_lph = Gauge(
    "sentinel_fuel_consumption_lph",
    "Fuel consumption in liters per hour",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_fuel_cost_zar = Gauge(
    "sentinel_fuel_cost_zar",
    "Total fuel cost in ZAR",
    labelnames=["site_id"],
    registry=REGISTRY,
)

# ESG
sentinel_esg_carbon_footprint_kg = Gauge(
    "sentinel_esg_carbon_footprint_kg",
    "Carbon footprint in kg CO2",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_esg_renewable_percent = Gauge(
    "sentinel_esg_renewable_percent",
    "Renewable energy percentage",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_esg_energy_intensity_kwh_per_sqm = Gauge(
    "sentinel_esg_energy_intensity_kwh_per_sqm",
    "Energy intensity kWh per sqm",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_esg_water_intensity_l_per_sqm = Gauge(
    "sentinel_esg_water_intensity_l_per_sqm",
    "Water intensity liters per sqm",
    labelnames=["site_id"],
    registry=REGISTRY,
)

sentinel_esg_waste_kg = Gauge(
    "sentinel_esg_waste_kg",
    "Waste in kg",
    labelnames=["site_id"],
    registry=REGISTRY,
)


# ---------------------------------------------------------------------------
# Phase 212 — Discipline Metrics Collection
# ---------------------------------------------------------------------------


def _collect_discipline_metrics() -> None:
    """Collect HVAC/Energy/Lighting/Water/Security/Fire/Space/Fuel metrics from bridge sensor data.

    Reads latest values from equipment_sensor_readings table (written by SIMBIOT bridge)
    and exposes them as Prometheus gauges for the discipline dashboards.
    """
    import logging

    logger = logging.getLogger("sentinel.metrics")

    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        if not client:
            return
    except Exception:
        return

    SITE_ID = "site-002"

    # Shared dict for latest sensor values across metric blocks below
    latest: dict[str, float] = {}

    # — Latest reading timestamp for data freshness —
    try:
        fresh_resp = (
            client.table("equipment_sensor_readings")
            .select("recorded_at")
            .eq("site_id", SITE_ID)
            .order("recorded_at", desc=True)
            .limit(1)
            .execute()
        )
        if fresh_resp.data:
            last_ts = datetime.fromisoformat(fresh_resp.data[0]["recorded_at"].replace("Z", "+00:00"))
            age_seconds = (datetime.now(UTC) - last_ts).total_seconds()
            sentinel_data_freshness_seconds.labels(site_id=SITE_ID).set(age_seconds)
    except Exception as e:
        logger.debug(f"Discipline metrics: freshness query failed: {e}")

    # — Zone temperature (room_temp sensor, keyed by equipment_id) —
    try:
        zone_resp = (
            client.table("equipment_sensor_readings")
            .select("equipment_id, value")
            .eq("site_id", SITE_ID)
            .eq("sensor_type", "room_temp")
            .execute()
        )
        zone_count = 0
        for row in zone_resp.data or []:
            zone_id = row.get("equipment_id", "unknown")
            val = row.get("value")
            if val is not None:
                sentinel_hvac_zone_temp_celsius.labels(site_id=SITE_ID, zone_id=zone_id).set(val)
                zone_count += 1
        if zone_count > 0:
            sentinel_zone_coverage_percent.labels(site_id=SITE_ID).set(zone_count / 50.0)  # approx 50 zones max
    except Exception as e:
        logger.warning(f"Discipline metrics: zone temp query failed: {e}")

    # — HVAC energy from CHILLER-AGG kWh readings (rate from counters) —
    try:
        hvac_resp = (
            client.table("equipment_sensor_readings")
            .select("equipment_id, sensor_type, value, recorded_at")
            .eq("site_id", SITE_ID)
            .in_("sensor_type", ["hvac_kw", "lighting_kw", "total_kw"])
            .order("recorded_at", desc=True)
            .execute()
        )
        # Latest value per type
        for row in hvac_resp.data or []:
            st = row.get("sensor_type", "")
            if st not in latest:
                latest[st] = row.get("value", 0) or 0

        if "hvac_kw" in latest:
            sentinel_energy_total_kwh.labels(site_id=SITE_ID).set(latest["hvac_kw"])
        if "lighting_kw" in latest:
            sentinel_energy_lighting_kwh.labels(site_id=SITE_ID).set(latest["lighting_kw"])
        if "total_kw" in latest:
            sentinel_energy_demand_kw.labels(site_id=SITE_ID).set(latest["total_kw"])
    except Exception as e:
        logger.debug(f"Discipline metrics: energy query failed: {e}")

    # — AHU status from fan_speed sensor —
    try:
        ahu_resp = (
            client.table("equipment_sensor_readings")
            .select("equipment_id, value")
            .eq("site_id", SITE_ID)
            .ilike("equipment_id", "%AHU%")
            .eq("sensor_type", "fan_speed")
            .execute()
        )
        for row in ahu_resp.data or []:
            ahu_id = row.get("equipment_id", "unknown")
            val = row.get("value", 0) or 0
            # fan_speed > 0 means running
            sentinel_hvac_ahu_status.labels(site_id=SITE_ID, ahu_id=ahu_id).set(1 if val > 0 else 0)
    except Exception as e:
        logger.debug(f"Discipline metrics: AHU query failed: {e}")

    # — CO2 / occupancy for space metrics —
    try:
        occ_resp = (
            client.table("equipment_sensor_readings")
            .select("equipment_id, sensor_type, value")
            .eq("site_id", SITE_ID)
            .in_("sensor_type", ["co2_ppm", "occupied_zones", "total_occupancy"])
            .execute()
        )
        occ_zones = 0
        occ_total = 0
        for row in occ_resp.data or []:
            st = row.get("sensor_type", "")
            val = row.get("value", 0) or 0
            if st == "occupied_zones":
                occ_zones = val
                sentinel_space_occupancy_percent.labels(site_id=SITE_ID, zone_id="aggregate").set(val)
            elif st == "total_occupancy":
                occ_total = val
        if occ_zones > 0 and occ_total > 0:
            # utilization estimate
            sentinel_space_utilization_percent.labels(site_id=SITE_ID, zone_id="aggregate").set(
                min(100, occ_total / (occ_zones * 10) * 100)
            )
    except Exception as e:
        logger.debug(f"Discipline metrics: occupancy query failed: {e}")

    # — Security — access events from access_denied_count —
    try:
        sec_resp = (
            client.table("equipment_sensor_readings")
            .select("equipment_id, value")
            .eq("site_id", SITE_ID)
            .in_("sensor_type", ["access_denied_count", "forced_door_count", "entry_count"])
            .execute()
        )
        for row in sec_resp.data or []:
            eq = row.get("equipment_id", "unknown")
            st = row.get("sensor_type", "")
            val = row.get("value", 0) or 0
            event_type = st.replace("_count", "").replace("_", " ")
            sentinel_security_access_events_total.labels(site_id=SITE_ID, event_type=event_type).set(val)
            if st in ("access_denied_count", "forced_door_count") and val > 0:
                # Zone breach: extract zone from equipment_id (e.g. S002-DOOR-MAIN-ENT → MAIN-ENT)
                zone = eq.split("-")[-1] if "-" in eq else eq
                sentinel_security_zone_breaches.labels(site_id=SITE_ID, zone_id=zone).set(val)
    except Exception as e:
        logger.debug(f"Discipline metrics: security query failed: {e}")

    # — Water from flow_rate_lpm sensor —
    try:
        water_resp = (
            client.table("equipment_sensor_readings")
            .select("equipment_id, value")
            .eq("site_id", SITE_ID)
            .in_("sensor_type", ["flow_rate_lpm", "total_consumption_m3"])
            .execute()
        )
        for row in water_resp.data or []:
            eq = row.get("equipment_id", "")
            st = row.get("sensor_type", "")
            val = row.get("value", 0) or 0
            if st == "flow_rate_lpm":
                sentinel_water_flow_rate_lph.labels(site_id=SITE_ID).set(val * 60)  # lpm → lph
            elif st == "total_consumption_m3":
                sentinel_water_consumption_kl_total.labels(site_id=SITE_ID).set(val * 1000)  # m3 → kL
    except Exception as e:
        logger.debug(f"Discipline metrics: water query failed: {e}")

    # — FCU status from fan_speed (FCU units) —
    try:
        fcu_resp = (
            client.table("equipment_sensor_readings")
            .select("equipment_id, value")
            .eq("site_id", SITE_ID)
            .ilike("equipment_id", "%FCU%")
            .eq("sensor_type", "fan_speed")
            .execute()
        )
        for row in fcu_resp.data or []:
            eq = row.get("equipment_id", "")
            val = row.get("value", 0) or 0
            # Zone temp for FCU zones using room_temp readings filtered to same equipment_id base
            zone_id = eq
            if val > 0:
                sentinel_hvac_zone_temp_celsius.labels(site_id=SITE_ID, zone_id=zone_id).set(
                    row.get("value", 22)  # fallback if no separate room_temp
                )
    except Exception as e:
        logger.debug(f"Discipline metrics: FCU query failed: {e}")

    # — Energy cost, peak demand, carbon from sensor data —
    try:
        # Use latest total_kw × flat tariff rate for cost estimation
        total_kw = latest.get("total_kw", 0)
        tariff_rate = 0.63  # ZAR/kWh (City Power 2026 blended rate)
        est_cost = total_kw * tariff_rate
        sentinel_energy_cost_zar.labels(site_id=SITE_ID).set(round(est_cost, 2))

        # Peak demand: max total_kw from recent readings
        peak_resp = (
            client.table("equipment_sensor_readings")
            .select("value")
            .eq("site_id", SITE_ID)
            .eq("sensor_type", "total_kw")
            .order("recorded_at", desc=True)
            .limit(100)
            .execute()
        )
        peak_kw = 0
        if peak_resp.data:
            vals = [float(r.get("value", 0) or 0) for r in peak_resp.data]
            peak_kw = max(vals)
        sentinel_energy_peak_demand_kw.labels(site_id=SITE_ID).set(peak_kw)

        # Carbon: kWh × grid emission factor
        grid_factor = 1.06  # kg CO2/kWh (South African grid average)
        sentinel_energy_carbon_kg.labels(site_id=SITE_ID).set(round(total_kw * grid_factor, 2))
    except Exception as e:
        logger.debug(f"Discipline metrics: cost/peak/carbon calc failed: {e}")

    # — Onboarding/shadow baseline and phase comparison metrics —
    try:
        site_resp = client.table("sites").select("id, code, onboarding_phase").eq("code", SITE_ID).limit(1).execute()
        site_row = (site_resp.data or [{}])[0]
        site_uuid = str(site_row.get("id") or "")

        equipment_resp = (
            client.table("equipment").select("id").eq("site_id", site_uuid).execute() if site_uuid else None
        )
        equipment_ids = [str(row.get("id")) for row in (equipment_resp.data or []) if row.get("id")]
        total_equipment = len(equipment_ids)
        baseline_count = 0
        if equipment_ids:
            baseline_resp = (
                client.table("equipment_baselines")
                .select("equipment_id")
                .in_("equipment_id", equipment_ids)
                .eq("status", "active")
                .execute()
            )
            baseline_count = len(
                {str(row.get("equipment_id")) for row in (baseline_resp.data or []) if row.get("equipment_id")}
            )
        if total_equipment:
            sentinel_equipment_baseline_coverage_percent.labels(site_id=SITE_ID).set(
                round((baseline_count / total_equipment) * 100, 2)
            )

        transition_resp = (
            client.table("phase_transition_log")
            .select("to_phase, created_at")
            .eq("site_id", SITE_ID)
            .order("created_at", desc=False)
            .execute()
        )
        transitions: list[tuple[datetime, str]] = []
        for row in transition_resp.data or []:
            ts_raw = row.get("created_at")
            phase = str(row.get("to_phase") or "unknown")
            if not ts_raw:
                continue
            transitions.append((datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")), phase))

        def phase_for(ts: datetime) -> str:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            phase = "pre_onboarding"
            for transition_ts, transition_phase in transitions:
                if ts >= transition_ts:
                    phase = transition_phase
                else:
                    break
            return phase

        # Energy phase averages from daily accumulated kWh.
        energy_resp = (
            client.table("energy_consumption_history").select("date,total_kwh").eq("site_id", SITE_ID).execute()
        )
        energy_by_phase: dict[str, list[float]] = {}
        for row in energy_resp.data or []:
            date_raw = row.get("date")
            total_kwh = row.get("total_kwh")
            if date_raw is None or total_kwh is None:
                continue
            day_ts = datetime.fromisoformat(f"{date_raw}T12:00:00+00:00")
            energy_by_phase.setdefault(phase_for(day_ts), []).append(float(total_kwh))
        energy_avg_by_phase = {phase: sum(values) / len(values) for phase, values in energy_by_phase.items() if values}
        shadow_energy_values = [
            value for phase, value in energy_avg_by_phase.items() if phase in {"shadow", "shadow_live"}
        ]
        shadow_energy_avg = sum(shadow_energy_values) / len(shadow_energy_values) if shadow_energy_values else None
        for phase, avg_kwh in energy_avg_by_phase.items():
            sentinel_energy_phase_avg_daily_kwh.labels(site_id=SITE_ID, phase=phase).set(round(avg_kwh, 3))
            if shadow_energy_avg is not None:
                sentinel_energy_phase_delta_from_shadow_kwh.labels(site_id=SITE_ID, phase=phase).set(
                    round(avg_kwh - shadow_energy_avg, 3)
                )

        # Equipment health phase averages from asset health snapshots.
        if site_uuid:
            health_resp = (
                client.table("asset_health_snapshots")
                .select("snapshot_at,health_score")
                .eq("site_id", site_uuid)
                .execute()
            )
            health_by_phase: dict[str, list[float]] = {}
            for row in health_resp.data or []:
                ts_raw = row.get("snapshot_at")
                score = row.get("health_score")
                if ts_raw is None or score is None:
                    continue
                snapshot_ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                health_by_phase.setdefault(phase_for(snapshot_ts), []).append(float(score))
            health_avg_by_phase = {
                phase: sum(values) / len(values) for phase, values in health_by_phase.items() if values
            }
            shadow_health_values = [
                value for phase, value in health_avg_by_phase.items() if phase in {"shadow", "shadow_live"}
            ]
            shadow_health_avg = sum(shadow_health_values) / len(shadow_health_values) if shadow_health_values else None
            for phase, avg_score in health_avg_by_phase.items():
                sentinel_equipment_phase_health_score_avg.labels(site_id=SITE_ID, phase=phase).set(round(avg_score, 3))
                if shadow_health_avg is not None:
                    sentinel_equipment_phase_health_delta_from_shadow.labels(site_id=SITE_ID, phase=phase).set(
                        round(avg_score - shadow_health_avg, 3)
                    )
    except Exception as e:
        logger.debug(f"Discipline metrics: phase baseline comparison failed: {e}")

    # — Measured recommendation energy feedback loop —
    try:
        rec_resp = (
            client.table("recommendations")
            .select(
                "id, site_id, target_equipment, baseline_energy_kwh, actual_energy_kwh, "
                "actual_saving_kwh, actual_saving_zar, executed_at"
            )
            .eq("site_id", SITE_ID)
            .in_("status", ["executed", "auto_executed"])
            .not_.is_("actual_saving_kwh", "null")
            .order("executed_at", desc=True)
            .limit(100)
            .execute()
        )
        for row in rec_resp.data or []:
            labels = {
                "site_id": row.get("site_id") or SITE_ID,
                "recommendation_id": row.get("id") or "unknown",
                "equipment_id": row.get("target_equipment") or "unknown",
            }
            if row.get("baseline_energy_kwh") is not None:
                sentinel_recommendation_baseline_energy_kwh.labels(**labels).set(float(row["baseline_energy_kwh"]))
            if row.get("actual_energy_kwh") is not None:
                sentinel_recommendation_actual_energy_kwh.labels(**labels).set(float(row["actual_energy_kwh"]))
            if row.get("actual_saving_kwh") is not None:
                sentinel_recommendation_actual_saving_kwh.labels(**labels).set(float(row["actual_saving_kwh"]))
            if row.get("actual_saving_zar") is not None:
                sentinel_recommendation_actual_saving_zar.labels(**labels).set(float(row["actual_saving_zar"]))
    except Exception as e:
        logger.debug(f"Discipline metrics: recommendation energy feedback query failed: {e}")

    # — ESG: renewable %, energy intensity, water intensity, waste —
    try:
        site_resp = client.table("sites").select("sqm").eq("code", SITE_ID).limit(1).execute()
        sqm = float(site_resp.data[0]["sqm"]) if site_resp.data and site_resp.data[0].get("sqm") else 4500.0

        # Latest total_kw for intensity
        esg_kwh = float(latest.get("total_kw", 0))

        # Water from consumption sensor
        water_l = 0
        water_resp = (
            client.table("equipment_sensor_readings")
            .select("value")
            .eq("site_id", SITE_ID)
            .eq("sensor_type", "total_consumption_m3")
            .order("recorded_at", desc=True)
            .limit(1)
            .execute()
        )
        if water_resp.data:
            water_l = float(water_resp.data[0].get("value", 0) or 0) * 1000  # m3 → L

        # Renewable: solar generation as % of total
        renewable_kw = 0
        solar_resp = (
            client.table("equipment_sensor_readings")
            .select("value")
            .eq("site_id", SITE_ID)
            .eq("sensor_type", "solar_pv_kw")
            .order("recorded_at", desc=True)
            .limit(1)
            .execute()
        )
        if solar_resp.data:
            renewable_kw = float(solar_resp.data[0].get("value", 0) or 0)
        renewable_pct = (renewable_kw / esg_kwh * 100) if esg_kwh > 0 else 0

        sentinel_esg_renewable_percent.labels(site_id=SITE_ID).set(round(renewable_pct, 1))
        sentinel_esg_energy_intensity_kwh_per_sqm.labels(site_id=SITE_ID).set(round(esg_kwh / sqm, 4) if sqm > 0 else 0)
        sentinel_esg_water_intensity_l_per_sqm.labels(site_id=SITE_ID).set(round(water_l / sqm, 4) if sqm > 0 else 0)
        sentinel_esg_waste_kg.labels(site_id=SITE_ID).set(0)
    except Exception as e:
        logger.warning(f"Discipline metrics: ESG calc failed: {e}")

    logger.debug(f"Discipline metrics: collected for site {SITE_ID}")


_site_name_cache: dict[str, str] = {}


def _resolve_site_name(client, site_id: str) -> str:
    """Resolve site UUID to readable name, with caching."""
    if not site_id or site_id == "None":
        return "unknown"
    if site_id in _site_name_cache:
        return _site_name_cache[site_id]
    try:
        resp = client.table("sites").select("name, code").eq("id", site_id).limit(1).execute()
        if resp.data:
            name = resp.data[0].get("code") or resp.data[0].get("name") or site_id
            _site_name_cache[site_id] = name
            return name
    except Exception:
        pass
    _site_name_cache[site_id] = site_id
    return site_id


def _collect_drift_metrics() -> None:
    """Collect ML drift scores by running feature drift detection on each scrape.

    Queries Supabase for each equipment type and computes real KS-statistic drift
    scores. Persists results to drift_detection_log table for trend durability.

    Only emits metrics when both baseline and current windows have >= MIN_SAMPLES
    readings per feature. Below that threshold the KS statistic is statistically
    meaningless and the metric is suppressed (data_sufficient="false").
    """
    import logging

    logger = logging.getLogger("sentinel.metrics")
    # KS test unreliable below this sample count per feature window
    try:
        from ml.monitoring.drift import EQUIPMENT_TO_SENSORS, EQUIPMENT_TYPES

        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
        except Exception:
            client = None

        for eq_type in EQUIPMENT_TYPES:
            try:
                cfg = EQUIPMENT_TO_SENSORS.get(eq_type, {})
                uses_real_data = cfg.get("uses_real_data", False)

                # Synthetic data: emit with source="synthetic", data_quality="sufficient"
                # (seeded distributions always have enough samples — no temporal gate needed)
                if not uses_real_data:
                    score = 0.0  # synthetic fallback score — not real drift
                    sentinel_model_drift_score.labels(
                        model_id=eq_type,
                        model_type=eq_type.upper(),
                        source="synthetic",
                        data_sufficient="true",
                        data_quality="sufficient",
                    ).set(score)
                    sentinel_model_drift_alerts.labels(
                        site_id="site-002",
                        model_type=eq_type.upper(),
                        source="synthetic",
                        data_sufficient="true",
                    ).set(0)
                    sentinel_drift_baseline_hours.labels(
                        model_id=eq_type,
                        site_id="site-002",
                        data_quality="sufficient",
                    ).set(720)  # synthetic baseline is always "old enough"
                    if client is not None:
                        with contextlib.suppress(Exception):
                            client.table("drift_detection_log").insert(
                                {
                                    "equipment_type": eq_type,
                                    "drift_detected": False,
                                    "features_checked": 0,
                                    "features_drifted": 0,
                                    "score": score,
                                    "source": "synthetic",
                                }
                            ).execute()
                    continue

                # Real Supabase data path: query baseline timespan directly from sensor data
                cfg_equipment_ids = cfg.get("equipment_ids", [])
                cfg_features = cfg.get("features", [])
                baseline_span_seconds = 0.0

                if client is not None and cfg_equipment_ids and cfg_features:
                    try:
                        min_resp = (
                            client.table("equipment_sensor_readings")
                            .select("recorded_at")
                            .in_("equipment_id", cfg_equipment_ids)
                            .in_("sensor_type", cfg_features)
                            .order("recorded_at", desc=False)
                            .limit(1)
                            .execute()
                        )
                        if min_resp.data:
                            oldest = datetime.fromisoformat(min_resp.data[0]["recorded_at"].replace("Z", "+00:00"))
                            baseline_span_seconds = (datetime.now(UTC) - oldest).total_seconds()
                    except Exception:
                        pass

                # Run drift detection
                from ml.monitoring.drift import get_drift_detector

                detector = get_drift_detector()
                try:
                    result = detector.detect_feature_drift(eq_type)
                except Exception as exc:
                    logger.debug(f"DriftDetector failed for {eq_type}: {exc}")
                    continue

                features_checked = result.get("features_checked", 0) or 0
                features_drifted = result.get("features_drifted", 0) or 0
                score = features_drifted / features_checked if features_checked > 0 else 0.0

                # Two-tier gate: check temporal span, not just sample count
                data_quality, data_sufficient = _assess_drift_data_sufficiency(baseline_span_seconds, features_checked)

                sentinel_model_drift_score.labels(
                    model_id=eq_type,
                    model_type=eq_type.upper(),
                    source="supabase",
                    data_sufficient=data_sufficient,
                    data_quality=data_quality,
                ).set(score)
                sentinel_model_drift_alerts.labels(
                    site_id="site-002",
                    model_type=eq_type.upper(),
                    source="supabase",
                    data_sufficient=data_sufficient,
                ).set(1 if result.get("drift_detected") and data_sufficient == "true" else 0)
                sentinel_drift_baseline_hours.labels(
                    model_id=eq_type,
                    site_id="site-002",
                    data_quality=data_quality,
                ).set(round(baseline_span_seconds / 3600, 2))

                if client is not None:
                    try:
                        client.table("drift_detection_log").insert(
                            {
                                "equipment_type": eq_type,
                                "drift_detected": result.get("drift_detected", False),
                                "features_checked": features_checked,
                                "features_drifted": features_drifted,
                                "score": score,
                                "source": "supabase",
                            }
                        ).execute()
                    except Exception as insert_err:
                        logger.debug(f"Drift log insert failed for {eq_type}: {insert_err}")

                # Phase 241 Plan 1: enqueue retraining at the producer when real
                # drift is written. Feature drift invalidates both trainable model
                # families; enqueue() dedupes and rate-limits, and must never
                # break metric collection.
                if result.get("drift_detected") and data_sufficient == "true":
                    try:
                        from app.ml.models.retraining_queue import enqueue as enqueue_retraining

                        for queue_model_type in ("lstm", "autoencoder"):
                            enqueue_retraining(
                                site_id="site-002",
                                equipment_type=eq_type,
                                model_type=queue_model_type,
                                trigger_reason="drift_detected",
                                drift_verdict="DRIFT_DETECTED",
                            )
                    except Exception as enqueue_err:
                        logger.warning(f"Retraining enqueue failed for {eq_type}: {enqueue_err}")
            except Exception as exc:
                logger.debug(f"Drift metric failed for {eq_type}: {exc}")
    except Exception as e:
        logger.debug(f"Drift metrics collection failed: {e}")


def _collect_fm_metrics() -> None:
    """Collect FM metrics from Supabase for the media wall dashboard.

    Called on each /metrics scrape to provide fresh data.
    Gauges are reset and re-populated from live database queries.
    """
    import logging

    logger = logging.getLogger("sentinel.metrics")

    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        if not client:
            return
    except Exception:
        return

    # --- Alerts by severity and building ---
    try:
        alerts_resp = client.table("alerts").select("severity, site_id").eq("status", "active").execute()
        # Reset alert gauges
        sentinel_alerts._metrics.clear()

        if alerts_resp.data:
            # Count by severity and building
            alert_counts: dict[tuple[str, str], int] = {}
            for alert in alerts_resp.data:
                sev = alert.get("severity", "info")
                building = _resolve_site_name(client, alert.get("site_id", ""))
                key = (sev, building)
                alert_counts[key] = alert_counts.get(key, 0) + 1

            for (sev, building), count in alert_counts.items():
                sentinel_alerts.labels(severity=sev, building=building, status="active").set(count)
    except Exception as e:
        logger.debug(f"FM metrics: alerts query failed: {e}")

    # --- Equipment health ---
    try:
        equip_resp = client.table("equipment").select("code, name, health_score, site_id, status").execute()
        sentinel_equipment_health._metrics.clear()
        sentinel_equipment_issues._metrics.clear()

        if equip_resp.data:
            building_degrading: dict[str, int] = {}
            for eq in equip_resp.data:
                health = eq.get("health_score")
                if health is None:
                    continue
                code = eq.get("code", "unknown")
                # Skip lighting (LTG) and DALI controllers — no meaningful health metric
                if code.startswith(("S002-LTG-", "S002-DALI-")):
                    continue
                site = _resolve_site_name(client, eq.get("site_id", ""))
                code = eq.get("code", "unknown")
                status = eq.get("status", "unknown")

                if health < 50:
                    state = "critical"
                elif health < 75:
                    state = "degrading"
                    building_degrading[site] = building_degrading.get(site, 0) + 1
                else:
                    state = "healthy"

                sentinel_equipment_health.labels(building=site, equipment=code, health=state).set(health)

                # Populate issues table for degrading/critical
                if state in ("critical", "degrading"):
                    issue_text = f"Health score {health}% — {status}"
                    sentinel_equipment_issues.labels(
                        building=site,
                        equipment=code,
                        issue=issue_text,
                        severity="critical" if state == "critical" else "warning",
                    ).set(1)
    except Exception as e:
        logger.debug(f"FM metrics: equipment query failed: {e}")

    # --- Work orders (job cards) ---
    try:
        wo_resp = client.table("work_orders").select("site_id, status, priority, created_at, completed_at").execute()
        sentinel_job_cards._metrics.clear()
        sentinel_sla_met._metrics.clear()
        sentinel_maintenance_backlog_days._metrics.clear()

        if wo_resp.data:
            # Count by building + status
            wo_counts: dict[tuple[str, str], int] = {}
            completed_by_building: dict[str, int] = {}
            sla_met_by_building: dict[str, int] = {}
            open_by_building: dict[str, int] = {}

            for wo in wo_resp.data:
                site = _resolve_site_name(client, wo.get("site_id", ""))
                status = wo.get("status", "open")
                wo_counts[(site, status)] = wo_counts.get((site, status), 0) + 1

                if status == "completed":
                    completed_by_building[site] = completed_by_building.get(site, 0) + 1
                    # SLA: completed within 48h = met
                    created = wo.get("created_at")
                    completed = wo.get("completed_at")
                    if created and completed:
                        try:
                            from datetime import datetime as dt

                            c = dt.fromisoformat(created.replace("Z", "+00:00"))
                            d = dt.fromisoformat(completed.replace("Z", "+00:00"))
                            if (d - c).total_seconds() < 172800:  # 48h
                                sla_met_by_building[site] = sla_met_by_building.get(site, 0) + 1
                        except Exception:
                            pass
                elif status in ("open", "in_progress", "assigned"):
                    open_by_building[site] = open_by_building.get(site, 0) + 1

            for (site, status), count in wo_counts.items():
                outcome = "first_fix" if status == "completed" else "pending"
                sentinel_job_cards.labels(building=site, status=status, outcome=outcome).set(count)

            for site, count in sla_met_by_building.items():
                sentinel_sla_met.labels(building=site).set(count)

            # Backlog = open work orders (rough proxy for days)
            for site, count in open_by_building.items():
                sentinel_maintenance_backlog_days.labels(building=site).set(count)
    except Exception as e:
        logger.debug(f"FM metrics: work orders query failed: {e}")


# ---------------------------------------------------------------------------
# DDMP / Demand Response metrics collection (Phase 211)
# ---------------------------------------------------------------------------


def _collect_ddmp_metrics() -> None:
    """Collect Demand Response / DDMP metrics from latest API calculations.

    This function queries the latest demand response calculations from Supabase
    and exposes them as Prometheus metrics for IES/LTM integration dashboards.
    """
    import logging

    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        logger = logging.getLogger("sentinel.metrics")

        # Get latest demand response calculation per site
        resp = (
            client.table("demand_response_calculations")
            .select(
                "site_id, curtailable_load_kw, safe_duration_minutes, confidence, "
                "ddmp_eligible, data_freshness_seconds, thermal_runway_minutes, "
                "zone_coverage_percent, bess_soc_pct, limiting_factor, calculated_at"
            )
            .order("calculated_at", desc=True)
            .limit(100)
            .execute()
        )

        logger.info(f"DDMP metrics: query returned {len(resp.data) if resp.data else 0} rows")

        if resp.data:
            # Track which sites we've seen (to only take latest per site)
            seen_sites = set()

            for calc in resp.data:
                site_id = calc.get("site_id", "unknown")

                # Skip if we already have a newer entry for this site
                if site_id in seen_sites:
                    continue
                seen_sites.add(site_id)

                # Set metrics with safe defaults
                sentinel_curtailable_load_kw.labels(
                    site_id=site_id,
                    customer="sentinel-internal",  # Will be overridden per customer
                ).set(calc.get("curtailable_load_kw", 0))

                sentinel_safe_duration_minutes.labels(site_id=site_id).set(calc.get("safe_duration_minutes", 0))

                sentinel_confidence_score.labels(site_id=site_id).set(calc.get("confidence", 0))

                sentinel_ddmp_eligible.labels(site_id=site_id).set(1 if calc.get("ddmp_eligible", False) else 0)

                sentinel_data_freshness_seconds.labels(site_id=site_id).set(calc.get("data_freshness_seconds", 9999))

                sentinel_thermal_runway_minutes.labels(site_id=site_id).set(calc.get("thermal_runway_minutes", 0))

                sentinel_zone_coverage_percent.labels(site_id=site_id).set(calc.get("zone_coverage_percent", 0))

                # BESS SOC if available
                bess_soc = calc.get("bess_soc_pct")
                if bess_soc is not None:
                    sentinel_bess_soc_percent.labels(site_id=site_id, battery_id="primary").set(bess_soc)

            logger.info(f"DDMP metrics: collected for {len(seen_sites)} sites: {seen_sites}")
        else:
            logger.info("DDMP metrics: no data found in table")

    except Exception as e:
        # Fail silently - metrics collection should never break the endpoint
        logging.getLogger("sentinel.metrics").warning(f"DDMP metrics collection failed: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Static info set once at import time
# ---------------------------------------------------------------------------
_MODE = os.getenv("SENTINEL_MODE", settings.resolved_ingestion_mode.value)
_VERSION = os.getenv("APP_VERSION", settings.app_version)
_BUILD_DATE = os.getenv("BUILD_DATE", datetime.now(UTC).strftime("%Y-%m-%d"))

sentinel_info.info(
    {
        "version": _VERSION,
        "mode": _MODE,
        "build_date": _BUILD_DATE,
        "config_checksum": settings.config_checksum,
    }
)

# ---------------------------------------------------------------------------
# IP allowlist — restrict /metrics to local / Docker networks
# ---------------------------------------------------------------------------
_ALLOWED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # localhost
    ipaddress.ip_network("10.0.0.0/8"),  # Docker default bridge / overlay
    ipaddress.ip_network("172.16.0.0/12"),  # Docker bridge range
    ipaddress.ip_network("192.168.0.0/16"),  # Private LAN
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
]

# Allow override via env var (comma-separated CIDRs)
_EXTRA_CIDRS = os.getenv("METRICS_ALLOWED_CIDRS", "")
if _EXTRA_CIDRS:
    for cidr in _EXTRA_CIDRS.split(","):
        cidr = cidr.strip()
        if cidr:
            _ALLOWED_NETWORKS.append(ipaddress.ip_network(cidr, strict=False))


def _is_allowed(client_ip: str) -> bool:
    """Return True if client IP is in the allowlist."""
    try:
        addr = ipaddress.ip_address(client_ip)
        return any(addr in net for net in _ALLOWED_NETWORKS)
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
async def _metrics_bearer_auth(request: Request) -> AuthContext:
    """Accept METRICS_BEARER_TOKEN as valid Bearer auth for Prometheus scraping.

    This lets Prometheus scrape with: Authorization: Bearer <METRICS_BEARER_TOKEN>
    while still supporting Supabase JWT tokens for browser/API access.
    """
    import hmac

    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if settings.metrics_bearer_token and hmac.compare_digest(token, settings.metrics_bearer_token):
            source_ip = request.headers.get("x-forwarded-for", "unknown")
            return AuthContext(
                user_id="prometheus",
                role=SentinelRole.ADMIN,
                auth_method="metrics_bearer",
                source_ip=source_ip.split(",")[0].strip(),
            )
    # Fall back to Supabase JWT auth
    return await require_auth(AuthLevel.AUTHENTICATED)(request)


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    tags=["monitoring"],
    summary="Prometheus metrics endpoint",
    description="Returns AI governance metrics in Prometheus text exposition format.",
)
async def prometheus_metrics(
    request: Request,
    auth: AuthContext = Depends(_metrics_bearer_auth),
) -> PlainTextResponse:
    """Serve Prometheus-format metrics.

    Accepts METRICS_BEARER_TOKEN (Bearer) for Prometheus,
    or Supabase JWT tokens for browser/API access.
    """
    # Signal health to Prometheus/Grafana scraper
    sentinel_backend_up.set(1)
    sentinel_metrics_last_updated_timestamp.labels(job="sentinel-governance").set(int(datetime.now(UTC).timestamp()))

    # Collect live FM metrics from Supabase (media wall dashboard)
    try:
        _collect_fm_metrics()
    except Exception:
        pass  # Never let metrics collection crash the endpoint

    # Collect ML drift scores from Supabase sensor data (real drift detection)
    try:
        _collect_drift_metrics()
    except Exception:
        pass  # Never let metrics collection crash the endpoint

    # Collect DDMP / Demand Response metrics (Phase 211 — IES/LTM integration)
    try:
        _collect_ddmp_metrics()
    except Exception:
        pass  # Never let metrics collection crash the endpoint

    # Collect HVAC/Energy/Lighting/Water/Security discipline metrics from bridge sensor data
    try:
        _collect_discipline_metrics()
    except Exception:
        pass  # Never let metrics collection crash the endpoint

    # Generate Prometheus text exposition
    output = generate_latest(REGISTRY)
    return PlainTextResponse(
        content=output.decode("utf-8"),
        status_code=200,
        media_type=CONTENT_TYPE_LATEST,
    )
