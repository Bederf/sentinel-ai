"""REST API stub endpoints for Correlation & Issue Intelligence Layer.

Phase 155-01: Schema-first stubs. Returns valid response shapes with
placeholder data matching the correlation schema. No business logic.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["correlation"])


# ---------------------------------------------------------------------------
# Stub response data
# ---------------------------------------------------------------------------

_STUB_SIGNAL = {
    "signal_id": str(uuid.uuid4()),
    "status": "created",
    "source_module": "email_helpdesk",
    "signal_type": "complaint_email",
    "location_ref": "Fairlands/FA1/1Q4/MR10",
    "severity": "medium",
    "confidence": 0.85,
    "resolution_state": "active",
    "site_id": None,
    "is_managed": False,
    "site_resolution_status": "unresolved",
    "email_thread_id": None,
    "issue_cluster_id": None,
    "emits_multiple": False,
}

_STUB_CLUSTER = {
    "id": str(uuid.uuid4()),
    "title": "Fairlands meeting room availability conflict",
    "cluster_state": "escalated",
    "severity": "high",
    "escalation_level": "executive",
    "first_seen_at": "2026-01-05T14:30:00Z",
    "last_seen_at": "2026-03-06T14:20:00Z",
    "duration_days": 60,
    "confidence_score": 0.87,
    "likely_root_cause": "Block booking behaviour reducing effective room capacity",
    "site_id": None,
    "is_managed": False,
    "signal_count": 12,
    "entity_count": 9,
    "classifications": [
        {"domain": "space_optimisation", "confidence": 0.92},
        {"domain": "workplace_experience", "confidence": 0.81},
    ],
}


# ---------------------------------------------------------------------------
# Signal endpoints
# ---------------------------------------------------------------------------


@router.post("/signals/")
async def create_signal(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a new signal (stub)."""
    return _STUB_SIGNAL


@router.get("/signals/{signal_id}")
async def get_signal(signal_id: str) -> dict[str, Any]:
    """Get a signal by ID (stub)."""
    return {**_STUB_SIGNAL, "signal_id": signal_id}


# ---------------------------------------------------------------------------
# Cluster endpoints
# ---------------------------------------------------------------------------


@router.get("/clusters/")
async def list_clusters() -> list[dict[str, Any]]:
    """List all issue clusters (stub)."""
    return [_STUB_CLUSTER]


@router.get("/clusters/{cluster_id}")
async def get_cluster(cluster_id: str) -> dict[str, Any]:
    """Get a cluster by ID (stub)."""
    return {**_STUB_CLUSTER, "id": cluster_id}


@router.get("/clusters/{cluster_id}/signals")
async def get_cluster_signals(cluster_id: str) -> list[dict[str, Any]]:
    """Get signals for a cluster (stub)."""
    return [_STUB_SIGNAL]


@router.get("/clusters/{cluster_id}/graph")
async def get_cluster_graph(cluster_id: str) -> dict[str, Any]:
    """Get knowledge graph for a cluster (stub)."""
    return {
        "nodes": [
            {
                "id": str(uuid.uuid4()),
                "node_type": "cluster",
                "label": "Fairlands meeting room conflict",
                "severity": "high",
            },
            {
                "id": str(uuid.uuid4()),
                "node_type": "signal",
                "label": "Complaint — Shaun Grose",
                "signal_type": "complaint_email",
            },
            {
                "id": str(uuid.uuid4()),
                "node_type": "entity",
                "label": "FA1-1Q4-MR10",
                "entity_type": "room",
            },
            {
                "id": str(uuid.uuid4()),
                "node_type": "entity",
                "label": "Thandi Dineka",
                "entity_type": "person",
            },
        ],
        "edges": [
            {
                "id": str(uuid.uuid4()),
                "source": cluster_id,
                "target": str(uuid.uuid4()),
                "edge_type": "evidenced_by",
                "confidence": 0.91,
            },
            {
                "id": str(uuid.uuid4()),
                "source": str(uuid.uuid4()),
                "target": str(uuid.uuid4()),
                "edge_type": "involves",
                "confidence": 0.88,
            },
        ],
    }


@router.get("/clusters/{cluster_id}/entities")
async def get_cluster_entities(cluster_id: str) -> list[dict[str, Any]]:
    """Get entities for a cluster (stub)."""
    return [
        {
            "id": str(uuid.uuid4()),
            "entity_type": "room",
            "entity_value": "FA1-1Q4-MR10",
            "metadata": {},
        },
        {
            "id": str(uuid.uuid4()),
            "entity_type": "person",
            "entity_value": "Thandi Dineka",
            "metadata": {},
        },
    ]


@router.post("/clusters/{cluster_id}/override")
async def override_cluster(cluster_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Override a cluster state (stub)."""
    return {"cluster_id": cluster_id, "status": "overridden", "new_state": "suppressed"}


# ---------------------------------------------------------------------------
# Dashboard endpoints
# ---------------------------------------------------------------------------


@router.get("/dashboard/{role_type}/{person_id}")
async def get_dashboard_cards(role_type: str, person_id: str) -> dict[str, Any]:
    """Get dashboard cards for a role holder (stub)."""
    return {
        "person_id": person_id,
        "role_type": role_type,
        "cards": [
            {
                "card_id": str(uuid.uuid4()),
                "issue_cluster_id": str(uuid.uuid4()),
                "title": "Fairlands meeting room availability conflict",
                "cluster_state": "escalated",
                "severity": "high",
                "surfaced_at": "2026-01-05T14:31:00Z",
                "duration_days": 60,
                "card_content": {
                    "summary": (
                        "Block booking pattern detected across FA1-1Q4-MR10, "
                        "FA1-2Q1-MR03, FA2-1Q2-TR01. 60-day unresolved issue."
                    ),
                    "affected_rooms": [
                        "FA1-1Q4-MR10",
                        "FA1-2Q1-MR03",
                        "FA2-1Q2-TR01",
                    ],
                    "recommended_actions": [
                        "Review block bookings for rooms under your management",
                        "Cancel confirmed unoccupied slots",
                        "Monitor no-show patterns this week",
                    ],
                    "advisory_label": "These actions are suggestions. Human decision required.",
                },
                "acknowledged_at": None,
            }
        ],
    }


@router.post("/dashboard/cards/{card_id}/acknowledge")
async def acknowledge_card(card_id: str) -> dict[str, Any]:
    """Acknowledge a dashboard card (stub)."""
    return {"card_id": card_id, "status": "acknowledged"}


# ---------------------------------------------------------------------------
# Email ingest endpoint
# ---------------------------------------------------------------------------


@router.post("/email/ingest")
async def ingest_email(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ingest an email for correlation processing (stub)."""
    return {
        "status": "received",
        "thread_id": "derived-hash",
        "signals_created": 2,
        "signal_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
        "cluster_action": "created",
        "cluster_id": str(uuid.uuid4()),
    }
