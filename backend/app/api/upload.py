"""Upload API endpoints for CSV data files."""

import os
import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.services.csv_loader import (
    WorkOrderData,
    AssetData,
    SiteData,
    AlarmData,
    EnergyData,
    GeneratorTelemetryData,
    HVACTelemetryData,
    VSDTelemetryData,
    ChillerTelemetryData,
    PumpTelemetryData,
    DATA_DIR,
)

router = APIRouter()


class UploadResponse(BaseModel):
    """Upload response model."""
    success: bool
    message: str
    filename: str
    records_loaded: int


class DataStatusResponse(BaseModel):
    """Data status response model."""
    work_orders: int
    assets: int
    sites: int
    total_cost: float
    total_contract_value: float


ALLOWED_FILES = {
    "work_orders.csv": WorkOrderData,
    "assets.csv": AssetData,
    "sites.csv": SiteData,
    "alarms.csv": AlarmData,
    "energy_readings.csv": EnergyData,
    "generator_telemetry.csv": GeneratorTelemetryData,
    "hvac_telemetry.csv": HVACTelemetryData,
    "vsd_telemetry.csv": VSDTelemetryData,
    "chiller_telemetry.csv": ChillerTelemetryData,
    "pump_telemetry.csv": PumpTelemetryData,
}


@router.post("/upload/{file_type}", response_model=UploadResponse)
async def upload_csv(
    file_type: str,
    file: UploadFile = File(...),
):
    """
    Upload a CSV data file.

    Supported file types:
    - work_orders: Work order history from CAFM system
    - assets: Asset register with lifecycle data
    - sites: Site information with contract details
    - alarms: BCC alarm history (future)
    - energy_readings: Energy consumption data (future)
    """
    filename = f"{file_type}.csv"

    if filename not in ALLOWED_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {list(ALLOWED_FILES.keys())}"
        )

    # Validate file extension
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Only CSV files are allowed"
        )

    # Save the file
    filepath = DATA_DIR / filename

    try:
        # Create backup of existing file
        if filepath.exists():
            backup_path = DATA_DIR / f"{file_type}.csv.backup"
            shutil.copy(filepath, backup_path)

        # Write new file
        content = await file.read()
        with open(filepath, "wb") as f:
            f.write(content)

        # Reload the data cache
        loader_class = ALLOWED_FILES.get(filename)
        records_loaded = 0

        if loader_class:
            data = loader_class.load(force_reload=True)
            records_loaded = len(data)

        return UploadResponse(
            success=True,
            message=f"Successfully uploaded {filename}",
            filename=filename,
            records_loaded=records_loaded,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error uploading file: {str(e)}"
        )


@router.get("/data-status", response_model=DataStatusResponse)
async def get_data_status():
    """Get current data status - counts and totals."""
    work_orders = WorkOrderData.load()
    assets = AssetData.load()
    sites = SiteData.load()

    return DataStatusResponse(
        work_orders=len(work_orders),
        assets=len(assets),
        sites=len(sites),
        total_cost=sum(wo["total_cost"] for wo in work_orders),
        total_contract_value=SiteData.get_total_contract_value(),
    )


@router.post("/reload-data")
async def reload_all_data():
    """Force reload all CSV data from files."""
    WorkOrderData.load(force_reload=True)
    AssetData.load(force_reload=True)
    SiteData.load(force_reload=True)
    AlarmData.load(force_reload=True)
    EnergyData.load(force_reload=True)
    GeneratorTelemetryData.load(force_reload=True)
    HVACTelemetryData.load(force_reload=True)
    VSDTelemetryData.load(force_reload=True)
    ChillerTelemetryData.load(force_reload=True)
    PumpTelemetryData.load(force_reload=True)

    return {
        "success": True,
        "message": "All data reloaded from CSV files",
        "work_orders": len(WorkOrderData.load()),
        "assets": len(AssetData.load()),
        "sites": len(SiteData.load()),
        "alarms": len(AlarmData.load()),
        "energy_readings": len(EnergyData.load()),
        "generator_telemetry": len(GeneratorTelemetryData.load()),
        "hvac_telemetry": len(HVACTelemetryData.load()),
        "vsd_telemetry": len(VSDTelemetryData.load()),
        "chiller_telemetry": len(ChillerTelemetryData.load()),
        "pump_telemetry": len(PumpTelemetryData.load()),
    }


@router.get("/download/{file_type}")
async def download_csv(file_type: str):
    """Download a CSV data file."""
    filename = f"{file_type}.csv"
    filepath = DATA_DIR / filename

    if not filepath.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File {filename} not found"
        )

    with open(filepath, "r") as f:
        content = f.read()

    return {
        "filename": filename,
        "content": content,
    }
