"""Municipal billing API endpoints."""

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.database.repositories.municipal_invoice_repository import MunicipalInvoiceRepository
from app.services.municipal_reconciliation_service import MunicipalReconciliationService
from app.services.tariff_schedule_service import TariffScheduleService
from app.services.municipal_tariff_ingestion_service import MunicipalTariffIngestionService
from app.services.module_registry_service import ModuleRegistryService
from app.models.module_registry import AIRecommendation, ModuleType, RecommendationType, RecommendationPriority

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/municipal-billing", tags=["municipal-billing"])


@router.post("/invoices/upload")
async def upload_invoice(
    file: UploadFile = File(...),
    site_id: str = Form(...),
    municipality: str = Form(...),
    utility_type: str = Form(...),
    account_number: str = Form(...),
    tariff_type: Optional[str] = Form(None),
    meter_number: Optional[str] = Form(None),
):
    """Upload municipal invoice PDF for OCR parsing and reconciliation."""
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files supported")

    repo = MunicipalInvoiceRepository()
    recon = MunicipalReconciliationService()

    account = repo.get_or_create_account(
        site_id=site_id,
        municipality=municipality,
        utility_type=utility_type,
        account_number=account_number,
        tariff_type=tariff_type,
        main_meter_id=meter_number,
    )
    if not account:
        raise HTTPException(status_code=500, detail="Failed to create municipal account")

    pdf_path = _store_invoice_pdf(site_id, file)

    parsed_data = {}
    ocr_status = "pending"
    ocr_confidence = None

    try:
        from app.services.municipal_pdf_extraction_service import MunicipalPdfExtractionService

        pdf_service = MunicipalPdfExtractionService()
        parsed_data = await pdf_service.parse_invoice(pdf_path)
        ocr_status = "completed" if parsed_data else "pending"
        ocr_confidence = parsed_data.get("confidence") if parsed_data else None
    except Exception as exc:
        logger.info("Municipal PDF extraction unavailable or failed: %s", exc)

    invoice_number = parsed_data.get("invoice_number") or f"UPLOAD-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    confidence = _infer_invoice_confidence(parsed_data)

    payload = {
        "municipal_account_id": account["id"],
        "site_id": site_id,
        "municipality": municipality,
        "utility_type": utility_type,
        "invoice_number": invoice_number,
        "invoice_date": parsed_data.get("invoice_date") or date.today().isoformat(),
        "due_date": parsed_data.get("due_date"),
        "billing_period_start": parsed_data.get("billing_period_start"),
        "billing_period_end": parsed_data.get("billing_period_end"),
        "consumption_kwh": parsed_data.get("consumption_kwh"),
        "previous_reading": parsed_data.get("previous_reading"),
        "current_reading": parsed_data.get("current_reading"),
        "meter_number": parsed_data.get("meter_number") or meter_number,
        "demand_kva": parsed_data.get("demand_kva"),
        "peak_demand_kw": parsed_data.get("peak_demand_kw"),
        "energy_charge_zar": parsed_data.get("energy_charge_zar"),
        "network_charge_zar": parsed_data.get("network_charge_zar"),
        "demand_charge_zar": parsed_data.get("demand_charge_zar"),
        "service_charge_zar": parsed_data.get("service_charge_zar"),
        "vat_zar": parsed_data.get("vat_zar"),
        "total_amount_zar": parsed_data.get("total_amount_zar"),
        "tou_breakdown": parsed_data.get("tou_breakdown"),
        "raw_pdf_path": str(pdf_path),
        "ocr_confidence": ocr_confidence,
        "ocr_status": ocr_status,
        "invoice_confidence_score": confidence["score"],
        "invoice_confidence_flags": confidence["flags"],
    }

    created = repo.create_invoice(payload)
    if not created:
        raise HTTPException(status_code=500, detail="Failed to create invoice")

    reconciliation = None
    if parsed_data:
        parsed_data.setdefault("municipality", municipality)
        parsed_data.setdefault("utility_type", utility_type)
        parsed_data.setdefault("tariff_type", tariff_type)
        parsed_data.setdefault("billing_period_start", created.get("billing_period_start"))
        parsed_data.setdefault("billing_period_end", created.get("billing_period_end"))
        parsed_data.setdefault("meter_number", created.get("meter_number"))
        reconciliation = recon.reconcile_invoice(parsed_data, site_id, created["id"])

        if reconciliation.get("status") == "variance_detected":
            dispute_pack = recon.generate_dispute_pack(created, reconciliation)
            repo.update_invoice(created["id"], {"dispute_pack": dispute_pack})

        # Add AI recommendations for tariff fit and demand exposure
        try:
            module_registry = ModuleRegistryService()
            demand_analysis = recon.maximum_demand_analysis(
                site_id=site_id,
                period_start=recon._parse_date(created.get("billing_period_start")) or date.today(),
                period_end=recon._parse_date(created.get("billing_period_end")) or date.today(),
                meter_id=created.get("meter_number"),
            )
            load_profile = recon.analyze_load_profile(
                site_id=site_id,
                period_start=recon._parse_date(created.get("billing_period_start")) or date.today(),
                period_end=recon._parse_date(created.get("billing_period_end")) or date.today(),
            )

            peak_kw = float(demand_analysis.get("peak_demand_kw") or 0.0)
            if peak_kw > 0:
                ai_rec = AIRecommendation(
                    recommendation_id=f"municipal-demand-{created['id']}",
                    timestamp=datetime.utcnow().isoformat(),
                    source_module=ModuleType.ENERGY,
                    recommendation_type=RecommendationType.OPTIMIZATION,
                    priority=RecommendationPriority.MEDIUM,
                    title="Reduce Maximum Demand Exposure",
                    description="Peak demand is high for this billing period. Consider staggering non-critical loads.",
                    confidence=0.7,
                    related_modules=[ModuleType.CONTRACTS],
                    telemetry_context={
                        "site_id": site_id,
                        "peak_demand_kw": peak_kw,
                    },
                    suggested_action={
                        "type": "stagger_loads",
                        "recommendations": demand_analysis.get("stagger_recommendations", []),
                    },
                    auto_actionable=False,
                    acknowledged=False,
                    resolved=False,
                )
                module_registry.add_recommendation(site_id, ai_rec)

            if load_profile.get("recommendations"):
                ai_rec = AIRecommendation(
                    recommendation_id=f"municipal-tariff-{created['id']}",
                    timestamp=datetime.utcnow().isoformat(),
                    source_module=ModuleType.CONTRACTS,
                    recommendation_type=RecommendationType.OPTIMIZATION,
                    priority=RecommendationPriority.LOW,
                    title="Tariff Optimization Opportunity",
                    description="Load profile suggests a better tariff fit for this site.",
                    confidence=0.6,
                    related_modules=[ModuleType.ENERGY],
                    telemetry_context={
                        "site_id": site_id,
                        "profile": load_profile.get("profile", {}),
                    },
                    suggested_action={
                        "type": "review_tariff",
                        "recommendations": load_profile.get("recommendations", []),
                    },
                    auto_actionable=False,
                    acknowledged=False,
                    resolved=False,
                )
                module_registry.add_recommendation(site_id, ai_rec)
        except Exception as exc:
            logger.info("Failed to create municipal AI recommendations: %s", exc)

    return {
        "invoice": created,
        "reconciliation": reconciliation,
        "pdf_path": str(pdf_path),
    }


@router.post("/invoices/upload-batch")
async def upload_invoice_batch(
    files: List[UploadFile] = File(...),
    site_id: str = Form(...),
    municipality: str = Form(...),
    utility_type: str = Form(...),
    account_number: str = Form(...),
    tariff_type: Optional[str] = Form(None),
):
    """Bulk upload multiple invoices."""
    results = []
    for file in files:
        try:
            result = await upload_invoice(
                file=file,
                site_id=site_id,
                municipality=municipality,
                utility_type=utility_type,
                account_number=account_number,
                tariff_type=tariff_type,
            )
            results.append({"file": file.filename, "status": "success", "data": result})
        except Exception as exc:
            results.append({"file": file.filename, "status": "error", "message": str(exc)})

    return {"results": results}


@router.get("/invoices")
async def list_invoices(
    site_id: Optional[str] = None,
    municipality: Optional[str] = None,
    utility_type: Optional[str] = None,
    billing_period: Optional[str] = None,
    reconciliation_status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    repo = MunicipalInvoiceRepository()
    invoices = repo.list_invoices(
        site_id=site_id,
        municipality=municipality,
        utility_type=utility_type,
        billing_period=billing_period,
        reconciliation_status=reconciliation_status,
        limit=limit,
        offset=offset,
    )
    return {"invoices": invoices, "count": len(invoices)}


@router.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str):
    repo = MunicipalInvoiceRepository()
    invoice = repo.get_by_id(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.get("/invoices/{invoice_id}/pdf")
async def get_invoice_pdf(invoice_id: str):
    repo = MunicipalInvoiceRepository()
    invoice = repo.get_by_id(invoice_id)
    if not invoice or not invoice.get("raw_pdf_path"):
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(invoice["raw_pdf_path"], media_type="application/pdf")


@router.post("/invoices/{invoice_id}/approve")
async def approve_invoice(invoice_id: str, approved_by: str = Form(...)):
    repo = MunicipalInvoiceRepository()
    invoice = repo.approve_invoice(invoice_id, approved_by)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"success": True, "invoice": invoice}


@router.post("/invoices/{invoice_id}/dispute")
async def dispute_invoice(invoice_id: str, dispute_reason: str = Form(...), disputed_by: str = Form(...)):
    repo = MunicipalInvoiceRepository()
    invoice = repo.get_by_id(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    dispute_pack = invoice.get("dispute_pack") or {}
    dispute_pack["dispute_reason"] = dispute_reason
    dispute_pack["disputed_by"] = disputed_by
    dispute_pack["disputed_at"] = datetime.utcnow().isoformat()

    updated = repo.update_invoice(
        invoice_id,
        {"reconciliation_status": "disputed", "approved_by": disputed_by, "dispute_pack": dispute_pack},
    )
    return {"success": True, "invoice": updated or invoice}


@router.get("/invoices/{invoice_id}/dispute-pack")
async def get_dispute_pack(invoice_id: str):
    repo = MunicipalInvoiceRepository()
    recon = MunicipalReconciliationService()

    invoice = repo.get_by_id(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.get("dispute_pack"):
        return invoice["dispute_pack"]

    reconciliation = recon.reconcile_invoice(invoice, invoice.get("site_id"), invoice_id)
    dispute_pack = recon.generate_dispute_pack(invoice, reconciliation)
    repo.update_invoice(invoice_id, {"dispute_pack": dispute_pack})
    return dispute_pack


@router.get("/tariffs")
async def list_tariff_schedules(
    municipality: Optional[str] = None,
    utility_type: Optional[str] = None,
    active_date: Optional[str] = None,
):
    svc = TariffScheduleService()
    active = datetime.fromisoformat(active_date).date() if active_date else None
    tariffs = svc.list_tariffs(municipality, utility_type, active)
    return {"tariffs": tariffs}


@router.post("/tariffs")
async def create_tariff_schedule(
    municipality: str = Form(...),
    tariff_name: str = Form(...),
    utility_type: str = Form(...),
    effective_date: str = Form(...),
    tariff_data: str = Form(...),
):
    svc = TariffScheduleService()
    payload = {
        "municipality": municipality,
        "tariff_name": tariff_name,
        "utility_type": utility_type,
        "effective_date": effective_date,
        "tariff_data": _parse_json_field(tariff_data),
    }
    tariff = svc.upsert_tariff(payload)
    if not tariff:
        raise HTTPException(status_code=500, detail="Failed to create tariff")
    return {"success": True, "tariff": tariff}


@router.post("/tariffs/ingest")
async def ingest_tariffs():
    """Ingest latest tariffs from official sources registry."""
    svc = MunicipalTariffIngestionService()
    results = svc.ingest_all()
    return {"results": results}


@router.get("/tariffs/{municipality}/{tariff_name}/calculate")
async def calculate_projected_bill(
    municipality: str,
    tariff_name: str,
    site_id: str,
    month: int,
    year: int,
):
    svc = TariffScheduleService()
    recon = MunicipalReconciliationService()
    period_start = date(year, month, 1)
    period_end = date(year, month, 28)

    tariff = svc.get_tariff(municipality, tariff_name, period_start)
    if not tariff:
        raise HTTPException(status_code=404, detail="Tariff not found")

    bms_data = recon.get_bms_consumption(site_id, "electricity", period_start, period_end)
    bill = tariff.calculate_total_charge(
        consumption_kwh=bms_data.get("by_band", {}),
        demand_kva=float(bms_data.get("peak_demand_kva") or 0.0),
        month=month,
    )

    return {
        "tariff": tariff_name,
        "period": f"{year}-{month:02d}",
        "projected_bill_zar": bill.get("total_zar"),
        "breakdown": bill,
        "bms_consumption_kwh": bms_data.get("total_kwh"),
    }


@router.get("/reconciliation/portfolio")
async def get_portfolio_reconciliation(billing_period: str):
    recon = MunicipalReconciliationService()
    portfolio = recon.get_portfolio_metrics(billing_period)
    return {
        "period": billing_period,
        **portfolio,
    }


@router.get("/reconciliation/{site_id}/load-profile")
async def analyze_load_profile(site_id: str, period_start: str, period_end: str):
    recon = MunicipalReconciliationService()
    analysis = recon.analyze_load_profile(
        site_id=site_id,
        period_start=datetime.fromisoformat(period_start).date(),
        period_end=datetime.fromisoformat(period_end).date(),
    )
    return {
        "site_id": site_id,
        "period": f"{period_start} to {period_end}",
        **analysis,
    }


@router.get("/reconciliation/{site_id}/maximum-demand")
async def analyze_maximum_demand(
    site_id: str,
    period_start: str,
    period_end: str,
    meter_id: Optional[str] = None,
):
    recon = MunicipalReconciliationService()
    analysis = recon.maximum_demand_analysis(
        site_id=site_id,
        period_start=datetime.fromisoformat(period_start).date(),
        period_end=datetime.fromisoformat(period_end).date(),
        meter_id=meter_id,
    )
    return {
        "site_id": site_id,
        "period": f"{period_start} to {period_end}",
        **analysis,
    }


# === Helpers ===


def _store_invoice_pdf(site_id: str, file: UploadFile) -> Path:
    storage_root = Path("backend/app/data/municipal_invoices") / site_id
    storage_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"{timestamp}_{file.filename}"
    path = storage_root / filename
    content = file.file.read()
    with open(path, "wb") as f:
        f.write(content)
    return path


def _parse_json_field(value: str):
    try:
        import json

        return json.loads(value)
    except Exception:
        return {}


def _infer_invoice_confidence(parsed_data: dict) -> dict:
    flags = []
    if parsed_data.get("is_estimated"):
        flags.append("estimated")
    if parsed_data.get("is_back_billed"):
        flags.append("back_billed")

    score = 0.85
    if flags:
        score = 0.6

    return {"score": score, "flags": flags}
