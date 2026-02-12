"""
Analytics API router registrar.

Registers routers for AI/ML, predictions, diagnostics, and analytics.
"""

from fastapi import FastAPI

from app.api import chat, hybrid_chat, local_chat
from app.api import predictions, optimization, energy, ml_predictions
from app.api import equipment_lookup, diagnosis, vision, ocr
from app.api import timeseries, sensor_analysis, features, data_quality
from app.api import survival, classification, ml_feedback, repair_effectiveness
from app.api import rag, ml_retraining, fleet_learning, mlops
from app.api import mcp, mcp_sse, mcp_openai
from app.api import recommendations, simulation_analytics
from app.api import system_health, solar, solar_grid, solar_performance, solar_arbitrage
from app.api import peak_demand


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
    app.include_router(simulation_analytics.router, tags=["simulation-analytics"])

    # Equipment lookup and diagnostics
    app.include_router(equipment_lookup.router, prefix="/api", tags=["equipment-lookup"])
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

    # System Health & Diagnostics
    app.include_router(system_health.router, tags=["system-health"])

    # Solar & BESS
    app.include_router(solar.router, prefix="/api", tags=["solar"])
    app.include_router(solar_grid.router, prefix="/api", tags=["solar-grid"])
    app.include_router(solar_performance.router, prefix="/api", tags=["solar-performance"])
    app.include_router(solar_arbitrage.router, prefix="/api", tags=["solar-arbitrage"])

    # Peak Demand Management (Phase 081: Cross-module coordination)
    app.include_router(peak_demand.router, tags=["peak-demand"])

    # MCP (Model Context Protocol) for AI tool integration
    app.include_router(mcp.router, tags=["mcp"])
    app.include_router(mcp_sse.router, tags=["mcp-sse"])
    app.include_router(mcp_openai.router, tags=["mcp-openai"])
    app.include_router(mcp_openai.wellknown_router, tags=["mcp-discovery"])
