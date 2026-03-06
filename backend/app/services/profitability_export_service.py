"""
Profitability Export Service
============================
Exports profitability reports to CSV or PDF.
"""

from __future__ import annotations

import csv
import io
from typing import Dict, Any, List


def export_report_csv(report: Dict[str, Any]) -> bytes:
    """
    Export profitability report to CSV (Excel-friendly).
    """
    output = io.StringIO()
    writer = csv.writer(output)

    contract = report.get("contract", {})
    period = report.get("period", {})
    profitability = report.get("profitability", {})
    assets = report.get("assets", [])

    writer.writerow(["Contract Code", contract.get("code")])
    writer.writerow(["Contract ID", contract.get("id")])
    writer.writerow(["Organization", contract.get("organization_name")])
    writer.writerow(["Building", contract.get("site_name")])
    writer.writerow(["Period Start", period.get("start")])
    writer.writerow(["Period End", period.get("end")])
    writer.writerow([])

    writer.writerow(["Metric", "Value"])
    writer.writerow(["Net Revenue (ZAR)", profitability.get("net_revenue_zar")])
    writer.writerow(["Total Cost (ZAR)", profitability.get("total_cost_zar")])
    writer.writerow(["Gross Margin (ZAR)", profitability.get("gross_margin_zar")])
    writer.writerow(["Gross Margin %", profitability.get("gross_margin_percentage")])
    writer.writerow(["Assets", profitability.get("asset_count")])
    writer.writerow([])

    writer.writerow(["Asset ROI"])
    writer.writerow(["Equipment ID", "Equipment Name", "Type", "Revenue (ZAR)", "Cost (ZAR)", "ROI %"])
    for asset in assets:
        writer.writerow(
            [
                asset.get("equipment_id"),
                asset.get("equipment_name") or asset.get("equipment_code"),
                asset.get("equipment_type"),
                asset.get("allocated_revenue_zar"),
                asset.get("allocated_cost_zar"),
                asset.get("roi_percentage"),
            ]
        )

    return output.getvalue().encode("utf-8")


def export_report_pdf(report: Dict[str, Any]) -> bytes:
    """
    Export profitability report to a minimal PDF.

    This is a lightweight PDF generator to avoid external dependencies.
    """
    contract = report.get("contract", {})
    period = report.get("period", {})
    profitability = report.get("profitability", {})
    assets = report.get("assets", [])

    lines: List[str] = []
    lines.append("SENTINEL Profitability Report")
    lines.append("")
    lines.append(f"Contract: {contract.get('code') or contract.get('id')}")
    lines.append(f"Organization: {contract.get('organization_name') or 'N/A'}")
    lines.append(f"Building: {contract.get('site_name') or 'N/A'}")
    lines.append(f"Period: {period.get('start')} to {period.get('end')}")
    lines.append("")
    lines.append("Summary")
    lines.append(f"Net Revenue (ZAR): {profitability.get('net_revenue_zar')}")
    lines.append(f"Total Cost (ZAR): {profitability.get('total_cost_zar')}")
    lines.append(f"Gross Margin (ZAR): {profitability.get('gross_margin_zar')}")
    lines.append(f"Gross Margin (%): {profitability.get('gross_margin_percentage')}")
    lines.append(f"Assets: {profitability.get('asset_count')}")
    lines.append("")
    lines.append("Asset ROI")
    for asset in assets:
        name = asset.get("equipment_name") or asset.get("equipment_code") or asset.get("equipment_id")
        roi = asset.get("roi_percentage")
        lines.append(f"- {name} ({asset.get('equipment_type') or 'unknown'}): {roi}% ROI")

    return _generate_simple_pdf(lines)


def _generate_simple_pdf(lines: List[str]) -> bytes:
    """
    Minimal PDF generator supporting basic text lines.
    """

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
