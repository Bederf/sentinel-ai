"""Local LLM Chat API - conversational interface for ML predictions.

Phase 44-03: Routes queries through intent classification and local Ollama LLM.
Provides natural language access to equipment health, predictions, maintenance,
and anomaly data without requiring paid API calls.
"""

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.query_handler import get_query_handler

logger = logging.getLogger(__name__)

router = APIRouter()


class LocalChatRequest(BaseModel):
    """Request model for local chat endpoint."""
    message: str
    site_id: str | None = None


class LocalChatResponse(BaseModel):
    """Response model for local chat endpoint."""
    response: str
    intent: str
    confidence: float
    equipment_ids: list[str]
    equipment_type: str | None = None
    model_used: str | None = None
    llm_available: bool


@router.post("/chat/local", response_model=LocalChatResponse)
async def local_chat(request: LocalChatRequest):
    """Query ML predictions and equipment data using natural language.

    Routes queries through intent classification to the appropriate service
    (RAG, ExplanationService, MaintenanceRecommender) and generates responses
    via local Ollama LLM.

    Supported query types:
    - "Why is S002-CHILLER-B1-001 predicted to fail?" (prediction explanation)
    - "When is maintenance due for the AHU?" (maintenance recommendation)
    - "Compare S002-CHILLER-B1-001 vs S002-CHILLER-B1-002" (equipment comparison)
    - "Show trends for S002-FCU-L1-A" (trend analysis)
    - "What's the anomaly on S002-PUMP-B1-CHW1?" (anomaly explanation)
    - "What's the status of S002-AHU-L2-001?" (equipment status)
    """
    handler = get_query_handler()
    result = await handler.handle_query(request.message)

    return LocalChatResponse(
        response=result["response"],
        intent=result["intent"],
        confidence=result["confidence"],
        equipment_ids=result["equipment_ids"],
        equipment_type=result.get("equipment_type"),
        model_used=result.get("model_used"),
        llm_available=result.get("llm_available", False),
    )


@router.post("/chat/local/stream")
async def local_chat_stream(request: LocalChatRequest):
    """Stream local chat response via Server-Sent Events.

    Same as /chat/local but with SSE streaming for real-time UI updates.
    """
    handler = get_query_handler()

    async def generate() -> AsyncGenerator[str, None]:
        try:
            result = await handler.handle_query(request.message)

            # Send metadata first
            metadata = {
                "type": "metadata",
                "intent": result["intent"],
                "confidence": result["confidence"],
                "equipment_ids": result["equipment_ids"],
                "model_used": result.get("model_used"),
            }
            yield f"data: {json.dumps(metadata)}\n\n"

            # Stream response in chunks for smoother UI
            response_text = result["response"]
            chunk_size = 50
            for i in range(0, len(response_text), chunk_size):
                chunk = response_text[i:i + chunk_size]
                yield f"data: {json.dumps({'type': 'content', 'text': chunk})}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error("Local chat stream error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/local/intents")
async def list_intents():
    """List supported query intents with example queries."""
    return {
        "intents": [
            {
                "intent": "why_prediction",
                "description": "Explain why a prediction was made",
                "examples": [
                    "Why is S002-CHILLER-B1-001 predicted to fail?",
                    "What caused the health score drop on the AHU?",
                    "Explain the prediction for S002-FCU-L1-A",
                ],
            },
            {
                "intent": "maintenance_due",
                "description": "Check maintenance schedules and recommendations",
                "examples": [
                    "When is maintenance due for S002-CHILLER-B1-001?",
                    "Does the pump need service?",
                    "How long will S002-AHU-L2-001 last?",
                ],
            },
            {
                "intent": "compare_equipment",
                "description": "Compare two pieces of equipment",
                "examples": [
                    "Compare S002-CHILLER-B1-001 vs S002-CHILLER-B1-002",
                    "Which chiller is healthier?",
                ],
            },
            {
                "intent": "show_trends",
                "description": "View equipment performance trends",
                "examples": [
                    "Show trends for S002-CHILLER-B1-001 over the last 7 days",
                    "How has the AHU performed this month?",
                ],
            },
            {
                "intent": "explain_anomaly",
                "description": "Explain unusual equipment behavior",
                "examples": [
                    "What's the anomaly on S002-PUMP-B1-CHW1?",
                    "Why is there a spike in chiller vibration?",
                ],
            },
            {
                "intent": "equipment_status",
                "description": "Check current equipment status and health",
                "examples": [
                    "What's the status of S002-AHU-L2-001?",
                    "How is the chiller doing?",
                    "Health score for S002-FCU-L1-A",
                ],
            },
        ],
    }
