"""
Budget Export Service
=====================
Phase 49-10: CSV/PDF export for budget reports.
"""

from __future__ import annotations

import csv
import io
from typing import Dict, Any, List


def export_budget_report_csv(report: Dict[str, Any]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Contract ID", report.get("contract_id")])
    writer.writerow(["Year", report.get("year")])
    writer.writerow([])

    totals = report.get("totals", {})
    writer.writerow(["Total Budget (ZAR)", totals.get("total_budget_zar")])
    writer.writerow(["Total Actual (ZAR)", totals.get("total_actual_zar")])
    writer.writerow(["Variance (ZAR)", totals.get("variance_zar")])
    writer.writerow(["Spend %", totals.get("spend_percentage")])
    writer.writerow([])

    writer.writerow(["Month", "Budget (ZAR)", "Actual (ZAR)", "Variance (ZAR)", "Spend %"])
    for row in report.get("monthly", []):
        writer.writerow(
            [
                row.get("month"),
                row.get("total_budget_zar"),
                row.get("total_actual_zar"),
                row.get("variance_zar"),
                row.get("spend_percentage"),
            ]
        )

    writer.writerow([])
    writer.writerow(["Equipment Type Breakdown"])
    writer.writerow(["Equipment Type", "Budget (ZAR)", "Actual (ZAR)", "Variance (ZAR)", "Spend %"])
    for row in report.get("equipment_type_breakdown", []):
        writer.writerow(
            [
                row.get("equipment_type"),
                row.get("total_budget_zar"),
                row.get("total_actual_zar"),
                row.get("variance_zar"),
                row.get("spend_percentage"),
            ]
        )

    summary = report.get("alert_summary", {})
    writer.writerow([])
    writer.writerow(["Alert Summary"])
    writer.writerow(["Warning Alerts", summary.get("warning", 0)])
    writer.writerow(["Critical Alerts", summary.get("critical", 0)])
    writer.writerow(["Open Alerts", summary.get("open", 0)])
    writer.writerow(["Acknowledged Alerts", summary.get("acknowledged", 0)])
    writer.writerow(["Resolved Alerts", summary.get("resolved", 0)])

    return output.getvalue().encode("utf-8")


def export_budget_report_pdf(report: Dict[str, Any]) -> bytes:
    lines: List[str] = []
    lines.append("SENTINEL Budget Report")
    lines.append("")
    lines.append(f"Contract ID: {report.get('contract_id')}")
    lines.append(f"Year: {report.get('year')}")
    lines.append("")

    totals = report.get("totals", {})
    lines.append("Totals")
    lines.append(f"Total Budget (ZAR): {totals.get('total_budget_zar')}")
    lines.append(f"Total Actual (ZAR): {totals.get('total_actual_zar')}")
    lines.append(f"Variance (ZAR): {totals.get('variance_zar')}")
    lines.append(f"Spend %: {totals.get('spend_percentage')}")
    lines.append("")

    lines.append("Monthly Breakdown")
    for row in report.get("monthly", []):
        lines.append(
            f"- Month {row.get('month')}: Budget {row.get('total_budget_zar')}, "
            f"Actual {row.get('total_actual_zar')}, Spend {row.get('spend_percentage')}%"
        )

    equipment_breakdown = report.get("equipment_type_breakdown", [])
    if equipment_breakdown:
        lines.append("")
        lines.append("Equipment Type Breakdown")
        for row in equipment_breakdown:
            lines.append(
                f"- {row.get('equipment_type')}: Budget {row.get('total_budget_zar')}, "
                f"Actual {row.get('total_actual_zar')}, Spend {row.get('spend_percentage')}%"
            )

    summary = report.get("alert_summary", {})
    if summary:
        lines.append("")
        lines.append("Alert Summary")
        lines.append(f"- Warning: {summary.get('warning', 0)}")
        lines.append(f"- Critical: {summary.get('critical', 0)}")
        lines.append(f"- Open: {summary.get('open', 0)}")
        lines.append(f"- Acknowledged: {summary.get('acknowledged', 0)}")
        lines.append(f"- Resolved: {summary.get('resolved', 0)}")

    return _generate_simple_pdf(lines)


def _generate_simple_pdf(lines: List[str]) -> bytes:
    def escape_pdf_text(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content_lines = []
    y = 760
    for line in lines:
        content_lines.append(f"1 0 0 1 50 {y} Tm ({escape_pdf_text(line)}) Tj")
        y -= 14

    content_stream = "BT\n/F1 11 Tf\n" + "\n".join(content_lines) + "\nET"
    content_bytes = content_stream.encode("latin1")

    objects = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objects.append(
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Contents 5 0 R /Resources << /Font << /F1 4 0 R >> >> >> endobj\n"
    )
    objects.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    objects.append(
        b"5 0 obj << /Length "
        + str(len(content_bytes)).encode("ascii")
        + b" >> stream\n"
        + content_bytes
        + b"\nendstream endobj\n"
    )

    offsets = []
    pdf = b"%PDF-1.4\n"
    for obj in objects:
        offsets.append(len(pdf))
        pdf += obj

    xref_offset = len(pdf)
    pdf += b"xref\n0 " + str(len(objects) + 1).encode("ascii") + b"\n"
    pdf += b"0000000000 65535 f \n"
    for offset in offsets:
        pdf += f"{offset:010d} 00000 n \n".encode("ascii")

    pdf += b"trailer << /Size " + str(len(objects) + 1).encode("ascii") + b" /Root 1 0 R >>\n"
    pdf += b"startxref\n" + str(xref_offset).encode("ascii") + b"\n%%EOF\n"

    return pdf
