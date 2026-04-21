"""Indoor Air Quality Intelligence Service.

Calculates IAQ scores per zone from existing telemetry (CO2, humidity,
temperature, VOC, PM2.5). Generates alerts when thresholds are exceeded
and produces compliance reports for WELL/ESG certification.

Uses existing zone data from HVACZoneRepository and JSON fallback.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.iaq import (
    IAQAlert,
    IAQComplianceReport,
    IAQComponentScore,
    IAQSiteOverview,
    IAQZoneScore,
)

logger = logging.getLogger("sentinel.iaq")

DATA_DIR = Path(__file__).parent.parent / "data"

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# CO2 thresholds (ppm)
CO2_EXCELLENT = 600
CO2_GOOD = 800
CO2_WARNING = 900  # was 1000 — 950ppm sustained across 20 zones warrants warning
CO2_CRITICAL = 1500

# Humidity thresholds (%)
HUMIDITY_LOW_CRITICAL = 20
HUMIDITY_LOW_WARNING = 30
HUMIDITY_EXCELLENT_MIN = 40
HUMIDITY_EXCELLENT_MAX = 55
HUMIDITY_WARNING = 60
HUMIDITY_CRITICAL = 70

# Temperature deviation from setpoint (C)
TEMP_DEV_EXCELLENT = 0.5
TEMP_DEV_GOOD = 1.0
TEMP_DEV_WARNING = 2.0
TEMP_DEV_CRITICAL = 3.0

# VOC thresholds (ppb)
VOC_EXCELLENT = 100
VOC_GOOD = 300
VOC_WARNING = 500
VOC_CRITICAL = 1000

# PM2.5 thresholds (ug/m3)
PM25_EXCELLENT = 10
PM25_GOOD = 15
PM25_WARNING = 25
PM25_CRITICAL = 50

# Component weights for composite IAQ score
WEIGHTS = {
    "co2": 0.30,
    "humidity": 0.20,
    "temperature": 0.25,
    "voc": 0.15,
    "pm25": 0.10,
}


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------


def _score_status(score: float) -> str:
    if score >= 90:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 50:
        return "poor"
    return "unhealthy"


def _score_co2(ppm: float | None) -> tuple[float, str]:
    """Score CO2 level. Lower is better."""
    if ppm is None:
        return 75.0, "No sensor"
    if ppm <= CO2_EXCELLENT:
        score = 100.0
    elif ppm <= CO2_GOOD:
        score = 100 - ((ppm - CO2_EXCELLENT) / (CO2_GOOD - CO2_EXCELLENT)) * 20
    elif ppm <= CO2_WARNING:
        score = 80 - ((ppm - CO2_GOOD) / (CO2_WARNING - CO2_GOOD)) * 30
    elif ppm <= CO2_CRITICAL:
        score = 50 - ((ppm - CO2_WARNING) / (CO2_CRITICAL - CO2_WARNING)) * 30
    else:
        score = max(0, 20 - ((ppm - CO2_CRITICAL) / 500) * 20)
    return round(score, 1), f"{ppm:.0f} ppm"


def _score_humidity(rh: float | None) -> tuple[float, str]:
    """Score humidity. Optimal range 40-55%."""
    if rh is None:
        return 75.0, "No sensor"
    if HUMIDITY_EXCELLENT_MIN <= rh <= HUMIDITY_EXCELLENT_MAX:
        score = 100.0
    elif HUMIDITY_LOW_WARNING <= rh < HUMIDITY_EXCELLENT_MIN:
        score = 80 - ((HUMIDITY_EXCELLENT_MIN - rh) / (HUMIDITY_EXCELLENT_MIN - HUMIDITY_LOW_WARNING)) * 30
    elif rh < HUMIDITY_LOW_WARNING:
        score = max(0, 50 - ((HUMIDITY_LOW_WARNING - rh) / 10) * 25)
    elif HUMIDITY_EXCELLENT_MAX < rh <= HUMIDITY_WARNING:
        score = 80 - ((rh - HUMIDITY_EXCELLENT_MAX) / (HUMIDITY_WARNING - HUMIDITY_EXCELLENT_MAX)) * 30
    elif HUMIDITY_WARNING < rh <= HUMIDITY_CRITICAL:
        score = 50 - ((rh - HUMIDITY_WARNING) / (HUMIDITY_CRITICAL - HUMIDITY_WARNING)) * 30
    else:
        score = max(0, 20 - ((rh - HUMIDITY_CRITICAL) / 10) * 20)
    return round(score, 1), f"{rh:.1f}%"


def _score_temperature(temp: float | None, setpoint: float | None) -> tuple[float, str]:
    """Score temperature deviation from setpoint."""
    if temp is None or setpoint is None:
        return 75.0, "No sensor"
    deviation = abs(temp - setpoint)
    if deviation <= TEMP_DEV_EXCELLENT:
        score = 100.0
    elif deviation <= TEMP_DEV_GOOD:
        score = 90 - ((deviation - TEMP_DEV_EXCELLENT) / (TEMP_DEV_GOOD - TEMP_DEV_EXCELLENT)) * 10
    elif deviation <= TEMP_DEV_WARNING:
        score = 80 - ((deviation - TEMP_DEV_GOOD) / (TEMP_DEV_WARNING - TEMP_DEV_GOOD)) * 30
    elif deviation <= TEMP_DEV_CRITICAL:
        score = 50 - ((deviation - TEMP_DEV_WARNING) / (TEMP_DEV_CRITICAL - TEMP_DEV_WARNING)) * 30
    else:
        score = max(0, 20 - ((deviation - TEMP_DEV_CRITICAL) / 2) * 20)
    return round(score, 1), f"{deviation:.1f}C deviation"


def _score_voc(ppb: float | None) -> tuple[float, str]:
    """Score VOC level. Lower is better."""
    if ppb is None:
        return 75.0, "No sensor"
    if ppb <= VOC_EXCELLENT:
        score = 100.0
    elif ppb <= VOC_GOOD:
        score = 80 - ((ppb - VOC_EXCELLENT) / (VOC_GOOD - VOC_EXCELLENT)) * 20
    elif ppb <= VOC_WARNING:
        score = 60 - ((ppb - VOC_GOOD) / (VOC_WARNING - VOC_GOOD)) * 20
    elif ppb <= VOC_CRITICAL:
        score = 40 - ((ppb - VOC_WARNING) / (VOC_CRITICAL - VOC_WARNING)) * 20
    else:
        score = max(0, 20 - ((ppb - VOC_CRITICAL) / 500) * 20)
    return round(score, 1), f"{ppb:.0f} ppb"


def _score_pm25(ugm3: float | None) -> tuple[float, str]:
    """Score PM2.5 level. Lower is better."""
    if ugm3 is None:
        return 75.0, "No sensor"
    if ugm3 <= PM25_EXCELLENT:
        score = 100.0
    elif ugm3 <= PM25_GOOD:
        score = 80 - ((ugm3 - PM25_EXCELLENT) / (PM25_GOOD - PM25_EXCELLENT)) * 20
    elif ugm3 <= PM25_WARNING:
        score = 60 - ((ugm3 - PM25_GOOD) / (PM25_WARNING - PM25_GOOD)) * 20
    elif ugm3 <= PM25_CRITICAL:
        score = 40 - ((ugm3 - PM25_WARNING) / (PM25_CRITICAL - PM25_WARNING)) * 20
    else:
        score = max(0, 20 - ((ugm3 - PM25_CRITICAL) / 50) * 20)
    return round(score, 1), f"{ugm3:.1f} ug/m3"


# ---------------------------------------------------------------------------
# Alert generation
# ---------------------------------------------------------------------------


def _generate_alerts(zone: dict[str, Any]) -> list[IAQAlert]:
    """Generate IAQ alerts for a zone based on thresholds."""
    alerts: list[IAQAlert] = []
    zone_id = zone.get("zone_id", "")
    zone_name = zone.get("zone_name", zone_id)
    floor = zone.get("floor", "")
    site_id = zone.get("site_id", "")

    co2 = zone.get("co2_ppm")
    if co2 is not None:
        if co2 >= CO2_CRITICAL:
            alerts.append(
                IAQAlert(
                    zone_id=zone_id,
                    zone_name=zone_name,
                    floor=floor,
                    site_id=site_id,
                    alert_type="co2_high",
                    severity="critical",
                    message=f"CO2 at {co2:.0f} ppm — exceeds critical threshold ({CO2_CRITICAL} ppm)",
                    current_value=co2,
                    threshold=CO2_CRITICAL,
                    unit="ppm",
                )
            )
        elif co2 >= CO2_WARNING:
            alerts.append(
                IAQAlert(
                    zone_id=zone_id,
                    zone_name=zone_name,
                    floor=floor,
                    site_id=site_id,
                    alert_type="co2_high",
                    severity="warning",
                    message=f"CO2 at {co2:.0f} ppm — exceeds warning threshold ({CO2_WARNING} ppm)",
                    current_value=co2,
                    threshold=CO2_WARNING,
                    unit="ppm",
                )
            )

    humidity = zone.get("humidity")
    if humidity is not None:
        if humidity >= HUMIDITY_CRITICAL:
            alerts.append(
                IAQAlert(
                    zone_id=zone_id,
                    zone_name=zone_name,
                    floor=floor,
                    site_id=site_id,
                    alert_type="humidity_high",
                    severity="critical",
                    message=f"Humidity at {humidity:.1f}% — exceeds critical threshold ({HUMIDITY_CRITICAL}%)",
                    current_value=humidity,
                    threshold=HUMIDITY_CRITICAL,
                    unit="%",
                )
            )
        elif humidity >= HUMIDITY_WARNING:
            alerts.append(
                IAQAlert(
                    zone_id=zone_id,
                    zone_name=zone_name,
                    floor=floor,
                    site_id=site_id,
                    alert_type="humidity_high",
                    severity="warning",
                    message=f"Humidity at {humidity:.1f}% — exceeds warning threshold ({HUMIDITY_WARNING}%)",
                    current_value=humidity,
                    threshold=HUMIDITY_WARNING,
                    unit="%",
                )
            )
        if humidity <= HUMIDITY_LOW_CRITICAL:
            alerts.append(
                IAQAlert(
                    zone_id=zone_id,
                    zone_name=zone_name,
                    floor=floor,
                    site_id=site_id,
                    alert_type="humidity_low",
                    severity="critical",
                    message=f"Humidity at {humidity:.1f}% — below critical threshold ({HUMIDITY_LOW_CRITICAL}%)",
                    current_value=humidity,
                    threshold=HUMIDITY_LOW_CRITICAL,
                    unit="%",
                )
            )

    temp = zone.get("current_temp")
    setpoint = zone.get("setpoint")
    if temp is not None and setpoint is not None:
        deviation = abs(temp - setpoint)
        if deviation >= TEMP_DEV_CRITICAL:
            alerts.append(
                IAQAlert(
                    zone_id=zone_id,
                    zone_name=zone_name,
                    floor=floor,
                    site_id=site_id,
                    alert_type="temp_deviation",
                    severity="critical",
                    message=f"Temperature {temp:.1f}C deviates {deviation:.1f}C from setpoint {setpoint:.1f}C",
                    current_value=deviation,
                    threshold=TEMP_DEV_CRITICAL,
                    unit="C",
                )
            )
        elif deviation >= TEMP_DEV_WARNING:
            alerts.append(
                IAQAlert(
                    zone_id=zone_id,
                    zone_name=zone_name,
                    floor=floor,
                    site_id=site_id,
                    alert_type="temp_deviation",
                    severity="warning",
                    message=f"Temperature {temp:.1f}C deviates {deviation:.1f}C from setpoint {setpoint:.1f}C",
                    current_value=deviation,
                    threshold=TEMP_DEV_WARNING,
                    unit="C",
                )
            )

    voc = zone.get("voc_ppb")
    if voc is not None and voc >= VOC_WARNING:
        sev = "critical" if voc >= VOC_CRITICAL else "warning"
        thresh = VOC_CRITICAL if voc >= VOC_CRITICAL else VOC_WARNING
        alerts.append(
            IAQAlert(
                zone_id=zone_id,
                zone_name=zone_name,
                floor=floor,
                site_id=site_id,
                alert_type="voc_high",
                severity=sev,
                message=f"VOC at {voc:.0f} ppb — exceeds {sev} threshold ({thresh} ppb)",
                current_value=voc,
                threshold=thresh,
                unit="ppb",
            )
        )

    pm25 = zone.get("pm25_ugm3")
    if pm25 is not None and pm25 >= PM25_WARNING:
        sev = "critical" if pm25 >= PM25_CRITICAL else "warning"
        thresh = PM25_CRITICAL if pm25 >= PM25_CRITICAL else PM25_WARNING
        alerts.append(
            IAQAlert(
                zone_id=zone_id,
                zone_name=zone_name,
                floor=floor,
                site_id=site_id,
                alert_type="pm25_high",
                severity=sev,
                message=f"PM2.5 at {pm25:.1f} ug/m3 — exceeds {sev} threshold ({thresh} ug/m3)",
                current_value=pm25,
                threshold=thresh,
                unit="ug/m3",
            )
        )

    return alerts


# ---------------------------------------------------------------------------
# Zone scoring
# ---------------------------------------------------------------------------


def score_zone(zone: dict[str, Any]) -> IAQZoneScore:
    """Calculate IAQ score for a single zone."""
    co2 = zone.get("co2_ppm")
    humidity = zone.get("humidity")
    temp = zone.get("current_temp")
    setpoint = zone.get("setpoint")
    voc = zone.get("voc_ppb")
    pm25 = zone.get("pm25_ugm3")

    co2_score, co2_info = _score_co2(co2)
    hum_score, hum_info = _score_humidity(humidity)
    temp_score, temp_info = _score_temperature(temp, setpoint)
    voc_score, voc_info = _score_voc(voc)
    pm25_score, pm25_info = _score_pm25(pm25)

    components = [
        IAQComponentScore(
            component="co2",
            value=co2,
            score=co2_score,
            weight=WEIGHTS["co2"],
            status=_score_status(co2_score),
            unit="ppm",
            threshold_info=co2_info,
        ),
        IAQComponentScore(
            component="humidity",
            value=humidity,
            score=hum_score,
            weight=WEIGHTS["humidity"],
            status=_score_status(hum_score),
            unit="%",
            threshold_info=hum_info,
        ),
        IAQComponentScore(
            component="temperature",
            value=temp,
            score=temp_score,
            weight=WEIGHTS["temperature"],
            status=_score_status(temp_score),
            unit="C",
            threshold_info=temp_info,
        ),
        IAQComponentScore(
            component="voc",
            value=voc,
            score=voc_score,
            weight=WEIGHTS["voc"],
            status=_score_status(voc_score),
            unit="ppb",
            threshold_info=voc_info,
        ),
        IAQComponentScore(
            component="pm25",
            value=pm25,
            score=pm25_score,
            weight=WEIGHTS["pm25"],
            status=_score_status(pm25_score),
            unit="ug/m3",
            threshold_info=pm25_info,
        ),
    ]

    # Weighted composite score
    total_weight = sum(c.weight for c in components)
    composite = sum(c.score * c.weight for c in components) / total_weight
    composite = round(composite, 1)

    alerts = _generate_alerts(zone)
    alert_messages = [a.message for a in alerts]

    return IAQZoneScore(
        zone_id=zone.get("zone_id", ""),
        zone_name=zone.get("zone_name", ""),
        floor=zone.get("floor", ""),
        site_id=zone.get("site_id", ""),
        iaq_score=composite,
        status=_score_status(composite),
        components=components,
        alerts=alert_messages,
        occupancy=zone.get("typical_occupancy"),
        area_sqm=zone.get("area_sqm"),
    )


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------


class IAQService:
    """Indoor Air Quality Intelligence Service."""

    def __init__(self):
        self._zone_repo = None

    @property
    def zone_repo(self):
        if self._zone_repo is None:
            try:
                from app.database.repositories.hvac_zone_repository import HVACZoneRepository

                self._zone_repo = HVACZoneRepository()
            except Exception:
                self._zone_repo = None
        return self._zone_repo

    def _load_zones_json(self, site_id: str) -> list[dict[str, Any]]:
        """Load zones from JSON fallback."""
        zones_path = DATA_DIR / "hvac_zones.json"
        if not zones_path.exists():
            return []
        with open(zones_path) as f:
            all_zones = json.load(f)
        return [z for z in all_zones if z.get("site_id") == site_id]

    def get_zones(self, site_id: str) -> list[dict[str, Any]]:
        """Get zone data from Supabase or JSON fallback."""
        if self.zone_repo:
            try:
                zones = self.zone_repo.get_by_site_code(site_id)
                if zones:
                    return zones
            except Exception as e:
                logger.warning(f"Supabase zone fetch failed, using JSON: {e}")
        return self._load_zones_json(site_id)

    def get_site_iaq(self, site_id: str) -> IAQSiteOverview:
        """Calculate IAQ scores for all zones in a site."""
        zones = self.get_zones(site_id)
        scored_zones = [score_zone(z) for z in zones]

        all_alerts: list[IAQAlert] = []
        for z in zones:
            all_alerts.extend(_generate_alerts(z))

        counts = {"excellent": 0, "good": 0, "poor": 0, "unhealthy": 0}
        total_score = 0.0
        for sz in scored_zones:
            counts[sz.status] = counts.get(sz.status, 0) + 1
            total_score += sz.iaq_score

        avg = round(total_score / len(scored_zones), 1) if scored_zones else 0.0

        return IAQSiteOverview(
            site_id=site_id,
            total_zones=len(scored_zones),
            avg_iaq_score=avg,
            zones_excellent=counts["excellent"],
            zones_good=counts["good"],
            zones_poor=counts["poor"],
            zones_unhealthy=counts["unhealthy"],
            zones=scored_zones,
            alerts=all_alerts,
        )

    def get_zone_iaq(self, site_id: str, zone_id: str) -> IAQZoneScore | None:
        """Get IAQ score for a specific zone."""
        zones = self.get_zones(site_id)
        for z in zones:
            if z.get("zone_id") == zone_id:
                return score_zone(z)
        return None

    def get_alerts(self, site_id: str) -> list[IAQAlert]:
        """Get all active IAQ alerts for a site."""
        zones = self.get_zones(site_id)
        alerts: list[IAQAlert] = []
        for z in zones:
            alerts.extend(_generate_alerts(z))
        return alerts

    def get_compliance_report(self, site_id: str, report_type: str = "well") -> IAQComplianceReport:
        """Generate WELL or ESG compliance report."""
        overview = self.get_site_iaq(site_id)
        zones = overview.zones

        if report_type == "well":
            return self._well_report(site_id, overview, zones)
        return self._esg_report(site_id, overview, zones)

    def _well_report(self, site_id: str, overview: IAQSiteOverview, zones: list[IAQZoneScore]) -> IAQComplianceReport:
        """WELL Building Standard compliance report.

        WELL v2 Air concept thresholds:
        - CO2 < 800 ppm (precondition)
        - Humidity 30-60% (optimization)
        - Temperature within 1C of setpoint
        """
        compliant = 0
        non_compliant = 0
        co2_values = []
        humidity_values = []
        temp_devs = []

        for z in zones:
            zone_ok = True
            for c in z.components:
                if c.component == "co2":
                    if c.value is not None:
                        co2_values.append(c.value)
                        if c.value > CO2_GOOD:
                            zone_ok = False
                elif c.component == "humidity":
                    if c.value is not None:
                        humidity_values.append(c.value)
                        if c.value < 30 or c.value > 60:
                            zone_ok = False
                elif c.component == "temperature" and c.value is not None:
                    temp_devs.append(c.score)
                    if c.score < 80:
                        zone_ok = False
            if zone_ok:
                compliant += 1
            else:
                non_compliant += 1

        recommendations: list[str] = []
        if co2_values and max(co2_values) > CO2_GOOD:
            recommendations.append(f"Increase ventilation in zones with CO2 > {CO2_GOOD} ppm")
        if humidity_values:
            if any(h > 60 for h in humidity_values):
                recommendations.append("Reduce humidity in affected zones (target 30-60%)")
            if any(h < 30 for h in humidity_values):
                recommendations.append("Increase humidity in dry zones (target 30-60%)")
        if any(z.iaq_score < 70 for z in zones):
            recommendations.append("Investigate poor-scoring zones for ventilation issues")

        return IAQComplianceReport(
            site_id=site_id,
            report_type="well",
            generated_at=datetime.now(UTC).isoformat(),
            overall_score=overview.avg_iaq_score,
            zones_compliant=compliant,
            zones_non_compliant=non_compliant,
            metrics={
                "avg_co2_ppm": round(sum(co2_values) / len(co2_values), 1) if co2_values else None,
                "max_co2_ppm": max(co2_values) if co2_values else None,
                "avg_humidity": round(sum(humidity_values) / len(humidity_values), 1) if humidity_values else None,
                "zones_co2_compliant": sum(1 for v in co2_values if v <= CO2_GOOD),
                "zones_humidity_compliant": sum(1 for v in humidity_values if 30 <= v <= 60),
                "well_air_precondition_met": all(v <= CO2_GOOD for v in co2_values) if co2_values else False,
            },
            recommendations=recommendations,
        )

    def _esg_report(self, site_id: str, overview: IAQSiteOverview, zones: list[IAQZoneScore]) -> IAQComplianceReport:
        """ESG sustainability compliance report for IAQ."""
        compliant = sum(1 for z in zones if z.iaq_score >= 70)
        non_compliant = len(zones) - compliant

        recommendations: list[str] = []
        if overview.zones_poor + overview.zones_unhealthy > 0:
            recommendations.append(
                f"{overview.zones_poor + overview.zones_unhealthy} zones below 'good' threshold — review ventilation"
            )
        if overview.avg_iaq_score < 80:
            recommendations.append("Overall IAQ below ESG target of 80 — consider HVAC optimization")

        alert_counts: dict[str, int] = {}
        for a in overview.alerts:
            alert_counts[a.alert_type] = alert_counts.get(a.alert_type, 0) + 1

        return IAQComplianceReport(
            site_id=site_id,
            report_type="esg",
            generated_at=datetime.now(UTC).isoformat(),
            overall_score=overview.avg_iaq_score,
            zones_compliant=compliant,
            zones_non_compliant=non_compliant,
            metrics={
                "total_zones": overview.total_zones,
                "zones_excellent": overview.zones_excellent,
                "zones_good": overview.zones_good,
                "zones_poor": overview.zones_poor,
                "zones_unhealthy": overview.zones_unhealthy,
                "active_alerts": len(overview.alerts),
                "alert_breakdown": alert_counts,
            },
            recommendations=recommendations,
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_iaq_service: IAQService | None = None


def get_iaq_service() -> IAQService:
    global _iaq_service
    if _iaq_service is None:
        _iaq_service = IAQService()
    return _iaq_service
