"""SLO Report Service — Tier 4: Availability SLI.

Sends monthly SLO reports to stakeholders (Peter Marshall + Ntaote).
Renders HTML report and delivers via SMTP.
"""

import logging
import os
import smtplib
from datetime import UTC, date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger("slo-report-service")

SLO_RECIPIENTS = []


class SLOReportService:
    """Generate and email monthly SLO reports."""

    def send_monthly_slo_report(self, month: str | None = None) -> dict[str, Any]:
        """
        Fetch monthly SLO data, render HTML, email to stakeholders.
        Sync wrapper for APScheduler.
        """
        import asyncio

        try:
            return asyncio.run(self._send_monthly_slo_report_async(month))
        except Exception as e:
            logger.error(f"send_monthly_slo_report failed: {e}", exc_info=True)
            return {"error": str(e)}

    async def _send_monthly_slo_report_async(self, month: str | None = None) -> dict[str, Any]:
        """Async internals of SLO report delivery."""
        from app.database.supabase_client import get_supabase_client

        if month is None:
            today = date.today()
            if today.day == 1:
                prior = today.replace(day=1) - timedelta(days=1)
                month = prior.strftime("%Y-%m")
            else:
                month = today.strftime("%Y-%m")

        supabase = get_supabase_client()

        try:
            monthly_result = supabase.table("api_uptime_monthly").select("*").eq("month", month).execute()

            data = monthly_result.data[0] if monthly_result.data else None

            if not data:
                logger.warning(f"No monthly SLO data found for {month}")
                return {"month": month, "status": "no_data"}

            html_body = self._render_slo_report_html(month, data)

            await self._send_email(
                to=SLO_RECIPIENTS,
                subject=f"SENTINEL SLO Report — {month}",
                html_body=html_body,
            )

            logger.info(f"Monthly SLO report sent for {month} to {SLO_RECIPIENTS}")
            return {
                "month": month,
                "status": "sent",
                "recipients": SLO_RECIPIENTS,
            }

        except Exception as e:
            logger.error(f"_send_monthly_slo_report_async failed: {e}", exc_info=True)
            return {"error": str(e)}

    def _render_slo_report_html(self, month: str, data: dict[str, Any]) -> str:
        """Render SLO report as HTML email."""
        uptime = data.get("uptime_percent", 0)
        slo_target = data.get("slo_target", 99.5)
        slo_pass = data.get("slo_pass", False)
        error_budget = data.get("error_budget_remaining", 0)
        downtime = data.get("downtime_minutes", 0)
        total = data.get("total_checks", 0)
        successful = data.get("successful_checks", 0)

        status_color = "#22c55e" if slo_pass else "#ef4444"
        status_text = "PASS" if slo_pass else "FAIL"
        status_icon = "✅" if slo_pass else "❌"

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
  .container {{ max-width: 600px; margin: 0 auto; background: white;
    border-radius: 8px; padding: 24px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
  .status-banner {{ background: {status_color}; color: white; padding: 20px;
    border-radius: 8px; margin-bottom: 20px; text-align: center; }}
  .metric-table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
  .metric-table td {{ padding: 10px; border-bottom: 1px solid #eee; }}
  .metric-table td:last-child {{ text-align: right; font-weight: bold; }}
  .context-box {{ background: #f0f9ff; border-left: 4px solid #3b82f6;
    padding: 15px; border-radius: 4px; margin-bottom: 20px; }}
  .footer {{ border-top: 1px solid #eee; padding-top: 15px; color: #999; font-size: 12px; }}
</style>
</head>
<body>
<div class="container">
  <h2 style="margin: 0 0 4px 0; color: #333;">SENTINEL Monthly SLO Report</h2>
  <p style="margin: 0 0 20px 0; color: #666; font-size: 14px;">Period: <strong>{month}</strong></p>

  <div class="status-banner">
    <h2 style="margin: 0 0 10px 0; font-size: 32px;">{uptime:.3f}%</h2>
    <p style="margin: 0; font-size: 14px;">
      Uptime vs. {slo_target}% Target → <strong>{status_icon} {status_text}</strong>
    </p>
  </div>

  <table class="metric-table">
    <tr><td>Total Checks</td><td>{total:,}</td></tr>
    <tr><td>Successful Checks</td><td>{successful:,}</td></tr>
    <tr><td>Failed Checks</td><td>{total - successful:,}</td></tr>
    <tr><td>Error Budget Remaining</td><td>{error_budget:.3f}%</td></tr>
    <tr><td>Total Downtime</td><td>{downtime:.1f} minutes</td></tr>
  </table>

  <div class="context-box">
    <p style="margin: 0; color: #1e40af; font-size: 14px;">
      <strong>SLO Target:</strong> 99.5% uptime (3.6 hours downtime budget per month)
    </p>
    <p style="margin: 8px 0 0 0; color: #1e40af; font-size: 14px;">
      <strong>Definition:</strong> HTTP 200 to /api/health (synthetic, every 60s)
    </p>
  </div>

  <div class="footer">
    <p style="margin: 0;">SENTINEL Building Intelligence Platform</p>
    <p style="margin: 4px 0 0 0;">Report generated: {datetime.now(UTC).isoformat()}</p>
  </div>
</div>
</body>
</html>"""

    async def _send_email(self, to: list[str], subject: str, html_body: str) -> None:
        """Send HTML email via SMTP."""
        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER")
        smtp_pass = os.getenv("SMTP_PASSWORD")

        if not smtp_user or not smtp_pass:
            logger.warning("SMTP credentials not set — skipping email send")
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = ", ".join(to)

        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, to, msg.as_string())
            logger.info(f"Email sent to {to}")
        except Exception as e:
            logger.error(f"Failed to send email: {e}", exc_info=True)
            raise
