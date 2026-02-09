"""Solar Grid Compliance Service — NRS 097-2-1 monitoring, SSEG reporting.

Monitors inverter behaviour against SA grid compliance standards:
  - NRS 097-2-1 voltage and frequency limits
  - Power quality (THD, DC injection, power factor)
  - SSEG export limit enforcement
  - NRS 097 certificate validity tracking
  - Anti-islanding verification
  - Compliance event logging and report generation

Pattern follows safety_boundary_service.py for rule evaluation.
"""

import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.services.solar_ingestion_service import get_solar_ingestion_service

logger = logging.getLogger(__name__)


# === Enums ===

class ComplianceStatus(str, Enum):
    """Traffic-light compliance status."""
    COMPLIANT = "compliant"
    WARNING = "warning"
    VIOLATION = "violation"


class ComplianceEventType(str, Enum):
    """Types of compliance events."""
    VOLTAGE_HIGH = "voltage_high"
    VOLTAGE_LOW = "voltage_low"
    FREQUENCY_HIGH = "frequency_high"
    FREQUENCY_LOW = "frequency_low"
    THD_EXCEEDED = "thd_exceeded"
    PF_LOW = "power_factor_low"
    DC_INJECTION = "dc_injection_high"
    EXPORT_LIMIT = "export_limit_exceeded"
    ANTI_ISLAND_TRIP = "anti_islanding_trip"
    RECONNECTION = "reconnection"
    CERT_EXPIRY_WARNING = "certificate_expiry_warning"
    CERT_EDITION_OUTDATED = "certificate_edition_outdated"


# === Dataclass Models ===

@dataclass
class VoltageCompliance:
    """Voltage compliance check result."""
    status: str  # compliant/warning/violation
    nominal_v: float = 230.0
    min_v: float = 207.0
    max_v: float = 253.0
    disconnect_low_v: float = 195.5
    disconnect_high_v: float = 264.5
    current_readings: List[Dict[str, Any]] = field(default_factory=list)
    violations_24h: int = 0
    violations: List[Dict[str, Any]] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "nominal_v": self.nominal_v,
            "limits": {
                "min_v": self.min_v,
                "max_v": self.max_v,
                "disconnect_low_v": self.disconnect_low_v,
                "disconnect_high_v": self.disconnect_high_v,
            },
            "current_readings": self.current_readings,
            "violations_24h": self.violations_24h,
            "violations": self.violations,
            "message": self.message,
        }


@dataclass
class FrequencyCompliance:
    """Frequency compliance check result."""
    status: str
    nominal_hz: float = 50.0
    min_hz: float = 49.0
    max_hz: float = 51.0
    disconnect_low_hz: float = 47.5
    disconnect_high_hz: float = 52.0
    current_readings: List[Dict[str, Any]] = field(default_factory=list)
    violations_24h: int = 0
    violations: List[Dict[str, Any]] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "nominal_hz": self.nominal_hz,
            "limits": {
                "min_hz": self.min_hz,
                "max_hz": self.max_hz,
                "disconnect_low_hz": self.disconnect_low_hz,
                "disconnect_high_hz": self.disconnect_high_hz,
            },
            "current_readings": self.current_readings,
            "violations_24h": self.violations_24h,
            "violations": self.violations,
            "message": self.message,
        }


@dataclass
class PowerQualityReport:
    """Power quality compliance check result."""
    status: str
    thd_pct: float = 0.0
    max_thd_pct: float = 5.0
    dc_injection_pct: float = 0.0
    max_dc_injection_pct: float = 0.5
    power_factor: float = 1.0
    power_factor_min: float = 0.95
    details: List[Dict[str, Any]] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "thd": {
                "current_pct": self.thd_pct,
                "limit_pct": self.max_thd_pct,
                "margin_pct": round(self.max_thd_pct - self.thd_pct, 2),
            },
            "dc_injection": {
                "current_pct": self.dc_injection_pct,
                "limit_pct": self.max_dc_injection_pct,
            },
            "power_factor": {
                "current": self.power_factor,
                "minimum": self.power_factor_min,
            },
            "details": self.details,
            "message": self.message,
        }


@dataclass
class ExportCompliance:
    """Export limit compliance check result."""
    status: str
    current_export_kw: float = 0.0
    export_limit_kw: Optional[float] = None
    zero_export_required: bool = False
    zero_export_tolerance_kw: float = 5.0
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "current_export_kw": self.current_export_kw,
            "export_limit_kw": self.export_limit_kw,
            "zero_export_required": self.zero_export_required,
            "zero_export_tolerance_kw": self.zero_export_tolerance_kw,
            "message": self.message,
        }


@dataclass
class CertificateStatus:
    """NRS 097 certificate status."""
    equipment: str
    cert_no: str
    standard: str
    date: str
    issuer: str
    expiry: Optional[str] = None
    status: str = "valid"
    edition_current: bool = True
    days_to_expiry: Optional[int] = None
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "equipment": self.equipment,
            "cert_no": self.cert_no,
            "standard": self.standard,
            "date": self.date,
            "issuer": self.issuer,
            "expiry": self.expiry,
            "status": self.status,
            "edition_current": self.edition_current,
            "days_to_expiry": self.days_to_expiry,
            "message": self.message,
        }


@dataclass
class ComplianceEvent:
    """A compliance event (violation, reconnection, etc.)."""
    timestamp: str
    event_type: str
    severity: str  # warning/violation/info
    equipment_id: str
    description: str
    value: Optional[float] = None
    limit: Optional[float] = None
    resolved: bool = False
    resolved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "severity": self.severity,
            "equipment_id": self.equipment_id,
            "description": self.description,
            "value": self.value,
            "limit": self.limit,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at,
        }


@dataclass
class ComplianceReport:
    """Full compliance report for SSEG utility submission."""
    site_id: str
    site_name: str
    period: str
    generated_at: str
    overall_status: str
    sseg_category: str
    voltage: VoltageCompliance = field(default_factory=lambda: VoltageCompliance(status="compliant"))
    frequency: FrequencyCompliance = field(default_factory=lambda: FrequencyCompliance(status="compliant"))
    power_quality: PowerQualityReport = field(default_factory=lambda: PowerQualityReport(status="compliant"))
    export: ExportCompliance = field(default_factory=lambda: ExportCompliance(status="compliant"))
    certificates: List[CertificateStatus] = field(default_factory=list)
    events: List[ComplianceEvent] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "site_name": self.site_name,
            "period": self.period,
            "generated_at": self.generated_at,
            "overall_status": self.overall_status,
            "sseg_category": self.sseg_category,
            "voltage": self.voltage.to_dict(),
            "frequency": self.frequency.to_dict(),
            "power_quality": self.power_quality.to_dict(),
            "export": self.export.to_dict(),
            "certificates": [c.to_dict() for c in self.certificates],
            "events_count": len(self.events),
            "events": [e.to_dict() for e in self.events],
            "summary": self.summary,
        }


# === Service ===

class SolarComplianceService:
    """Monitors solar installation compliance with SA grid standards.

    Checks NRS 097-2-1 voltage/frequency limits, power quality (THD, PF,
    DC injection), SSEG export limits, and certificate validity.
    Simulates occasional violations for demo realism.
    """

    def __init__(self):
        self._rules: Dict[str, Any] = {}
        self._events: List[ComplianceEvent] = []
        self._load_rules()
        self._seed_demo_events()

    def _load_rules(self) -> None:
        """Load compliance rules from JSON configuration."""
        rules_path = Path(__file__).parent.parent / "data" / "solar" / "compliance_rules.json"
        try:
            with open(rules_path) as f:
                self._rules = json.load(f)
            logger.info("Loaded solar compliance rules from %s", rules_path.name)
        except Exception as e:
            logger.error("Failed to load compliance rules: %s", e)
            self._rules = {}

    def _seed_demo_events(self) -> None:
        """Seed realistic compliance events for demo purposes.

        Simulates:
          - A voltage dip during load shedding transition (common in SA)
          - A brief frequency excursion during Eskom grid instability
          - A reconnection event after the frequency event
        """
        now = datetime.now(timezone.utc)

        # Voltage dip during load shedding transition (4 hours ago)
        ls_time = now - timedelta(hours=4, minutes=12)
        self._events.append(ComplianceEvent(
            timestamp=ls_time.isoformat(),
            event_type=ComplianceEventType.VOLTAGE_LOW.value,
            severity="warning",
            equipment_id="S002-MTR-GRID",
            description=(
                "Grid voltage dipped to 204.3V during load shedding Stage 2 "
                "transition. Below NRS 097 minimum (207V) for 3.2 seconds. "
                "Inverters maintained operation (above disconnect threshold 195.5V)."
            ),
            value=204.3,
            limit=207.0,
            resolved=True,
            resolved_at=(ls_time + timedelta(seconds=3.2)).isoformat(),
        ))

        # Frequency excursion (8 hours ago)
        freq_time = now - timedelta(hours=8, minutes=45)
        self._events.append(ComplianceEvent(
            timestamp=freq_time.isoformat(),
            event_type=ComplianceEventType.FREQUENCY_LOW.value,
            severity="warning",
            equipment_id="S002-MTR-GRID",
            description=(
                "Grid frequency dropped to 48.7 Hz during Eskom generation "
                "shortfall. Below NRS 097 minimum (49.0 Hz) for 1.8 seconds. "
                "Inverters remained connected (above disconnect threshold 47.5 Hz)."
            ),
            value=48.7,
            limit=49.0,
            resolved=True,
            resolved_at=(freq_time + timedelta(seconds=1.8)).isoformat(),
        ))

        # Reconnection after frequency event
        self._events.append(ComplianceEvent(
            timestamp=(freq_time + timedelta(seconds=62)).isoformat(),
            event_type=ComplianceEventType.RECONNECTION.value,
            severity="info",
            equipment_id="S002-MTR-GRID",
            description=(
                "Grid frequency recovered to 50.01 Hz. All inverters confirmed "
                "reconnection after 60-second delay per NRS 097-2-1 requirements."
            ),
            value=50.01,
            limit=49.0,
            resolved=True,
            resolved_at=(freq_time + timedelta(seconds=62)).isoformat(),
        ))

        logger.info("Seeded %d demo compliance events", len(self._events))

    # === Voltage Compliance ===

    async def check_voltage_compliance(self, site_id: str) -> VoltageCompliance:
        """Check all meter/inverter voltage readings against NRS 097 limits."""
        nrs = self._rules.get("nrs_097_2_1", {})
        v_limits = nrs.get("voltage_limits", {})

        nominal = v_limits.get("nominal_v", 230)
        min_v = v_limits.get("min_v", 207)
        max_v = v_limits.get("max_v", 253)
        disc_low = v_limits.get("disconnect_low_v", 195.5)
        disc_high = v_limits.get("disconnect_high_v", 264.5)

        ingestion = get_solar_ingestion_service()
        meters = await ingestion.get_meter_readings(site_id)

        current_readings = []
        violations = []
        status = ComplianceStatus.COMPLIANT.value

        for meter in meters:
            voltage = meter.voltage_v
            # Phase voltage (line-to-neutral) for NRS 097 comparison
            # Grid meters read line-to-line (400V); convert to phase
            phase_v = voltage / 1.732 if voltage > 300 else voltage

            reading = {
                "meter_id": meter.meter_id,
                "name": meter.name,
                "voltage_v": round(voltage, 1),
                "phase_voltage_v": round(phase_v, 1),
            }
            current_readings.append(reading)

            if phase_v < min_v or phase_v > max_v:
                if phase_v < disc_low or phase_v > disc_high:
                    status = ComplianceStatus.VIOLATION.value
                    violations.append({
                        "meter_id": meter.meter_id,
                        "voltage_v": round(phase_v, 1),
                        "type": "disconnect_required",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                else:
                    if status != ComplianceStatus.VIOLATION.value:
                        status = ComplianceStatus.WARNING.value
                    violations.append({
                        "meter_id": meter.meter_id,
                        "voltage_v": round(phase_v, 1),
                        "type": "outside_normal_range",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

        # Count historical violations in last 24h from events
        now = datetime.now(timezone.utc)
        v_events_24h = [
            e for e in self._events
            if e.event_type in (ComplianceEventType.VOLTAGE_HIGH.value, ComplianceEventType.VOLTAGE_LOW.value)
            and datetime.fromisoformat(e.timestamp) > now - timedelta(hours=24)
        ]

        message = "All voltage readings within NRS 097-2-1 limits"
        if violations:
            message = f"{len(violations)} voltage reading(s) outside normal range"
        elif v_events_24h:
            message = f"Currently compliant; {len(v_events_24h)} event(s) in last 24 hours"

        return VoltageCompliance(
            status=status,
            nominal_v=nominal,
            min_v=min_v,
            max_v=max_v,
            disconnect_low_v=disc_low,
            disconnect_high_v=disc_high,
            current_readings=current_readings,
            violations_24h=len(v_events_24h),
            violations=violations,
            message=message,
        )

    # === Frequency Compliance ===

    async def check_frequency_compliance(self, site_id: str) -> FrequencyCompliance:
        """Check inverter/meter frequency readings against NRS 097 limits."""
        nrs = self._rules.get("nrs_097_2_1", {})
        f_limits = nrs.get("frequency_limits", {})

        nominal = f_limits.get("nominal_hz", 50)
        min_hz = f_limits.get("min_hz", 49.0)
        max_hz = f_limits.get("max_hz", 51.0)
        disc_low = f_limits.get("disconnect_low_hz", 47.5)
        disc_high = f_limits.get("disconnect_high_hz", 52.0)

        ingestion = get_solar_ingestion_service()
        meters = await ingestion.get_meter_readings(site_id)

        current_readings = []
        violations = []
        status = ComplianceStatus.COMPLIANT.value

        for meter in meters:
            freq = meter.frequency_hz
            reading = {
                "meter_id": meter.meter_id,
                "name": meter.name,
                "frequency_hz": round(freq, 2),
            }
            current_readings.append(reading)

            if freq < min_hz or freq > max_hz:
                if freq < disc_low or freq > disc_high:
                    status = ComplianceStatus.VIOLATION.value
                    violations.append({
                        "meter_id": meter.meter_id,
                        "frequency_hz": round(freq, 2),
                        "type": "disconnect_required",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                else:
                    if status != ComplianceStatus.VIOLATION.value:
                        status = ComplianceStatus.WARNING.value
                    violations.append({
                        "meter_id": meter.meter_id,
                        "frequency_hz": round(freq, 2),
                        "type": "outside_normal_range",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

        # Count historical frequency events in last 24h
        now = datetime.now(timezone.utc)
        f_events_24h = [
            e for e in self._events
            if e.event_type in (ComplianceEventType.FREQUENCY_HIGH.value, ComplianceEventType.FREQUENCY_LOW.value)
            and datetime.fromisoformat(e.timestamp) > now - timedelta(hours=24)
        ]

        message = "All frequency readings within NRS 097-2-1 limits"
        if violations:
            message = f"{len(violations)} frequency reading(s) outside normal range"
        elif f_events_24h:
            message = f"Currently compliant; {len(f_events_24h)} event(s) in last 24 hours"

        return FrequencyCompliance(
            status=status,
            nominal_hz=nominal,
            min_hz=min_hz,
            max_hz=max_hz,
            disconnect_low_hz=disc_low,
            disconnect_high_hz=disc_high,
            current_readings=current_readings,
            violations_24h=len(f_events_24h),
            violations=violations,
            message=message,
        )

    # === Power Quality ===

    async def check_power_quality(self, site_id: str) -> PowerQualityReport:
        """Check THD, DC injection, and power factor against NRS 097 limits."""
        nrs = self._rules.get("nrs_097_2_1", {})
        pq = nrs.get("power_quality", {})

        max_thd = pq.get("max_thd_pct", 5.0)
        max_dc = pq.get("max_dc_injection_pct", 0.5)
        pf_min = pq.get("power_factor_min", 0.95)

        ingestion = get_solar_ingestion_service()
        meters = await ingestion.get_meter_readings(site_id)
        inverters = await ingestion.get_inverters(site_id)

        # Aggregate THD from meters
        thd_values = [m.thd_pct for m in meters if m.thd_pct > 0]
        avg_thd = sum(thd_values) / len(thd_values) if thd_values else 0.0

        # Simulate near-limit THD for demo (makes compliance dashboard
        # non-trivially empty — shows realistic warning state for SA grid)
        if avg_thd < 3.5:
            avg_thd = round(random.uniform(4.2, 4.9), 1)

        # DC injection is simulated (requires specialised measurement)
        dc_injection = round(random.uniform(0.05, 0.25), 2)

        # Average power factor from meters
        pf_values = [m.power_factor for m in meters if m.power_factor > 0]
        avg_pf = sum(pf_values) / len(pf_values) if pf_values else 1.0

        # Determine status
        status = ComplianceStatus.COMPLIANT.value
        details = []

        if avg_thd > max_thd:
            status = ComplianceStatus.VIOLATION.value
            details.append({
                "parameter": "THD",
                "status": "violation",
                "message": f"THD {avg_thd}% exceeds {max_thd}% limit",
            })
        elif avg_thd > max_thd * 0.9:
            if status != ComplianceStatus.VIOLATION.value:
                status = ComplianceStatus.WARNING.value
            details.append({
                "parameter": "THD",
                "status": "warning",
                "message": f"THD {avg_thd}% approaching {max_thd}% limit ({round(max_thd - avg_thd, 1)}% margin)",
            })

        if dc_injection > max_dc:
            status = ComplianceStatus.VIOLATION.value
            details.append({
                "parameter": "DC Injection",
                "status": "violation",
                "message": f"DC injection {dc_injection}% exceeds {max_dc}% limit",
            })

        if avg_pf < pf_min:
            if status != ComplianceStatus.VIOLATION.value:
                status = ComplianceStatus.WARNING.value
            details.append({
                "parameter": "Power Factor",
                "status": "warning",
                "message": f"Power factor {avg_pf:.3f} below {pf_min} minimum",
            })

        message = "All power quality parameters within NRS 097-2-1 limits"
        if details:
            warnings = [d for d in details if d["status"] == "warning"]
            violations_list = [d for d in details if d["status"] == "violation"]
            parts = []
            if violations_list:
                parts.append(f"{len(violations_list)} violation(s)")
            if warnings:
                parts.append(f"{len(warnings)} warning(s)")
            message = "Power quality: " + ", ".join(parts)

        return PowerQualityReport(
            status=status,
            thd_pct=round(avg_thd, 1),
            max_thd_pct=max_thd,
            dc_injection_pct=dc_injection,
            max_dc_injection_pct=max_dc,
            power_factor=round(avg_pf, 3),
            power_factor_min=pf_min,
            details=details,
            message=message,
        )

    # === Export Compliance ===

    async def check_export_compliance(self, site_id: str) -> ExportCompliance:
        """Verify grid export against SSEG limits (zero-export or capped)."""
        sseg = self._rules.get("sseg_category_b", {})
        export_limit = sseg.get("export_limit_kw")
        zero_export = sseg.get("zero_export_required", False)

        ingestion = get_solar_ingestion_service()
        meters = await ingestion.get_meter_readings(site_id)

        current_export = sum(m.export_kw for m in meters)
        tolerance = 5.0  # kW tolerance for zero-export

        status = ComplianceStatus.COMPLIANT.value
        message = "Export within SSEG limits"

        if zero_export:
            if current_export > tolerance:
                status = ComplianceStatus.VIOLATION.value
                message = (
                    f"Zero-export violation: exporting {current_export:.1f} kW "
                    f"(tolerance: {tolerance} kW)"
                )
            else:
                message = f"Zero-export compliant: {current_export:.1f} kW (tolerance: {tolerance} kW)"
        elif export_limit is not None:
            if current_export > export_limit:
                status = ComplianceStatus.VIOLATION.value
                message = (
                    f"Export limit exceeded: {current_export:.1f} kW / "
                    f"{export_limit} kW limit"
                )
            elif current_export > export_limit * 0.9:
                status = ComplianceStatus.WARNING.value
                message = (
                    f"Approaching export limit: {current_export:.1f} kW / "
                    f"{export_limit} kW (90% threshold)"
                )
            else:
                message = f"Export within limit: {current_export:.1f} kW / {export_limit} kW"
        else:
            message = f"No export limit configured (SSEG Category B); current export: {current_export:.1f} kW"

        return ExportCompliance(
            status=status,
            current_export_kw=round(current_export, 1),
            export_limit_kw=export_limit,
            zero_export_required=zero_export,
            zero_export_tolerance_kw=tolerance,
            message=message,
        )

    # === Certificate Validity ===

    async def check_certificate_validity(self, site_id: str) -> List[CertificateStatus]:
        """Check NRS 097 certificate dates, flag expiry or outdated editions."""
        certs_config = self._rules.get("nrs_097_certificates", [])
        now = datetime.now(timezone.utc)
        current_edition = "NRS 097-2-1:2024 Ed.3"

        results = []
        for cert in certs_config:
            expiry = cert.get("expiry")
            days_to_expiry = None
            cert_status = "valid"
            edition_current = cert.get("standard", "") == current_edition
            message = "Certificate valid"

            if expiry:
                try:
                    expiry_date = datetime.strptime(expiry, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    days_to_expiry = (expiry_date - now).days
                    if days_to_expiry < 0:
                        cert_status = "expired"
                        message = f"Certificate expired {abs(days_to_expiry)} days ago"
                    elif days_to_expiry < 90:
                        cert_status = "expiry_warning"
                        message = f"Certificate expires in {days_to_expiry} days"
                except ValueError:
                    pass

            if not edition_current and cert_status == "valid":
                cert_status = "edition_outdated"
                message = (
                    f"Certified under {cert.get('standard', 'unknown')}; "
                    f"current edition is {current_edition}"
                )

            results.append(CertificateStatus(
                equipment=cert.get("equipment", ""),
                cert_no=cert.get("cert_no", ""),
                standard=cert.get("standard", ""),
                date=cert.get("date", ""),
                issuer=cert.get("issuer", ""),
                expiry=expiry,
                status=cert_status,
                edition_current=edition_current,
                days_to_expiry=days_to_expiry,
                message=message,
            ))

        return results

    # === Compliance Report ===

    async def generate_compliance_report(
        self, site_id: str, period: str = "month"
    ) -> Optional[ComplianceReport]:
        """Generate full SSEG compliance report for utility submission."""
        ingestion = get_solar_ingestion_service()
        sites = ingestion.get_registered_sites()
        site_info = next((s for s in sites if s["site_id"] == site_id), None)
        if not site_info:
            return None

        # Load site config for SSEG category
        site_reg = ingestion._sites.get(site_id)
        sseg_category = "B"
        if site_reg and site_reg.config.get("grid", {}).get("sseg_category"):
            sseg_category = site_reg.config["grid"]["sseg_category"]

        # Run all checks
        voltage = await self.check_voltage_compliance(site_id)
        frequency = await self.check_frequency_compliance(site_id)
        power_quality = await self.check_power_quality(site_id)
        export = await self.check_export_compliance(site_id)
        certificates = await self.check_certificate_validity(site_id)

        # Get events for the period
        now = datetime.now(timezone.utc)
        if period == "week":
            from_ts = now - timedelta(weeks=1)
        elif period == "day":
            from_ts = now - timedelta(days=1)
        else:
            from_ts = now - timedelta(days=30)

        events = await self.get_compliance_events(site_id, from_ts.isoformat(), now.isoformat())

        # Determine overall status
        statuses = [
            voltage.status,
            frequency.status,
            power_quality.status,
            export.status,
        ]

        # Certificate status
        cert_statuses = [c.status for c in certificates]
        if "expired" in cert_statuses:
            statuses.append(ComplianceStatus.VIOLATION.value)
        elif "edition_outdated" in cert_statuses or "expiry_warning" in cert_statuses:
            statuses.append(ComplianceStatus.WARNING.value)

        if ComplianceStatus.VIOLATION.value in statuses:
            overall = ComplianceStatus.VIOLATION.value
        elif ComplianceStatus.WARNING.value in statuses:
            overall = ComplianceStatus.WARNING.value
        else:
            overall = ComplianceStatus.COMPLIANT.value

        # Build summary
        total_events = len(events)
        violations_count = sum(1 for e in events if e.severity == "violation")
        warnings_count = sum(1 for e in events if e.severity == "warning")

        summary = {
            "total_events": total_events,
            "violations": violations_count,
            "warnings": warnings_count,
            "certificates_valid": sum(1 for c in certificates if c.status == "valid"),
            "certificates_expired": sum(1 for c in certificates if c.status == "expired"),
            "certificates_outdated": sum(1 for c in certificates if c.status == "edition_outdated"),
            "reporting_period": period,
            "utility": "City Power Johannesburg",
        }

        # Next report due
        if period == "month":
            next_month = now.replace(day=1) + timedelta(days=32)
            next_report = next_month.replace(day=1).strftime("%Y-%m-%d")
            summary["next_report_due"] = next_report

        return ComplianceReport(
            site_id=site_id,
            site_name=site_info.get("site_name", site_id),
            period=period,
            generated_at=now.isoformat(),
            overall_status=overall,
            sseg_category=sseg_category,
            voltage=voltage,
            frequency=frequency,
            power_quality=power_quality,
            export=export,
            certificates=certificates,
            events=events,
            summary=summary,
        )

    # === Compliance Events ===

    async def get_compliance_events(
        self, site_id: str, from_ts: Optional[str] = None, to_ts: Optional[str] = None
    ) -> List[ComplianceEvent]:
        """Get historical compliance events, optionally filtered by time range."""
        events = list(self._events)

        if from_ts:
            try:
                from_dt = datetime.fromisoformat(from_ts)
                events = [
                    e for e in events
                    if datetime.fromisoformat(e.timestamp) >= from_dt
                ]
            except ValueError:
                pass

        if to_ts:
            try:
                to_dt = datetime.fromisoformat(to_ts)
                events = [
                    e for e in events
                    if datetime.fromisoformat(e.timestamp) <= to_dt
                ]
            except ValueError:
                pass

        # Sort by timestamp descending (most recent first)
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events

    # === Overall Status (for dashboard) ===

    async def get_overall_compliance(self, site_id: str) -> Optional[Dict[str, Any]]:
        """Get traffic-light compliance summary for dashboard display."""
        ingestion = get_solar_ingestion_service()
        sites = ingestion.get_registered_sites()
        site_info = next((s for s in sites if s["site_id"] == site_id), None)
        if not site_info:
            return None

        # Load site config for SSEG category
        site_reg = ingestion._sites.get(site_id)
        sseg_category = "B"
        if site_reg and site_reg.config.get("grid", {}).get("sseg_category"):
            sseg_category = site_reg.config["grid"]["sseg_category"]

        voltage = await self.check_voltage_compliance(site_id)
        frequency = await self.check_frequency_compliance(site_id)
        power_quality = await self.check_power_quality(site_id)
        export = await self.check_export_compliance(site_id)
        certificates = await self.check_certificate_validity(site_id)

        # Determine overall
        statuses = [voltage.status, frequency.status, power_quality.status, export.status]
        cert_statuses = [c.status for c in certificates]
        if "expired" in cert_statuses:
            statuses.append(ComplianceStatus.VIOLATION.value)
        elif "edition_outdated" in cert_statuses or "expiry_warning" in cert_statuses:
            statuses.append(ComplianceStatus.WARNING.value)

        if ComplianceStatus.VIOLATION.value in statuses:
            overall = ComplianceStatus.VIOLATION.value
        elif ComplianceStatus.WARNING.value in statuses:
            overall = ComplianceStatus.WARNING.value
        else:
            overall = ComplianceStatus.COMPLIANT.value

        # Next report due
        now = datetime.now(timezone.utc)
        next_month = now.replace(day=1) + timedelta(days=32)
        next_report_due = next_month.replace(day=1).strftime("%Y-%m-%d")

        return {
            "site_id": site_id,
            "overall_status": overall,
            "checks": {
                "voltage": {
                    "status": voltage.status,
                    "violations_24h": voltage.violations_24h,
                },
                "frequency": {
                    "status": frequency.status,
                    "violations_24h": frequency.violations_24h,
                },
                "power_quality": {
                    "status": power_quality.status,
                    "thd_pct": power_quality.thd_pct,
                    "limit": power_quality.max_thd_pct,
                },
                "export": {
                    "status": export.status,
                    "current_export_kw": export.current_export_kw,
                },
                "certificates": {
                    "status": "compliant" if all(
                        c.status == "valid" for c in certificates
                    ) else "warning",
                    "valid_count": sum(1 for c in certificates if c.status == "valid"),
                    "expired_count": sum(1 for c in certificates if c.status == "expired"),
                },
            },
            "next_report_due": next_report_due,
            "sseg_category": sseg_category,
        }


# === Singleton ===

_solar_compliance_service: Optional[SolarComplianceService] = None


def get_solar_compliance_service() -> SolarComplianceService:
    """Get the singleton solar compliance service instance."""
    global _solar_compliance_service
    if _solar_compliance_service is None:
        _solar_compliance_service = SolarComplianceService()
    return _solar_compliance_service
