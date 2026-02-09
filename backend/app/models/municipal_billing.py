"""Municipal billing models (Phase 49).

Defines Pydantic models for municipal accounts, invoices, tariff schedules,
reconciliation alerts, and dispute packs.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MunicipalAccount(BaseModel):
    id: Optional[str] = None
    site_id: str
    municipality: str
    utility_type: str
    account_number: str
    tariff_type: Optional[str] = None
    main_meter_id: Optional[str] = None
    active_from: Optional[date] = None
    active_until: Optional[date] = None
    is_active: bool = True
    billing_email: Optional[str] = None
    payment_method: Optional[str] = None


class MunicipalInvoice(BaseModel):
    id: Optional[str] = None
    municipal_account_id: str
    site_id: str
    invoice_number: str
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    billing_period_start: Optional[date] = None
    billing_period_end: Optional[date] = None

    consumption_kwh: Optional[Decimal] = None
    previous_reading: Optional[Decimal] = None
    current_reading: Optional[Decimal] = None
    meter_number: Optional[str] = None

    demand_kva: Optional[Decimal] = None
    peak_demand_kw: Optional[Decimal] = None

    energy_charge_zar: Optional[Decimal] = None
    network_charge_zar: Optional[Decimal] = None
    demand_charge_zar: Optional[Decimal] = None
    service_charge_zar: Optional[Decimal] = None
    vat_zar: Optional[Decimal] = None
    total_amount_zar: Optional[Decimal] = None

    tou_breakdown: Optional[Dict[str, Any]] = None

    raw_pdf_path: Optional[str] = None
    ocr_confidence: Optional[Decimal] = None
    ocr_status: Optional[str] = None

    invoice_confidence_score: Optional[Decimal] = None
    invoice_confidence_flags: Optional[List[str]] = None

    bms_consumption_kwh: Optional[Decimal] = None
    variance_pct: Optional[Decimal] = None
    reconciliation_status: Optional[str] = None

    dispute_pack: Optional[Dict[str, Any]] = None

    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class MunicipalTariffSchedule(BaseModel):
    id: Optional[str] = None
    municipality: str
    tariff_name: str
    utility_type: str
    effective_date: date
    expiry_date: Optional[date] = None
    tariff_data: Dict[str, Any]
    nersa_approved: bool = False
    source_url: Optional[str] = None
    notes: Optional[str] = None


class MunicipalReconciliationAlert(BaseModel):
    id: Optional[str] = None
    invoice_id: str
    alert_type: str
    severity: str
    expected_value: Optional[Decimal] = None
    actual_value: Optional[Decimal] = None
    variance_pct: Optional[Decimal] = None
    variance_amount_zar: Optional[Decimal] = None
    status: str = Field(default="open")
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None


class DisputePack(BaseModel):
    invoice_id: str
    municipality: str
    utility_type: str
    billing_period: str
    invoice_confidence: Dict[str, Any]
    bms_summary: Dict[str, Any]
    invoice_summary: Dict[str, Any]
    variance: Dict[str, Any]
    tariff_recalculation: Dict[str, Any]
    evidence: Dict[str, Any]
    recommended_action: Dict[str, Any]
    dispute_letter_template: Dict[str, Any]
