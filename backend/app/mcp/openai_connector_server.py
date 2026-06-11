"""
OpenAI ChatGPT Connector MCP Server

Implements the exact `search` and `fetch` tools required by OpenAI connectors
and Deep Research with strict JSON-encoded text content responses.

Data Sources (in order of preference):
1. Supabase (primary) - buildings, equipment, alerts, predictions, work_orders, documents
2. JSON files (fallback) - reference_devices.json, equipment.json, alerts.json

Ref: https://platform.openai.com/docs/mcp

Requirements:
- Must expose `search` and `fetch` tools
- Tool results must be exactly one content item of type `text`
- The `text` field must contain JSON-encoded string

Usage:
    # SSE endpoint must end in /sse/ for OpenAI connectors
    GET /api/mcp/openai/sse/
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.demand_response_service import get_demand_response_service
from app.services.odse_service import odse_service

logger = logging.getLogger(__name__)

# Data paths (fallback)
DATA_DIR = Path(__file__).parent.parent / "data"
EQUIPMENT_FILE = DATA_DIR / "equipment.json"
ALERTS_FILE = DATA_DIR / "alerts.json"
SITES_DIR = DATA_DIR / "sites"

# Base URL for document links (set from settings at runtime)
# Priority: SENTINEL_PUBLIC_URL > backend_url > localhost fallback
try:
    from app.config.settings import settings

    BASE_URL = settings.sentinel_public_url or settings.backend_url or "http://localhost:9095"
except Exception:
    BASE_URL = "http://localhost:9095"


def _load_json(filepath: Path) -> Any:
    """Load JSON file safely."""
    try:
        with open(filepath) as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load {filepath}: {e}")
        return []


def _get_supabase_client():
    """Get Supabase client if available."""
    try:
        from app.database.supabase_client import get_supabase_client

        return get_supabase_client()
    except Exception as e:
        logger.warning(f"Supabase not available: {e}")
        return None


class SupabaseDataLoader:
    """Load data from Supabase for the OpenAI connector."""

    def __init__(self, client):
        self.client = client

    def load_buildings(self) -> list[dict[str, Any]]:
        """Load buildings from Supabase."""
        try:
            response = self.client.table("sites").select("*").execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to load buildings from Supabase: {e}")
            return []

    def load_equipment(self) -> list[dict[str, Any]]:
        """Load equipment from Supabase with building info (paginated)."""
        try:
            all_equipment = []
            page_size = 1000
            offset = 0

            while True:
                response = (
                    self.client.table("equipment")
                    .select("*, sites(name, code)")
                    .range(offset, offset + page_size - 1)
                    .execute()
                )

                if not response.data:
                    break

                all_equipment.extend(response.data)

                if len(response.data) < page_size:
                    break

                offset += page_size

            return all_equipment
        except Exception as e:
            logger.error(f"Failed to load equipment from Supabase: {e}")
            return []

    def load_alerts(self) -> list[dict[str, Any]]:
        """Load alerts from Supabase with related info."""
        try:
            response = (
                self.client.table("alerts")
                .select("*, equipment(name, code, type), sites(name, code)")
                .order("created_at", desc=True)
                .limit(100)
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to load alerts from Supabase: {e}")
            return []

    def load_predictions(self) -> list[dict[str, Any]]:
        """Load predictions from Supabase with related info (paginated)."""
        try:
            all_predictions = []
            page_size = 500
            offset = 0
            max_records = 2000  # Limit total predictions to avoid huge indexes

            while len(all_predictions) < max_records:
                response = (
                    self.client.table("predictions")
                    .select("*, equipment(name, code, type, manufacturer, model), sites(name, code)")
                    .order("created_at", desc=True)
                    .range(offset, offset + page_size - 1)
                    .execute()
                )

                if not response.data:
                    break

                all_predictions.extend(response.data)

                if len(response.data) < page_size:
                    break

                offset += page_size

            return all_predictions[:max_records]
        except Exception as e:
            logger.error(f"Failed to load predictions from Supabase: {e}")
            return []

    def load_work_orders(self) -> list[dict[str, Any]]:
        """Load work orders from Supabase."""
        try:
            response = self.client.table("work_orders").select("*").order("created_at", desc=True).limit(100).execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to load work orders from Supabase: {e}")
            return []

    def load_documents(self) -> list[dict[str, Any]]:
        """Load technical documents from Supabase."""
        try:
            response = (
                self.client.table("documents")
                .select(
                    "id, code, title, document_type, equipment_type, manufacturer, model, "
                    "summary, keywords, source, full_text"
                )
                .order("created_at", desc=True)
                .limit(1000)
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to load documents from Supabase: {e}")
            return []


def _build_building_document(building: dict, source: str = "supabase") -> dict[str, Any]:
    """Build searchable document for a building."""
    site_id = building.get("code") or building.get("id", "unknown")

    text_parts = [
        f"Building: {building.get('name', 'Unknown')}",
        f"Code: {site_id}",
        f"Address: {building.get('address', 'N/A')}",
        f"Region: {building.get('region', 'N/A')}",
        f"Type: {building.get('type', 'N/A')}",
        f"Floor Area: {building.get('sqm', 'N/A')} sqm",
        f"Floors: {building.get('floors', 'N/A')}",
    ]

    if building.get("year_built"):
        text_parts.append(f"Year Built: {building['year_built']}")
    if building.get("occupancy_pattern"):
        text_parts.append(f"Occupancy Pattern: {building['occupancy_pattern']}")
    if building.get("equipment_count"):
        text_parts.append(f"Equipment Count: {building['equipment_count']}")
    if building.get("optimization_enabled"):
        text_parts.append("Optimization: Enabled")
    if building.get("control_enabled"):
        text_parts.append("Remote Control: Enabled")

    return {
        "id": f"building-{site_id}",
        "title": f"Building: {building.get('name', site_id)}",
        "text": "\n".join(text_parts),
        "url": f"{BASE_URL}/api/buildings/{site_id}",
        "doc_type": "building",
        "metadata": {
            "site_id": site_id,
            "region": building.get("region"),
            "type": building.get("type"),
            "sqm": building.get("sqm"),
            "source": source,
        },
    }


def _build_equipment_document(equipment: dict, source: str = "supabase") -> dict[str, Any]:
    """Build searchable document for equipment."""
    equip_id = equipment.get("code") or equipment.get("id", "unknown")
    site_name = ""
    if equipment.get("sites"):
        site_name = equipment["sites"].get("name", "")

    text_parts = [
        f"Equipment: {equipment.get('name', equip_id)}",
        f"Code: {equip_id}",
        f"Type: {equipment.get('type', 'N/A')}",
    ]

    if site_name:
        text_parts.append(f"Building: {site_name}")
    if equipment.get("location"):
        text_parts.append(f"Location: {equipment['location']}")
    if equipment.get("manufacturer"):
        text_parts.append(f"Manufacturer: {equipment['manufacturer']}")
    if equipment.get("model"):
        text_parts.append(f"Model: {equipment['model']}")
    if equipment.get("capacity"):
        text_parts.append(f"Capacity: {equipment['capacity']}")
    if equipment.get("serial_number"):
        text_parts.append(f"Serial: {equipment['serial_number']}")
    if equipment.get("status"):
        text_parts.append(f"Status: {equipment['status']}")
    if equipment.get("health_score") is not None:
        text_parts.append(f"Health Score: {equipment['health_score']}%")
    if equipment.get("install_date"):
        text_parts.append(f"Installed: {equipment['install_date']}")
    if equipment.get("last_service"):
        text_parts.append(f"Last Service: {equipment['last_service']}")

    return {
        "id": f"equipment-{equip_id}",
        "title": f"Equipment: {equipment.get('name', equip_id)}",
        "text": "\n".join(text_parts),
        "url": f"{BASE_URL}/api/equipment/{equip_id}",
        "doc_type": "equipment",
        "metadata": {
            "equipment_id": equip_id,
            "type": equipment.get("type"),
            "manufacturer": equipment.get("manufacturer"),
            "model": equipment.get("model"),
            "health_score": equipment.get("health_score"),
            "status": equipment.get("status"),
            "source": source,
        },
    }


def _build_alert_document(alert: dict, source: str = "supabase") -> dict[str, Any]:
    """Build searchable document for an alert."""
    alert_id = alert.get("id", "unknown")
    equipment_name = ""
    site_name = ""

    if alert.get("equipment"):
        equipment_name = alert["equipment"].get("name", "")
    if alert.get("sites"):
        site_name = alert["sites"].get("name", "")

    text_parts = [
        f"Alert: {alert.get('title', 'Unknown Alert')}",
        f"Severity: {alert.get('severity', 'N/A')}",
        f"Status: {alert.get('status', 'N/A')}",
        f"Type: {alert.get('type', 'N/A')}",
    ]

    if equipment_name:
        text_parts.append(f"Equipment: {equipment_name}")
    if site_name:
        text_parts.append(f"Building: {site_name}")
    if alert.get("message"):
        text_parts.append(f"Message: {alert['message']}")
    if alert.get("created_at"):
        text_parts.append(f"Created: {alert['created_at']}")
    if alert.get("acknowledged_by"):
        text_parts.append(f"Acknowledged by: {alert['acknowledged_by']}")

    return {
        "id": f"alert-{alert_id}",
        "title": f"Alert: {alert.get('title', 'Unknown')} ({alert.get('severity', 'N/A')})",
        "text": "\n".join(text_parts),
        "url": f"{BASE_URL}/api/alerts/{alert_id}",
        "doc_type": "alert",
        "metadata": {
            "alert_id": str(alert_id),
            "severity": alert.get("severity"),
            "status": alert.get("status"),
            "type": alert.get("type"),
            "source": source,
        },
    }


def _build_prediction_document(prediction: dict, source: str = "supabase") -> dict[str, Any]:
    """Build searchable document for a prediction."""
    pred_id = prediction.get("code") or prediction.get("id", "unknown")
    equipment_name = ""
    equipment_type = ""
    site_name = ""

    if prediction.get("equipment"):
        equipment_name = prediction["equipment"].get("name", "")
        equipment_type = prediction["equipment"].get("type", "")
    if prediction.get("sites"):
        site_name = prediction["sites"].get("name", "")

    text_parts = [
        f"Prediction: {prediction.get('prediction_type', 'Unknown')}",
        f"Probability: {prediction.get('probability_percent', 'N/A')}%",
        f"Confidence: {prediction.get('confidence', 'N/A')}",
        f"Severity: {prediction.get('severity', 'N/A')}",
        f"Urgency: {prediction.get('urgency', 'N/A')}",
    ]

    if equipment_name:
        text_parts.append(f"Equipment: {equipment_name}")
    if equipment_type:
        text_parts.append(f"Equipment Type: {equipment_type}")
    if site_name:
        text_parts.append(f"Building: {site_name}")
    if prediction.get("predicted_failure_date"):
        text_parts.append(f"Predicted Failure Date: {prediction['predicted_failure_date']}")
    if prediction.get("timeframe_days"):
        text_parts.append(f"Timeframe: {prediction['timeframe_days']} days")
    if prediction.get("recommended_action"):
        text_parts.append(f"Recommended Action: {prediction['recommended_action']}")
    if prediction.get("repair_cost_zar"):
        text_parts.append(f"Estimated Repair Cost: R{prediction['repair_cost_zar']:,.0f}")
    if prediction.get("potential_loss_zar"):
        text_parts.append(f"Potential Loss: R{prediction['potential_loss_zar']:,.0f}")
    if prediction.get("parts_required"):
        text_parts.append(f"Parts Required: {', '.join(prediction['parts_required'])}")

    # Add contributing factors
    factors = prediction.get("contributing_factors")
    if factors and isinstance(factors, list):
        factor_texts = []
        for f in factors[:3]:
            if isinstance(f, dict):
                factor_texts.append(f"{f.get('factor', 'Unknown')}: {f.get('impact', 'N/A')}")
        if factor_texts:
            text_parts.append(f"Contributing Factors: {'; '.join(factor_texts)}")

    return {
        "id": f"prediction-{pred_id}",
        "title": (
            f"Prediction: {prediction.get('prediction_type', 'Unknown')} - {equipment_name or 'Unknown Equipment'}"
        ),
        "text": "\n".join(text_parts),
        "url": f"{BASE_URL}/api/predictions/{pred_id}",
        "doc_type": "prediction",
        "metadata": {
            "prediction_id": str(pred_id),
            "prediction_type": prediction.get("prediction_type"),
            "probability_percent": prediction.get("probability_percent"),
            "severity": prediction.get("severity"),
            "urgency": prediction.get("urgency"),
            "status": prediction.get("status"),
            "source": source,
        },
    }


def _build_work_order_document(wo: dict, source: str = "supabase") -> dict[str, Any]:
    """Build searchable document for a work order."""
    wo_id = wo.get("code") or wo.get("id", "unknown")
    equipment_name = ""
    site_name = ""

    if wo.get("equipment"):
        equipment_name = wo["equipment"].get("name", "")
    if wo.get("sites"):
        site_name = wo["sites"].get("name", "")

    text_parts = [
        f"Work Order: {wo.get('title', 'Unknown')}",
        f"Priority: {wo.get('priority', 'N/A')}",
        f"Status: {wo.get('status', 'N/A')}",
    ]

    if equipment_name:
        text_parts.append(f"Equipment: {equipment_name}")
    if site_name:
        text_parts.append(f"Building: {site_name}")
    if wo.get("description"):
        text_parts.append(f"Description: {wo['description']}")
    if wo.get("assigned_to"):
        text_parts.append(f"Assigned To: {wo['assigned_to']}")
    if wo.get("scheduled_date"):
        text_parts.append(f"Scheduled: {wo['scheduled_date']}")
    if wo.get("work_performed"):
        text_parts.append(f"Work Performed: {wo['work_performed']}")
    if wo.get("findings"):
        text_parts.append(f"Findings: {wo['findings']}")
    if wo.get("total_cost_zar"):
        text_parts.append(f"Total Cost: R{wo['total_cost_zar']:,.0f}")

    return {
        "id": f"workorder-{wo_id}",
        "title": f"Work Order: {wo.get('title', wo_id)}",
        "text": "\n".join(text_parts),
        "url": f"{BASE_URL}/api/work-orders/{wo_id}",
        "doc_type": "work_order",
        "metadata": {
            "work_order_id": str(wo_id),
            "priority": wo.get("priority"),
            "status": wo.get("status"),
            "source": source,
        },
    }


def _build_tech_document(doc: dict, source: str = "supabase") -> dict[str, Any]:
    """Build searchable document for technical documentation."""
    doc_id = doc.get("code") or doc.get("id", "unknown")

    text_parts = [
        f"Document: {doc.get('title', 'Unknown')}",
        f"Type: {doc.get('document_type', 'N/A')}",
    ]

    if doc.get("equipment_type"):
        text_parts.append(f"Equipment Type: {doc['equipment_type']}")
    if doc.get("manufacturer"):
        text_parts.append(f"Manufacturer: {doc['manufacturer']}")
    if doc.get("model"):
        text_parts.append(f"Model: {doc['model']}")
    if doc.get("summary"):
        text_parts.append(f"Summary: {doc['summary']}")
    if doc.get("keywords"):
        text_parts.append(f"Keywords: {', '.join(doc['keywords'])}")
    if doc.get("full_text"):
        text_parts.append(f"Full Text: {doc['full_text']}")

    return {
        "id": str(doc_id),  # Use raw UUID so fetch can match search results directly
        "title": f"Document: {doc.get('title', doc_id)}",
        "text": "\n".join(text_parts),
        "url": doc.get("source") or f"{BASE_URL}/api/documents/{doc_id}",
        "doc_type": "technical_document",
        "metadata": {
            "document_id": str(doc_id),
            "document_type": doc.get("document_type"),
            "equipment_type": doc.get("equipment_type"),
            "manufacturer": doc.get("manufacturer"),
            "source": source,
        },
    }


def _build_searchable_documents() -> list[dict[str, Any]]:
    """
    Build searchable document index from Supabase (primary) or JSON files (fallback).
    """
    documents = []
    supabase_client = _get_supabase_client()

    if supabase_client:
        logger.info("OpenAI Connector: Loading data from Supabase")
        loader = SupabaseDataLoader(supabase_client)

        # Load buildings
        for building in loader.load_buildings():
            documents.append(_build_building_document(building, "supabase"))

        # Load equipment
        for equipment in loader.load_equipment():
            documents.append(_build_equipment_document(equipment, "supabase"))

        # Load alerts
        for alert in loader.load_alerts():
            documents.append(_build_alert_document(alert, "supabase"))

        # Load predictions
        for prediction in loader.load_predictions():
            documents.append(_build_prediction_document(prediction, "supabase"))

        # Load work orders
        for wo in loader.load_work_orders():
            documents.append(_build_work_order_document(wo, "supabase"))

        # Load technical documents
        for doc in loader.load_documents():
            documents.append(_build_tech_document(doc, "supabase"))

        logger.info(f"OpenAI Connector: Loaded {len(documents)} documents from Supabase")

    else:
        logger.info("OpenAI Connector: Supabase not available, falling back to JSON files")

        # Load equipment from JSON
        devices = []
        if EQUIPMENT_FILE.exists():
            devices = _load_json(EQUIPMENT_FILE)

        for device in devices:
            # Map JSON structure to expected format
            equipment = {
                "code": device.get("id"),
                "name": device.get("name", device.get("id")),
                "type": device.get("type"),
                "location": device.get("location"),
                "status": device.get("status"),
                "health_score": device.get("metadata", {}).get("health_score"),
                "manufacturer": device.get("metadata", {}).get("manufacturer"),
                "model": device.get("metadata", {}).get("model"),
            }
            documents.append(_build_equipment_document(equipment, "json"))

        # Load alerts from JSON
        if ALERTS_FILE.exists():
            alerts = _load_json(ALERTS_FILE)
            if isinstance(alerts, list):
                for alert in alerts:
                    documents.append(_build_alert_document(alert, "json"))

        logger.info(f"OpenAI Connector: Loaded {len(documents)} documents from JSON files")

    return documents


def _simple_text_search(query: str, documents: list[dict], limit: int = 10) -> list[dict]:
    """
    Simple text search across documents.

    In production, this could use the RAG service with vector search for better results.
    """
    query_lower = query.lower()
    query_terms = query_lower.split()

    scored_docs = []
    for doc in documents:
        text_lower = doc["text"].lower()
        title_lower = doc["title"].lower()

        # Calculate relevance score
        score = 0

        # Exact phrase match in title (highest weight)
        if query_lower in title_lower:
            score += 100

        # Exact phrase match in text
        if query_lower in text_lower:
            score += 50

        # Individual term matches
        for term in query_terms:
            if len(term) < 2:  # Skip very short terms
                continue
            if term in title_lower:
                score += 20
            if term in text_lower:
                score += 5
                # Bonus for multiple occurrences
                score += min(text_lower.count(term) * 2, 20)

        if score > 0:
            scored_docs.append((score, doc))

    # Sort by score descending
    scored_docs.sort(key=lambda x: x[0], reverse=True)

    return [doc for _, doc in scored_docs[:limit]]


class OpenAIConnectorMCPServer:
    """
    MCP Server compatible with OpenAI ChatGPT connectors.

    Implements exactly two tools:
    - search: Find documents matching a query
    - fetch: Retrieve full document content by ID
    """

    def __init__(self):
        self._documents: list[dict] | None = None
        self._document_index: dict[str, dict] | None = None
        self._last_refresh: datetime | None = None
        self._refresh_interval_seconds = 300  # Refresh every 5 minutes

    def _ensure_index(self, force_refresh: bool = False):
        """Lazy load document index with periodic refresh."""
        now = datetime.now()

        should_refresh = (
            self._documents is None
            or force_refresh
            or (self._last_refresh and (now - self._last_refresh).total_seconds() > self._refresh_interval_seconds)
        )

        if should_refresh:
            self._documents = _build_searchable_documents()
            self._document_index = {doc["id"]: doc for doc in self._documents}
            self._last_refresh = now

            # Log document counts by type
            type_counts = {}
            for doc in self._documents:
                t = doc.get("doc_type", "unknown")
                type_counts[t] = type_counts.get(t, 0) + 1
            logger.info(f"OpenAI Connector: Indexed {len(self._documents)} documents - {type_counts}")

    def list_tools(self) -> list[dict[str, Any]]:
        """List available tools (search and fetch only)."""
        return [
            {
                "name": "search",
                "description": (
                    "Search SENTINEL BMS data including buildings, equipment, alerts, "
                    "predictions, work orders, and technical documentation. "
                    "Returns matching document references."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Search query to find relevant documents "
                                "(e.g., 'chiller maintenance', 'Sandton building alerts', "
                                "'high risk predictions')"
                            ),
                        }
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "fetch",
                "description": (
                    "Retrieve full content of a document by its ID. "
                    "Use IDs from search results to get detailed information."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Document ID to fetch (from search results)"}
                    },
                    "required": ["id"],
                },
            },
            # Category A: Live Data (6 tools)
            {
                "name": "get_site_status",
                "description": "Get current operational status for a building site including alerts, equipment health, and recommendations.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "site_id": {
                            "type": "string",
                            "description": "Site identifier (e.g., S002)",
                            "enum": ["S002"],
                        }
                    },
                    "required": ["site_id"],
                },
            },
            {
                "name": "get_recommendations",
                "description": "Get top active recommendations for a site with action, priority, and projected savings.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "site_id": {
                            "type": "string",
                            "description": "Site identifier (e.g., S002)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum recommendations to return",
                            "default": 5,
                        },
                        "status": {
                            "type": "string",
                            "description": "Filter by recommendation status",
                            "enum": ["pending", "executed", "auto_executed", "all"],
                            "default": "pending",
                        },
                    },
                    "required": ["site_id"],
                },
            },
            {
                "name": "trace_recommendation",
                "description": "Trace a recommendation's origin, ML model used, confidence breakdown, and execution status.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "recommendation_id": {
                            "type": "string",
                            "description": "Recommendation UUID to trace",
                        }
                    },
                    "required": ["recommendation_id"],
                },
            },
            {
                "name": "inspect_equipment",
                "description": "Get detailed equipment information including health, maintenance history, and failure risk.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "site_id": {
                            "type": "string",
                            "description": "Site identifier (e.g., S002)",
                        },
                        "equipment_id": {
                            "type": "string",
                            "description": "Equipment identifier (e.g., S002-CHILLER-B1-001)",
                        },
                    },
                    "required": ["site_id", "equipment_id"],
                },
            },
            {
                "name": "get_roi_summary",
                "description": "Get ROI metrics for executed recommendations including energy savings and maintenance avoided.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "site_id": {
                            "type": "string",
                            "description": "Site identifier (e.g., S002)",
                        },
                        "metric": {
                            "type": "string",
                            "description": "Metric category to retrieve",
                            "enum": ["energy", "maintenance", "uptime", "all"],
                            "default": "all",
                        },
                    },
                    "required": ["site_id"],
                },
            },
            {
                "name": "analyze_impact",
                "description": "Analyze the predicted and actual impact of a recommendation including energy savings and risk trajectory.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "recommendation_id": {
                            "type": "string",
                            "description": "Recommendation UUID to analyze",
                        },
                    },
                    "required": ["recommendation_id"],
                },
            },
            {
                "name": "compare_sites",
                "description": "Compare metrics across all sites including status, energy efficiency, uptime, and recommendations.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "description": "Metric to compare across sites",
                            "enum": ["status", "energy_efficiency", "uptime", "recommendation_count"],
                        },
                    },
                    "required": ["metric"],
                },
            },
            {
                "name": "get_curtailable_load",
                "description": "Get real-time curtailable HVAC load signal for a site — how much load can be safely shed, for how long, and with what confidence.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "site_id": {
                            "type": "string",
                            "description": "Site identifier (e.g., S002)",
                        },
                        "min_priority": {
                            "type": "integer",
                            "description": "Minimum zone priority to include (1=critical/never shed, 5=lowest/shed first). Default 3.",
                            "default": 3,
                        },
                        "include_zones": {
                            "type": "boolean",
                            "description": "Include per-zone breakdown in response",
                            "default": False,
                        },
                    },
                    "required": ["site_id"],
                },
            },
            {
                "name": "get_odse_export",
                "description": "Export Sentinel energy timeseries data in ODS-E v0.4.0 compliant format for eSUMS ingestion.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "site_id": {
                            "type": "string",
                            "description": "Site identifier (e.g., S002)",
                        },
                        "start": {
                            "type": "string",
                            "description": "Start of export window (ISO 8601 UTC)",
                        },
                        "end": {
                            "type": "string",
                            "description": "End of export window (ISO 8601 UTC)",
                        },
                        "equipment_id": {
                            "type": "string",
                            "description": "Optional: filter to single equipment UUID",
                        },
                    },
                    "required": ["site_id", "start", "end"],
                },
            },
            # Category B: RAG Knowledge (2 tools)
            {
                "name": "search_knowledge",
                "description": "Search the equipment knowledge base using semantic vector search for diagnostic and maintenance information.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g., 'chiller high vibration', 'AHU filter replacement')",
                        },
                        "doc_type": {
                            "type": "string",
                            "description": "Optional filter by knowledge type (e.g., 'fault_code', 'maintenance_procedure')",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results to return",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_knowledge_detail",
                "description": "Retrieve detailed knowledge article for a specific equipment topic including diagnostic steps and solutions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "Topic title or code to retrieve (e.g., 'CHILLER_HIGH_HEAD_PRESSURE')",
                        },
                        "detail_level": {
                            "type": "string",
                            "description": "Level of detail to return",
                            "enum": ["summary", "full", "examples"],
                            "default": "full",
                        },
                    },
                    "required": ["topic"],
                },
            },
            # Category C: Work Orders (read-only for advisory mode)
            {
                "name": "get_work_orders",
                "description": "List work orders for a site with optional status filter.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "site_id": {"type": "string", "description": "Site identifier (e.g., S002)"},
                        "status": {
                            "type": "string",
                            "description": "Filter by status",
                            "enum": ["scheduled", "in_progress", "resolved", "verified", "all"],
                        },
                        "limit": {"type": "integer", "description": "Max results to return", "default": 10},
                    },
                    "required": ["site_id"],
                },
            },
            {
                "name": "get_work_order",
                "description": "Get detailed information about a specific work order by ID.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "work_order_id": {"type": "string", "description": "Work order UUID"},
                    },
                    "required": ["work_order_id"],
                },
            },
            {
                "name": "ping",
                "description": "Lightweight health check for the Sentinel MCP connector. Returns connection status, index state, and server metadata. Use to verify the connector is operational before running other tools.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

    async def ping(self) -> dict[str, Any]:
        """
        Lightweight health check for the Sentinel MCP connector.

        Returns:
            {
                "status": "ok",
                "tools_registered": 17,
                "documents_indexed": 564,
                "supabase_connected": true,
                "version": "1.0.0",
                "mcp_version": "2024-11-05",
            }
        """
        self._ensure_index()
        try:
            from app.database.supabase_client import get_supabase_client

            client = get_supabase_client()
            client.table("sites").select("code").limit(1).execute()
            supabase_ok = True
        except Exception:
            supabase_ok = False

        return {
            "status": "ok",
            "tools_registered": len(self.list_tools()),
            "documents_indexed": len(self._documents) if self._documents else 0,
            "supabase_connected": supabase_ok,
            "version": "1.0.0",
            "mcp_version": "2024-11-05",
        }

    async def search(self, query: str) -> dict[str, Any]:
        """
        Search for documents matching query using HyDE-enhanced hybrid search.

        HyDE (Hypothetical Document Embedding) generates a brief hypothetical
        answer with Haiku, embeds that, and searches with it. This resolves
        vocabulary mismatches between informal queries and formal documents.
        Raw embedding fallback for table_row filtered queries where vocabulary
        is already precise.

        Returns:
            {
                "results": [
                    {"id": "...", "title": "...", "url": "..."},
                    ...
                ]
            }
        """
        vector_db = self._get_vector_db_service()

        if not vector_db:
            # Fallback to simple text search if VectorDB unavailable
            self._ensure_index()
            matching_docs = _simple_text_search(query, self._documents, limit=15)
            results = [{"id": doc["id"], "title": doc["title"], "url": doc["url"]} for doc in matching_docs]
        else:
            try:
                search_results = await vector_db.hybrid_search(query=query, n_results=15, use_hyde=True)
                results = [
                    {
                        "id": r.get("document_id", r.get("id", "")),
                        "title": r.get("title", r.get("document_title", "Untitled")),
                        "url": r.get("url", ""),
                    }
                    for r in search_results
                ]
            except Exception as e:
                logger.warning(f"VectorDB search failed, falling back to text search: {e}")
                self._ensure_index()
                matching_docs = _simple_text_search(query, self._documents, limit=15)
                results = [{"id": doc["id"], "title": doc["title"], "url": doc["url"]} for doc in matching_docs]

        logger.info(f"OpenAI Connector search: '{query}' -> {len(results)} results")

        return {"results": results}

    async def fetch(self, id: str) -> dict[str, Any]:
        """
        Fetch full document content by ID.

        Returns:
            {
                "id": "...",
                "title": "...",
                "text": "...",
                "url": "...",
                "metadata": {...}
            }
        """
        if not id:
            return {
                "id": "",
                "title": "Invalid ID",
                "text": "No ID provided",
                "url": "",
                "metadata": {"error": "bad_input"},
            }

        # Try in-memory index first (fast path for tech docs indexed at startup)
        self._ensure_index()
        doc = self._document_index.get(id)

        if not doc:
            # Fallback: query documents table directly by UUID
            doc = self._fetch_doc_from_db(id)

        if not doc:
            logger.warning(f"OpenAI Connector fetch: document not found: {id}")
            return {
                "id": id,
                "title": "Document Not Found",
                "text": f"No document found with ID: {id}",
                "url": "",
                "metadata": {"error": "not_found"},
            }

        logger.info(f"OpenAI Connector fetch: {id}")
        return {
            "id": doc["id"],
            "title": doc["title"],
            "text": doc["text"],
            "url": doc["url"],
            "metadata": doc.get("metadata", {}),
        }

    def _fetch_doc_from_db(self, doc_uuid: str) -> dict[str, Any] | None:
        """Fetch a document directly from Supabase by UUID."""
        client = _get_supabase_client()
        if not client:
            return None
        try:
            # Try fetching from documents table by id (UUID)
            result = (
                client.table("documents")
                .select(
                    "id, code, title, document_type, equipment_type, manufacturer, model, summary, keywords, source, full_text"
                )
                .eq("id", doc_uuid)
                .limit(1)
                .execute()
            )
            if result.data:
                raw = result.data[0]
                return _build_tech_document(raw, "supabase")
        except Exception as e:
            logger.debug(f"Document fetch by UUID failed: {e}")

        # Try fetching by code (some docs use code as identifier)
        try:
            result = (
                client.table("documents")
                .select(
                    "id, code, title, document_type, equipment_type, manufacturer, model, summary, keywords, source, full_text"
                )
                .eq("code", doc_uuid)
                .limit(1)
                .execute()
            )
            if result.data:
                raw = result.data[0]
                return _build_tech_document(raw, "supabase")
        except Exception as e:
            logger.debug(f"Document fetch by code failed: {e}")

        return None

    def _get_vector_db_service(self):
        """Get VectorDB service for RAG operations."""
        try:
            client = _get_supabase_client()
            if client:
                from app.services.vector_db import get_vector_db_service

                return get_vector_db_service(client)
        except Exception as e:
            logger.warning(f"VectorDB service unavailable: {e}")
        return None

    def _get_site_code(self, site_id: str) -> str:
        """Normalize site ID to site-002 format for recommendations/queries."""
        if not site_id:
            return ""
        # Already in correct format
        if site_id.lower() in ("site-002"):
            return site_id.lower()
        if site_id.upper() in ("S002"):
            return f"site-{site_id[-3:].lower()}"
        # Try to resolve UUID to code
        try:
            client = _get_supabase_client()
            if client:
                result = client.table("sites").select("code").eq("id", site_id).limit(1).execute()
                if result.data:
                    return result.data[0]["code"]
        except Exception:
            pass
        return site_id

    def _get_site_uuid(self, site_id: str) -> str:
        """Get site UUID for equipment table joins."""
        if not site_id:
            return ""
        # Already a UUID
        if len(site_id) == 36:
            return site_id
        # First normalize to code, then resolve to UUID
        site_code = self._get_site_code(site_id)
        if site_code:
            try:
                client = _get_supabase_client()
                if client:
                    result = client.table("sites").select("id").eq("code", site_code).limit(1).execute()
                    if result.data:
                        return result.data[0]["id"]
            except Exception:
                pass
        return site_id

    async def get_site_status(self, site_id: str) -> dict[str, Any]:
        """Get current operational status for a building site."""
        client = _get_supabase_client()
        if not client:
            return {"error": "Supabase not available"}

        site_code = self._get_site_code(site_id)
        site_uuid = self._get_site_uuid(site_id)
        if not site_code:
            return {"error": "Invalid site_id"}

        try:
            # Get site info
            site_result = client.table("sites").select("name, code, region, type").eq("code", site_code).execute()
            site_data = site_result.data[0] if site_result.data else {}

            # Get critical alerts count (alerts uses site UUID)
            alerts_result = (
                client.table("alerts")
                .select("id, severity, status")
                .eq("site_id", site_uuid)
                .eq("status", "active")
                .in_("severity", ["high", "critical"])
                .execute()
            )
            critical_alerts = len(alerts_result.data) if alerts_result.data else 0

            # Get recent recommendations count (recommendations uses site-002 format)
            recs_result = (
                client.table("recommendations")
                .select("id, status, risk_level")
                .eq("site_id", site_code)
                .eq("shadow_mode", False)
                .order("timestamp", desc=True)
                .limit(100)
                .execute()
            )
            recent_recs = len(recs_result.data) if recs_result.data else 0

            # Get equipment at risk (equipment uses site UUID)
            equip_result = (
                client.table("equipment")
                .select("id, code, name, health_score, status, health_confidence, health_trend")
                .eq("site_id", site_uuid)
                .in_("status", ["warning", "critical", "fault"])
                .order("health_score", desc=False)
                .limit(10)
                .execute()
            )
            equipment_at_risk = []
            if equip_result.data:
                for eq in equip_result.data:
                    equipment_at_risk.append(
                        {
                            "id": eq.get("code") or eq.get("id"),
                            "name": eq.get("name"),
                            "risk_level": "high" if eq.get("status") == "critical" else "medium",
                            "health_score": eq.get("health_score"),
                            "health_confidence": eq.get("health_confidence", "unknown"),
                            "health_trend": eq.get("health_trend", "unknown"),
                        }
                    )

            # Determine overall status
            overall_status = "green"
            if critical_alerts > 0:
                overall_status = "red"
            elif len(equipment_at_risk) > 3:
                overall_status = "amber"

            # Get ML training status from sites.ml_hours_ingested
            ml_status = "unknown"
            ml_hours = 0.0
            try:
                site_result = client.table("sites").select("ml_hours_ingested").eq("id", site_uuid).execute()
                if site_result.data:
                    ml_hours = float(site_result.data[0].get("ml_hours_ingested") or 0)
                    if ml_hours >= 72:
                        ml_status = f"trained ({ml_hours:.0f}h)"
                    elif ml_hours > 0:
                        ml_status = f"training ({ml_hours:.0f}h / 72h)"
                    else:
                        ml_status = "not_started"
            except Exception:
                pass

            return {
                "site_name": site_data.get("name", site_id),
                "overall_status": overall_status,
                "critical_alerts": critical_alerts,
                "recent_recommendations": recent_recs,
                "ml_training_status": ml_status,
                "equipment_at_risk": equipment_at_risk,
                "summary": f"{site_data.get('name', site_id)}: {critical_alerts} critical alerts, {len(equipment_at_risk)} equipment at risk",
            }
        except Exception as e:
            logger.error(f"get_site_status failed: {e}")
            return {"error": str(e)}

    async def get_recommendations(self, site_id: str, limit: int = 5, status: str = "pending") -> dict[str, Any]:
        """Get top active recommendations for a site."""
        client = _get_supabase_client()
        if not client:
            return {"error": "Supabase not available"}

        site_code = self._get_site_code(site_id)
        if not site_code:
            return {"error": "Invalid site_id"}

        try:
            # Build query — recommendations table uses site-002 format
            # Columns: id, site_id, timestamp, action_type, risk_level, action, expected_impact, status
            query = (
                client.table("recommendations")
                .select(
                    "id, action_type, risk_level, action, expected_impact, status, timestamp, "
                    "confidence_score, target_equipment, reason, profile"
                )
                .eq("site_id", site_code)
                .eq("shadow_mode", False)
                .order("timestamp", desc=True)
            )
            if status != "all":
                query = query.eq("status", status)
            query = query.limit(limit)
            result = query.execute()

            recommendations = []
            if result.data:
                for rec in result.data:
                    ei = rec.get("expected_impact") or {}
                    risk_level = rec.get("risk_level", "medium")
                    priority = {"critical": "high", "high": "high", "medium": "medium", "low": "low"}.get(
                        risk_level, "medium"
                    )
                    confidence = (
                        rec.get("confidence_score")
                        if rec.get("confidence_score") is not None
                        else (rec.get("confidence") if rec.get("confidence") is not None else 0.5)
                    )
                    # Extract projected saving from expected_impact
                    projected_saving_zar = None
                    if isinstance(ei, dict):
                        projected_saving_zar = ei.get("cost_zar") or ei.get("saving_zar")
                    # Build the recommended_action from action dict
                    action_obj = rec.get("action") or {}
                    if isinstance(action_obj, dict):
                        point = action_obj.get("point", "")
                        value = action_obj.get("value")
                        unit = action_obj.get("unit", "")
                        current = action_obj.get("current_value")
                        if point and value is not None:
                            if current is not None:
                                action_text = f"Set {point} from {current} to {value}{unit}"
                            else:
                                action_text = f"Set {point} to {value}{unit}"
                        else:
                            action_text = (
                                action_obj.get("type", "")
                                or rec.get("reason", "")
                                or f"Take action: {rec.get('action_type')}"
                            )
                    else:
                        action_text = str(action_obj) if action_obj else f"Take action: {rec.get('action_type')}"
                    # The full SENTRY advisory text is in the reason field
                    full_advisory = rec.get("reason") or ""
                    # Equipment this recommendation applies to
                    equipment = rec.get("target_equipment") or ""
                    # Optimisation goal (cost/comfort/profile)
                    goal = rec.get("profile") or rec.get("action_type", "") or None
                    recommendations.append(
                        {
                            "id": rec.get("id"),
                            "equipment": equipment,
                            "action_type": rec.get("action_type", "unknown"),
                            "status": rec.get("status"),
                            "priority": priority,
                            "confidence": confidence,
                            "recommended_action": action_text,
                            "full_advisory": full_advisory,
                            "goal": goal,
                            "projected_saving_zar": projected_saving_zar,
                            "created_at": rec.get("timestamp"),
                        }
                    )

            return {
                "site_id": site_code,
                "count": len(recommendations),
                "status_filter": status,
                "recommendations": recommendations,
            }
        except Exception as e:
            logger.error(f"get_recommendations failed: {e}")
            return {"error": str(e)}

    async def get_curtailable_load(
        self,
        site_id: str,
        min_priority: int = 3,
        include_zones: bool = False,
    ) -> dict[str, Any]:
        """Get real-time curtailable HVAC load signal for a site."""
        site_code = self._get_site_code(site_id)
        if not site_code:
            return {"error": "Invalid site_id"}
        try:
            service = get_demand_response_service()
            result = await service.get_curtailable_load(
                site_id=site_code,
                min_priority=min_priority,
                include_zones=include_zones,
            )
            return {
                "site_id": site_code,
                "curtailable_load_kw": result.curtailable_load_kw,
                "safe_duration_minutes": result.safe_duration_minutes,
                "confidence": result.confidence,
                "limiting_factor": result.limiting_factor,
                "ddmp_eligible": result.ddmp_eligible,
                "ddmp_threshold_kw": 500,
                "zone_breakdown": [
                    {"zone_id": z.zone_id, "zone_name": z.zone_name, "curtailable_kw": z.curtailable_kw}
                    for z in (result.zone_breakdown or [])
                ]
                if include_zones
                else [],
                "data_freshness": "live",
            }
        except Exception as e:
            err_str = str(e)
            # Graceful degradation: 503 means no live sensor data
            if "503" in err_str or "Insufficient live sensor data" in err_str:
                return {
                    "site_id": site_code,
                    "curtailable_load_kw": None,
                    "safe_duration_minutes": None,
                    "confidence": 0.0,
                    "limiting_factor": "no_live_sensor_data",
                    "ddmp_eligible": False,
                    "ddmp_threshold_kw": 500,
                    "data_freshness": "unavailable",
                    "data_freshness_warning": (
                        "Live sensor data unavailable for demand response calculation. "
                        "Connect BMS integration for real-time curtailable load signal."
                    ),
                    "zone_breakdown": [],
                }
            logger.error(f"get_curtailable_load failed: {e}")
            return {"error": err_str}

    async def get_odse_export(
        self,
        site_id: str,
        start: str,
        end: str,
        equipment_id: str | None = None,
    ) -> dict[str, Any]:
        """Export energy timeseries data in ODS-E v0.4.0 format."""
        site_code = self._get_site_code(site_id)
        if not site_code:
            return {"error": "Invalid site_id"}
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            result = await odse_service.export_timeseries(
                site_id=site_code,
                start=start_dt,
                end=end_dt,
                equipment_id=equipment_id,
            )
            return {
                "site_id": site_code,
                "schema_version": result.schema_version,
                "record_count": result.record_count,
                "exported_at": result.exported_at,
                "first_records": [
                    {"timestamp": r.timestamp, "kWh": r.kWh, "direction": r.direction} for r in result.records[:3]
                ],
            }
        except Exception as e:
            logger.error(f"get_odse_export failed: {e}")
            return {"error": str(e)}

    async def trace_recommendation(self, recommendation_id: str) -> dict[str, Any]:
        """Trace a recommendation's origin, ML model, and execution status."""
        client = _get_supabase_client()
        if not client:
            return {"error": "Supabase not available"}

        try:
            # Get recommendation
            rec_result = client.table("recommendations").select("*").eq("id", recommendation_id).limit(1).execute()
            if not rec_result.data:
                return {"error": f"Recommendation not found: {recommendation_id}"}

            rec = rec_result.data[0]

            # Cross-reference live equipment health
            live_health = None
            live_status = None
            equipment_code = rec.get("target_equipment")
            if equipment_code:
                try:
                    eq_result = (
                        client.table("equipment")
                        .select("health_score, status, updated_at")
                        .eq("code", equipment_code)
                        .limit(1)
                        .execute()
                    )
                    if eq_result.data:
                        live_health = eq_result.data[0].get("health_score")
                        live_status = eq_result.data[0].get("status")
                except Exception as e:
                    logger.debug(f"Live health lookup failed for {equipment_code}: {e}")

            # Get predictions for the target equipment
            predictions = []
            try:
                pred_result = (
                    client.table("predictions")
                    .select("prediction_type, contributing_factors, confidence, probability_percent, severity")
                    .eq("equipment_id", rec.get("target_equipment"))
                    .order("created_at", desc=True)
                    .limit(5)
                    .execute()
                )
                if pred_result.data:
                    predictions = pred_result.data
            except Exception:
                pass

            # Build triggered_by from contributing_factors
            triggered_by = []
            if predictions and predictions[0].get("contributing_factors"):
                factors = predictions[0].get("contributing_factors", [])
                if isinstance(factors, list):
                    for f in factors[:5]:
                        if isinstance(f, dict):
                            triggered_by.append(f.get("factor", str(f)))
                        else:
                            triggered_by.append(str(f))

            # Calculate confidence breakdown
            ml_score = rec.get("confidence_score", 0.0)
            source_type = rec.get("source_type", "unknown")
            final_confidence = ml_score  # Raw score — trust_weight is governance metadata, not a penalty

            # Get predicted outcome from execution_result or expected_impact
            predicted_outcome = "unknown"
            if rec.get("execution_result"):
                predicted_outcome = rec["execution_result"].get("status", "completed")
            elif rec.get("expected_impact"):
                ei = rec["expected_impact"]
                if isinstance(ei, dict):
                    predicted_outcome = f"Expected savings: R{ei.get('cost_zar', 0):,.0f}"

            return {
                "recommendation": f"{rec.get('action_type')}: {rec.get('reason', 'No reason provided')}",
                "triggered_by": triggered_by or ["Rule-based trigger (no ML factors)"],
                "ml_model_used": rec.get("source", "unknown"),
                "confidence_breakdown": {
                    "ml_score": ml_score,
                    "source_type": source_type,
                    "final": final_confidence,
                    "note": "Raw confidence score. Trust weight is a governance phase indicator, not a score penalty.",
                },
                "predicted_outcome": predicted_outcome,
                "execution_status": rec.get("status", "unknown"),
                "live_equipment_health": {
                    "health_score": live_health,
                    "status": live_status,
                    "note": "Current live value — may differ from snapshot at recommendation creation time",
                },
            }
        except Exception as e:
            logger.error(f"trace_recommendation failed: {e}")
            return {"error": str(e)}

    async def inspect_equipment(self, site_id: str, equipment_id: str) -> dict[str, Any]:
        """Get detailed equipment information."""
        client = _get_supabase_client()
        if not client:
            return {"error": "Supabase not available"}

        try:
            # Get equipment by code (globally unique, no site_id join needed)
            equip_result = client.table("equipment").select("*").eq("code", equipment_id).limit(1).execute()
            if not equip_result.data:
                return {"error": f"Equipment not found: {equipment_id}"}

            equip = equip_result.data[0]
            equip_uuid = equip.get("id")  # Equipment UUID for joins

            # Calculate age
            install_date = equip.get("install_date")
            age_years = "unknown"
            if install_date:
                try:
                    from datetime import datetime

                    if isinstance(install_date, str):
                        install = datetime.fromisoformat(install_date.replace("Z", "+00:00"))
                        age_years = round((datetime.now() - install).days / 365, 1)
                except Exception:
                    pass

            # Get open alerts count (alerts use equipment UUID)
            alerts_result = (
                client.table("alerts").select("id").eq("equipment_id", equip_uuid).eq("status", "active").execute()
            )
            open_alerts = len(alerts_result.data) if alerts_result.data else 0

            # Get active predictions count (predictions use equipment UUID)
            # ⚠️ MUST filter by status='active' — resolved/work_order_raised are not current risks
            preds_result = (
                client.table("predictions")
                .select("id, probability_percent, severity, timeframe_days")
                .eq("equipment_id", equip_uuid)
                .eq("status", "active")
                .order("probability_percent", desc=True)
                .execute()
            )
            active_predictions = []
            if preds_result.data:
                for p in preds_result.data:
                    active_predictions.append(
                        {
                            "probability": p.get("probability_percent"),
                            "severity": p.get("severity"),
                            "timeframe_days": p.get("timeframe_days"),
                        }
                    )

            # Calculate failure risk — use all signals, not just >70 threshold
            failure_risk = {"score": 0.0, "reason": "No risk factors detected", "timeline_hours": None}
            if active_predictions or open_alerts > 0:
                # Factor in prediction count, highest probability, and open alerts
                pred_count = len(active_predictions)
                highest_prob = max((p.get("probability_percent", 0) for p in active_predictions), default=0)
                # Score: weighted combination — 60% highest prob, 40% pred count signal
                base_score = (highest_prob * 0.6) + (min(pred_count * 15, 30) * 0.4)
                failure_risk["score"] = round(min(base_score / 100, 0.99), 2)
                if highest_prob >= 70:
                    failure_risk["reason"] = "High failure probability predicted"
                elif pred_count >= 2:
                    failure_risk["reason"] = f"{pred_count} active predictions — equipment requires attention"
                else:
                    failure_risk["reason"] = "Elevated risk — open alerts and predictions present"
                # Use the most urgent prediction timeline
                for p in active_predictions:
                    if p.get("probability_percent", 0) == highest_prob:
                        failure_risk["timeline_hours"] = (p.get("timeframe_days") or 30) * 24
                        break

            # Start with equipment state fields; live readings override below
            current_readings = {
                "run_status": equip.get("status", "unknown"),
                "health_score": equip.get("health_score"),
                "health_confidence": equip.get("health_confidence", "unknown"),
                "health_trend": equip.get("health_trend", "unknown"),
                "data_freshness_minutes": equip.get("data_freshness_minutes"),
                "last_ml_update": equip.get("last_ml_update"),
            }
            # If equipment has operating_data from SIMBIOT bridge, include it
            operating_data = equip.get("operating_data") or {}
            has_live_telemetry = bool(operating_data)
            if operating_data:
                for k, v in operating_data.items():
                    if v is not None:
                        current_readings[k] = v

            # Query live sensor readings from Supabase (WireGuard bridge data)
            # equipment_sensor_readings table: equipment_id=equipment code, sensor_type, value
            try:
                sensor_map = {}
                equip_type = equip.get("type", "").lower()
                if "chiller" in equip_type:
                    sensor_map = {
                        "supply_temp_c": "chw_supply_temp",
                        "return_temp_c": "chw_return_temp",
                        "compressor_current_1": "compressor_current_1",
                        "compressor_current_2": "compressor_current_2",
                    }
                elif "ahu" in equip_type or "air" in equip_type:
                    sensor_map = {
                        "supply_temp_c": "supply_air_temp",
                        "return_temp_c": "return_air_temp",
                        "fan_speed": "fan_speed_pct",
                    }
                elif "cooling_tower" in equip_type or "ct" in equip_type:
                    sensor_map = {
                        "fan_speed": "fan_speed_pct",
                    }

                if sensor_map:
                    # Map equipment code to sensor reading ID (WireGuard bridge uses abbreviated codes)
                    # Fallback chain tries common abbreviation patterns
                    sensor_equip_id = equipment_id

                    if equipment_id.endswith("-B01"):
                        base = equipment_id[:-4]  # S002-CHILLER-B01 → S002-CHILLER or S002-CT-B01 → S002-CT
                        for variant in (f"{base}-B1-001", f"{base}-R-001", f"{base}-001", equipment_id):
                            check = (
                                client.table("equipment_sensor_readings")
                                .select("id")
                                .eq("equipment_id", variant)
                                .limit(1)
                                .execute()
                            )
                            if check.data:
                                sensor_equip_id = variant
                                break
                    elif equipment_id.endswith("-R01"):
                        base = equipment_id[:-4]
                        for variant in (f"{base}-R-001", f"{base}-001", equipment_id):
                            check = (
                                client.table("equipment_sensor_readings")
                                .select("id")
                                .eq("equipment_id", variant)
                                .limit(1)
                                .execute()
                            )
                            if check.data:
                                sensor_equip_id = variant
                                break

                    for field_key, sensor_type in sensor_map.items():
                        if current_readings.get(field_key) is None:
                            reading = (
                                client.table("equipment_sensor_readings")
                                .select("value, recorded_at")
                                .eq("equipment_id", sensor_equip_id)
                                .eq("sensor_type", sensor_type)
                                .order("recorded_at", desc=True)
                                .limit(1)
                                .execute()
                            )
                            if reading.data:
                                current_readings[field_key] = reading.data[0]["value"]
                    current_readings["data_source"] = "supabase"

                # Per-equipment power estimation for chillers (Option C):
                # If compressor current readings exist, estimate power_kw from them.
                if "chiller" in equip_type:
                    c1 = current_readings.get("compressor_current_1")
                    c2 = current_readings.get("compressor_current_2")
                    if c1 is not None and c2 is not None:
                        VOLTAGE = 380.0
                        POWER_FACTOR = 0.85
                        estimated_power_kw = (float(c1) + float(c2)) * VOLTAGE * 1.732 * POWER_FACTOR / 1000.0
                        current_readings["power_kw"] = round(estimated_power_kw, 2)
                        current_readings["power_source"] = "estimated_from_compressor_current"
                        current_readings["power_note"] = "Estimated from compressor current readings — ±15% accuracy"

                # Fallback for chillers/AHUs without compressor current data:
                # don't attribute aggregate building HVAC power to individual equipment.
                if current_readings.get("power_kw") is None and ("chiller" in equip_type or "ahu" in equip_type):
                    current_readings["power_kw"] = None
                    current_readings["power_source"] = "not_metered_individually"
                    current_readings["power_note"] = "Individual equipment power metering not configured for this site"

            except Exception as e:
                logger.debug(f"Failed to query equipment_sensor_readings: {e}")
                current_readings["data_source"] = current_readings.get("data_source", "unavailable")

            # Legacy InfluxDB fallback (token_present=False in production)
            if (
                current_readings.get("data_source") == "unavailable"
                or current_readings.get("data_source") == "influxdb_unavailable"
            ):
                try:
                    from app.services.influxdb_service import get_influxdb_service

                    influx = get_influxdb_service()
                    if influx._available and influx._client and influx._token_present:
                        eq_uuid = equip.get("id")
                        influx_sensor_map = {
                            "supply_temp_c": "supply_water_temp",
                            "return_temp_c": "return_water_temp",
                            "power_kw": "active_power",
                            "run_hours": "run_hours",
                        }
                        for field_key, sensor_type in influx_sensor_map.items():
                            if current_readings.get(field_key) is None:
                                readings = influx.query_raw(eq_uuid, sensor_type)
                                if readings:
                                    latest = readings[-1]
                                    current_readings[field_key] = latest.get("value")
                        current_readings["data_source"] = "influxdb"
                except Exception:
                    pass

            # Get last updated from hvac_zones if applicable
            last_updated = equip.get("updated_at") or equip.get("created_at")

            return {
                "equipment_name": equip.get("name"),
                "type": equip.get("type"),
                "age_years": age_years,
                "manufacturer": equip.get("manufacturer"),
                "model": equip.get("model"),
                "current_readings": current_readings,
                "health_score": equip.get("health_score"),
                "status": equip.get("status"),
                "maintenance_history": {"last_service": equip.get("last_service")},
                "failure_risk": failure_risk,
                "open_alerts": open_alerts,
                "active_predictions": len(active_predictions),
                "last_updated": last_updated,
            }
        except Exception as e:
            logger.error(f"inspect_equipment failed: {e}")
            return {"error": str(e)}

    async def get_roi_summary(self, site_id: str, metric: str = "all") -> dict[str, Any]:
        """Get ROI metrics for executed recommendations."""
        client = _get_supabase_client()
        if not client:
            return {"error": "Supabase not available"}

        site_code = self._get_site_code(site_id)
        try:
            # Get executed recommendations with expected_impact (recommendations uses site-002 format)
            recs_result = (
                client.table("recommendations")
                .select("expected_impact, actual_saving_zar, actual_value_set, action_type, timestamp, executed_at")
                .eq("site_id", site_code)
                .in_("status", ["executed", "auto_executed"])
                .eq("shadow_mode", False)
                .order("executed_at", desc=True)
                .limit(100)
                .execute()
            )

            total_savings_zar = 0.0
            verified_savings_zar = 0.0
            estimated_savings_zar = 0.0
            total_energy_kwh = 0.0
            maintenance_saved_zar = 0.0
            uptime_improvement = 0.0
            count = len(recs_result.data) if recs_result.data else 0
            verified_count = 0

            if recs_result.data:
                for rec in recs_result.data:
                    ei = rec.get("expected_impact") or {}
                    actual = rec.get("actual_saving_zar")
                    if actual:
                        # Verified — actual saving measured after outcome verification
                        total_savings_zar += float(actual)
                        verified_savings_zar += float(actual)
                        verified_count += 1
                    elif isinstance(ei, dict) and ei.get("cost_zar"):
                        # Estimated — predicted at recommendation creation, not yet verified
                        total_savings_zar += float(ei.get("cost_zar", 0))
                        estimated_savings_zar += float(ei.get("cost_zar", 0))
                    # Accumulate secondary metrics from expected_impact regardless
                    if isinstance(ei, dict):
                        total_energy_kwh += float(ei.get("energy_kwh", 0))
                        maintenance_saved_zar += float(ei.get("maintenance_saved_zar", 0))
                        uptime_improvement += float(ei.get("uptime_hours", 0))

            # Calculate confidence based on sample size
            confidence = min(0.5 + (count * 0.02), 0.95) if count > 0 else 0.0

            # Determine time period
            time_period = "Last 30 days"
            if recs_result.data:
                try:
                    from datetime import datetime

                    timestamps = [r.get("executed_at") for r in recs_result.data if r.get("executed_at")]
                    if timestamps:
                        oldest = min(datetime.fromisoformat(t.replace("Z", "+00:00")) for t in timestamps if t)
                        days_span = (datetime.now() - oldest).days
                        time_period = f"Last {days_span} days"
                except Exception:
                    pass

            result = {
                "metric": metric,
                "value_zar": total_savings_zar,
                "verified_savings_zar": round(verified_savings_zar, 2),
                "estimated_savings_zar": round(estimated_savings_zar, 2),
                "verified_count": verified_count,
                "recommendation_count": count,
                "confidence": confidence,
                "comparison_to_baseline_pct": round((confidence - 0.5) * 100, 1) if confidence > 0.5 else 0,
                "time_period": time_period,
            }

            if metric in ("energy", "all"):
                result["breakdown"] = result.get("breakdown", {})
                result["breakdown"]["energy_kwh"] = round(total_energy_kwh, 2)
                result["breakdown"]["energy_cost_zar"] = round(total_savings_zar, 2)
            if metric in ("maintenance", "all"):
                result["breakdown"] = result.get("breakdown", {})
                result["breakdown"]["maintenance_saved_zar"] = round(maintenance_saved_zar, 2)
            if metric in ("uptime", "all"):
                result["breakdown"] = result.get("breakdown", {})
                result["breakdown"]["uptime_improvement_pct"] = round(uptime_improvement, 2)

            return result
        except Exception as e:
            logger.error(f"get_roi_summary failed: {e}")
            return {"error": str(e)}

    async def analyze_impact(self, recommendation_id: str) -> dict[str, Any]:
        """Analyze predicted and actual impact of a recommendation."""
        client = _get_supabase_client()
        if not client:
            return {"error": "Supabase not available"}

        try:
            # Get recommendation
            rec_result = client.table("recommendations").select("*").eq("id", recommendation_id).limit(1).execute()
            if not rec_result.data:
                return {"error": f"Recommendation not found: {recommendation_id}"}

            rec = rec_result.data[0]
            ei = rec.get("expected_impact") or {}

            # Get predictions for equipment
            predictions = []
            try:
                pred_result = (
                    client.table("predictions")
                    .select("probability_percent, severity, timeframe_days, contributing_factors")
                    .eq("equipment_id", rec.get("target_equipment"))
                    .order("created_at", desc=True)
                    .limit(10)
                    .execute()
                )
                if pred_result.data:
                    predictions = pred_result.data
            except Exception:
                pass

            # Build risk trajectory
            risk_trajectory = []
            if predictions:
                for i, p in enumerate(predictions[:24]):  # 24-hour trajectory
                    risk_trajectory.append(
                        {
                            "hour": i,
                            "risk_level": p.get("severity", "medium"),
                        }
                    )

            # Get side effects from execution_result
            side_effects = []
            if rec.get("execution_result"):
                er = rec["execution_result"]
                if isinstance(er, dict) and er.get("side_effects"):
                    side_effects = er.get("side_effects", [])

            # Calculate comfort impact
            comfort_impact = "neutral"
            if isinstance(ei, dict):
                comfort_delta = ei.get("comfort_delta")
                if comfort_delta:
                    comfort_impact = "improved" if comfort_delta > 0 else "degraded"

            return {
                "recommendation": f"{rec.get('action_type')}: {rec.get('reason', '')}",
                "predicted_energy_impact": {
                    "savings_kwh": ei.get("energy_kwh", 0) if isinstance(ei, dict) else 0,
                    "savings_zar": ei.get("cost_zar", 0) if isinstance(ei, dict) else 0,
                },
                "comfort_impact": comfort_impact,
                "equipment_stress": ei.get("equipment_stress", "minimal") if isinstance(ei, dict) else "unknown",
                "risk_trajectory": risk_trajectory or [{"hour": 0, "risk_level": rec.get("risk_level", "low")}],
                "confidence": rec.get("confidence_score", 0.0),
                "side_effects": side_effects,
            }
        except Exception as e:
            logger.error(f"analyze_impact failed: {e}")
            return {"error": str(e)}

    async def compare_sites(self, metric: str) -> dict[str, Any]:
        """Compare metrics across all sites."""
        client = _get_supabase_client()
        if not client:
            return {"error": "Supabase not available"}

        try:
            # Get all sites
            sites_result = client.table("sites").select("id, code, name").execute()
            sites_data = sites_result.data if sites_result.data else []

            sites_comparison = []

            # Build comparison based on metric
            if metric == "status":
                for site in sites_data:
                    site_code = site.get("code")
                    site_uuid = site.get("id")
                    # Get alert counts (alerts uses site UUID)
                    alerts_result = (
                        client.table("alerts")
                        .select("id, severity")
                        .eq("site_id", site_uuid)
                        .eq("status", "active")
                        .execute()
                    )
                    critical = sum(1 for a in (alerts_result.data or []) if a.get("severity") == "critical")
                    warnings = sum(1 for a in (alerts_result.data or []) if a.get("severity") == "warning")

                    status = "green"
                    if critical > 0:
                        status = "red"
                    elif warnings > 0:
                        status = "amber"

                    sites_comparison.append(
                        {
                            "site_id": site_code,
                            "site_name": site.get("name"),
                            "value": None,
                            "status": status,
                            "trend": "stable",
                        }
                    )
            else:
                # Default: just list sites with basic info
                for site in sites_data:
                    sites_comparison.append(
                        {
                            "site_id": site.get("code"),
                            "site_name": site.get("name"),
                            "value": None,
                            "status": "unknown",
                            "trend": "unknown",
                        }
                    )

            # Determine best/worst performers
            best = sites_comparison[0] if sites_comparison else {}
            worst = sites_comparison[-1] if sites_comparison else {}

            return {
                "metric": metric,
                "sites": sites_comparison,
                "best_performer": best.get("site_name", "N/A"),
                "worst_performer": worst.get("site_name", "N/A"),
                "average": "N/A",
            }
        except Exception as e:
            logger.error(f"compare_sites failed: {e}")
            return {"error": str(e)}

    async def search_knowledge(self, query: str, doc_type: str = None, limit: int = 5) -> dict[str, Any]:
        """Search equipment knowledge base using vector similarity."""
        vector_db = self._get_vector_db_service()
        if not vector_db:
            return {"error": "VectorDB service not available"}

        try:
            results = vector_db.search_knowledge(
                query=query,
                n_results=limit,
                knowledge_type=doc_type,
                similarity_threshold=0.3,
            )

            formatted_results = []
            for r in results:
                formatted_results.append(
                    {
                        "title": r.get("title", "Untitled"),
                        "content": r.get("description", r.get("content", ""))[:500],
                        "source": r.get("source", "knowledge_base"),
                        "relevance_score": round(r.get("similarity", 0.0) * 100, 1),
                        "doc_type": r.get("knowledge_type", "unknown"),
                    }
                )

            return {
                "results": formatted_results,
                "synthesis_hint": "Review relevant diagnostic steps and solution sections for the most relevant matches.",
            }
        except Exception as e:
            logger.error(f"search_knowledge failed: {e}")
            return {"error": str(e)}

    async def get_knowledge_detail(self, topic: str, detail_level: str = "full") -> dict[str, Any]:
        """Get detailed knowledge article by topic or code."""
        client = _get_supabase_client()
        if not client:
            return {"error": "Supabase not available"}

        try:
            # Search by title or code
            result = (
                client.table("equipment_knowledge")
                .select("*")
                .or_(f"title.ilike.%{topic}%,code.ilike.%{topic}%")
                .limit(1)
                .execute()
            )

            if not result.data:
                return {"error": f"Knowledge topic not found: {topic}"}

            k = result.data[0]

            if detail_level == "summary":
                content = k.get("description", "")[:300]
            else:
                content = k.get("description", "")
                if detail_level == "examples":
                    if k.get("diagnostic_steps"):
                        content += "\n\n## Diagnostic Steps\n" + "\n".join(f"- {s}" for s in k["diagnostic_steps"])
                    if k.get("solution"):
                        content += "\n\n## Solution\n" + k["solution"]

            # Get related topics
            related = []
            if k.get("equipment_type"):
                related_result = (
                    client.table("equipment_knowledge")
                    .select("title, code")
                    .eq("equipment_type", k["equipment_type"])
                    .neq("code", k.get("code"))
                    .limit(3)
                    .execute()
                )
                if related_result.data:
                    related = [{"title": r.get("title"), "topic": r.get("code")} for r in related_result.data]

            return {
                "topic": k.get("title"),
                "content": content,
                "related_topics": related,
                "examples": k.get("symptoms", []) if detail_level == "examples" else [],
            }
        except Exception as e:
            logger.error(f"get_knowledge_detail failed: {e}")
            return {"error": str(e)}

    # ==========================================================================
    # Work Order Tools
    # ==========================================================================

    def _get_complaint_handler(self):
        """Get ComfortComplaintHandler instance."""
        try:
            from app.services.complaint_handler import get_complaint_handler

            return get_complaint_handler()
        except Exception as e:
            logger.warning(f"ComplaintHandler unavailable: {e}")
            return None

    async def submit_complaint(self, desk_id: str, complaint_type: str) -> dict[str, Any]:
        """Handle a comfort complaint from a desk user."""
        handler = self._get_complaint_handler()
        if not handler:
            return {"error": "Complaint handler service unavailable"}

        try:
            diagnosis = handler.handle_complaint(desk_id, complaint_type)
            return diagnosis.to_dict()
        except Exception as e:
            logger.error(f"submit_complaint failed: {e}")
            return {"error": str(e)}

    async def control_equipment(
        self,
        equipment_id: str,
        point: str,
        value: float,
        reason: str = "MCP direct control in supervised mode",
    ) -> dict[str, Any]:
        """Write a control value to BMS equipment.

        Governance:
        - supervised mode: write directly via device_manager (no approval needed)
        - auto mode: low/medium risk writes via device_manager, high/critical rejected
        - Always validates safety and logs via ApprovalService._write_device_value()
        """
        client = _get_supabase_client()
        if not client:
            return {"error": "Supabase not available"}

        try:
            # Resolve equipment -> site for control_enabled check
            # Try zones table first (zone IDs like "Zone-201" map to a site)
            control_enabled = False
            site_code = None

            try:
                zone_result = client.table("zones").select("site_id").eq("zone_id", equipment_id).limit(1).execute()
                if zone_result.data:
                    site_uuid = zone_result.data[0].get("site_id")
                    site_result = (
                        client.table("sites").select("code, control_enabled").eq("id", site_uuid).limit(1).execute()
                    )
                    if site_result.data:
                        site_code = site_result.data[0]["code"]
                        control_enabled = site_result.data[0].get("control_enabled", False)
            except Exception:
                pass

            # Fallback: parse site prefix from equipment_id
            if not site_code:
                parts = equipment_id.split("-")
                if len(parts) >= 2 and parts[0] == "site":
                    site_code = f"{parts[0]}-{parts[1]}"
                elif len(parts) >= 2 and parts[0] in ("S002"):
                    site_code = f"site-{parts[0][-3:].lower()}"
                else:
                    # Default to site-002 for zone-level equipment
                    site_code = "site-002"

            # Final site lookup if not already resolved
            if not control_enabled:
                site_result = (
                    client.table("sites").select("code, control_enabled").eq("code", site_code).limit(1).execute()
                )
                if not site_result.data:
                    return {"error": f"Site not found: {site_code}"}
                control_enabled = site_result.data[0].get("control_enabled", False)

            # Phase gate: control writes require supervised or automatic mode
            from app.models.onboarding_phase import effective_phase, phase_allows

            current_phase = await effective_phase(site_code)
            if not phase_allows(current_phase, "approve_reject"):
                return {
                    "success": False,
                    "error": f"Control not permitted in {current_phase} phase — requires supervised or automatic mode.",
                    "site_code": site_code,
                    "current_phase": current_phase,
                }

            if not control_enabled:
                return {
                    "success": False,
                    "error": f"Control disabled for {site_code}. Set control_enabled=true on site to allow writes.",
                    "site_code": site_code,
                }

            # Use ApprovalService for safe write with COV verification
            from app.services.approval_service import get_approval_service

            approval_svc = get_approval_service()

            result = await approval_svc._execute_device_write(equipment_id, point, value)

            if result.get("success"):
                logger.info(f"MCP control: {equipment_id}.{point}={value} by {reason}")
                return {
                    "success": True,
                    "equipment_id": equipment_id,
                    "point": point,
                    "value_written": value,
                    "cov_verified": True,
                    "message": f"Successfully set {point} to {value} on {equipment_id}",
                    "reason": reason,
                }
            return {
                "success": False,
                "error": result.get("error", "Write failed"),
                "equipment_id": equipment_id,
                "point": point,
            }
        except Exception as e:
            logger.error(f"control_equipment failed: {e}")
            return {"error": str(e)}

    async def get_work_orders(
        self,
        site_id: str,
        status: str = "all",
        limit: int = 10,
    ) -> dict[str, Any]:
        """List work orders for a site."""
        client = _get_supabase_client()
        if not client:
            return {"error": "Supabase not available"}

        try:
            site_code = self._get_site_code(site_id)
            query = (
                client.table("work_orders")
                .select("id, code, title, priority, status, assigned_to, equipment_id, created_at")
                .eq("site_id", site_code)
            )

            if status != "all":
                query = query.eq("status", status)

            result = query.order("created_at", desc=True).limit(limit).execute()

            work_orders = []
            for wo in result.data or []:
                work_orders.append(
                    {
                        "id": wo.get("id"),
                        "code": wo.get("code"),
                        "title": wo.get("title"),
                        "priority": wo.get("priority"),
                        "status": wo.get("status"),
                        "assigned_to": wo.get("assigned_to"),
                        "created_at": wo.get("created_at"),
                    }
                )

            return {
                "site_id": site_id,
                "count": len(work_orders),
                "work_orders": work_orders,
            }
        except Exception as e:
            logger.error(f"get_work_orders failed: {e}")
            return {"error": str(e)}

    async def get_work_order(self, work_order_id: str) -> dict[str, Any]:
        """Get a specific work order by ID."""
        client = _get_supabase_client()
        if not client:
            return {"error": "Supabase not available"}

        try:
            result = client.table("work_orders").select("*").eq("id", work_order_id).limit(1).execute()
            if result.data:
                wo = result.data[0]
                return {
                    "id": wo.get("id"),
                    "code": wo.get("code"),
                    "title": wo.get("title"),
                    "priority": wo.get("priority"),
                    "status": wo.get("status"),
                    "assigned_to": wo.get("assigned_to"),
                    "site_id": wo.get("site_id"),
                    "equipment_id": wo.get("equipment_id"),
                    "description": wo.get("description"),
                    "notes": wo.get("notes"),
                    "created_at": wo.get("created_at"),
                    "updated_at": wo.get("updated_at"),
                }
            return {"error": f"Work order not found: {work_order_id}"}
        except Exception as e:
            logger.error(f"get_work_order failed: {e}")
            return {"error": str(e)}

    async def update_work_order(
        self,
        work_order_id: str,
        status: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Update a work order's status or notes."""
        client = _get_supabase_client()
        if not client:
            return {"error": "Supabase not available"}

        try:
            updates = {}
            if status:
                updates["status"] = status
            if notes:
                updates["notes"] = notes

            if not updates:
                return {"error": "No updates provided"}

            result = client.table("work_orders").update(updates).eq("id", work_order_id).execute()

            if result.data:
                return {
                    "work_order_id": work_order_id,
                    "status": status,
                    "updated": True,
                    "message": f"Work order {work_order_id} updated successfully",
                }
            return {"error": f"Work order not found: {work_order_id}"}
        except Exception as e:
            logger.error(f"update_work_order failed: {e}")
            return {"error": str(e)}

    async def call_tool(self, tool_name: str, **kwargs) -> dict[str, Any]:
        """Execute a tool by name."""
        if tool_name == "search":
            return await self.search(kwargs.get("query", ""))
        elif tool_name == "fetch":
            return await self.fetch(kwargs.get("id", ""))
        elif tool_name == "get_site_status":
            return await self.get_site_status(kwargs.get("site_id", ""))
        elif tool_name == "get_recommendations":
            return await self.get_recommendations(
                kwargs.get("site_id", ""),
                kwargs.get("limit", 5),
                kwargs.get("status", "pending"),
            )
        elif tool_name == "trace_recommendation":
            return await self.trace_recommendation(kwargs.get("recommendation_id", ""))
        elif tool_name == "inspect_equipment":
            return await self.inspect_equipment(kwargs.get("site_id", ""), kwargs.get("equipment_id", ""))
        elif tool_name == "get_roi_summary":
            return await self.get_roi_summary(kwargs.get("site_id", ""), kwargs.get("metric", "all"))
        elif tool_name == "analyze_impact":
            return await self.analyze_impact(kwargs.get("recommendation_id", ""))
        elif tool_name == "compare_sites":
            return await self.compare_sites(kwargs.get("metric", "status"))
        elif tool_name == "get_curtailable_load":
            return await self.get_curtailable_load(
                kwargs.get("site_id", ""),
                kwargs.get("min_priority", 3),
                kwargs.get("include_zones", False),
            )
        elif tool_name == "get_odse_export":
            return await self.get_odse_export(
                kwargs.get("site_id", ""),
                kwargs.get("start", ""),
                kwargs.get("end", ""),
                kwargs.get("equipment_id"),
            )
        elif tool_name == "search_knowledge":
            return await self.search_knowledge(kwargs.get("query", ""), kwargs.get("doc_type"), kwargs.get("limit", 5))
        elif tool_name == "get_knowledge_detail":
            return await self.get_knowledge_detail(kwargs.get("topic", ""), kwargs.get("detail_level", "full"))
        elif tool_name == "get_work_orders":
            return await self.get_work_orders(
                kwargs.get("site_id", ""),
                kwargs.get("status", "all"),
                kwargs.get("limit", 10),
            )
        elif tool_name == "get_work_order":
            return await self.get_work_order(kwargs.get("work_order_id", ""))
        elif tool_name == "ping":
            return await self.ping()
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def refresh_index(self):
        """Force refresh the document index."""
        self._ensure_index(force_refresh=True)

    def get_stats(self) -> dict[str, Any]:
        """Get index statistics."""
        self._ensure_index()

        type_counts = {}
        source_counts = {}
        for doc in self._documents:
            t = doc.get("doc_type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
            s = doc.get("metadata", {}).get("source", "unknown")
            source_counts[s] = source_counts.get(s, 0) + 1

        return {
            "total_documents": len(self._documents),
            "by_type": type_counts,
            "by_source": source_counts,
            "last_refresh": self._last_refresh.isoformat() if self._last_refresh else None,
        }


# Singleton instance
_openai_connector_server: OpenAIConnectorMCPServer | None = None


def get_openai_connector_server() -> OpenAIConnectorMCPServer:
    """Get or create singleton server instance."""
    global _openai_connector_server
    if _openai_connector_server is None:
        _openai_connector_server = OpenAIConnectorMCPServer()
    return _openai_connector_server
