"""
Alert Routing Rules API
========================
CRUD for configurable alert routing rules — severity-to-channel mapping,
escalation chains, discipline-based auto-routing.
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.middleware.auth_middleware import require_role
from app.models.auth import AuthContext, SentinelRole

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/alert-routing", tags=["alert-routing"])

DATA_PATH = Path(__file__).parent.parent / "data"
RULES_FILE = DATA_PATH / "alert_routing_rules.json"


class AlertRoutingRuleCreate(BaseModel):
    name: str
    enabled: bool = True
    severity: list[str] = ["critical"]  # critical, warning, info
    equipment_types: list[str] = []  # empty = all types
    site_ids: list[str] = []  # empty = all sites
    channels: list[str] = ["telegram"]  # telegram, whatsapp, email, sms
    recipient_roles: list[str] = ["technician"]  # technician, supervisor, manager, admin
    recipient_ids: list[str] = []  # specific technician IDs
    escalation_minutes: int | None = None  # None = no escalation
    escalation_to_roles: list[str] = []


class AlertRoutingRuleUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    severity: list[str] | None = None
    equipment_types: list[str] | None = None
    site_ids: list[str] | None = None
    channels: list[str] | None = None
    recipient_roles: list[str] | None = None
    recipient_ids: list[str] | None = None
    escalation_minutes: int | None = None
    escalation_to_roles: list[str] | None = None


def _load_rules() -> list:
    if not RULES_FILE.exists():
        return _default_rules()
    try:
        with open(RULES_FILE) as f:
            return json.load(f)
    except Exception:
        return _default_rules()


def _save_rules(rules: list) -> None:
    RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RULES_FILE, "w") as f:
        json.dump(rules, f, indent=2)


def _default_rules() -> list:
    """Sensible default routing rules."""
    return [
        {
            "id": "default-critical",
            "name": "Critical alerts to all channels",
            "enabled": True,
            "severity": ["critical"],
            "equipment_types": [],
            "site_ids": [],
            "channels": ["telegram", "whatsapp"],
            "recipient_roles": ["technician", "supervisor"],
            "recipient_ids": [],
            "escalation_minutes": 15,
            "escalation_to_roles": ["manager", "admin"],
            "created_at": "2026-01-01T00:00:00Z",
        },
        {
            "id": "default-warning",
            "name": "Warning alerts to Telegram",
            "enabled": True,
            "severity": ["warning"],
            "equipment_types": [],
            "site_ids": [],
            "channels": ["telegram"],
            "recipient_roles": ["technician"],
            "recipient_ids": [],
            "escalation_minutes": 60,
            "escalation_to_roles": ["supervisor"],
            "created_at": "2026-01-01T00:00:00Z",
        },
    ]


@router.get("/rules")
async def list_routing_rules(
    site_id: str | None = Query(None, description="Optional site scope"),
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN, SentinelRole.OPERATOR)),
) -> dict:
    """List all alert routing rules."""
    rules = _load_rules()
    if site_id:
        rules = [r for r in rules if not r.get("site_ids") or site_id in (r.get("site_ids") or [])]
    return {"rules": rules, "count": len(rules)}


@router.post("/rules")
async def create_routing_rule(
    rule: AlertRoutingRuleCreate,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Create a new alert routing rule."""
    rules = _load_rules()
    new_rule = {
        "id": str(uuid.uuid4()),
        **rule.model_dump(),
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    rules.append(new_rule)
    _save_rules(rules)
    logger.info(f"Created alert routing rule: {rule.name}")
    return {"status": "created", "rule": new_rule}


@router.put("/rules/{rule_id}")
async def update_routing_rule(
    rule_id: str,
    update: AlertRoutingRuleUpdate,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Update an alert routing rule."""
    rules = _load_rules()
    for i, r in enumerate(rules):
        if r["id"] == rule_id:
            update_data = {k: v for k, v in update.model_dump().items() if v is not None}
            rules[i] = {**r, **update_data}
            _save_rules(rules)
            return {"status": "updated", "rule": rules[i]}
    raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")


@router.delete("/rules/{rule_id}")
async def delete_routing_rule(
    rule_id: str,
    auth: AuthContext = Depends(require_role(SentinelRole.ADMIN)),
) -> dict:
    """Delete an alert routing rule."""
    rules = _load_rules()
    original_len = len(rules)
    rules = [r for r in rules if r["id"] != rule_id]
    if len(rules) == original_len:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
    _save_rules(rules)
    logger.info(f"Deleted alert routing rule: {rule_id}")
    return {"status": "deleted", "rule_id": rule_id}
