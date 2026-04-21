"""
n8n Workflow Automation Service for SENTINEL.

REST API client for managing n8n workflows from SENTINEL. Makes existing n8n
infrastructure (email intake, contractor dispatch, notifications) visible and
controllable from the dashboard and AI chat.

Configuration via environment variables:
    N8N_API_URL     - API base URL (e.g., http://localhost:5678/api/v1)
    N8N_API_KEY     - API key (generate in n8n Settings -> n8n API)

Optional:
    N8N_TIMEOUT     - Request timeout in seconds (default: 15)
    N8N_WEBHOOK_URL - Webhook base URL if different from API URL
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

import httpx

logger = logging.getLogger("sentinel.n8n")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class N8nConfig:
    api_url: str = ""
    api_key: str = ""
    timeout: int = 15
    webhook_url: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.api_url and self.api_key)

    @property
    def webhook_base(self) -> str:
        """Webhook URL base — often different from API URL."""
        if self.webhook_url:
            return self.webhook_url.rstrip("/")
        # Derive from API URL: http://localhost:5678/api/v1 -> http://localhost:5678/webhook
        base = self.api_url.split("/api/")[0] if "/api/" in self.api_url else self.api_url
        return f"{base.rstrip('/')}/webhook"

    @classmethod
    def from_env(cls) -> "N8nConfig":
        return cls(
            api_url=os.getenv("N8N_API_URL", ""),
            api_key=os.getenv("N8N_API_KEY", ""),
            timeout=int(os.getenv("N8N_TIMEOUT", "15")),
            webhook_url=os.getenv("N8N_WEBHOOK_URL", ""),
        )


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class N8nConnectionStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    CONNECTED = "connected"
    AUTH_FAILED = "auth_failed"
    UNREACHABLE = "unreachable"
    ERROR = "error"


@dataclass
class N8nStatus:
    status: N8nConnectionStatus
    message: str
    version: str | None = None
    active_workflows: int = 0
    total_workflows: int = 0
    failed_24h: int = 0
    last_checked: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "message": self.message,
            "version": self.version,
            "active_workflows": self.active_workflows,
            "total_workflows": self.total_workflows,
            "failed_24h": self.failed_24h,
            "last_checked": self.last_checked,
        }


# ---------------------------------------------------------------------------
# Workflow & Execution Models
# ---------------------------------------------------------------------------


@dataclass
class WorkflowSummary:
    id: str
    name: str
    active: bool
    tags: list[str] = field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "active": self.active,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ExecutionSummary:
    id: str
    workflow_id: str
    workflow_name: str
    status: str  # "success", "error", "waiting", "running"
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error_message": self.error_message,
        }


# ---------------------------------------------------------------------------
# Main Service
# ---------------------------------------------------------------------------


class N8nService:
    """n8n workflow management service for SENTINEL.

    Provides:
        - Health monitoring (active workflows, failed executions)
        - Workflow listing and status
        - Execution history and debugging
        - Webhook triggering for event-driven automation
        - Workflow activation/deactivation for maintenance
    """

    def __init__(self, config: N8nConfig | None = None):
        self._config = config or N8nConfig.from_env()
        self._client: httpx.AsyncClient | None = None
        self._status = N8nStatus(
            status=N8nConnectionStatus.NOT_CONFIGURED,
            message="n8n credentials not configured",
        )

    @property
    def is_configured(self) -> bool:
        return self._config.is_configured

    @property
    def status(self) -> N8nStatus:
        return self._status

    # -------------------------------------------------------------------
    # HTTP Client
    # -------------------------------------------------------------------

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._config.api_url.rstrip("/"),
                headers={
                    "X-N8N-API-KEY": self._config.api_key,
                    "Accept": "application/json",
                },
                timeout=self._config.timeout,
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # -------------------------------------------------------------------
    # Connection & Health Check
    # -------------------------------------------------------------------

    async def check_connection(self) -> N8nStatus:
        """Health check — verifies connectivity and gathers key metrics."""
        if not self._config.is_configured:
            self._status = N8nStatus(
                status=N8nConnectionStatus.NOT_CONFIGURED,
                message="Set N8N_API_URL and N8N_API_KEY to connect.",
            )
            return self._status

        try:
            client = self._get_client()
            wf_response = await client.get("/workflows")

            if wf_response.status_code == 401:
                self._status = N8nStatus(
                    status=N8nConnectionStatus.AUTH_FAILED,
                    message="API key invalid. Regenerate in n8n Settings.",
                    last_checked=datetime.utcnow().isoformat(),
                )
                return self._status

            if wf_response.status_code != 200:
                self._status = N8nStatus(
                    status=N8nConnectionStatus.ERROR,
                    message=f"n8n returned HTTP {wf_response.status_code}",
                    last_checked=datetime.utcnow().isoformat(),
                )
                return self._status

            wf_data = wf_response.json()
            workflows = wf_data.get("data", [])
            active_count = sum(1 for w in workflows if w.get("active"))
            failed_count = await self._count_failed_24h(client)

            self._status = N8nStatus(
                status=N8nConnectionStatus.CONNECTED,
                message=f"{active_count} active workflows, {failed_count} failed (24h)",
                active_workflows=active_count,
                total_workflows=len(workflows),
                failed_24h=failed_count,
                last_checked=datetime.utcnow().isoformat(),
            )
            return self._status

        except httpx.ConnectError:
            self._status = N8nStatus(
                status=N8nConnectionStatus.UNREACHABLE,
                message=f"Cannot reach n8n at {self._config.api_url}",
                last_checked=datetime.utcnow().isoformat(),
            )
            return self._status
        except Exception as e:
            logger.error("n8n health check failed: %s", e)
            self._status = N8nStatus(
                status=N8nConnectionStatus.ERROR,
                message="Health check failed",
                last_checked=datetime.utcnow().isoformat(),
            )
            return self._status

    async def _count_failed_24h(self, client: httpx.AsyncClient) -> int:
        """Count failed executions in the last 24 hours."""
        try:
            response = await client.get(
                "/executions",
                params={"status": "error", "limit": 100},
            )
            if response.status_code != 200:
                return 0

            data = response.json()
            executions = data.get("data", [])
            cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            return sum(1 for e in executions if (e.get("startedAt") or "") > cutoff)
        except Exception:
            return 0

    # -------------------------------------------------------------------
    # Workflow Management
    # -------------------------------------------------------------------

    async def list_workflows(
        self,
        active_only: bool = False,
        tag: str | None = None,
    ) -> dict[str, Any]:
        """List all workflows with optional filters."""
        if not self._config.is_configured:
            return self._not_available("Workflows", "n8n not configured")

        try:
            client = self._get_client()
            params: dict[str, str] = {}
            if active_only:
                params["active"] = "true"

            response = await client.get("/workflows", params=params)
            if response.status_code != 200:
                return self._not_available("Workflows", f"HTTP {response.status_code}")

            data = response.json()
            workflows = []
            for w in data.get("data", []):
                wf = WorkflowSummary(
                    id=str(w.get("id", "")),
                    name=w.get("name", "Unnamed"),
                    active=w.get("active", False),
                    tags=[t.get("name", "") for t in w.get("tags", [])],
                    created_at=w.get("createdAt"),
                    updated_at=w.get("updatedAt"),
                )
                if tag and tag.lower() not in [t.lower() for t in wf.tags]:
                    continue
                workflows.append(wf.to_dict())

            return {
                "workflows": workflows,
                "count": len(workflows),
                "active_count": sum(1 for w in workflows if w["active"]),
            }

        except Exception as e:
            logger.error("n8n list workflows failed: %s", e)
            return self._not_available("Workflows", "Request failed")

    async def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        """Get detailed workflow info including node configuration."""
        if not self._config.is_configured:
            return self._not_available("Workflow", "n8n not configured")

        try:
            client = self._get_client()
            response = await client.get(f"/workflows/{workflow_id}")
            if response.status_code != 200:
                return self._not_available("Workflow", f"HTTP {response.status_code}")

            data = response.json()
            nodes = data.get("nodes", [])

            return {
                "id": str(data.get("id", "")),
                "name": data.get("name", ""),
                "active": data.get("active", False),
                "tags": [t.get("name", "") for t in data.get("tags", [])],
                "node_count": len(nodes),
                "node_types": list({n.get("type", "") for n in nodes}),
                "trigger_type": self._detect_trigger_type(nodes),
                "created_at": data.get("createdAt"),
                "updated_at": data.get("updatedAt"),
            }
        except Exception as e:
            logger.error("n8n get workflow failed: %s", e)
            return self._not_available("Workflow", "Request failed")

    async def activate_workflow(self, workflow_id: str) -> dict[str, Any]:
        """Activate a workflow."""
        return await self._set_workflow_active(workflow_id, True)

    async def deactivate_workflow(self, workflow_id: str) -> dict[str, Any]:
        """Deactivate a workflow."""
        return await self._set_workflow_active(workflow_id, False)

    async def _set_workflow_active(self, workflow_id: str, active: bool) -> dict[str, Any]:
        if not self._config.is_configured:
            return {"success": False, "reason": "n8n not configured"}

        try:
            client = self._get_client()
            response = await client.patch(
                f"/workflows/{workflow_id}",
                json={"active": active},
            )
            if response.status_code == 200:
                return {"success": True, "workflow_id": workflow_id, "active": active}
            return {"success": False, "reason": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "reason": str(e)}

    # -------------------------------------------------------------------
    # Execution History & Debugging
    # -------------------------------------------------------------------

    async def list_executions(
        self,
        workflow_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List recent executions with optional filters."""
        if not self._config.is_configured:
            return self._not_available("Executions", "n8n not configured")

        try:
            client = self._get_client()
            params: dict[str, Any] = {"limit": limit}
            if workflow_id:
                params["workflowId"] = workflow_id
            if status:
                params["status"] = status

            response = await client.get("/executions", params=params)
            if response.status_code != 200:
                return self._not_available("Executions", f"HTTP {response.status_code}")

            data = response.json()
            executions = []
            for e in data.get("data", []):
                ex = ExecutionSummary(
                    id=str(e.get("id", "")),
                    workflow_id=str(e.get("workflowId", "")),
                    workflow_name=e.get("workflowData", {}).get("name", "Unknown"),
                    status=e.get("status", "unknown"),
                    started_at=e.get("startedAt"),
                    finished_at=e.get("stoppedAt"),
                    error_message=self._extract_error(e),
                )
                executions.append(ex.to_dict())

            return {"executions": executions, "count": len(executions)}

        except Exception as e:
            logger.error("n8n list executions failed: %s", e)
            return self._not_available("Executions", "Request failed")

    async def get_execution(self, execution_id: str) -> dict[str, Any]:
        """Get detailed execution info including node-level results."""
        if not self._config.is_configured:
            return self._not_available("Execution", "n8n not configured")

        try:
            client = self._get_client()
            response = await client.get(f"/executions/{execution_id}")
            if response.status_code != 200:
                return self._not_available("Execution", f"HTTP {response.status_code}")

            data = response.json()
            node_results = self._extract_node_results(data)

            return {
                "id": str(data.get("id", "")),
                "workflow_name": data.get("workflowData", {}).get("name", ""),
                "status": data.get("status", "unknown"),
                "started_at": data.get("startedAt"),
                "finished_at": data.get("stoppedAt"),
                "mode": data.get("mode", ""),
                "node_results": node_results,
                "error": self._extract_error(data),
            }

        except Exception as e:
            logger.error("n8n get execution failed: %s", e)
            return self._not_available("Execution", "Request failed")

    # -------------------------------------------------------------------
    # Webhook Triggers (for event bus integration)
    # -------------------------------------------------------------------

    async def trigger_webhook(
        self,
        webhook_path: str,
        payload: dict[str, Any],
        test: bool = False,
    ) -> dict[str, Any]:
        """Trigger a workflow via its webhook URL.

        Args:
            webhook_path: Path portion of webhook (e.g., "work-order-created")
            payload: JSON payload to send
            test: Use test webhook URL instead of production
        """
        if not self._config.is_configured:
            return {"success": False, "reason": "n8n not configured"}

        # SSRF prevention: webhook_path must be a simple slug (no slashes, dots, or scheme)
        import re

        if not re.match(r"^[a-zA-Z0-9_-]+$", webhook_path):
            return {"success": False, "reason": f"Invalid webhook path: {webhook_path}"}

        prefix = "webhook-test" if test else "webhook"
        base = self._config.webhook_base.rsplit("/webhook", 1)[0]
        url = f"{base}/{prefix}/{webhook_path}"

        try:
            async with httpx.AsyncClient(timeout=self._config.timeout) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                resp_body = None
                content_type = response.headers.get("content-type", "")
                resp_body = response.json() if content_type.startswith("application/json") else response.text[:500]

                return {
                    "success": response.status_code in (200, 201, 204),
                    "status_code": response.status_code,
                    "webhook_path": webhook_path,
                    "test": test,
                    "response": resp_body,
                }
        except httpx.ConnectError:
            return {"success": False, "reason": f"Cannot reach webhook at {url}"}
        except Exception as e:
            return {"success": False, "reason": str(e)}

    # -------------------------------------------------------------------
    # Health Summary for Dashboard
    # -------------------------------------------------------------------

    async def get_health_summary(self) -> dict[str, Any]:
        """Comprehensive health summary for the System Health dashboard card."""
        if not self._config.is_configured:
            return {
                "configured": False,
                "status": "not_configured",
                "message": "n8n not connected",
            }

        status = await self.check_connection()
        if status.status != N8nConnectionStatus.CONNECTED:
            return {
                "configured": True,
                "status": status.status.value,
                "message": status.message,
            }

        failed = await self.list_executions(status="error", limit=5)

        return {
            "configured": True,
            "status": "healthy" if status.failed_24h == 0 else "degraded",
            "message": status.message,
            "active_workflows": status.active_workflows,
            "total_workflows": status.total_workflows,
            "failed_24h": status.failed_24h,
            "recent_failures": failed.get("executions", [])[:5],
            "last_checked": status.last_checked,
        }

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    @staticmethod
    def _detect_trigger_type(nodes: list[dict]) -> str:
        """Detect the trigger type from workflow nodes."""
        for node in nodes:
            node_type = node.get("type", "").lower()
            if "webhook" in node_type:
                return "webhook"
            elif "cron" in node_type or "schedule" in node_type:
                return "schedule"
            elif "email" in node_type and "trigger" in node_type:
                return "email"
            elif "trigger" in node_type:
                return "trigger"
        return "manual"

    @staticmethod
    def _extract_error(execution: dict) -> str | None:
        """Extract error message from execution data."""
        if execution.get("error"):
            err = execution["error"]
            if isinstance(err, dict):
                return err.get("message", str(err))
            return str(err)

        run_data = execution.get("data", {}).get("resultData", {}).get("runData", {})
        for node_name, runs in run_data.items():
            if runs and runs[-1].get("error"):
                err = runs[-1]["error"]
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                return f"[{node_name}] {msg}"

        return None

    @staticmethod
    def _extract_node_results(data: dict) -> list[dict[str, Any]]:
        """Extract per-node execution results for debugging."""
        node_results = []
        run_data = data.get("data", {}).get("resultData", {}).get("runData", {})
        for node_name, runs in run_data.items():
            if not runs:
                continue
            last_run = runs[-1]
            items_count = 0
            if last_run.get("data"):
                main_data = last_run["data"].get("main", [[]])
                if main_data and main_data[0]:
                    items_count = len(main_data[0])

            node_results.append(
                {
                    "node": node_name,
                    "status": "success" if not last_run.get("error") else "error",
                    "items": items_count,
                    "error": str(last_run["error"]) if last_run.get("error") else None,
                    "execution_time_ms": last_run.get("executionTime", 0),
                }
            )
        return node_results

    def _not_available(self, label: str, reason: str) -> dict[str, Any]:
        return {"not_available": True, "reason": reason, "label": label}


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service: N8nService | None = None


def get_n8n_service() -> N8nService:
    global _service
    if _service is None:
        _service = N8nService()
    return _service


async def shutdown_n8n_service():
    global _service
    if _service:
        await _service.close()
        _service = None
