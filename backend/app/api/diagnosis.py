"""
Diagnosis Flow API Endpoints

Provides REST API for guided diagnosis conversations:
- POST /api/diagnosis/start - Start new diagnosis session
- POST /api/diagnosis/respond - Process technician response
- GET /api/diagnosis/{session_id} - Get current flow state
- DELETE /api/diagnosis/{session_id} - End diagnosis session
"""

import uuid
import logging
from typing import Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException

from app.services.technician_chat import get_diagnosis_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


# Request/Response Models

class StartDiagnosisRequest(BaseModel):
    """Request to start a new diagnosis session"""
    query: str = Field(..., description="Initial problem description")
    session_id: Optional[str] = Field(None, description="Optional session ID (auto-generated if not provided)")


class StartDiagnosisResponse(BaseModel):
    """Response from starting diagnosis"""
    session_id: str
    type: str
    state: str
    message: str
    questions: Optional[list] = None
    check: Optional[dict] = None
    progress: Optional[dict] = None


class RespondRequest(BaseModel):
    """Request to respond to a checkpoint"""
    session_id: str = Field(..., description="Session ID")
    step_id: str = Field(..., description="ID of the step being answered")
    response: str = Field(..., description="Technician's response")


class FlowStateResponse(BaseModel):
    """Current state of a diagnosis flow"""
    session_id: str
    state: str
    equipment: dict
    fault_code: Optional[str]
    current_step_index: int
    checkpoints: list
    created_at: str
    updated_at: str


# API Endpoints

@router.post("/start", response_model=dict)
async def start_diagnosis(request: StartDiagnosisRequest):
    """
    Start a new guided diagnosis session.

    Takes an initial problem description and returns:
    - Session ID for tracking the conversation
    - First set of questions to identify the equipment/fault
    - Current diagnosis state

    Example:
        POST /api/diagnosis/start
        {"query": "Carrier chiller showing E4 fault"}
    """
    engine = get_diagnosis_engine()

    # Generate session ID if not provided
    session_id = request.session_id or f"diag-{uuid.uuid4().hex[:8]}"

    try:
        result = engine.start_diagnosis(session_id, request.query)
        return result
    except Exception as e:
        logger.error(f"Failed to start diagnosis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/respond", response_model=dict)
async def process_response(request: RespondRequest):
    """
    Process technician's response to a checkpoint question.

    Returns:
    - Next checkpoint question, OR
    - Analysis results, OR
    - Resolution plan

    Example:
        POST /api/diagnosis/respond
        {"session_id": "diag-abc123", "step_id": "oil_level", "response": "1/4 or less"}
    """
    engine = get_diagnosis_engine()

    try:
        result = engine.process_response(
            session_id=request.session_id,
            step_id=request.step_id,
            response=request.response
        )

        if result.get("error"):
            raise HTTPException(status_code=404, detail=result.get("message"))

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process response: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}", response_model=dict)
async def get_flow_state(session_id: str):
    """
    Get current state of a diagnosis session.

    Returns the full flow state including:
    - Equipment info
    - Fault code
    - All checkpoints with responses
    - Current diagnosis state

    Example:
        GET /api/diagnosis/diag-abc123
    """
    engine = get_diagnosis_engine()

    flow_state = engine.get_flow_state(session_id)
    if not flow_state:
        raise HTTPException(
            status_code=404,
            detail=f"Diagnosis session not found: {session_id}"
        )

    return flow_state


@router.delete("/{session_id}", response_model=dict)
async def end_diagnosis(session_id: str):
    """
    End a diagnosis session and get summary.

    Returns a summary of the completed diagnosis including:
    - Equipment identified
    - Checkpoints completed
    - Total duration

    Example:
        DELETE /api/diagnosis/diag-abc123
    """
    engine = get_diagnosis_engine()

    try:
        summary = engine.end_diagnosis(session_id)
        if summary.get("error"):
            raise HTTPException(status_code=404, detail=summary.get("message"))
        return summary
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to end diagnosis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/checklists/{fault_code}", response_model=dict)
async def get_fault_checklist(fault_code: str):
    """
    Get the diagnostic checklist for a specific fault code.

    Returns the predefined checklist questions for the fault code,
    or the default checklist if fault code is unknown.

    Example:
        GET /api/diagnosis/checklists/E4
    """
    engine = get_diagnosis_engine()

    fault_code_upper = fault_code.upper()
    checklist = engine.FAULT_CHECKLISTS.get(
        fault_code_upper,
        engine.DEFAULT_CHECKLIST
    )

    return {
        "fault_code": fault_code_upper,
        "checklist": checklist,
        "is_default": fault_code_upper not in engine.FAULT_CHECKLISTS,
        "total_steps": len(checklist)
    }
