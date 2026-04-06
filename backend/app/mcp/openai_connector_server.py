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
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# Data paths (fallback)
DATA_DIR = Path(__file__).parent.parent / "data"
DEVICES_FILE = Path(__file__).parent.parent / "services" / "bms_simulator" / "data" / "reference_devices.json"
EQUIPMENT_FILE = DATA_DIR / "equipment.json"
ALERTS_FILE = DATA_DIR / "alerts.json"
SITES_DIR = DATA_DIR / "sites"

# Base URL for document links (set from settings at runtime)
BASE_URL = None


def _load_json(filepath: Path) -> Any:
    """Load JSON file safely."""
    try:
        with open(filepath, "r") as f:
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

    def load_buildings(self) -> List[Dict[str, Any]]:
        """Load buildings from Supabase."""
        try:
            response = self.client.table("sites").select("*").execute()
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to load buildings from Supabase: {e}")
            return []

    def load_equipment(self) -> List[Dict[str, Any]]:
        """Load equipment from Supabase with building info (paginated)."""
        try:
            all_equipment = []
            page_size = 1000
            offset = 0

            while True:
                response = (
                    self.client.table("equipment")
                    .select("*, buildings(name, code)")
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

    def load_alerts(self) -> List[Dict[str, Any]]:
        """Load alerts from Supabase with related info."""
        try:
            response = (
                self.client.table("alerts")
                .select("*, equipment(name, code, type), buildings(name, code)")
                .order("created_at", desc=True)
                .limit(100)
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to load alerts from Supabase: {e}")
            return []

    def load_predictions(self) -> List[Dict[str, Any]]:
        """Load predictions from Supabase with related info (paginated)."""
        try:
            all_predictions = []
            page_size = 500
            offset = 0
            max_records = 2000  # Limit total predictions to avoid huge indexes

            while len(all_predictions) < max_records:
                response = (
                    self.client.table("predictions")
                    .select("*, equipment(name, code, type, manufacturer, model), buildings(name, code)")
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

    def load_work_orders(self) -> List[Dict[str, Any]]:
        """Load work orders from Supabase."""
        try:
            response = (
                self.client.table("work_orders")
                .select("*, equipment(name, code, type), buildings(name, code)")
                .order("created_at", desc=True)
                .limit(100)
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Failed to load work orders from Supabase: {e}")
            return []

    def load_documents(self) -> List[Dict[str, Any]]:
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


def _build_building_document(building: Dict, source: str = "supabase") -> Dict[str, Any]:
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
        "url": f"{BASE_URL}/buildings/{site_id}",
        "doc_type": "building",
        "metadata": {
            "site_id": site_id,
            "region": building.get("region"),
            "type": building.get("type"),
            "sqm": building.get("sqm"),
            "source": source,
        },
    }


def _build_equipment_document(equipment: Dict, source: str = "supabase") -> Dict[str, Any]:
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
        "url": f"{BASE_URL}/equipment/{equip_id}",
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


def _build_alert_document(alert: Dict, source: str = "supabase") -> Dict[str, Any]:
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
        "url": f"{BASE_URL}/alerts/{alert_id}",
        "doc_type": "alert",
        "metadata": {
            "alert_id": str(alert_id),
            "severity": alert.get("severity"),
            "status": alert.get("status"),
            "type": alert.get("type"),
            "source": source,
        },
    }


def _build_prediction_document(prediction: Dict, source: str = "supabase") -> Dict[str, Any]:
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
        "url": f"{BASE_URL}/predictions/{pred_id}",
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


def _build_work_order_document(wo: Dict, source: str = "supabase") -> Dict[str, Any]:
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
        "url": f"{BASE_URL}/work-orders/{wo_id}",
        "doc_type": "work_order",
        "metadata": {
            "work_order_id": str(wo_id),
            "priority": wo.get("priority"),
            "status": wo.get("status"),
            "source": source,
        },
    }


def _build_tech_document(doc: Dict, source: str = "supabase") -> Dict[str, Any]:
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
        "url": doc.get("source_url") or f"{BASE_URL}/documents/{doc_id}",
        "doc_type": "technical_document",
        "metadata": {
            "document_id": str(doc_id),
            "document_type": doc.get("document_type"),
            "equipment_type": doc.get("equipment_type"),
            "manufacturer": doc.get("manufacturer"),
            "source": source,
        },
    }


def _build_searchable_documents() -> List[Dict[str, Any]]:
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


def _simple_text_search(query: str, documents: List[Dict], limit: int = 10) -> List[Dict]:
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
        self._documents: Optional[List[Dict]] = None
        self._document_index: Optional[Dict[str, Dict]] = None
        self._last_refresh: Optional[datetime] = None
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

    def list_tools(self) -> List[Dict[str, Any]]:
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
        ]

    async def search(self, query: str) -> Dict[str, Any]:
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

    async def fetch(self, id: str) -> Dict[str, Any]:
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

    async def call_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Execute a tool by name."""
        if tool_name == "search":
            return await self.search(kwargs.get("query", ""))
        elif tool_name == "fetch":
            return await self.fetch(kwargs.get("id", ""))
        else:
            raise ValueError(f"Unknown tool: {tool_name}. Only 'search' and 'fetch' are available.")

    def refresh_index(self):
        """Force refresh the document index."""
        self._ensure_index(force_refresh=True)

    def get_stats(self) -> Dict[str, Any]:
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
_openai_connector_server: Optional[OpenAIConnectorMCPServer] = None


def get_openai_connector_server() -> OpenAIConnectorMCPServer:
    """Get or create singleton server instance."""
    global _openai_connector_server
    if _openai_connector_server is None:
        _openai_connector_server = OpenAIConnectorMCPServer()
    return _openai_connector_server
