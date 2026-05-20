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

logger = logging.getLogger(__name__)

# Data paths (fallback)
DATA_DIR = Path(__file__).parent.parent / "data"
DEVICES_FILE = Path(__file__).parent.parent / "services" / "bms_simulator" / "data" / "reference_devices.json"
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
            response = (
                self.client.table("work_orders")
                .select("*, equipment(name, code, type), sites(name, code)")
                .order("created_at", desc=True)
                .limit(100)
                .execute()
            )
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
                    "summary, keywords, failure_modes, source_url"
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
    if doc.get("failure_modes"):
        text_parts.append(f"Failure Modes: {', '.join(doc['failure_modes'])}")

    return {
        "id": f"document-{doc_id}",
        "title": f"Document: {doc.get('title', doc_id)}",
        "text": "\n".join(text_parts),
        "url": doc.get("source_url") or f"{BASE_URL}/api/documents/{doc_id}",
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
        if DEVICES_FILE.exists():
            devices = _load_json(DEVICES_FILE)
        if not devices and EQUIPMENT_FILE.exists():
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
                            "description": "Site identifier (e.g., S002, S005)",
                            "enum": ["S001", "S002", "S005"],
                        }
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
            # Category C: Work Orders + Controls
            {
                "name": "submit_complaint",
                "description": "Handle a comfort complaint by desk location. Maps desk to HVAC zone, diagnoses the issue, and returns actionable suggestions including equipment that can be adjusted. Use this when someone says they're too hot, too cold, stuffy, or drafty at a specific desk.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "desk_id": {"type": "string", "description": "Desk identifier (e.g., '204', 'L12-25', 'Desk 25'). Accepts partial formats like just the desk number."},
                        "complaint_type": {"type": "string", "description": "Type of discomfort", "enum": ["too_hot", "too_cold", "stuffy", "drafty"]},
                    },
                    "required": ["desk_id", "complaint_type"],
                },
            },
            {
                "name": "control_equipment",
                "description": "Write a control value to BMS equipment (setpoint, state, etc.) when in supervised mode. Returns updated value with COV verification. Use after submit_complaint to action a suggestion. Example: 'Set cooling setpoint to 22°C on Zone-201'.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "equipment_id": {"type": "string", "description": "Equipment ID to control (e.g., 'Zone-201', 'S002-FCU-L2-C'). Get from submit_complaint zone output."},
                        "point": {"type": "string", "description": "Point name to write (e.g., 'cooling_setpoint', 'occupied_setpoint', ' airflow')"},
                        "value": {"type": "number", "description": "Value to write (e.g., 22.0)"},
                        "reason": {"type": "string", "description": "Reason for the control action (for audit log)"},
                    },
                    "required": ["equipment_id", "point", "value"],
                },
            },
            {
                "name": "create_work_order",
                "description": "Create a new work order for equipment maintenance or repair.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "site_id": {"type": "string", "description": "Site identifier (e.g., S002)"},
                        "equipment_id": {"type": "string", "description": "Equipment code (e.g., S002-CHILLER-B01)"},
                        "title": {"type": "string", "description": "Work order title"},
                        "description": {"type": "string", "description": "Detailed description of work needed"},
                        "priority": {"type": "string", "description": "Priority level", "enum": ["low", "medium", "high", "urgent"]},
                        "assigned_to": {"type": "string", "description": "Technician name to assign to"},
                    },
                    "required": ["site_id", "title", "description"],
                },
            },
            {
                "name": "get_work_orders",
                "description": "List work orders for a site with optional status filter.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "site_id": {"type": "string", "description": "Site identifier (e.g., S002)"},
                        "status": {"type": "string", "description": "Filter by status", "enum": ["scheduled", "in_progress", "resolved", "verified", "all"]},
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
                "name": "update_work_order",
                "description": "Update a work order's status or milestone.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "work_order_id": {"type": "string", "description": "Work order UUID"},
                        "status": {"type": "string", "description": "New status", "enum": ["scheduled", "in_progress", "resolved", "verified"]},
                        "notes": {"type": "string", "description": "Work notes or resolution details"},
                    },
                    "required": ["work_order_id"],
                },
            },
        ]

    async def search(self, query: str) -> dict[str, Any]:
        """
        Search for documents matching query.

        Returns:
            {
                "results": [
                    {"id": "...", "title": "...", "url": "..."},
                    ...
                ]
            }
        """
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
        self._ensure_index()

        doc = self._document_index.get(id)

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
        if site_id.lower() in ("site-001", "site-002", "site-005"):
            return site_id.lower()
        if site_id.upper() in ("S001", "S002", "S005"):
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
                .select("id, code, name, health_score, status")
                .eq("site_id", site_uuid)
                .in_("status", ["warning", "critical", "fault"])
                .order("health_score", desc=False)
                .limit(10)
                .execute()
            )
            equipment_at_risk = []
            if equip_result.data:
                for eq in equip_result.data:
                    equipment_at_risk.append({
                        "id": eq.get("code") or eq.get("id"),
                        "name": eq.get("name"),
                        "risk_level": "high" if eq.get("status") == "critical" else "medium",
                    })

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

    async def trace_recommendation(self, recommendation_id: str) -> dict[str, Any]:
        """Trace a recommendation's origin, ML model, and execution status."""
        client = _get_supabase_client()
        if not client:
            return {"error": "Supabase not available"}

        try:
            # Get recommendation
            rec_result = (
                client.table("recommendations")
                .select("*")
                .eq("id", recommendation_id)
                .limit(1)
                .execute()
            )
            if not rec_result.data:
                return {"error": f"Recommendation not found: {recommendation_id}"}

            rec = rec_result.data[0]

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
            trust_weight = 0.8 if rec.get("source_type") == "ml_model" else 0.5
            final_confidence = round(ml_score * trust_weight, 3)

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
                    "trust_weight": trust_weight,
                    "final": final_confidence,
                },
                "predicted_outcome": predicted_outcome,
                "execution_status": rec.get("status", "unknown"),
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
            equip_result = (
                client.table("equipment")
                .select("*")
                .eq("code", equipment_id)
                .limit(1)
                .execute()
            )
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
                client.table("alerts")
                .select("id")
                .eq("equipment_id", equip_uuid)
                .eq("status", "active")
                .execute()
            )
            open_alerts = len(alerts_result.data) if alerts_result.data else 0

            # Get active predictions count (predictions use equipment UUID)
            preds_result = (
                client.table("predictions")
                .select("id, probability_percent, severity, timeframe_days")
                .eq("equipment_id", equip_uuid)
                .order("probability_percent", desc=True)
                .execute()
            )
            active_predictions = []
            if preds_result.data:
                for p in preds_result.data:
                    active_predictions.append({
                        "probability": p.get("probability_percent"),
                        "severity": p.get("severity"),
                        "timeframe_days": p.get("timeframe_days"),
                    })

            # Calculate failure risk
            failure_risk = {"score": 0.0, "reason": "No risk factors detected", "timeline_hours": None}
            if active_predictions:
                highest_prob = max(p.get("probability_percent", 0) for p in active_predictions)
                if highest_prob > 70:
                    failure_risk["score"] = highest_prob / 100
                    failure_risk["reason"] = "High failure probability predicted"
                    for p in active_predictions:
                        if p.get("probability") == highest_prob:
                            failure_risk["timeline_hours"] = (p.get("timeframe_days") or 30) * 24
                            break

            # Get last updated from hvac_zones if applicable
            last_updated = equip.get("updated_at") or equip.get("created_at")

            return {
                "equipment_name": equip.get("name"),
                "type": equip.get("type"),
                "age_years": age_years,
                "manufacturer": equip.get("manufacturer"),
                "model": equip.get("model"),
                "current_readings": {},  # Would join hvac_zones if equipment has zone linkage
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
                .select("expected_impact, action_type, timestamp, executed_at")
                .eq("site_id", site_code)
                .in_("status", ["executed", "auto_executed"])
                .eq("shadow_mode", False)
                .order("executed_at", desc=True)
                .limit(100)
                .execute()
            )

            total_savings_zar = 0.0
            total_energy_kwh = 0.0
            maintenance_saved_zar = 0.0
            uptime_improvement = 0.0
            count = len(recs_result.data) if recs_result.data else 0

            if recs_result.data:
                for rec in recs_result.data:
                    ei = rec.get("expected_impact") or {}
                    if isinstance(ei, dict):
                        total_savings_zar += float(ei.get("cost_zar", 0))
                        total_energy_kwh += float(ei.get("energy_kwh", 0))
                        maintenance_saved_zar += float(ei.get("maintenance_saved_zar", 0))
                        uptime_improvement += float(ei.get("uptime_hours", 0))

            # Calculate confidence based on sample size
            confidence = min(0.5 + (count * 0.02), 0.95) if count > 0 else 0.0

            # Determine time period
            time_period = "Last 30 days"
            if recs_result.data:
                try:
                    from datetime import datetime, timedelta
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
            rec_result = (
                client.table("recommendations")
                .select("*")
                .eq("id", recommendation_id)
                .limit(1)
                .execute()
            )
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
                    risk_trajectory.append({
                        "hour": i,
                        "risk_level": p.get("severity", "medium"),
                    })

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

                    sites_comparison.append({
                        "site_id": site_code,
                        "site_name": site.get("name"),
                        "value": None,
                        "status": status,
                        "trend": "stable",
                    })
            else:
                # Default: just list sites with basic info
                for site in sites_data:
                    sites_comparison.append({
                        "site_id": site.get("code"),
                        "site_name": site.get("name"),
                        "value": None,
                        "status": "unknown",
                        "trend": "unknown",
                    })

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
                formatted_results.append({
                    "title": r.get("title", "Untitled"),
                    "content": r.get("description", r.get("content", ""))[:500],
                    "source": r.get("source", "knowledge_base"),
                    "relevance_score": round(r.get("similarity", 0.0) * 100, 1),
                    "doc_type": r.get("knowledge_type", "unknown"),
                })

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

    def _get_work_order_repo(self):
        """Get WorkOrderRepository instance."""
        try:
            from app.database.repositories.work_order_repository import WorkOrderRepository
            return WorkOrderRepository()
        except Exception as e:
            logger.warning(f"WorkOrderRepository unavailable: {e}")
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
                    site_result = client.table("sites").select("code, control_enabled").eq("id", site_uuid).limit(1).execute()
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
                elif len(parts) >= 2 and parts[0] in ("S001", "S002", "S005"):
                    site_code = f"site-{parts[0][-3:].lower()}"
                else:
                    # Default to site-002 for zone-level equipment
                    site_code = "site-002"

            # Final site lookup if not already resolved
            if not control_enabled:
                site_result = client.table("sites").select("code, control_enabled").eq("code", site_code).limit(1).execute()
                if not site_result.data:
                    return {"error": f"Site not found: {site_code}"}
                control_enabled = site_result.data[0].get("control_enabled", False)

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

    async def create_work_order(
        self,
        site_id: str,
        equipment_id: str,
        title: str,
        description: str,
        priority: str = "medium",
        assigned_to: str | None = None,
    ) -> dict[str, Any]:
        """Create a new work order."""
        repo = self._get_work_order_repo()
        if not repo:
            return {"error": "Work order service unavailable"}

        try:
            work_order_data = {
                "title": title,
                "description": description,
                "priority": priority,
                "site_id": site_id,
                "equipment_code": equipment_id if equipment_id else None,
                "assigned_to": assigned_to,
                "created_by": "SENTINEL-MCP",
            }
            result = await repo.create_work_order(work_order_data)
            if result:
                return {
                    "work_order_id": result.get("id"),
                    "code": result.get("code"),
                    "status": result.get("status", "scheduled"),
                    "created_at": result.get("created_at"),
                    "message": f"Work order {result.get('code')} created successfully",
                }
            return {"error": "Failed to create work order"}
        except Exception as e:
            logger.error(f"create_work_order failed: {e}")
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
            query = client.table("work_orders").select(
                "id, code, title, priority, status, assigned_to, equipment_id, created_at"
            )

            if status != "all":
                query = query.eq("status", status)

            result = query.order("created_at", desc=True).limit(limit).execute()

            work_orders = []
            for wo in (result.data or []):
                work_orders.append({
                    "id": wo.get("id"),
                    "code": wo.get("code"),
                    "title": wo.get("title"),
                    "priority": wo.get("priority"),
                    "status": wo.get("status"),
                    "assigned_to": wo.get("assigned_to"),
                    "created_at": wo.get("created_at"),
                })

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
        repo = self._get_work_order_repo()
        if not repo:
            return {"error": "Work order service unavailable"}

        try:
            result = await repo.get_work_order(work_order_id)
            if result:
                return result
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
        elif tool_name == "search_knowledge":
            return await self.search_knowledge(kwargs.get("query", ""), kwargs.get("doc_type"), kwargs.get("limit", 5))
        elif tool_name == "get_knowledge_detail":
            return await self.get_knowledge_detail(kwargs.get("topic", ""), kwargs.get("detail_level", "full"))
        elif tool_name == "create_work_order":
            return await self.create_work_order(
                kwargs.get("site_id", ""),
                kwargs.get("equipment_id", ""),
                kwargs.get("title", ""),
                kwargs.get("description", ""),
                kwargs.get("priority", "medium"),
                kwargs.get("assigned_to"),
            )
        elif tool_name == "get_work_orders":
            return await self.get_work_orders(
                kwargs.get("site_id", ""),
                kwargs.get("status", "all"),
                kwargs.get("limit", 10),
            )
        elif tool_name == "get_work_order":
            return await self.get_work_order(kwargs.get("work_order_id", ""))
        elif tool_name == "update_work_order":
            return await self.update_work_order(
                kwargs.get("work_order_id", ""),
                kwargs.get("status"),
                kwargs.get("notes"),
            )
        elif tool_name == "submit_complaint":
            return await self.submit_complaint(
                kwargs.get("desk_id", ""),
                kwargs.get("complaint_type", ""),
            )
        elif tool_name == "control_equipment":
            return await self.control_equipment(
                kwargs.get("equipment_id", ""),
                kwargs.get("point", ""),
                kwargs.get("value", 0),
                kwargs.get("reason", "MCP direct control"),
            )
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
