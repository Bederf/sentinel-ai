"""
Baseline Comparison Service (Phase 54-03)

Compare current equipment readings to baseline values.
Detect deviations, classify severity, generate alerts for conditional maintenance.

This is the equipment-level baseline comparison (vs sensor_analysis baseline_comparator for phone sensors).

Severity thresholds:
- Within tolerance: OK (normal)
- 1-2x tolerance: WARNING (monitor)
- 2x+ tolerance: CRITICAL (action required)
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

from app.database.repositories.baseline_repository import BaselineRepository
from app.models.baseline import EquipmentBaseline, DeviationStatus

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================


class BaselineDeviation(BaseModel):
    """Individual baseline deviation result."""

    element_name: str = Field(..., description="Name of deviating element")
    baseline_value: float = Field(..., description="Baseline value")
    current_value: float = Field(..., description="Current reading")
    tolerance: float = Field(..., description="Allowed tolerance (absolute or %)")
    tolerance_type: str = Field(default="absolute", description="'absolute' or 'percentage'")
    deviation_percent: float = Field(..., description="Deviation as % of baseline")
    severity: str = Field(..., description="Severity: 'normal', 'warning', 'critical'")
    recommended_action: Optional[str] = Field(None, description="Suggested action")


class BaselineComparison(BaseModel):
    """Complete baseline comparison result."""

    baseline_id: str
    equipment_id: str
    comparison_date: datetime
    baseline_date: datetime
    deviations: List[BaselineDeviation] = Field(default_factory=list)
    overall_status: DeviationStatus
    max_deviation_percent: float
    summary: str


class BaselineReportRequest(BaseModel):
    """Request for baseline report generation."""

    equipment_id: str
    baseline_id: Optional[str] = Field(None, description="Specific baseline, uses latest if None")
    include_recommendations: bool = Field(default=True)


# ============================================================================
# Service
# ============================================================================


class BaselineComparisonService:
    """
    Service for comparing current equipment readings to baseline.

    Features:
    - Fetches latest baseline from database
    - Compares each element with tolerance checking
    - Calculates deviation percentage and severity
    - Generates recommended actions
    - Produces PDF baseline reports
    """

    def __init__(self):
        """Initialize comparison service with repository."""
        self.repository: Optional[BaselineRepository] = None

    def ensure_repository(self):
        """Ensure repository is initialized."""
        if self.repository is None:
            self.repository = BaselineRepository()

    async def compare_to_baseline(
        self, equipment_id: str, current_data: Dict[str, float], baseline_id: Optional[str] = None
    ) -> BaselineComparison:
        """
        Compare current readings to baseline.

        Args:
            equipment_id: Equipment identifier
            current_data: Current readings {element_name: value}
            baseline_id: Specific baseline ID (uses latest active if None)

        Returns:
            BaselineComparison with deviations list and overall status

        Raises:
            ValueError: If equipment not found or no baseline exists
        """
        self.ensure_repository()

        # 1. Fetch baseline
        if baseline_id:
            baseline = await self.repository.get_baseline_by_id(baseline_id)
        else:
            baseline = await self.repository.get_active_equipment_baseline(equipment_id)

        if not baseline:
            raise ValueError(f"No baseline found for equipment {equipment_id}")

        # 2. Compare each element
        deviations = []
        baseline_values = baseline.baseline_values if isinstance(baseline.baseline_values, dict) else {}

        for element_name, current_value in current_data.items():
            baseline_el = baseline_values.get(element_name)

            if not baseline_el:
                logger.warning(f"Element {element_name} not found in baseline for {equipment_id}")
                continue

            # Handle both simple values and complex structures
            if isinstance(baseline_el, dict):
                baseline_value = baseline_el.get("value")
                tolerance = baseline_el.get("tolerance", 10)
                tolerance_type = baseline_el.get("tolerance_type", "absolute")
                unit = baseline_el.get("unit", "")
            else:
                baseline_value = baseline_el
                tolerance = 10  # Default tolerance
                tolerance_type = "absolute"
                unit = ""

            # Calculate deviation
            deviation = self._calculate_deviation(
                element_name=element_name,
                baseline_value=baseline_value,
                current_value=current_value,
                tolerance=tolerance,
                tolerance_type=tolerance_type,
            )

            if deviation:
                deviations.append(deviation)

        # 3. Determine overall status
        overall_status, max_deviation = self._determine_overall_status(deviations)

        # 4. Build summary
        summary = self._build_summary(deviations, overall_status)

        return BaselineComparison(
            baseline_id=baseline.id,
            equipment_id=equipment_id,
            comparison_date=datetime.now(),
            baseline_date=baseline.baseline_date,
            deviations=deviations,
            overall_status=overall_status,
            max_deviation_percent=max_deviation,
            summary=summary,
        )

    def _calculate_deviation(
        self, element_name: str, baseline_value: float, current_value: float, tolerance: float, tolerance_type: str
    ) -> Optional[BaselineDeviation]:
        """
        Calculate deviation for a single element.

        Formula:
        - Absolute tolerance: deviation = |current - baseline|
        - Percentage tolerance: deviation = |current - baseline| / baseline * 100
        - Check if deviation > tolerance
        - Severity: warning if > tolerance, critical if > 2*tolerance

        Returns:
            BaselineDeviation or None if within tolerance
        """
        if baseline_value == 0:
            # Avoid division by zero
            deviation_abs = abs(current_value)
            deviation_percent = 0.0
        else:
            deviation_abs = abs(current_value - baseline_value)
            deviation_percent = (deviation_abs / abs(baseline_value)) * 100

        # Calculate tolerance threshold
        if tolerance_type == "percentage":
            # Tolerance is a percentage of baseline
            tolerance_threshold = (tolerance / 100) * abs(baseline_value)
        else:
            # Absolute tolerance
            tolerance_threshold = tolerance

        # Calculate deviation as percentage for severity check
        if baseline_value != 0:
            deviation_pct_for_severity = deviation_percent
        else:
            deviation_pct_for_severity = 0.0

        # Determine severity
        severity = self._determine_severity(
            deviation_percent=deviation_pct_for_severity, tolerance=tolerance if tolerance_type == "percentage" else 0
        )

        # Only return deviation if not normal
        if severity == "normal":
            return None

        # Generate recommended action
        action = self._generate_recommended_action(
            element_name=element_name, severity=severity, deviation_percent=deviation_pct_for_severity
        )

        return BaselineDeviation(
            element_name=element_name,
            baseline_value=baseline_value,
            current_value=current_value,
            tolerance=tolerance,
            tolerance_type=tolerance_type,
            deviation_percent=round(deviation_pct_for_severity, 2),
            severity=severity,
            recommended_action=action,
        )

    def _determine_severity(self, deviation_percent: float, tolerance: float) -> str:
        """
        Determine severity classification.

        Thresholds:
        - normal: deviation <= tolerance (or < 15% if tolerance=0)
        - warning: deviation > tolerance but < 2*tolerance (or 15-30%)
        - critical: deviation >= 2*tolerance (or >= 30%)

        Returns:
            "normal", "warning", or "critical"
        """
        # Use tolerance if provided, otherwise default to 15% threshold
        warning_threshold = tolerance if tolerance > 0 else 15.0
        critical_threshold = 2 * tolerance if tolerance > 0 else 30.0

        if deviation_percent >= critical_threshold:
            return "critical"
        elif deviation_percent > warning_threshold:
            return "warning"
        else:
            return "normal"

    def _generate_recommended_action(self, element_name: str, severity: str, deviation_percent: float) -> str:
        """Generate recommended action based on severity and element."""
        if severity == "critical":
            return f"Critical deviation detected for {element_name} ({deviation_percent:.1f}%). Immediate inspection required."
        elif severity == "warning":
            return f"Warning: {element_name} deviation {deviation_percent:.1f}% from baseline. Monitor trend and schedule inspection if continues."
        else:
            return f"Monitor {element_name} - within acceptable range."

    def _determine_overall_status(self, deviations: List[BaselineDeviation]) -> tuple[DeviationStatus, float]:
        """
        Determine overall status from deviations list.

        Rules:
        - critical if any critical deviations
        - warning if any warning deviations (and no critical)
        - normal if all normal

        Returns:
            (overall_status, max_deviation_percent)
        """
        if not deviations:
            return DeviationStatus.NORMAL, 0.0

        max_deviation = 0.0
        has_critical = False
        has_warning = False

        for dev in deviations:
            if dev.deviation_percent > max_deviation:
                max_deviation = dev.deviation_percent

            if dev.severity == "critical":
                has_critical = True
            elif dev.severity == "warning":
                has_warning = True

        if has_critical:
            return DeviationStatus.CRITICAL, max_deviation
        elif has_warning:
            return DeviationStatus.WARNING, max_deviation
        else:
            return DeviationStatus.NORMAL, max_deviation

    def _build_summary(self, deviations: List[BaselineDeviation], overall_status: DeviationStatus) -> str:
        """Build human-readable summary."""
        critical_count = sum(1 for d in deviations if d.severity == "critical")
        warning_count = sum(1 for d in deviations if d.severity == "warning")

        if critical_count > 0:
            return f"{critical_count} critical deviation(s) detected. Immediate action required."
        elif warning_count > 0:
            return f"{warning_count} warning(s) detected. Monitor closely."
        else:
            return "All readings within normal range."

    async def generate_baseline_report(
        self, equipment_id: str, baseline: EquipmentBaseline, comparison: Optional[BaselineComparison] = None
    ) -> bytes:
        """
        Generate PDF baseline report.

        Report sections:
        1. Header: Equipment name, ID, baseline date
        2. Baseline summary table: Element | Baseline | Unit | Tolerance
        3. Comparison table: Element | Baseline | Current | Deviation | Status
        4. Deviation details: Highlighted warnings/critical
        5. Notes section: Technician observations
        6. Footer: Generated by SENTINEL, timestamp

        Args:
            equipment_id: Equipment identifier
            baseline: Baseline to report on
            comparison: Optional comparison result

        Returns:
            PDF bytes for download/email
        """
        # Import PDF library here to avoid dependency if not used
        try:
            from reportlab.lib.pagesizes import landscape, letter
            from reportlab.lib import colors
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.enums import TA_CENTER, TA_LEFT
            from io import BytesIO

            buffer = BytesIO()

            # Create PDF with landscape orientation
            doc = SimpleDocTemplate(
                buffer,
                pagesize=landscape(letter),
                rightMargin=0.5 * inch,
                leftMargin=0.5 * inch,
                topMargin=0.5 * inch,
                bottomMargin=0.5 * inch,
            )

            # Build PDF content
            story = []
            styles = getSampleStyleSheet()

            # Custom styles
            header_style = ParagraphStyle(
                "CustomHeader", parent=styles["Heading1"], fontSize=18, alignment=TA_CENTER, spaceAfter=0.2 * inch
            )

            title_style = ParagraphStyle("CustomTitle", parent=styles["Heading2"], fontSize=14, spaceAfter=0.15 * inch)

            # 1. Header
            story.append(Paragraph("Baseline Assessment Report", header_style))
            story.append(Paragraph(f"Equipment: {equipment_id}", styles["Normal"]))
            story.append(
                Paragraph(f"Baseline Date: {baseline.baseline_date.strftime('%Y-%m-%d %H:%M')}", styles["Normal"])
            )
            story.append(Paragraph(f"Captured By: {baseline.captured_by}", styles["Normal"]))
            story.append(Spacer(1, 0.2 * inch))

            # 2. Baseline summary table
            story.append(Paragraph("Baseline Values", title_style))

            baseline_data = [["Element", "Baseline", "Unit", "Tolerance"]]
            baseline_values = baseline.baseline_values if isinstance(baseline.baseline_values, dict) else {}

            for element_name, element_data in baseline_values.items():
                if isinstance(element_data, dict):
                    value = element_data.get("value", "N/A")
                    unit = element_data.get("unit", "")
                    tolerance = element_data.get("tolerance", "N/A")
                else:
                    value = element_data
                    unit = ""
                    tolerance = "N/A"

                baseline_data.append([element_name, str(value), str(unit), str(tolerance)])

            baseline_table = Table(baseline_data)
            baseline_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 12),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                        ("GRID", (0, 0), (-1, -1), 1, colors.black),
                    ]
                )
            )
            story.append(baseline_table)
            story.append(Spacer(1, 0.2 * inch))

            # 3. Comparison table (if comparison provided)
            if comparison and comparison.deviations:
                story.append(Paragraph("Current Comparison", title_style))

                comparison_data = [["Element", "Baseline", "Current", "Deviation", "Status"]]

                for dev in comparison.deviations:
                    comparison_data.append(
                        [
                            dev.element_name,
                            f"{dev.baseline_value:.2f}",
                            f"{dev.current_value:.2f}",
                            f"{dev.deviation_percent:.1f}%",
                            dev.severity.upper(),
                        ]
                    )

                comparison_table = Table(comparison_data)

                # Build table styles with color-coded status cells
                comp_styles = [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ]

                # Add color coding for status column (column index 4)
                for i, dev in enumerate(comparison.deviations, start=1):  # start=1 to skip header row
                    if dev.severity == "critical":
                        comp_styles.append(("BACKGROUND", (4, i), (4, i), colors.red))
                        comp_styles.append(("TEXTCOLOR", (4, i), (4, i), colors.whitesmoke))
                    elif dev.severity == "warning":
                        comp_styles.append(("BACKGROUND", (4, i), (4, i), colors.yellow))
                        comp_styles.append(("TEXTCOLOR", (4, i), (4, i), colors.black))

                comparison_table.setStyle(TableStyle(comp_styles))
                story.append(comparison_table)
                story.append(Spacer(1, 0.2 * inch))

            # 4. Notes section
            if baseline.notes:
                story.append(Paragraph("Notes", title_style))
                story.append(Paragraph(baseline.notes, styles["Normal"]))
                story.append(Spacer(1, 0.2 * inch))

            # 5. Footer
            story.append(Spacer(1, 0.5 * inch))
            story.append(
                Paragraph(
                    f"Generated by SENTINEL BMS Intelligence - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, alignment=TA_CENTER),
                )
            )

            # Build PDF
            doc.build(story)

            pdf_bytes = buffer.getvalue()
            buffer.close()

            logger.info(f"Generated PDF report for {equipment_id}, baseline {baseline.id}")
            return pdf_bytes

        except ImportError:
            # Fallback: simple text-based report if reportlab not available
            logger.warning("reportlab not available, generating text report")
            return self._generate_text_report(equipment_id, baseline, comparison)

    def _generate_text_report(
        self, equipment_id: str, baseline: EquipmentBaseline, comparison: Optional[BaselineComparison]
    ) -> bytes:
        """Generate simple text report as fallback."""
        lines = [
            "=" * 80,
            "BASELINE ASSESSMENT REPORT",
            "=" * 80,
            f"Equipment: {equipment_id}",
            f"Baseline Date: {baseline.baseline_date.strftime('%Y-%m-%d %H:%M')}",
            f"Captured By: {baseline.captured_by}",
            "",
            "-" * 80,
            "BASELINE VALUES",
            "-" * 80,
        ]

        baseline_values = baseline.baseline_values if isinstance(baseline.baseline_values, dict) else {}
        for element_name, element_data in baseline_values.items():
            if isinstance(element_data, dict):
                value = element_data.get("value", "N/A")
                unit = element_data.get("unit", "")
                tolerance = element_data.get("tolerance", "N/A")
            else:
                value = element_data
                unit = ""
                tolerance = "N/A"

            lines.append(f"{element_name}: {value} {unit} (tolerance: ±{tolerance})")

        if comparison and comparison.deviations:
            lines.extend(
                [
                    "",
                    "-" * 80,
                    "CURRENT COMPARISON",
                    "-" * 80,
                ]
            )

            for dev in comparison.deviations:
                lines.append(
                    f"{dev.element_name}: {dev.baseline_value:.2f} → {dev.current_value:.2f} "
                    f"({dev.deviation_percent:+.1f}%) - {dev.severity.upper()}"
                )
                if dev.recommended_action:
                    lines.append(f"  → {dev.recommended_action}")

        if baseline.notes:
            lines.extend(["", "-" * 80, "NOTES", "-" * 80, baseline.notes])

        lines.extend(
            [
                "",
                "=" * 80,
                f"Generated by SENTINEL BMS Intelligence - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "=" * 80,
            ]
        )

        return "\n".join(lines).encode("utf-8")


# ============================================================================
# Singleton Instance
# ============================================================================

_comparison_service: Optional[BaselineComparisonService] = None


def get_baseline_comparison_service() -> BaselineComparisonService:
    """Get singleton comparison service instance."""
    global _comparison_service
    if _comparison_service is None:
        _comparison_service = BaselineComparisonService()
    return _comparison_service
