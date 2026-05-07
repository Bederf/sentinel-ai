"""Upload API endpoints for CSV data files."""

import shutil

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.csv_loader import (
    DATA_DIR,
    AlarmData,
    AssetData,
    ChillerTelemetryData,
    EnergyData,
    GeneratorTelemetryData,
    HVACTelemetryData,
    PumpTelemetryData,
    SiteData,
    VSDTelemetryData,
    WorkOrderData,
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
        raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {list(ALLOWED_FILES.keys())}")

    # Validate file extension
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")

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
        raise HTTPException(status_code=500, detail=f"Error uploading file: {e!s}")


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

    # Sync runtime hours from telemetry to equipment operating_data
    synced = _sync_telemetry_runtime_to_equipment()

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
        "runtime_synced": synced,
    }


def _sync_telemetry_runtime_to_equipment() -> int:
    """Sync latest runtime hours from telemetry CSVs to equipment operating_data.

    Matches telemetry asset_tag to equipment code by equipment TYPE
    (chiller→chiller, ahu→AHU, fcu→FCU, pump→pump, generator→generator).
    Takes max runtime across all telemetry readings per type.

    Returns:
        Number of equipment records updated.
    """
    try:
        from app.database.repositories.equipment_metadata_repository import EquipmentMetadataRepository
        from app.services.csv_loader import (
            ChillerTelemetryData,
            GeneratorTelemetryData,
            HVACTelemetryData,
            PumpTelemetryData,
            VSDTelemetryData,
        )

        meta_repo = EquipmentMetadataRepository()
        updated = 0

        # Collect latest runtime by equipment TYPE from all telemetry sources
        # Map asset_tag patterns to canonical equipment type
        TYPE_KEYWORDS = {
            "chiller": ["chiller", "ch-", "ch_"],
            "ahu": ["ahu", "air handling"],
            "fcu": ["fcu", "fan coil"],
            "pump": ["pump", "cp-", "hp-"],
            "generator": ["generator", "gen-", "genset"],
            "vsd": ["vsd", "drive", "inverter"],
        }

        def get_type_from_tag(asset_tag: str) -> str | None:
            tag_lower = asset_tag.lower()
            for eq_type, keywords in TYPE_KEYWORDS.items():
                if any(kw in tag_lower for kw in keywords):
                    return eq_type
            return None

        # Collect max runtime per equipment type from all telemetry
        max_runtime_by_type: dict[str, float] = {}
        for telemetry_class in (GeneratorTelemetryData, HVACTelemetryData, VSDTelemetryData, ChillerTelemetryData, PumpTelemetryData):
            data = telemetry_class.load()
            for row in data:
                asset_tag = row.get("asset_tag", "")
                run_hours = row.get("run_hours") or 0
                if not asset_tag or not run_hours:
                    continue
                eq_type = get_type_from_tag(asset_tag)
                if eq_type:
                    if eq_type not in max_runtime_by_type or run_hours > max_runtime_by_type[eq_type]:
                        max_runtime_by_type[eq_type] = run_hours

        if not max_runtime_by_type:
            return 0

        # Query all equipment and update by matching type
        from app.database.supabase_client import get_supabase_client
        client = get_supabase_client()
        all_equipment = client.table("equipment").select("id,code,type,operating_data").execute().data or []

        for equipment in all_equipment:
            eq_type = (equipment.get("type") or "").lower()
            # Match equipment type to telemetry type
            matched_type = None
            for tel_type, keywords in TYPE_KEYWORDS.items():
                if any(kw in eq_type for kw in keywords):
                    matched_type = tel_type
                    break
            if matched_type and matched_type in max_runtime_by_type:
                runtime_hours = max_runtime_by_type[matched_type]
                try:
                    meta_repo.update_operating_data(equipment["id"], {"total_runtime_hours": runtime_hours})
                    updated += 1
                except Exception:
                    pass

        return updated
    except Exception:
        return 0


@router.get("/download/{file_type}")
async def download_csv(file_type: str):
    """Download a CSV data file."""
    filename = f"{file_type}.csv"
    filepath = DATA_DIR / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"File {filename} not found")

    with open(filepath) as f:
        content = f.read()

    return {
        "filename": filename,
        "content": content,
    }
