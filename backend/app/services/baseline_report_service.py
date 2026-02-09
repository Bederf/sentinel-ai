"""
Baseline Report Generation Service

Generates comprehensive baseline assessment reports in multiple formats (JSON, PDF, HTML).

Phase 44: Asset Baseline Assessment
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import logging

from app.services.baseline_service import get_baseline_service
from app.services.building_loader import get_building_loader
from app.models.baseline import EquipmentBaseline, BaselineComparison

logger = logging.getLogger(__name__)


class BaselineReportService:
    """Service for generating baseline assessment reports."""

    def __init__(self):
        self.baseline_service = get_baseline_service()
        self.building_loader = get_building_loader()

    async def generate_json_report(
        self,
        equipment_id: str,
        include_element_baselines: bool = True,
        include_comparison_history: bool = True
    ) -> Dict[str, Any]:
        """
        Generate comprehensive baseline report in JSON format.

        Args:
            equipment_id: Equipment identifier
            include_element_baselines: Include element-level baselines
            include_comparison_history: Include recent comparison history

        Returns:
            Complete baseline report as dictionary
        """
        # Get equipment details
        equipment = await self.building_loader.get_equipment(equipment_id)
        if not equipment:
            raise ValueError(f"Equipment {equipment_id} not found")

        # Get active baseline
        active_baseline = await self.baseline_service.repository.get_active_equipment_baseline(
            equipment_id
        )

        # Get baseline history
        baseline_history = await self.baseline_service.get_baseline_history(equipment_id, limit=10)

        # Get element baselines if requested
        element_baselines = []
        if include_element_baselines:
            elements = await self.baseline_service.repository.get_equipment_elements(equipment_id)
            for element in elements:
                element_baseline = await self.baseline_service.repository.get_active_element_baseline(
                    element.id
                )
                if element_baseline:
                    element_baselines.append({
                        "element": element,
                        "baseline": element_baseline
                    })

        # Get comparison history if requested
        comparison_history = []
        if include_comparison_history:
            comparison_history = await self.baseline_service.repository.get_recent_comparisons(
                equipment_id, limit=10
            )

        # Calculate deviation statistics
        deviation_stats = self._calculate_deviation_stats(comparison_history)

        # Get baseline summary
        summary = await self.baseline_service.repository.get_baseline_summary(equipment_id)

        # Build report structure
        report = {
            "report_metadata": {
                "generated_at": datetime.now().isoformat(),
                "report_type": "equipment_baseline_assessment",
                "version": "1.0"
            },
            "equipment_info": {
                "equipment_id": equipment.equipment_id,
                "name": equipment.equipment_name,
                "type": equipment.equipment_type,
                "site_id": equipment.site_id,
                "location": equipment.location,
                "criticality": equipment.criticality
            },
            "baseline_status": {
                "has_active_baseline": active_baseline is not None,
                "active_baseline": active_baseline,
                "baseline_history_count": len(baseline_history),
                "last_baseline_date": summary.get("last_baseline_date")
            },
            "element_baselines": element_baselines,
            "comparison_history": comparison_history,
            "deviation_statistics": deviation_stats,
            "summary": summary
        }

        # Add recommendations if deviations found
        if deviation_stats["critical_count"] > 0 or deviation_stats["warning_count"] > 0:
            report["recommendations"] = self._generate_recommendations(
                deviation_stats, equipment
            )

        return report

    def _calculate_deviation_stats(
        self,
        comparison_history: List[BaselineComparison]
    ) -> Dict[str, Any]:
        """Calculate deviation statistics from comparison history."""
        if not comparison_history:
            return {
                "total_comparisons": 0,
                "critical_count": 0,
                "warning_count": 0,
                "normal_count": 0,
                "average_deviation": 0.0,
                "max_deviation": 0.0,
                "trend": "stable"
            }

        critical_count = sum(1 for c in comparison_history if c.overall_status == "critical")
        warning_count = sum(1 for c in comparison_history if c.overall_status == "warning")
        normal_count = sum(1 for c in comparison_history if c.overall_status == "normal")

        max_deviations = [c.max_deviation_percent for c in comparison_history]
        avg_deviation = sum(max_deviations) / len(max_deviations)
        max_deviation = max(max_deviations) if max_deviations else 0

        # Determine trend
        recent = comparison_history[:3]
        if len(recent) >= 2:
            first_deviation = recent[0].max_deviation_percent
            last_deviation = recent[-1].max_deviation_percent
            if last_deviation > first_deviation * 1.1:
                trend = "deteriorating"
            elif last_deviation < first_deviation * 0.9:
                trend = "improving"
            else:
                trend = "stable"
        else:
            trend = "stable"

        return {
            "total_comparisons": len(comparison_history),
            "critical_count": critical_count,
            "warning_count": warning_count,
            "normal_count": normal_count,
            "average_deviation": round(avg_deviation, 2),
            "max_deviation": round(max_deviation, 2),
            "trend": trend
        }

    def _generate_recommendations(
        self,
        deviation_stats: Dict[str, Any],
        equipment: Any
    ) -> List[Dict[str, Any]]:
        """Generate maintenance recommendations based on deviations."""
        recommendations = []

        if deviation_stats["critical_count"] > 0:
            recommendations.append({
                "priority": "high",
                "type": "immediate_action",
                "title": "Critical Deviations Detected",
                "description": f"{deviation_stats['critical_count']} recent comparisons show critical deviations.",
                "recommended_action": "Schedule immediate inspection and maintenance",
                "estimated_cost_range": {"min": 5000, "max": 25000}
            })

        if deviation_stats["warning_count"] > 2:
            recommendations.append({
                "priority": "medium",
                "type": "preventive_maintenance",
                "title": "Multiple Warning Deviations",
                "description": "Multiple warning-level deviations indicate equipment degradation.",
                "recommended_action": "Schedule preventive maintenance within 30 days",
                "estimated_cost_range": {"min": 2000, "max": 8000}
            })

        if deviation_stats["trend"] == "deteriorating":
            recommendations.append({
                "priority": "high",
                "type": "investigation",
                "title": "Deteriorating Trend",
                "description": "Equipment performance is trending away from baseline.",
                "recommended_action": "Investigate root cause and schedule corrective maintenance",
                "estimated_cost_range": {"min": 3000, "max": 15000}
            })

        # RUL estimation based on deviation trend
        if deviation_stats["max_deviation"] > 30:
            rul_days = 30
        elif deviation_stats["max_deviation"] > 20:
            rul_days = 90
        elif deviation_stats["max_deviation"] > 15:
            rul_days = 180
        else:
            rul_days = 365

        recommendations.append({
            "priority": "info",
            "type": "rul_estimate",
            "title": "Remaining Useful Life Estimate",
            "description": "Based on deviation trend analysis",
            "estimated_rul_days": rul_days,
            "confidence": "medium" if deviation_stats["total_comparisons"] > 5 else "low"
        })

        return recommendations

    def _format_baseline_value(self, value: Any, metric_id: str) -> str:
        """Format baseline value with units based on metric type."""
        unit_mappings = {
            "temp": "°C",
            "pressure": "bar",
            "voltage": "V",
            "current": "A",
            "frequency": "Hz",
            "vibration": "mm/s",
            "sound": "dBA",
            "percent": "%",
            "dp": "Pa"
        }

        unit = ""
        for key, unit_str in unit_mappings.items():
            if key in metric_id.lower():
                unit = f" {unit_str}"
                break

        return f"{value}{unit}"

    async def generate_pdf_report(self, equipment_id: str) -> bytes:
        """
        Generate PDF baseline assessment report.

        Args:
            equipment_id: Equipment identifier

        Returns:
            PDF report as bytes
        """
        # Generate JSON report first
        json_report = await self.generate_json_report(equipment_id)

        # Create PDF using reportlab or similar library
        # This is a simplified example - real implementation would use proper PDF generation
        from io import BytesIO

        buffer = BytesIO()
        buffer.write("Baseline Assessment Report\n".encode())
        buffer.write(f"Equipment: {json_report['equipment_info']['name']}\n".encode())
        buffer.write(f"Generated: {json_report['report_metadata']['generated_at']}\n\n".encode())

        if json_report['baseline_status']['has_active_baseline']:
            buffer.write("BASELINE STATUS: ACTIVE\n".encode())
            baseline = json_report['baseline_status']['active_baseline']
            buffer.write(f"Last Baseline: {baseline['baseline_date']}\n".encode())
            buffer.write(f"Captured By: {baseline['captured_by']}\n\n".encode())
        else:
            buffer.write("BASELINE STATUS: NO ACTIVE BASELINE\n\n".encode())

        buffer.write("DEVIATION STATISTICS:\n".encode())
        stats = json_report['deviation_statistics']
        buffer.write(f"Total Comparisons: {stats['total_comparisons']}\n".encode())
        buffer.write(f"Normal: {stats['normal_count']}\n".encode())
        buffer.write(f"Warning: {stats['warning_count']}\n".encode())
        buffer.write(f"Critical: {stats['critical_count']}\n".encode())
        buffer.write(f"Max Deviation: {stats['max_deviation']}%\n\n".encode())

        if 'recommendations' in json_report:
            buffer.write("RECOMMENDATIONS:\n".encode())
            for rec in json_report['recommendations']:
                buffer.write(f"- {rec['title']} ({rec['priority']})\n".encode())

        return buffer.getvalue()

    async def generate_html_report(self, equipment_id: str) -> str:
        """
        Generate HTML baseline assessment report.

        Args:
            equipment_id: Equipment identifier

        Returns:
            HTML report as string
        """
        json_report = await self.generate_json_report(equipment_id)

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Baseline Assessment Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background: #f0f0f0; padding: 20px; border-radius: 5px; }}
                .status-normal {{ color: green; }}
                .status-warning {{ color: orange; }}
                .status-critical {{ color: red; }}
                .section {{ margin: 20px 0; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Equipment Baseline Assessment Report</h1>
                <h2>{json_report['equipment_info']['name']}</h2>
                <p><strong>Generated:</strong> {json_report['report_metadata']['generated_at']}</p>
            </div>

            <div class="section">
                <h2>Equipment Information</h2>
                <ul>
                    <li><strong>ID:</strong> {json_report['equipment_info']['equipment_id']}</li>
                    <li><strong>Type:</strong> {json_report['equipment_info']['type']}</li>
                    <li><strong>Location:</strong> {json_report['equipment_info']['location']}</li>
                    <li><strong>Criticality:</strong> {json_report['equipment_info']['criticality']}</li>
                </ul>
            </div>

            <div class="section">
                <h2>Baseline Status</h2>
                <p><strong>Active Baseline:</strong> {"Yes" if json_report['baseline_status']['has_active_baseline'] else "No"}</p>
        """

        if json_report['baseline_status']['has_active_baseline']:
            baseline = json_report['baseline_status']['active_baseline']
            html += f"""
                <p><strong>Last Updated:</strong> {baseline['baseline_date']}</p>
                <p><strong>Captured By:</strong> {baseline['captured_by']}</p>
                <p><strong>Type:</strong> {baseline['baseline_type']}</p>
            """

        html += f"""
            </div>

            <div class="section">
                <h2>Deviation Statistics</h2>
                <table>
                    <tr><th>Metric</th><th>Value</th></tr>
                    <tr><td>Total Comparisons</td><td>{json_report['deviation_statistics']['total_comparisons']}</td></tr>
                    <tr><td class="status-normal">Normal</td><td>{json_report['deviation_statistics']['normal_count']}</td></tr>
                    <tr><td class="status-warning">Warning</td><td>{json_report['deviation_statistics']['warning_count']}</td></tr>
                    <tr><td class="status-critical">Critical</td><td>{json_report['deviation_statistics']['critical_count']}</td></tr>
                    <tr><td>Max Deviation</td><td>{json_report['deviation_statistics']['max_deviation']}%</td></tr>
                    <tr><td>Trend</td><td>{json_report['deviation_statistics']['trend']}</td></tr>
                </table>
            </div>
        """

        if 'recommendations' in json_report:
            html += """
                <div class="section">
                    <h2>Recommendations</h2>
                    <table>
                        <tr><th>Priority</th><th>Recommendation</th><th>Action</th></tr>
            """
            for rec in json_report['recommendations']:
                html += f"""
                    <tr>
                        <td>{rec['priority']}</td>
                        <td>{rec['title']}</td>
                        <td>{rec['recommended_action']}</td>
                    </tr>
                """
            html += "</table></div>"

        html += """
        </body>
        </html>
        """

        return html


# Singleton instance
_report_service = None


def get_baseline_report_service() -> BaselineReportService:
    """Get singleton baseline report service instance."""
    global _report_service
    if _report_service is None:
        _report_service = BaselineReportService()
    return _report_service
