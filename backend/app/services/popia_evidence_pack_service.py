"""POPIA monthly evidence pack generator.

Produces a compliance evidence pack containing consent metrics,
retention enforcement stats, DSR completion rates, and access control
audit data.  Reads from existing JSON data files following the project's
3-tier fallback pattern (Supabase -> Redis -> JSON).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
PACKS_PATH = DATA_DIR / "popia_evidence_packs.json"
MAX_PACKS = 24  # Keep last 24 months (FIFO)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        logger.error("Failed reading %s: %s", path, exc)
        return {}


def _write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def _in_period(iso_str: str | None, year: int, month: int) -> bool:
    """Check whether an ISO timestamp falls within the given year/month."""
    dt = _parse_iso(iso_str)
    if dt is None:
        return False
    return dt.year == year and dt.month == month


class POPIAEvidencePackService:
    """Generates monthly POPIA compliance evidence packs."""

    def __init__(
        self,
        *,
        consent_path: Path | None = None,
        retention_path: Path | None = None,
        privacy_path: Path | None = None,
        packs_path: Path | None = None,
    ) -> None:
        self._consent_path = consent_path or DATA_DIR / "consent_records.json"
        self._retention_path = retention_path or DATA_DIR / "popia_retention_runs.json"
        self._privacy_path = privacy_path or DATA_DIR / "privacy_requests.json"
        self._packs_path = packs_path or PACKS_PATH

    # ------------------------------------------------------------------
    # Consent metrics
    # ------------------------------------------------------------------

    def _build_consent_metrics(self, year: int, month: int) -> dict[str, Any]:
        data = _load_json(self._consent_path)
        records: list[dict[str, Any]] = data.get("records", []) if isinstance(data, dict) else []

        total_active = 0
        withdrawals_in_period = 0

        for rec in records:
            if rec.get("consent_given") and not rec.get("withdrawn_at"):
                total_active += 1
            if _in_period(rec.get("withdrawn_at"), year, month):
                withdrawals_in_period += 1

        total = len(records) if records else 1  # avoid div-by-zero
        withdrawal_rate = withdrawals_in_period / total if total else 0.0

        return {
            "total_active_consents": total_active,
            "withdrawals_in_period": withdrawals_in_period,
            "withdrawal_rate": round(withdrawal_rate, 4),
        }

    # ------------------------------------------------------------------
    # Retention enforcement
    # ------------------------------------------------------------------

    def _build_retention_metrics(self, year: int, month: int) -> dict[str, Any]:
        data = _load_json(self._retention_path)
        runs: list[dict[str, Any]] = data.get("runs", []) if isinstance(data, dict) else []

        runs_in_period = 0
        reviewed = 0
        purged = 0
        overdue = 0

        for run in runs:
            if _in_period(run.get("executed_at"), year, month):
                runs_in_period += 1
                reviewed += run.get("total_reviewed", 0)
                purged += run.get("total_deleted", 0)
                for cat in run.get("categories", []):
                    # retention_service tracks overdue via get_retention_status,
                    # but runs may carry the count if future versions add it.
                    overdue += cat.get("records_overdue", 0)

        return {
            "runs_in_period": runs_in_period,
            "records_reviewed": reviewed,
            "records_purged": purged,
            "overdue_count": overdue,
        }

    # ------------------------------------------------------------------
    # DSR (Data Subject Request) completion
    # ------------------------------------------------------------------

    def _build_dsr_metrics(self, year: int, month: int) -> dict[str, Any]:
        data = _load_json(self._privacy_path)
        requests: list[dict[str, Any]] = data.get("requests", []) if isinstance(data, dict) else []

        received = 0
        completed = 0
        pending = 0
        completion_days: list[float] = []
        within_sla = 0

        for req in requests:
            if not _in_period(req.get("created_at"), year, month):
                continue
            received += 1
            status = (req.get("status") or "").lower()
            if status in ("fulfilled", "completed"):
                completed += 1
                created = _parse_iso(req.get("created_at"))
                closed = _parse_iso(req.get("closed_at"))
                if created and closed:
                    days = (closed - created).total_seconds() / 86400.0
                    completion_days.append(days)
                    if days <= 30:
                        within_sla += 1
            elif status == "pending":
                pending += 1

        avg_days = round(sum(completion_days) / len(completion_days), 2) if completion_days else 0.0
        sla_pct = round((within_sla / completed) * 100, 1) if completed else 0.0

        return {
            "requests_received": received,
            "requests_completed": completed,
            "requests_pending": pending,
            "avg_completion_days": avg_days,
            "sla_adherence_pct": sla_pct,
        }

    # ------------------------------------------------------------------
    # Access control audit (placeholder — real data from future metrics)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_access_control_metrics() -> dict[str, Any]:
        return {
            "tool_call_denials": 0,
            "role_enforcement_events": 0,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_monthly_pack(self, year: int, month: int) -> dict[str, Any]:
        """Generate a POPIA evidence pack for *year*-*month*."""
        pack: dict[str, Any] = {
            "metadata": {
                "generated_at": _iso(_utc_now()),
                "period": f"{year:04d}-{month:02d}",
                "version": "1.0",
            },
            "consent_metrics": self._build_consent_metrics(year, month),
            "retention_enforcement": self._build_retention_metrics(year, month),
            "dsr_completion": self._build_dsr_metrics(year, month),
            "access_control_audit": self._build_access_control_metrics(),
        }
        return pack

    async def get_latest_pack(self) -> dict[str, Any] | None:
        """Return the most recently saved pack, or ``None``."""
        data = _load_json(self._packs_path)
        packs: list[dict[str, Any]] = data.get("packs", []) if isinstance(data, dict) else []
        return packs[-1] if packs else None

    async def save_pack(self, pack: dict[str, Any]) -> None:
        """Append *pack* and keep at most :data:`MAX_PACKS` entries (FIFO)."""
        data = _load_json(self._packs_path)
        if not isinstance(data, dict):
            data = {}
        packs: list[dict[str, Any]] = data.get("packs", [])
        packs.append(pack)
        packs = packs[-MAX_PACKS:]
        data["packs"] = packs
        data["updated_at"] = _iso(_utc_now())
        _write_json(self._packs_path, data)


def get_popia_evidence_pack_service() -> POPIAEvidencePackService:
    """Factory helper."""
    return POPIAEvidencePackService()
