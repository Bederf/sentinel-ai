"""
Analytics API router registrar.

Registers routers for AI/ML, predictions, diagnostics, and analytics.
"""

from fastapi import FastAPI

from app.api import (
    agent_memory,
    chat,
    classification,
    dashboard_generator,
    data_quality,
    diagnosis,
    dispatch_optimizer,
    energy,
    equipment_lookup,
    features,
    fleet_learning,
    hybrid_chat,
    load_forecast,
    local_chat,
    mcp,
    mcp_openai,
    mcp_sse,
    ml_feedback,
    ml_predictions,
    ml_retraining,
    mlops,
    ocr,
    optimization,
    optimization_quality,
    peak_demand,
    predictions,
    rag,
    recommendations,
    repair_effectiveness,
    sensor_analysis,
    solar,
    solar_arbitrage,
    solar_config,
    solar_grid,
    solar_performance,
    survival,
    technical,
    timeseries,
    vision,
)
from app.config.settings import settings


def register_analytics_routers(app: FastAPI) -> None:
    """Register analytics API routers (AI/ML, predictions, diagnostics)."""
    # Chat and AI
    app.include_router(chat.router, prefix="/api", tags=["chat"])
    app.include_router(hybrid_chat.router, tags=["hybrid-chat"])
    app.include_router(local_chat.router, prefix="/api", tags=["local-chat"])

    # Predictions and optimization
    app.include_router(predictions.router, prefix="/api", tags=["predictions"])
    app.include_router(optimization.router, prefix="/api", tags=["optimization"])
    app.include_router(energy.router, prefix="/api", tags=["energy"])
    app.include_router(ml_predictions.router)
    app.include_router(recommendations.router, tags=["recommendations"])
    app.include_router(optimization_quality.router, prefix="/api/optimization", tags=["optimization-quality"])
    # Equipment lookup and diagnostics
    app.include_router(equipment_lookup.router, prefix="/api", tags=["equipment-lookup"])
    app.include_router(technical.router, tags=["technical"])
    app.include_router(diagnosis.router, prefix="/api", tags=["diagnosis"])
    app.include_router(vision.router, prefix="/api", tags=["vision"])
    app.include_router(ocr.router, prefix="/api", tags=["ocr"])

    # Time series and data quality
    app.include_router(timeseries.router)
    app.include_router(sensor_analysis.router)
    app.include_router(features.router)
    app.include_router(data_quality.router)

    # ML analytics
    app.include_router(survival.router)
    app.include_router(classification.router, prefix="/api/classification", tags=["classification"])
    app.include_router(ml_feedback.router, tags=["ml-feedback"])
    app.include_router(repair_effectiveness.router, tags=["repair-effectiveness"])

    # ML operations
    app.include_router(rag.router, tags=["rag"])
    app.include_router(ml_retraining.router, tags=["ml-retraining"])
    app.include_router(fleet_learning.router, tags=["fleet-learning"])
    app.include_router(mlops.router, tags=["mlops"])

    # Solar & BESS
    app.include_router(solar.router, prefix="/api", tags=["solar"])
    app.include_router(solar_config.router, tags=["solar-config"])
    app.include_router(solar_grid.router, prefix="/api", tags=["solar-grid"])
    app.include_router(solar_performance.router, prefix="/api", tags=["solar-performance"])
    app.include_router(solar_arbitrage.router, prefix="/api", tags=["solar-arbitrage"])
    # Load Forecast & Dispatch Optimizer (v26.0: MIP-optimized BESS dispatch)
    app.include_router(load_forecast.router, tags=["load-forecast"])
    app.include_router(dispatch_optimizer.router, tags=["dispatch-optimizer"])

    # Peak Demand Management (Phase 081: Cross-module coordination)
    app.include_router(peak_demand.router, tags=["peak-demand"])

    # MCP (Model Context Protocol) for AI tool integration
    app.include_router(mcp.router, tags=["mcp"])
    app.include_router(mcp_sse.router, tags=["mcp-sse"])
    app.include_router(mcp_openai.router, tags=["mcp-openai"])
    app.include_router(mcp_openai.wellknown_router, tags=["mcp-discovery"])

    # Agent Memory (persistent conversational memory for AI agents)
    app.include_router(agent_memory.router, tags=["agent-memory"])

    # Dashboard Generator (Phase 141: auto-dashboard from equipment discovery)
    app.include_router(dashboard_generator.router, tags=["dashboard-generator"])

    # RLM Runner orchestration (Phase 113 — feature-gated)
    if settings.rlm_runner_enabled:
        from app.api import rlm_orchestration

        app.include_router(rlm_orchestration.router, tags=["rlm"])
