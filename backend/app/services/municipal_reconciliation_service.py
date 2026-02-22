"""Municipal reconciliation service.

Compares municipal invoices against BMS meter data, computes variance,
validates tariff calculations, and generates dispute evidence packs.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from app.database.repositories.energy_consumption_repository import EnergyConsumptionRepository
from app.database.repositories.municipal_invoice_repository import MunicipalInvoiceRepository
from app.database.repositories.water_consumption_repository import WaterConsumptionRepository
from app.database.repositories.municipal_demand_repository import MunicipalDemandRepository
from app.services.tariff_schedule_service import TariffScheduleService

logger = logging.getLogger(__name__)


class MunicipalReconciliationService:
    """Validate municipal invoices against BMS meter data."""

    def __init__(self):
        self.tariff_service = TariffScheduleService()
        self.invoice_repo = MunicipalInvoiceRepository()
        self.energy_repo = None
        self.water_repo = None
        self._demand_repo = None
        try:
            self.energy_repo = EnergyConsumptionRepository()
        except Exception as exc:
            logger.warning("Energy repository unavailable: %s", exc)
        try:
            self.water_repo = WaterConsumptionRepository()
        except Exception as exc:
            logger.warning("Water repository unavailable: %s", exc)
        try:
            self._demand_repo = MunicipalDemandRepository()
        except Exception as exc:
            logger.warning("Municipal demand repository unavailable: %s", exc)

    def reconcile_invoice(
        self,
        parsed_data: Dict[str, Any],
        site_id: str,
        invoice_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reconcile parsed invoice data with BMS data."""
        utility_type = parsed_data.get("utility_type", "electricity")
        period_start = self._parse_date(parsed_data.get("billing_period_start"))
        period_end = self._parse_date(parsed_data.get("billing_period_end"))

        bms_data = self._fetch_bms_consumption(
            site_id=site_id,
            utility_type=utility_type,
            period_start=period_start,
            period_end=period_end,
            meter_id=parsed_data.get("meter_number"),
            tou_breakdown=parsed_data.get("tou_breakdown"),
        )

        billed_consumption = float(parsed_data.get("consumption_kwh") or 0.0)
        bms_consumption = float(bms_data.get("total_kwh") or 0.0)

        variance_pct = 0.0
        if bms_consumption > 0:
            variance_pct = ((billed_consumption - bms_consumption) / bms_consumption) * 100

        status = "matched"
        variance_explanation = None
        if abs(variance_pct) > 5.0:
            status = "variance_detected"
            variance_explanation = f"BMS shows {bms_consumption:.1f} kWh, billed for {billed_consumption:.1f} kWh"

        tariff_result = None
        tariff_name = parsed_data.get("tariff_type") or parsed_data.get("tariff_name")
        municipality = parsed_data.get("municipality")
        if tariff_name and municipality and period_start:
            tariff = self.tariff_service.get_tariff(municipality, tariff_name, period_start)
            if tariff:
                tariff_result = tariff.calculate_total_charge(
                    consumption_kwh=bms_data.get("by_band", {}),
                    demand_kva=float(bms_data.get("peak_demand_kva") or 0.0),
                    month=period_start.month,
                )

        if tariff_result and parsed_data.get("total_amount_zar"):
            billed_total = float(parsed_data.get("total_amount_zar") or 0.0)
            if abs(tariff_result.get("total_zar", 0) - billed_total) > 50.0:
                status = "variance_detected"
                if not variance_explanation:
                    variance_explanation = "Tariff calculation mismatch"

        reconciliation = {
            "invoice_id": invoice_id,
            "site_id": site_id,
            "bms_consumption_kwh": round(bms_consumption, 2),
            "billed_consumption_kwh": round(billed_consumption, 2),
            "consumption_variance_pct": round(variance_pct, 2),
            "status": status,
            "variance_explanation": variance_explanation,
            "tariff_recalculation": tariff_result,
        }

        if invoice_id:
            self.invoice_repo.update_invoice(
                invoice_id,
                {
                    "bms_consumption_kwh": bms_consumption,
                    "variance_pct": variance_pct,
                    "reconciliation_status": status,
                },
            )

        return reconciliation

    def analyze_load_profile(
        self,
        site_id: str,
        period_start: date,
        period_end: date,
        current_tariff: Optional[str] = None,
    ) -> Dict[str, Any]:
        bms_data = self._fetch_bms_consumption(
            site_id=site_id,
            utility_type="electricity",
            period_start=period_start,
            period_end=period_end,
        )

        total_kwh = float(bms_data.get("total_kwh") or 0.0)
        by_band = bms_data.get("by_band", {})
        peak_kwh = float(by_band.get("peak", 0.0))
        standard_kwh = float(by_band.get("standard", 0.0))
        off_peak_kwh = float(by_band.get("off_peak", 0.0))

        peak_ratio = peak_kwh / total_kwh if total_kwh > 0 else 0.0
        load_factor = 0.0
        peak_demand_kw = float(bms_data.get("peak_demand_kw") or 0.0)
        if peak_demand_kw > 0:
            load_factor = (total_kwh / 24.0) / peak_demand_kw

        recommendations = []
        if peak_ratio < 0.2:
            recommendations.append(
                {
                    "tariff": "TOU Commercial",
                    "reason": "Low peak usage (off-peak heavy)",
                    "confidence": "high",
                }
            )
        if peak_ratio > 0.4:
            recommendations.append(
                {
                    "tariff": "Flat / Homebug",
                    "reason": "High peak usage (flat rate may be better)",
                    "confidence": "medium",
                }
            )

        return {
            "profile": {
                "total_kwh": round(total_kwh, 1),
                "peak_kwh": round(peak_kwh, 1),
                "standard_kwh": round(standard_kwh, 1),
                "off_peak_kwh": round(off_peak_kwh, 1),
                "peak_ratio": round(peak_ratio, 3),
                "load_factor": round(load_factor, 3),
                "peak_demand_kw": round(peak_demand_kw, 1),
            },
            "current_tariff": current_tariff,
            "recommendations": recommendations,
        }

    def maximum_demand_analysis(
        self,
        site_id: str,
        period_start: date,
        period_end: date,
        meter_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        bms_data = self._fetch_bms_consumption(
            site_id=site_id,
            utility_type="electricity",
            period_start=period_start,
            period_end=period_end,
            meter_id=meter_id,
        )

        return {
            "peak_demand_kw": bms_data.get("peak_demand_kw", 0.0),
            "peak_windows": bms_data.get("peak_windows", []),
            "stagger_recommendations": bms_data.get("stagger_recommendations", []),
        }

    def generate_dispute_pack(
        self,
        invoice: Dict[str, Any],
        reconciliation: Dict[str, Any],
    ) -> Dict[str, Any]:
        billing_period = None
        if invoice.get("billing_period_start") and invoice.get("billing_period_end"):
            billing_period = f"{invoice['billing_period_start']} to {invoice['billing_period_end']}"

        dispute_pack = {
            "invoice_id": invoice.get("id"),
            "municipality": invoice.get("municipality"),
            "utility_type": invoice.get("utility_type"),
            "billing_period": billing_period or "unknown",
            "invoice_confidence": {
                "score": invoice.get("invoice_confidence_score"),
                "flags": invoice.get("invoice_confidence_flags") or [],
            },
            "bms_summary": {
                "total_kwh": reconciliation.get("bms_consumption_kwh"),
                "peak_demand_kw": invoice.get("peak_demand_kw"),
            },
            "invoice_summary": {
                "billed_kwh": invoice.get("consumption_kwh"),
                "billed_demand_kva": invoice.get("demand_kva"),
                "total_amount_zar": invoice.get("total_amount_zar"),
            },
            "variance": {
                "consumption_pct": reconciliation.get("consumption_variance_pct"),
                "amount_zar": None,
            },
            "tariff_recalculation": reconciliation.get("tariff_recalculation"),
            "evidence": {
                "meter_data_exports": [],
                "charts": [],
            },
            "recommended_action": {
                "action": "pay_then_dispute",
                "notes": "Invoice appears inconsistent with BMS data; pay under protest and file dispute.",
            },
            "dispute_letter_template": {
                "subject": f"Dispute of Municipal Invoice {invoice.get('invoice_number')}",
                "body": "We have paid the invoice under protest and request a formal review...",
            },
        }
        return dispute_pack

    def get_portfolio_metrics(self, period: str) -> Dict[str, Any]:
        invoices = self.invoice_repo.list_invoices()
        period_start = None
        period_end = None
        if period and len(period) == 7 and "-" in period:
            try:
                year, month = period.split("-")
                period_start = date(int(year), int(month), 1)
                period_end = date(int(year), int(month), 28)
            except Exception:
                period_start = None
                period_end = None

        if period_start and period_end:
            filtered = []
            for inv in invoices:
                inv_start = self._parse_date(inv.get("billing_period_start"))
                if inv_start and period_start <= inv_start <= period_end:
                    filtered.append(inv)
            invoices = filtered

        total_billed = sum(float(inv.get("total_amount_zar") or 0.0) for inv in invoices)
        variance_total = sum(float(inv.get("variance_pct") or 0.0) for inv in invoices)
        alerts = [inv for inv in invoices if inv.get("reconciliation_status") == "variance_detected"]

        return {
            "invoice_count": len(invoices),
            "total_billed_zar": round(total_billed, 2),
            "total_variance_pct": round(variance_total, 2),
            "alerts": alerts,
            "site_breakdowns": {},
        }

    def _fetch_bms_consumption(
        self,
        site_id: str,
        utility_type: str,
        period_start: Optional[date],
        period_end: Optional[date],
        meter_id: Optional[str] = None,
        tou_breakdown: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if utility_type == "water":
            return self._fetch_water_consumption(site_id, period_start, period_end)

        return self._fetch_energy_consumption(
            site_id,
            period_start,
            period_end,
            meter_id,
            tou_breakdown,
        )

    def get_bms_consumption(
        self,
        site_id: str,
        utility_type: str,
        period_start: Optional[date],
        period_end: Optional[date],
        meter_id: Optional[str] = None,
        tou_breakdown: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Public wrapper for BMS consumption retrieval."""
        return self._fetch_bms_consumption(
            site_id=site_id,
            utility_type=utility_type,
            period_start=period_start,
            period_end=period_end,
            meter_id=meter_id,
            tou_breakdown=tou_breakdown,
        )

    def _fetch_energy_consumption(
        self,
        site_id: str,
        period_start: Optional[date],
        period_end: Optional[date],
        meter_id: Optional[str] = None,
        tou_breakdown: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        total_kwh = 0.0
        if period_start and period_end:
            if self.energy_repo:
                records = self.energy_repo.get_by_date_range(site_id, period_start, period_end)
                total_kwh = sum(float(r.get("total_kwh") or 0.0) for r in records)

        peak_demand_kw = 0.0
        peak_windows: List[Dict[str, Any]] = []
        if self._demand_repo and period_start and period_end:
            demand_rows = self._demand_repo.get_by_site(site_id, period_start, period_end, meter_id)
            if demand_rows:
                peak_row = max(demand_rows, key=lambda r: float(r.get("peak_demand_kw") or 0.0))
                peak_demand_kw = float(peak_row.get("peak_demand_kw") or 0.0)
                peak_windows = [
                    {
                        "timestamp": row.get("peak_timestamp"),
                        "demand_kw": float(row.get("peak_demand_kw") or 0.0),
                    }
                    for row in sorted(demand_rows, key=lambda r: float(r.get("peak_demand_kw") or 0.0), reverse=True)[
                        :3
                    ]
                ]

        if tou_breakdown:
            by_band = {
                "peak": float(tou_breakdown.get("peak_kwh", 0.0)),
                "standard": float(tou_breakdown.get("standard_kwh", 0.0)),
                "off_peak": float(tou_breakdown.get("off_peak_kwh", 0.0)),
            }
        else:
            by_band = {
                "peak": total_kwh * 0.3,
                "standard": total_kwh * 0.5,
                "off_peak": total_kwh * 0.2,
            }

        return {
            "total_kwh": total_kwh,
            "by_band": by_band,
            "peak_demand_kw": peak_demand_kw,
            "peak_demand_kva": peak_demand_kw,
            "peak_windows": peak_windows,
            "stagger_recommendations": self._suggest_staggering(peak_demand_kw, peak_windows),
        }

    def _fetch_water_consumption(
        self,
        site_id: str,
        period_start: Optional[date],
        period_end: Optional[date],
    ) -> Dict[str, Any]:
        if not period_start or not period_end:
            return {"total_kl": 0.0, "total_kwh": 0.0, "by_band": {}}

        if not self.water_repo:
            return {"total_kl": 0.0, "total_kwh": 0.0, "by_band": {}}

        records = self.water_repo.get_consumption_by_site(site_id, period_start, period_end, limit=10000)
        if not records:
            return {"total_kl": 0.0, "total_kwh": 0.0, "by_band": {}}

        first = records[0]
        last = records[-1]
        volume_l = float(last.get("volume_liters") or 0.0) - float(first.get("volume_liters") or 0.0)
        total_kl = volume_l / 1000.0 if volume_l > 0 else 0.0
        return {"total_kl": total_kl, "total_kwh": total_kl, "by_band": {}}

    # NOTE: Peak demand now sourced from BMS aggregate tables (municipal_demand_history)

    def _suggest_staggering(
        self,
        peak_demand_kw: float,
        peak_windows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if peak_demand_kw <= 0 or not peak_windows:
            return []

        projected_reduction = round(peak_demand_kw * 0.1, 1)
        return [
            {
                "action": "stagger_non_critical_loads",
                "description": "Delay non-critical equipment start-ups during peak windows",
                "peak_window": peak_windows[0].get("timestamp"),
                "projected_kw_reduction": projected_reduction,
            }
        ]

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        if not value:
            return None
        if isinstance(value, date):
            return value
        try:
            return datetime.fromisoformat(str(value)).date()
        except Exception:
            return None
