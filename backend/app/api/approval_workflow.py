"""Approval workflow for parts orders."""

import os
import asyncio
import logging
from typing import List, Optional
from enum import Enum
from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.middleware.auth_middleware import require_auth
from app.models.auth import AuthContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/approval", tags=["approval_workflow"])


class ApprovalStatus(str, Enum):
    """Approval status enum."""

    PENDING = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalRequest(BaseModel):
    """Approval request model."""

    order_id: str
    requester_id: str
    amount: float
    items: List[dict]
    justification: str
    site_id: Optional[str] = None


class ApprovalResponse(BaseModel):
    """Approval response model."""

    order_id: str
    status: ApprovalStatus
    approver_id: Optional[str] = None
    approval_timestamp: Optional[datetime] = None
    rejection_reason: Optional[str] = None


class NotificationService:
    """Service for sending notifications."""

    def __init__(self):
        """Initialize notification service with SMTP configuration."""
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.frontend_url = os.getenv("FRONTEND_URL", "http://localhost:9096")
        self.enabled = bool(self.smtp_user)

    async def send_approval_email(self, approval: ApprovalRequest, approvers: List[str]) -> None:
        """Send approval request email to supervisors."""
        if not self.enabled:
            logger.info(f"Email notifications disabled. Would send to: {approvers}")
            return

        for approver in approvers:
            try:
                message = self._create_approval_message(approval, approver)
                await self._send_email(message)
                logger.info(f"Approval email sent to {approver}")
            except Exception as e:
                logger.error(f"Failed to send approval email to {approver}: {e}")

    def _create_approval_message(self, approval: ApprovalRequest, to_email: str) -> MIMEMultipart:
        """Create approval email message."""
        message = MIMEMultipart("alternative")
        message["From"] = self.smtp_user
        message["To"] = to_email
        message["Subject"] = f"Parts Order Approval Required - R{approval.amount:.2f}"

        # HTML email body
        items_html = "".join(
            [
                f"<li>{item.get('part_name', 'Unknown')} - {item.get('part_number', '')} - R{item.get('unit_price', '0')}</li>"
                for item in approval.items
            ]
        )

        html = f"""
        <html>
          <body style="font-family: Arial, sans-serif;">
            <h2>Parts Order Approval Request</h2>
            <p><strong>Order ID:</strong> {approval.order_id}</p>
            <p><strong>Requested by:</strong> {approval.requester_id}</p>
            <p><strong>Amount:</strong> R{approval.amount:.2f}</p>

            <h3>Items:</h3>
            <ul>
              {items_html}
            </ul>

            <h3>Justification:</h3>
            <p>{approval.justification}</p>

            <h3>Action Required:</h3>
            <p>
              <a href="{self.frontend_url}/orders/{approval.order_id}/approve"
                 style="background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">
                Approve Order
              </a>
              &nbsp;&nbsp;
              <a href="{self.frontend_url}/orders/{approval.order_id}/reject"
                 style="background-color: #f44336; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">
                Reject Order
              </a>
            </p>
          </body>
        </html>
        """

        message.attach(MIMEText(html, "html"))
        return message

    async def _send_email(self, message: MIMEMultipart) -> None:
        """Send email via SMTP (runs in thread pool)."""
        await asyncio.to_thread(self._send_email_sync, message)

    def _send_email_sync(self, message: MIMEMultipart) -> None:
        """Synchronous email sending."""
        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(message)
        except Exception as e:
            logger.error(f"SMTP error: {e}")
            raise

    async def send_approval_notification(self, order_id: str, approver_id: str, status: ApprovalStatus) -> None:
        """Send notification about approval decision."""
        if not self.enabled:
            logger.info(f"Would notify {approver_id} of {status} for order {order_id}")
            return

        try:
            message = MIMEMultipart("alternative")
            message["From"] = self.smtp_user
            message["To"] = approver_id
            message["Subject"] = f"Order {order_id} - {status.value.replace('_', ' ').title()}"

            html = f"""
            <html>
              <body style="font-family: Arial, sans-serif;">
                <h2>Order Approval Confirmation</h2>
                <p><strong>Order ID:</strong> {order_id}</p>
                <p><strong>Status:</strong> {status.value.replace("_", " ").title()}</p>
                <p>The order has been {status.value.replace("_", " ")}.</p>
              </body>
            </html>
            """

            message.attach(MIMEText(html, "html"))
            await self._send_email(message)
            logger.info(f"Notification sent to {approver_id}")
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")


# In-memory storage for approvals
_approvals: dict[str, dict] = {}


class ApprovalWorkflow:
    """Manage approval workflow for parts orders."""

    def __init__(self):
        """Initialize approval workflow."""
        self.notifications = NotificationService()

    async def request_approval(self, order: dict, background_tasks: BackgroundTasks) -> ApprovalRequest:
        """Initiate approval workflow."""
        # Calculate total amount
        amount = sum(
            item.get("quantity", 1) * float(item.get("unit_price", "0").replace("R", "").replace(",", ""))
            for item in order.get("items", [])
        )

        approval = ApprovalRequest(
            order_id=order["id"],
            requester_id=order.get("technician_id", "Unknown"),
            amount=amount,
            items=order.get("items", []),
            justification=order.get("justification", "Urgent repair needed"),
            site_id=order.get("site_id"),
        )

        # Get supervisors
        approvers = await self._get_approvers(order.get("site_id", ""))

        # Send notifications in background
        background_tasks.add_task(self.notifications.send_approval_email, approval, approvers)

        # Store approval request
        _approvals[order["id"]] = {
            "approval": approval,
            "status": ApprovalStatus.PENDING,
            "created_at": datetime.now().isoformat(),
            "approvers": approvers,
        }

        return approval

    async def _get_approvers(self, site_id: str) -> List[str]:
        """Get list of supervisors for site."""
        # TODO: Query database for supervisors at site
        # For now, return placeholder
        return ["supervisor@example.com"]

    async def approve_order(
        self,
        order_id: str,
        approver_id: str,
        background_tasks: BackgroundTasks,
    ) -> ApprovalResponse:
        """Approve order and place with supplier."""
        if order_id not in _approvals:
            raise HTTPException(status_code=404, detail="Order not found")

        approval_data = _approvals[order_id]

        # Update approval status
        approval_data["status"] = ApprovalStatus.APPROVED
        approval_data["approver_id"] = approver_id
        approval_data["approval_timestamp"] = datetime.now().isoformat()

        # Send confirmation notification
        background_tasks.add_task(
            self.notifications.send_approval_notification,
            order_id,
            approver_id,
            ApprovalStatus.APPROVED,
        )

        return ApprovalResponse(
            order_id=order_id,
            status=ApprovalStatus.APPROVED,
            approver_id=approver_id,
            approval_timestamp=datetime.now(),
        )

    async def reject_order(
        self,
        order_id: str,
        approver_id: str,
        reason: str,
        background_tasks: BackgroundTasks,
    ) -> ApprovalResponse:
        """Reject order and notify technician."""
        if order_id not in _approvals:
            raise HTTPException(status_code=404, detail="Order not found")

        approval_data = _approvals[order_id]

        # Update approval status
        approval_data["status"] = ApprovalStatus.REJECTED
        approval_data["approver_id"] = approver_id
        approval_data["rejection_reason"] = reason
        approval_data["approval_timestamp"] = datetime.now().isoformat()

        # Send rejection notification
        background_tasks.add_task(
            self.notifications.send_approval_notification,
            order_id,
            approver_id,
            ApprovalStatus.REJECTED,
        )

        return ApprovalResponse(
            order_id=order_id,
            status=ApprovalStatus.REJECTED,
            approver_id=approver_id,
            approval_timestamp=datetime.now(),
            rejection_reason=reason,
        )


# API Endpoints
_workflow = ApprovalWorkflow()


@router.post("/request/{order_id}")
async def request_approval(
    order_id: str,
    order: dict,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_auth),
) -> ApprovalRequest:
    """Request approval for parts order."""
    try:
        approval = await _workflow.request_approval(order, background_tasks)
        return approval
    except Exception as e:
        logger.error(f"Error requesting approval: {e}")
        raise HTTPException(status_code=500, detail="Failed to request approval")


@router.post("/{order_id}/approve")
async def approve_order(
    order_id: str,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_auth),
) -> ApprovalResponse:
    """Approve parts order."""
    try:
        response = await _workflow.approve_order(order_id, auth.user_id, background_tasks)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving order: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve order")


@router.post("/{order_id}/reject")
async def reject_order(
    order_id: str,
    reason: str,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_auth),
) -> ApprovalResponse:
    """Reject parts order."""
    try:
        response = await _workflow.reject_order(order_id, auth.user_id, reason, background_tasks)
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting order: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject order")


@router.get("/{order_id}/status")
async def get_approval_status(order_id: str, auth: AuthContext = Depends(require_auth)) -> dict:
    """Get approval status for order."""
    if order_id not in _approvals:
        raise HTTPException(status_code=404, detail="Order not found")

    approval_data = _approvals[order_id]
    return {
        "order_id": order_id,
        "status": approval_data["status"].value,
        "created_at": approval_data.get("created_at"),
        "approver_id": approval_data.get("approver_id"),
        "approval_timestamp": approval_data.get("approval_timestamp"),
        "rejection_reason": approval_data.get("rejection_reason"),
    }
