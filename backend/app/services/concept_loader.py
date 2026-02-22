"""
Concept Evolution CAFM Data Loader

Loads and processes job cards and asset data from Concept Evolution exports.
Used for health/condition assessment and predictive maintenance.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from app.services.health_threshold_service import get_health_thresholds

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


@dataclass
class ConceptJobCard:
    """Concept Evolution job card/work order."""

    job_card_no: str
    task_ref: str
    priority: str  # P1, P2, P3, P4
    status: str
    logged_date: Optional[datetime]
    target_date: Optional[datetime]
    completed_date: Optional[datetime]
    sla_met: bool
    building_code: str
    building_name: str
    location_code: str
    location_desc: str
    asset_code: str
    asset_desc: str
    asset_category: str
    asset_criticality: str
    fault_code: str
    fault_desc: str
    problem_desc: str
    cause_code: str
    cause_desc: str
    action_taken: str
    technician_code: str
    technician_name: str
    labour_hours: float
    labour_cost: float
    parts_cost: float
    contractor_cost: float
    total_cost: float
    repeat_call: bool
    related_job_card: str
    ppm_ref: str
    compliance_type: str
    tech_notes: str
    customer_feedback: Optional[int]

    @property
    def priority_level(self) -> str:
        """Convert P1-P4 to severity levels."""
        mapping = {"P1": "critical", "P2": "high", "P3": "medium", "P4": "low"}
        return mapping.get(self.priority, "medium")

    @property
    def has_warning_flags(self) -> bool:
        """Check if technician notes contain warning keywords."""
        if not self.tech_notes:
            return False
        warning_keywords = [
            "URGENT",
            "CRITICAL",
            "WILL fail",
            "RECOMMEND",
            "WARNING",
            "same issue",
            "again",
            "recurring",
            "EXACTLY same",
            "catastrophic",
            "emergency",
        ]
        notes_upper = self.tech_notes.upper()
        return any(kw.upper() in notes_upper for kw in warning_keywords)


@dataclass
class ConceptAsset:
    """Concept Evolution asset record."""

    asset_code: str
    asset_desc: str
    asset_category: str
    asset_type: str
    manufacturer: str
    model: str
    serial_no: str
    building_code: str
    building_name: str
    location_code: str
    location_desc: str
    install_date: Optional[datetime]
    warranty_expiry: Optional[datetime]
    expected_life_years: int
    criticality: str
    condition: str
    condition_score: int
    last_service_date: Optional[datetime]
    next_service_date: Optional[datetime]
    ppm_frequency: str
    replacement_cost: float
    annual_maint_cost: float
    risk_rating: str
    compliance_req: str
    notes: str

    @property
    def age_years(self) -> int:
        """Calculate asset age in years."""
        if not self.install_date:
            return 0
        delta = datetime.now() - self.install_date
        return delta.days // 365

    @property
    def remaining_life_years(self) -> int:
        """Calculate remaining expected life."""
        return max(0, self.expected_life_years - self.age_years)

    @property
    def is_beyond_life(self) -> bool:
        """Check if asset is beyond expected life."""
        return self.age_years > self.expected_life_years

    @property
    def health_score(self) -> int:
        """
        Calculate health score (inverse of condition for SENTINEL).
        SENTINEL uses 0-100 where 100 is healthy.
        """
        return self.condition_score


def parse_datetime(value: str) -> Optional[datetime]:
    """Parse datetime from various formats."""
    if not value or value.strip() == "":
        return None

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue

    return None


def parse_bool(value: str) -> bool:
    """Parse boolean from Y/N or True/False."""
    return value.strip().upper() in ("Y", "YES", "TRUE", "1")


def parse_float(value: str) -> float:
    """Parse float, defaulting to 0.0."""
    try:
        return float(value.strip()) if value.strip() else 0.0
    except ValueError:
        return 0.0


def parse_int(value: str) -> int:
    """Parse int, defaulting to 0."""
    try:
        return int(float(value.strip())) if value.strip() else 0
    except ValueError:
        return 0


class ConceptDataLoader:
    """Load and query Concept Evolution CAFM data."""

    def __init__(self):
        self._job_cards: Optional[list[ConceptJobCard]] = None
        self._assets: Optional[list[ConceptAsset]] = None

    def _load_job_cards(self) -> list[ConceptJobCard]:
        """Load job cards from CSV."""
        filepath = DATA_DIR / "concept_jobcards.csv"
        if not filepath.exists():
            logger.warning(f"Concept job cards file not found: {filepath}")
            return []

        job_cards = []
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    jc = ConceptJobCard(
                        job_card_no=row.get("JobCardNo", ""),
                        task_ref=row.get("TaskRef", ""),
                        priority=row.get("Priority", "P3"),
                        status=row.get("Status", ""),
                        logged_date=parse_datetime(row.get("LoggedDate", "")),
                        target_date=parse_datetime(row.get("TargetDate", "")),
                        completed_date=parse_datetime(row.get("CompletedDate", "")),
                        sla_met=parse_bool(row.get("SLAMet", "N")),
                        building_code=row.get("BuildingCode", ""),
                        building_name=row.get("BuildingName", ""),
                        location_code=row.get("LocationCode", ""),
                        location_desc=row.get("LocationDesc", ""),
                        asset_code=row.get("AssetCode", ""),
                        asset_desc=row.get("AssetDesc", ""),
                        asset_category=row.get("AssetCategory", ""),
                        asset_criticality=row.get("AssetCriticality", ""),
                        fault_code=row.get("FaultCode", ""),
                        fault_desc=row.get("FaultDesc", ""),
                        problem_desc=row.get("ProblemDesc", ""),
                        cause_code=row.get("CauseCode", ""),
                        cause_desc=row.get("CauseDesc", ""),
                        action_taken=row.get("ActionTaken", ""),
                        technician_code=row.get("TechnicianCode", ""),
                        technician_name=row.get("TechnicianName", ""),
                        labour_hours=parse_float(row.get("LabourHours", "0")),
                        labour_cost=parse_float(row.get("LabourCost", "0")),
                        parts_cost=parse_float(row.get("PartsCost", "0")),
                        contractor_cost=parse_float(row.get("ContractorCost", "0")),
                        total_cost=parse_float(row.get("TotalCost", "0")),
                        repeat_call=parse_bool(row.get("RepeatCall", "N")),
                        related_job_card=row.get("RelatedJobCard", ""),
                        ppm_ref=row.get("PPMRef", ""),
                        compliance_type=row.get("ComplianceType", ""),
                        tech_notes=row.get("TechNotes", ""),
                        customer_feedback=parse_int(row.get("CustomerFeedback", "0")) or None,
                    )
                    job_cards.append(jc)
                except Exception as e:
                    logger.error(f"Error parsing job card row: {e}")

        logger.info(f"Loaded {len(job_cards)} Concept job cards")
        return job_cards

    def _load_assets(self) -> list[ConceptAsset]:
        """Load assets from CSV."""
        filepath = DATA_DIR / "concept_assets.csv"
        if not filepath.exists():
            logger.warning(f"Concept assets file not found: {filepath}")
            return []

        assets = []
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    asset = ConceptAsset(
                        asset_code=row.get("AssetCode", ""),
                        asset_desc=row.get("AssetDesc", ""),
                        asset_category=row.get("AssetCategory", ""),
                        asset_type=row.get("AssetType", ""),
                        manufacturer=row.get("Manufacturer", ""),
                        model=row.get("Model", ""),
                        serial_no=row.get("SerialNo", ""),
                        building_code=row.get("BuildingCode", ""),
                        building_name=row.get("BuildingName", ""),
                        location_code=row.get("LocationCode", ""),
                        location_desc=row.get("LocationDesc", ""),
                        install_date=parse_datetime(row.get("InstallDate", "")),
                        warranty_expiry=parse_datetime(row.get("WarrantyExpiry", "")),
                        expected_life_years=parse_int(row.get("ExpectedLifeYears", "20")),
                        criticality=row.get("Criticality", "Medium"),
                        condition=row.get("Condition", "Good"),
                        condition_score=parse_int(row.get("ConditionScore", "70")),
                        last_service_date=parse_datetime(row.get("LastServiceDate", "")),
                        next_service_date=parse_datetime(row.get("NextServiceDate", "")),
                        ppm_frequency=row.get("PPMFrequency", ""),
                        replacement_cost=parse_float(row.get("ReplacementCost", "0")),
                        annual_maint_cost=parse_float(row.get("AnnualMaintCost", "0")),
                        risk_rating=row.get("RiskRating", "Medium"),
                        compliance_req=row.get("ComplianceReq", ""),
                        notes=row.get("Notes", ""),
                    )
                    assets.append(asset)
                except Exception as e:
                    logger.error(f"Error parsing asset row: {e}")

        logger.info(f"Loaded {len(assets)} Concept assets")
        return assets

    @property
    def job_cards(self) -> list[ConceptJobCard]:
        """Lazy load job cards."""
        if self._job_cards is None:
            self._job_cards = self._load_job_cards()
        return self._job_cards

    @property
    def assets(self) -> list[ConceptAsset]:
        """Lazy load assets."""
        if self._assets is None:
            self._assets = self._load_assets()
        return self._assets

    def get_asset(self, asset_code: str) -> Optional[ConceptAsset]:
        """Get asset by code."""
        for asset in self.assets:
            if asset.asset_code == asset_code:
                return asset
        return None

    def get_job_cards_for_asset(self, asset_code: str) -> list[ConceptJobCard]:
        """Get all job cards for an asset."""
        return [jc for jc in self.job_cards if jc.asset_code == asset_code]

    def get_repeat_calls(self, asset_code: str, months: int = 12) -> list[ConceptJobCard]:
        """Get repeat calls for an asset within time period."""
        cutoff = datetime.now().replace(
            year=datetime.now().year - (months // 12), month=max(1, datetime.now().month - (months % 12))
        )
        return [
            jc
            for jc in self.job_cards
            if jc.asset_code == asset_code and jc.repeat_call and jc.logged_date and jc.logged_date >= cutoff
        ]

    def get_warning_job_cards(self, asset_code: str) -> list[ConceptJobCard]:
        """Get job cards with technician warning flags."""
        return [jc for jc in self.job_cards if jc.asset_code == asset_code and jc.has_warning_flags]

    def calculate_health_score(self, asset_code: str) -> dict:
        """
        Calculate comprehensive health score for an asset.

        Factors:
        - Base condition score from asset register (40%)
        - Repeat call frequency last 12 months (25%)
        - PPM compliance rate (15%)
        - Age vs expected life (10%)
        - Technician warning flags in notes (10%)
        """
        asset = self.get_asset(asset_code)
        if not asset:
            return {"error": "Asset not found", "health_score": 0}

        # Base condition (40%)
        base_score = asset.condition_score * 0.4

        # Repeat calls factor (25%) - more repeats = lower score
        repeat_calls = self.get_repeat_calls(asset_code, 12)
        repeat_penalty = min(len(repeat_calls) * 10, 25)  # Max 25% penalty
        repeat_score = 25 - repeat_penalty

        # PPM compliance (15%) - simplified: assume compliant if last service recent
        ppm_score = 15
        if asset.last_service_date:
            days_since_service = (datetime.now() - asset.last_service_date).days
            if days_since_service > 180:  # Overdue
                ppm_score = 5
            elif days_since_service > 120:
                ppm_score = 10

        # Age factor (10%)
        age_score = 10
        if asset.is_beyond_life:
            age_score = 0
        elif asset.remaining_life_years <= 2:
            age_score = 3
        elif asset.remaining_life_years <= 5:
            age_score = 6

        # Warning flags (10%)
        warnings = self.get_warning_job_cards(asset_code)
        warning_score = max(0, 10 - len(warnings) * 3)

        total_score = int(base_score + repeat_score + ppm_score + age_score + warning_score)

        return {
            "asset_code": asset_code,
            "asset_desc": asset.asset_desc,
            "health_score": total_score,
            "condition_rating": asset.condition,
            "factors": {
                "base_condition": {"score": base_score, "weight": "40%", "raw": asset.condition_score},
                "repeat_calls": {"score": repeat_score, "weight": "25%", "count": len(repeat_calls)},
                "ppm_compliance": {"score": ppm_score, "weight": "15%"},
                "age_factor": {
                    "score": age_score,
                    "weight": "10%",
                    "age": asset.age_years,
                    "expected": asset.expected_life_years,
                },
                "warning_flags": {"score": warning_score, "weight": "10%", "count": len(warnings)},
            },
            "risk_level": "Critical"
            if total_score < 40
            else "High"
            if total_score < 60
            else "Medium"
            if total_score < 80
            else "Low",
            "recommendations": self._generate_recommendations(asset, repeat_calls, warnings),
        }

    def _generate_recommendations(
        self, asset: ConceptAsset, repeat_calls: list[ConceptJobCard], warnings: list[ConceptJobCard]
    ) -> list[str]:
        """Generate maintenance recommendations based on health factors."""
        recommendations = []

        if asset.is_beyond_life:
            recommendations.append(
                f"Asset is {asset.age_years - asset.expected_life_years} years beyond expected life. Plan replacement."
            )

        if len(repeat_calls) >= 3:
            recommendations.append(
                f"{len(repeat_calls)} repeat calls in 12 months indicates "
                f"systemic issue. Root cause analysis recommended."
            )

        if warnings:
            latest_warning = max(warnings, key=lambda x: x.logged_date or datetime.min)
            recommendations.append(f"Technician flagged: {latest_warning.tech_notes[:100]}...")

        if asset.condition_score < 50:
            recommendations.append(
                f"Condition score {asset.condition_score}/100 is poor. Comprehensive inspection needed."
            )

        if not recommendations:
            recommendations.append("Asset in acceptable condition. Continue regular PPM schedule.")

        return recommendations

    def get_assets_at_risk(self) -> list[dict]:
        """Get all assets with health score below configured warning threshold."""
        at_risk = []
        thresholds = get_health_thresholds()
        for asset in self.assets:
            health = self.calculate_health_score(asset.asset_code)
            if health.get("health_score", 100) < thresholds["warning"]:
                at_risk.append(health)

        return sorted(at_risk, key=lambda x: x.get("health_score", 100))

    def get_building_summary(self, building_code: str) -> dict:
        """Get health summary for all assets in a building."""
        building_assets = [a for a in self.assets if a.building_code == building_code]

        if not building_assets:
            return {"error": "Building not found"}

        health_scores = []
        critical_assets = []
        thresholds = get_health_thresholds()

        for asset in building_assets:
            health = self.calculate_health_score(asset.asset_code)
            health_scores.append(health.get("health_score", 0))
            if health.get("health_score", 100) < thresholds["critical"]:
                critical_assets.append(health)

        return {
            "building_code": building_code,
            "building_name": building_assets[0].building_name,
            "total_assets": len(building_assets),
            "average_health": sum(health_scores) // len(health_scores) if health_scores else 0,
            "critical_assets": len(critical_assets),
            "assets_at_risk": critical_assets,
        }


# Singleton instance
concept_loader = ConceptDataLoader()
