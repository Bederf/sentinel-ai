"""Municipal billing models (Phase 49).

Defines Pydantic models for municipal accounts, invoices, tariff schedules,
reconciliation alerts, and dispute packs.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class MunicipalAccount(BaseModel):
    id: str | None = None
    site_id: str
    municipality: str
    utility_type: str
    account_number: str
    tariff_type: str | None = None
    main_meter_id: str | None = None
    active_from: date | None = None
    active_until: date | None = None
    is_active: bool = True
    billing_email: str | None = None
    payment_method: str | None = None


class MunicipalInvoice(BaseModel):
    id: str | None = None
    municipal_account_id: str
    site_id: str
    invoice_number: str
    invoice_date: date | None = None
    due_date: date | None = None
    billing_period_start: date | None = None
    billing_period_end: date | None = None

    consumption_kwh: Decimal | None = None
    previous_reading: Decimal | None = None
    current_reading: Decimal | None = None
    meter_number: str | None = None

    demand_kva: Decimal | None = None
    peak_demand_kw: Decimal | None = None

    energy_charge_zar: Decimal | None = None
    network_charge_zar: Decimal | None = None
    demand_charge_zar: Decimal | None = None
    service_charge_zar: Decimal | None = None
    vat_zar: Decimal | None = None
    total_amount_zar: Decimal | None = None

    tou_breakdown: dict[str, Any] | None = None

    raw_pdf_path: str | None = None
    ocr_confidence: Decimal | None = None
    ocr_status: str | None = None

    invoice_confidence_score: Decimal | None = None
    invoice_confidence_flags: list[str] | None = None

    bms_consumption_kwh: Decimal | None = None
    variance_pct: Decimal | None = None
    reconciliation_status: str | None = None

    dispute_pack: dict[str, Any] | None = None

    approved_by: str | None = None
    approved_at: datetime | None = None


class MunicipalTariffSchedule(BaseModel):
    id: str | None = None
    municipality: str
    tariff_name: str
    utility_type: str
    effective_date: date
    expiry_date: date | None = None
    tariff_data: dict[str, Any]
    nersa_approved: bool = False
    source_url: str | None = None
    notes: str | None = None


class MunicipalReconciliationAlert(BaseModel):
    id: str | None = None
    invoice_id: str
    alert_type: str
    severity: str
    expected_value: Decimal | None = None
    actual_value: Decimal | None = None
    variance_pct: Decimal | None = None
    variance_amount_zar: Decimal | None = None
    status: str = Field(default="open")
    resolution_notes: str | None = None
    resolved_at: datetime | None = None


class DisputePack(BaseModel):
    invoice_id: str
    municipality: str
    utility_type: str
    billing_period: str
    invoice_confidence: dict[str, Any]
    bms_summary: dict[str, Any]
    invoice_summary: dict[str, Any]
    variance: dict[str, Any]
    tariff_recalculation: dict[str, Any]
    evidence: dict[str, Any]
    recommended_action: dict[str, Any]
    dispute_letter_template: dict[str, Any]
