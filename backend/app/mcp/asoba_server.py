"""
Asoba Terminal API MCP Server

Provides MCP tools for integrating with Asoba's eSUMS/Ona Terminal API.
Enables bidirectional intelligence between Sentinel BMS and Asoba fault detection.

Usage:
    from app.mcp.asoba_server import asoba_mcp_server

    result = await asoba_mcp_server.call_tool("asoba_get_ooda_summary", {"customer_id": "ltm-sandton-001"})
"""

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Configuration from environment
ASOBA_BASE_URL = os.getenv("ASOBA_API_BASE_URL", "https://api.asoba.co")
ASOBA_API_KEY = os.getenv("ASOBA_API_KEY", "")
ASOBA_ENABLED = os.getenv("ASOBA_ENABLED", "false").lower() == "true"

# Site ID mapping: Sentinel site_id -> Asoba customer_id
_SITE_MAP: dict[str, str] = {}
if os.getenv("ASOBA_SITE_MAPPING"):
    try:
        _SITE_MAP = dict(
            pair.split(":")
            for pair in os.getenv("ASOBA_SITE_MAPPING", "").split(",")
            if ":" in pair
        )
    except Exception as e:
        logger.error(f"Failed to parse ASOBA_SITE_MAPPING: {e}")


class AsobaMCPServer:
    """
    MCP server wrapping Asoba's Terminal API.
    Follows same pattern as SIMBIOTMCPServer.
    """

    def __init__(self):
        self.enabled = ASOBA_ENABLED
        self.api_key = ASOBA_API_KEY
        self.base_url = ASOBA_BASE_URL
        self.site_mapping = _SITE_MAP

        # Initialize HTTP client
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key

        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=30.0,
        )

    def _check_enabled(self) -> dict[str, Any] | None:
        """Return error dict if not enabled/configured, else None."""
        if not self.enabled:
            return {
                "error": "Asoba integration not enabled",
                "message": "Set ASOBA_ENABLED=true and ASOBA_API_KEY in environment",
                "contact": "support@asoba.co",
            }
        if not self.api_key:
            return {
                "error": "ASOBA_API_KEY not configured",
                "message": "Contact support@asoba.co for an API key",
            }
        return None

    def _resolve_customer_id(self, args: dict[str, Any]) -> str:
        """Resolve customer_id from Sentinel site_id if provided."""
        if "sentinel_site_id" in args:
            site_id = args.pop("sentinel_site_id")
            return self.site_mapping.get(site_id, site_id)
        return args.get("customer_id", "")

    def list_tools(self) -> list[dict[str, Any]]:
        """Return list of available MCP tools."""
        return [
            {
                "name": "asoba_get_ooda_summary",
                "description": "Get ML-enhanced OODA summary from Asoba eSUMS. Returns fault severity, energy-at-risk, root cause, and recommended actions for all assets under a customer account.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {
                            "type": "string",
                            "description": "Asoba customer ID (e.g., ltm-sandton-001)",
                        },
                        "sentinel_site_id": {
                            "type": "string",
                            "description": "Optional: Auto-resolve customer_id from Sentinel site_id (e.g., site-002)",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "asoba_run_fault_detection",
                "description": "Trigger Asoba OODA fault detection on a specific asset. Returns anomaly count and detection ID.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "asset_id": {
                            "type": "string",
                            "description": "Asoba asset ID to run detection on",
                        },
                    },
                    "required": ["asset_id"],
                },
            },
            {
                "name": "asoba_list_detections",
                "description": "List recent fault detection results for an asset.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "asset_id": {"type": "string", "description": "Asoba asset ID"},
                    },
                    "required": ["asset_id"],
                },
            },
            {
                "name": "asoba_run_diagnostics",
                "description": "Run AI diagnostics on a previously detected fault.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "detection_id": {
                            "type": "string",
                            "description": "Detection ID from previous fault detection",
                        },
                        "asset_id": {"type": "string", "description": "Asoba asset ID"},
                    },
                    "required": ["detection_id", "asset_id"],
                },
            },
            {
                "name": "asoba_list_assets",
                "description": "List assets registered in Asoba for a customer account.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {
                            "type": "string",
                            "description": "Asoba customer ID",
                        },
                        "sentinel_site_id": {
                            "type": "string",
                            "description": "Optional: Auto-resolve from Sentinel site_id",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "asoba_create_work_order",
                "description": "Create a maintenance work order in Asoba eSUMS. Optionally cross-references a Sentinel work order ID for audit linkage.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string", "description": "Asoba customer ID"},
                        "asset_id": {"type": "string", "description": "Asoba asset ID"},
                        "description": {"type": "string", "description": "Work order description"},
                        "priority": {
                            "type": "string",
                            "enum": ["low", "medium", "high", "critical"],
                            "default": "medium",
                        },
                        "sentinel_work_order_id": {
                            "type": "string",
                            "description": "Optional: Cross-reference to Sentinel work order",
                        },
                    },
                    "required": ["customer_id", "asset_id", "description"],
                },
            },
            {
                "name": "asoba_list_work_orders",
                "description": "List work orders in Asoba for a customer.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string", "description": "Asoba customer ID"},
                        "sentinel_site_id": {
                            "type": "string",
                            "description": "Optional: Auto-resolve from Sentinel site_id",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "asoba_create_maintenance_schedule",
                "description": "Schedule maintenance for an asset in Asoba.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string", "description": "Asoba customer ID"},
                        "asset_id": {"type": "string", "description": "Asoba asset ID"},
                        "schedule_date": {
                            "type": "string",
                            "description": "Scheduled date (ISO 8601)",
                        },
                        "description": {"type": "string", "description": "Maintenance description"},
                    },
                    "required": ["customer_id", "asset_id", "schedule_date", "description"],
                },
            },
            {
                "name": "asoba_get_bom",
                "description": "Get bill of materials for maintenance task.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "asset_id": {"type": "string", "description": "Asoba asset ID"},
                        "task_type": {"type": "string", "description": "Type of maintenance task"},
                    },
                    "required": ["asset_id"],
                },
            },
            {
                "name": "asoba_get_forecast",
                "description": "Retrieve stored ML energy forecast from Asoba for a site.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "site_id": {"type": "string", "description": "Site identifier"},
                        "asset_id": {"type": "string", "description": "Optional: Specific asset"},
                    },
                    "required": ["site_id"],
                },
            },
            {
                "name": "asoba_list_ml_models",
                "description": "List available ML models in Asoba's model registry.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute an MCP tool."""
        # Check if enabled
        error = self._check_enabled()
        if error:
            return error

        # Auto-resolve customer_id if sentinel_site_id provided
        if "sentinel_site_id" in arguments:
            arguments = dict(arguments)  # Copy to avoid mutating original
            arguments["customer_id"] = self._resolve_customer_id(arguments)

        # Dispatch to handler
        handlers: dict[str, callable] = {
            "asoba_get_ooda_summary": self._get_ooda_summary,
            "asoba_run_fault_detection": self._run_fault_detection,
            "asoba_list_detections": self._list_detections,
            "asoba_run_diagnostics": self._run_diagnostics,
            "asoba_list_assets": self._list_assets,
            "asoba_create_work_order": self._create_work_order,
            "asoba_list_work_orders": self._list_work_orders,
            "asoba_create_maintenance_schedule": self._create_maintenance_schedule,
            "asoba_get_bom": self._get_bom,
            "asoba_get_forecast": self._get_forecast,
            "asoba_list_ml_models": self._list_ml_models,
        }

        handler = handlers.get(name)
        if not handler:
            return {"error": f"Unknown tool: {name}"}

        try:
            return await handler(arguments)
        except httpx.HTTPError as e:
            logger.error(f"Asoba API error for {name}: {e}")
            return {
                "error": "Asoba API request failed",
                "detail": str(e),
                "tool": name,
            }
        except Exception as e:
            logger.error(f"Unexpected error in {name}: {e}")
            return {
                "error": "Internal error",
                "detail": str(e),
                "tool": name,
            }

    # ------------------------------------------------------------------
    # Tool Handlers
    # ------------------------------------------------------------------

    async def _get_ooda_summary(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get ML-enhanced OODA summary."""
        customer_id = args.get("customer_id")
        if not customer_id:
            return {"error": "customer_id or sentinel_site_id required"}

        resp = await self.client.post(
            "/terminal/ooda",
            json={"customer_id": customer_id},
        )
        resp.raise_for_status()
        data = resp.json()

        # Enrich with Sentinel data if available
        # TODO: Add Sentinel health scores and alert counts
        data["_sentinel_enriched"] = {
            "site_id": self._reverse_site_mapping(customer_id),
            "sentinel_health_score": None,  # TODO: Fetch from Sentinel
            "sentinel_alert_count": None,  # TODO: Fetch from Sentinel
        }

        return data

    async def _run_fault_detection(self, args: dict[str, Any]) -> dict[str, Any]:
        """Trigger fault detection on an asset."""
        asset_id = args.get("asset_id")
        if not asset_id:
            return {"error": "asset_id required"}

        resp = await self.client.post(
            "/terminal/detect",
            json={"action": "run", "asset_id": asset_id},
        )
        resp.raise_for_status()
        return resp.json()

    async def _list_detections(self, args: dict[str, Any]) -> dict[str, Any]:
        """List recent fault detection results."""
        asset_id = args.get("asset_id")
        if not asset_id:
            return {"error": "asset_id required"}

        resp = await self.client.post(
            "/terminal/detect",
            json={"action": "list", "asset_id": asset_id},
        )
        resp.raise_for_status()
        return resp.json()

    async def _run_diagnostics(self, args: dict[str, Any]) -> dict[str, Any]:
        """Run AI diagnostics on a detected fault."""
        detection_id = args.get("detection_id")
        asset_id = args.get("asset_id")

        if not detection_id or not asset_id:
            return {"error": "detection_id and asset_id required"}

        resp = await self.client.post(
            "/terminal/diagnose",
            json={
                "detection_id": detection_id,
                "asset_id": asset_id,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def _list_assets(self, args: dict[str, Any]) -> dict[str, Any]:
        """List assets for a customer."""
        customer_id = args.get("customer_id")
        if not customer_id:
            return {"error": "customer_id or sentinel_site_id required"}

        resp = await self.client.post(
            "/terminal/assets",
            json={"action": "list", "customer_id": customer_id},
        )
        resp.raise_for_status()
        return resp.json()

    async def _create_work_order(self, args: dict[str, Any]) -> dict[str, Any]:
        """Create a work order in Asoba."""
        customer_id = args.get("customer_id")
        asset_id = args.get("asset_id")
        description = args.get("description")

        if not all([customer_id, asset_id, description]):
            return {"error": "customer_id, asset_id, and description required"}

        payload = {
            "action": "create",
            "customer_id": customer_id,
            "asset_id": asset_id,
            "description": description,
            "priority": args.get("priority", "medium"),
        }

        if "sentinel_work_order_id" in args:
            payload["external_reference"] = args["sentinel_work_order_id"]

        resp = await self.client.post("/terminal/order", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def _list_work_orders(self, args: dict[str, Any]) -> dict[str, Any]:
        """List work orders for a customer."""
        customer_id = args.get("customer_id")
        if not customer_id:
            return {"error": "customer_id or sentinel_site_id required"}

        resp = await self.client.post(
            "/terminal/order",
            json={"action": "list", "customer_id": customer_id},
        )
        resp.raise_for_status()
        return resp.json()

    async def _create_maintenance_schedule(self, args: dict[str, Any]) -> dict[str, Any]:
        """Create maintenance schedule."""
        customer_id = args.get("customer_id")
        asset_id = args.get("asset_id")
        schedule_date = args.get("schedule_date")
        description = args.get("description")

        if not all([customer_id, asset_id, schedule_date, description]):
            return {"error": "customer_id, asset_id, schedule_date, and description required"}

        resp = await self.client.post(
            "/terminal/schedule",
            json={
                "customer_id": customer_id,
                "asset_id": asset_id,
                "schedule_date": schedule_date,
                "description": description,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def _get_bom(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get bill of materials."""
        asset_id = args.get("asset_id")
        if not asset_id:
            return {"error": "asset_id required"}

        payload = {"asset_id": asset_id}
        if "task_type" in args:
            payload["task_type"] = args["task_type"]

        resp = await self.client.post("/terminal/bom", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def _get_forecast(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get ML energy forecast."""
        site_id = args.get("site_id")
        if not site_id:
            return {"error": "site_id required"}

        payload = {"site_id": site_id}
        if "asset_id" in args:
            payload["asset_id"] = args["asset_id"]

        resp = await self.client.post("/terminal/forecast", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def _list_ml_models(self, args: dict[str, Any]) -> dict[str, Any]:
        """List available ML models."""
        resp = await self.client.post("/terminal/ml-models", json={})
        resp.raise_for_status()
        return resp.json()

    def _reverse_site_mapping(self, customer_id: str) -> str | None:
        """Reverse lookup: Asoba customer_id -> Sentinel site_id."""
        for site_id, cust_id in self.site_mapping.items():
            if cust_id == customer_id:
                return site_id
        return None


# Singleton instance
asoba_mcp_server = AsobaMCPServer()
