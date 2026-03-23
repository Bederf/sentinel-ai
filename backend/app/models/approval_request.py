"""
Request and response models for approval endpoint.

Phase 170-02: Control Actuation Loop
"""

from pydantic import BaseModel


class ApprovalRequest(BaseModel):
    """Request to approve and execute a decision."""

    decision_id: str
    approval_outcome: str  # "approved" | "rejected"


class ApprovalResponse(BaseModel):
    """Response from approval execution endpoint."""

    status: str  # "ACCEPTED"
    decision_id: str
    correlation_id: str
    message: str
    estimated_verification_time_seconds: int
