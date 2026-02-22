"""Repository for municipal invoice and account operations.

Uses Supabase when available, with JSON fallback for local/dev mode.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.database.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


class MunicipalInvoiceRepository:
    """CRUD operations for municipal accounts, invoices, and alerts."""

    def __init__(self):
        self.client = None
        try:
            self.client = get_supabase_client()
        except Exception as exc:
            logger.warning("Supabase client not available for municipal billing: %s", exc)

        self._json_path = Path("backend/app/data/municipal_invoices/index.json")
        self._json_path.parent.mkdir(parents=True, exist_ok=True)

    # === JSON fallback helpers ===

    def _load_json(self) -> Dict[str, Any]:
        if not self._json_path.exists():
            return {"accounts": [], "invoices": [], "alerts": []}
        with open(self._json_path, "r") as f:
            return json.load(f)

    def _save_json(self, data: Dict[str, Any]) -> None:
        with open(self._json_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    # === Accounts ===

    def get_or_create_account(
        self,
        site_id: str,
        municipality: str,
        utility_type: str,
        account_number: str,
        tariff_type: Optional[str] = None,
        main_meter_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch an existing municipal account or create a new one."""
        if self.client:
            try:
                result = (
                    self.client.table("municipal_accounts")
                    .select("*")
                    .eq("site_id", site_id)
                    .eq("municipality", municipality)
                    .eq("utility_type", utility_type)
                    .eq("account_number", account_number)
                    .limit(1)
                    .execute()
                )
                if result.data:
                    return result.data[0]

                payload = {
                    "site_id": site_id,
                    "municipality": municipality,
                    "utility_type": utility_type,
                    "account_number": account_number,
                    "tariff_type": tariff_type,
                    "main_meter_id": main_meter_id,
                }
                created = self.client.table("municipal_accounts").insert(payload).execute()
                return created.data[0] if created.data else None
            except Exception as exc:
                logger.error("Error creating municipal account: %s", exc)
                return None

        data = self._load_json()
        for account in data["accounts"]:
            if (
                account.get("site_id") == site_id
                and account.get("municipality") == municipality
                and account.get("utility_type") == utility_type
                and account.get("account_number") == account_number
            ):
                return account

        account = {
            "id": str(uuid4()),
            "site_id": site_id,
            "municipality": municipality,
            "utility_type": utility_type,
            "account_number": account_number,
            "tariff_type": tariff_type,
            "main_meter_id": main_meter_id,
            "created_at": datetime.utcnow().isoformat(),
        }
        data["accounts"].append(account)
        self._save_json(data)
        return account

    # === Invoices ===

    def create_invoice(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new invoice record."""
        if self.client:
            try:
                result = self.client.table("municipal_invoices").insert(payload).execute()
                return result.data[0] if result.data else None
            except Exception as exc:
                logger.error("Error creating municipal invoice: %s", exc)
                return None

        data = self._load_json()
        payload = dict(payload)
        payload.setdefault("id", str(uuid4()))
        payload.setdefault("created_at", datetime.utcnow().isoformat())
        data["invoices"].append(payload)
        self._save_json(data)
        return payload

    def update_invoice(self, invoice_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update an invoice record by ID."""
        if self.client:
            try:
                result = self.client.table("municipal_invoices").update(payload).eq("id", invoice_id).execute()
                return result.data[0] if result.data else None
            except Exception as exc:
                logger.error("Error updating municipal invoice %s: %s", invoice_id, exc)
                return None

        data = self._load_json()
        for idx, invoice in enumerate(data["invoices"]):
            if invoice.get("id") == invoice_id:
                updated = {**invoice, **payload}
                data["invoices"][idx] = updated
                self._save_json(data)
                return updated
        return None

    def get_by_id(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """Get invoice by ID."""
        if self.client:
            try:
                result = self.client.table("municipal_invoices").select("*").eq("id", invoice_id).limit(1).execute()
                return result.data[0] if result.data else None
            except Exception as exc:
                logger.error("Error fetching municipal invoice %s: %s", invoice_id, exc)
                return None

        data = self._load_json()
        for invoice in data["invoices"]:
            if invoice.get("id") == invoice_id:
                return invoice
        return None

    def list_invoices(
        self,
        site_id: Optional[str] = None,
        municipality: Optional[str] = None,
        utility_type: Optional[str] = None,
        billing_period: Optional[str] = None,
        reconciliation_status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List invoices with filters."""
        if self.client:
            try:
                query = self.client.table("municipal_invoices").select("*")
                if site_id:
                    query = query.eq("site_id", site_id)
                if municipality:
                    query = query.eq("municipality", municipality)
                if utility_type:
                    query = query.eq("utility_type", utility_type)
                if reconciliation_status:
                    query = query.eq("reconciliation_status", reconciliation_status)
                if billing_period:
                    query = query.eq("billing_period_start", billing_period)
                result = query.range(offset, offset + limit - 1).execute()
                return result.data or []
            except Exception as exc:
                logger.error("Error listing municipal invoices: %s", exc)
                return []

        data = self._load_json()
        invoices = data.get("invoices", [])
        filtered = []
        for invoice in invoices:
            if site_id and invoice.get("site_id") != site_id:
                continue
            if municipality and invoice.get("municipality") != municipality:
                continue
            if utility_type and invoice.get("utility_type") != utility_type:
                continue
            if billing_period and invoice.get("billing_period_start") != billing_period:
                continue
            if reconciliation_status and invoice.get("reconciliation_status") != reconciliation_status:
                continue
            filtered.append(invoice)

        return filtered[offset : offset + limit]

    def approve_invoice(self, invoice_id: str, approved_by: str) -> Optional[Dict[str, Any]]:
        """Mark invoice as approved."""
        return self.update_invoice(
            invoice_id,
            {
                "approved_by": approved_by,
                "approved_at": datetime.utcnow().isoformat(),
            },
        )

    # === Alerts ===

    def create_alert(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self.client:
            try:
                result = self.client.table("municipal_reconciliation_alerts").insert(payload).execute()
                return result.data[0] if result.data else None
            except Exception as exc:
                logger.error("Error creating municipal alert: %s", exc)
                return None

        data = self._load_json()
        payload = dict(payload)
        payload.setdefault("id", str(uuid4()))
        payload.setdefault("created_at", datetime.utcnow().isoformat())
        data["alerts"].append(payload)
        self._save_json(data)
        return payload
