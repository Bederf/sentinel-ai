"""Pydantic models for approval workflow API requests and responses."""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class ApprovalRequest(BaseModel):
    """Request to approve a recommendation."""

    approved_by: str = Field(..., description="User ID or name of person approving", min_length=1, max_length=255)
    approval_notes: Optional[str] = Field(None, description="Optional notes about the approval", max_length=500)

    class Config:
        json_schema_extra = {
            "example": {"approved_by": "technician@site-002", "approval_notes": "Peak demand response - urgent"}
        }


class RejectionRequest(BaseModel):
    """Request to reject a recommendation."""

    rejected_by: str = Field(..., description="User ID or name of person rejecting", min_length=1, max_length=255)
    reason: str = Field(..., description="Reason for rejection", min_length=1, max_length=500)

    class Config:
        json_schema_extra = {
            "example": {"rejected_by": "supervisor@site-002", "reason": "Conflicting with scheduled maintenance"}
        }


class ApprovalResponse(BaseModel):
    """Response from approval action."""

    success: bool = Field(..., description="Whether approval was successful")
    recommendation_id: str = Field(..., description="ID of the recommendation")
    status: str = Field(..., description="Result status: approved, rejected, executed, or failed")
    executed_at: Optional[datetime] = Field(None, description="Timestamp when approved action was executed")
    error_message: Optional[str] = Field(None, description="Error message if approval failed")
    cov_verified: bool = Field(False, description="Whether COV feedback verified the device change")
    execution_result: Optional[Dict[str, Any]] = Field(None, description="Detailed execution result data")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "recommendation_id": "rec-123",
                "status": "executed",
                "executed_at": "2026-02-12T14:32:01Z",
                "error_message": None,
                "cov_verified": True,
                "execution_result": {
                    "success": True,
                    "device_write": {"success": True},
                    "cov_verified": True,
                    "timestamp": "2026-02-12T14:32:01Z",
                },
            }
        }


class ApprovalStatus(BaseModel):
    """Current approval status of a recommendation."""

    recommendation_id: str = Field(..., description="ID of the recommendation")
    approval_status: str = Field(..., description="Current status: pending, approved, rejected, executed, or failed")
    approved_by: Optional[str] = Field(None, description="User who approved/rejected")
    approved_at: Optional[datetime] = Field(None, description="When the approval action was taken")
    executed_at: Optional[datetime] = Field(None, description="When the approved action was executed")
    rejection_reason: Optional[str] = Field(None, description="If rejected, the reason why")

    class Config:
        json_schema_extra = {
            "example": {
                "recommendation_id": "rec-123",
                "approval_status": "executed",
                "approved_by": "technician@site-002",
                "approved_at": "2026-02-12T14:30:00Z",
                "executed_at": "2026-02-12T14:32:01Z",
                "rejection_reason": None,
            }
        }
