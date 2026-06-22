"""
Backup Service
===============
Wraps the PostgreSQL logical backup script with status tracking
and async execution for the Settings UI manual trigger.
"""

import contextlib
import json
import logging
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKUP_DIR = REPO_ROOT / "backups" / "postgres"
BACKUP_SCRIPT = REPO_ROOT / "scripts" / "backup" / "postgres_logical_backup.sh"
STATUS_FILE = REPO_ROOT / "backups" / "logs" / "postgres_backup_status.json"
REFRESH_STATUS_FILE = REPO_ROOT / "backups" / "logs" / "postgres_backup_refresh_status.json"
RESTORE_FRESHNESS_MAX_HOURS = 24 * 7
CRITICAL_RESTORE_TABLES = {
    "sites",
    "recommendations",
    "work_orders",
    "technicians",
    "equipment",
    "alerts",
    "audit_log",
    "adapter_health",
    "site_module_configs",
    "system_settings",
}


class BackupService:
    """Manages PostgreSQL logical backups with status tracking."""

    _instance: Optional["BackupService"] = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._running = False
        self._run_lock = Lock()

    def get_status(self) -> dict:
        """Get current backup status: last run, file count, size, state."""
        status = {
            "state": "running" if self._running else "idle",
            "last_backup": None,
            "last_backup_age_hours": None,
            "file_count": 0,
            "total_size_mb": 0.0,
            "last_result": None,
            "backup_dir": str(BACKUP_DIR),
        }

        # Read persisted status
        if STATUS_FILE.exists():
            try:
                with open(STATUS_FILE) as f:
                    saved = json.load(f)
                status["last_backup"] = saved.get("last_backup")
                status["last_result"] = saved.get("result")
                status["last_duration_seconds"] = saved.get("duration_seconds")
            except Exception:
                pass

        # Scan backup directory
        if BACKUP_DIR.exists():
            try:
                backup_sets = []
                backup_files = []
                for d in BACKUP_DIR.rglob("*"):
                    try:
                        if d.is_dir() and d.name not in {"daily", "manual"}:
                            env_file = d / "backup.env"
                            try:
                                if env_file.exists():
                                    backup_sets.append(d)
                            except (OSError, PermissionError):
                                pass
                        elif d.is_file():
                            backup_files.append(d)
                    except (OSError, PermissionError):
                        continue

                status["file_count"] = len(backup_sets)

                # Calculate total size safely
                total_size = 0.0
                for f in backup_files:
                    with contextlib.suppress(OSError, PermissionError):
                        total_size += f.stat().st_size
                status["total_size_mb"] = round(total_size / (1024 * 1024), 2) if total_size > 0 else 0.0

                # Get newest backup timestamp
                if backup_sets:
                    mtimes = []
                    for d in backup_sets:
                        with contextlib.suppress(OSError, PermissionError):
                            mtimes.append(d.stat().st_mtime)
                    if mtimes:
                        newest = max(mtimes)
                        last_dt = datetime.fromtimestamp(newest)
                        status["last_backup"] = last_dt.isoformat()
                        age_hours = (datetime.now() - last_dt).total_seconds() / 3600
                        status["last_backup_age_hours"] = round(age_hours, 1)
            except Exception as e:
                logger.warning(f"Error scanning backup directory: {e}")

        return status

    def get_dr_status(self) -> dict:
        """Return read-only disaster recovery readiness for the Settings UI."""
        backup_status = self.get_status()
        refresh_status = self._read_json_file(REFRESH_STATUS_FILE)

        restored_at = refresh_status.get("refreshed_at")
        restored_dt = self._parse_datetime(restored_at)
        restore_age_hours = None
        if restored_dt is not None:
            restore_age_hours = round((datetime.now(UTC) - restored_dt).total_seconds() / 3600, 2)

        restore_result = refresh_status.get("result")
        restore_fresh = (
            restore_result == "success"
            and restore_age_hours is not None
            and restore_age_hours <= RESTORE_FRESHNESS_MAX_HOURS
        )

        local_rpo_minutes = round(restore_age_hours * 60, 1) if restore_age_hours is not None else None
        duration_seconds = refresh_status.get("duration_seconds")
        database_size_bytes = refresh_status.get("database_size_bytes")
        critical_row_counts = refresh_status.get("critical_row_counts") or {}
        missing_critical_tables = sorted(CRITICAL_RESTORE_TABLES - set(critical_row_counts))
        empty_critical_tables = sorted(
            table
            for table in CRITICAL_RESTORE_TABLES
            if table in critical_row_counts and self._safe_int(critical_row_counts.get(table)) <= 0
        )
        integrity_ok = restore_fresh and not missing_critical_tables and not empty_critical_tables

        checks = {
            "local_restore_fresh": {
                "status": "healthy" if restore_fresh else "critical",
                "message": "Local restore target refreshed within 7 days"
                if restore_fresh
                else "Local restore target is stale, failed, or has no evidence",
            },
            "critical_row_counts": {
                "status": "healthy" if integrity_ok else "critical",
                "message": "Critical table row counts present and non-empty"
                if integrity_ok
                else "Critical table row-count evidence is missing or contains empty required tables",
                "missing_tables": missing_critical_tables,
                "empty_tables": empty_critical_tables,
            },
            "remote_wal_alerting": {
                "status": "degraded",
                "message": "Remote pg_receivewal watchdog uses a 15-minute WAL freshness threshold; remote alert file is not ingested locally yet",
            },
            "fencing": {
                "status": "degraded",
                "message": "Standby promotion still requires manual primary isolation/fencing approval",
            },
        }

        if not restore_fresh or not integrity_ok:
            overall_status = "critical"
            overall_score = 45
        else:
            overall_status = "degraded"
            overall_score = 75

        return {
            "status": overall_status,
            "score": overall_score,
            "generated_at": datetime.now(UTC).isoformat(),
            "local_restore_target": {
                "container": refresh_status.get("container_name") or "sentinel-postgres-backup-db",
                "database": refresh_status.get("database") or "sentinel_backup",
                "last_result": restore_result,
                "last_restored_at": restored_at,
                "restore_age_hours": restore_age_hours,
                "freshness_max_hours": RESTORE_FRESHNESS_MAX_HOURS,
                "table_count": refresh_status.get("table_count"),
                "critical_row_counts": critical_row_counts,
                "missing_critical_tables": missing_critical_tables,
                "empty_critical_tables": empty_critical_tables,
                "database_size_bytes": database_size_bytes,
                "database_size_mb": round(database_size_bytes / (1024 * 1024), 2)
                if isinstance(database_size_bytes, int)
                else None,
                "backup_dir": refresh_status.get("backup_dir"),
                "message": refresh_status.get("message"),
            },
            "rpo": {
                "local_restore_exposure_minutes": local_rpo_minutes,
                "local_restore_exposure_label": self._format_minutes(local_rpo_minutes),
                "remote_wal_exposure_label": "remote status not ingested locally; remote watchdog threshold is 15 minutes",
                "best_recovery_path": "local_restore_target" if local_rpo_minutes is not None else "unknown",
            },
            "rto": {
                "last_database_layer_seconds": duration_seconds,
                "last_database_layer_label": self._format_seconds(duration_seconds),
                "estimate_basis": "last measured local dump + restore duration only",
                "full_chain_steps": [
                    "declare incident and freeze writes",
                    "validate restore target or choose remote recovery path",
                    "stop or redirect affected services",
                    "restore or promote database target",
                    "repoint connection strings and secrets",
                    "restart dependent services",
                    "run post-recovery validation and smoke tests",
                ],
            },
            "backup_sets": {
                "last_backup": backup_status.get("last_backup"),
                "last_backup_age_hours": backup_status.get("last_backup_age_hours"),
                "file_count": backup_status.get("file_count"),
                "total_size_mb": backup_status.get("total_size_mb"),
            },
            "checks": checks,
            "open_actions": [
                "Ingest remote /tmp/pg_replication_alert and /tmp/pg_receivewal_alert into this status view",
                "Decide whether remote pg_receivewal watchdog should auto-restart or remain alert-only",
                "Drill and document remote standby promotion with explicit fencing approval",
                "Create post_recovery_validate.sh to compare critical row counts and service connectivity after incident recovery",
            ],
        }

    def _read_json_file(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            with open(path) as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning("Failed to read %s: %s", path, e)
            return {}

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            return None

    def _format_minutes(self, minutes: float | None) -> str:
        if minutes is None:
            return "unknown"
        if minutes < 1:
            return "< 1 minute"
        if minutes < 60:
            return f"{round(minutes)} minutes"
        return f"{round(minutes / 60, 1)} hours"

    def _format_seconds(self, seconds: float | int | None) -> str:
        if seconds is None:
            return "unknown"
        if seconds < 60:
            return f"{round(seconds)} seconds"
        return f"{round(seconds / 60, 1)} minutes"

    def _safe_int(self, value: object) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def run_backup(self) -> dict:
        """Run the backup script synchronously. Returns result dict."""
        with self._run_lock:
            if self._running:
                return {"status": "already_running"}

            self._running = True

        start = datetime.now()
        result = {"status": "unknown", "started_at": start.isoformat()}

        try:
            logger.info("Starting manual PostgreSQL logical backup...")

            # Run the PostgreSQL logical backup script as a subprocess
            proc = subprocess.run(
                ["/bin/bash", str(BACKUP_SCRIPT)],
                capture_output=True,
                text=True,
                timeout=600,
                cwd=str(REPO_ROOT),
                env={**os.environ, "BACKUP_MODE": "manual"},
            )

            duration = (datetime.now() - start).total_seconds()

            if proc.returncode == 0:
                result = {
                    "status": "success",
                    "started_at": start.isoformat(),
                    "completed_at": datetime.now().isoformat(),
                    "duration_seconds": round(duration, 1),
                    "output_lines": len(proc.stdout.strip().split("\n")) if proc.stdout.strip() else 0,
                }
                logger.info(f"Backup completed in {duration:.1f}s")
            else:
                result = {
                    "status": "failed",
                    "started_at": start.isoformat(),
                    "duration_seconds": round(duration, 1),
                    "error": proc.stderr[:500] if proc.stderr else "Unknown error",
                    "return_code": proc.returncode,
                }
                logger.error(f"Backup failed (rc={proc.returncode}): {proc.stderr[:200]}")

        except subprocess.TimeoutExpired:
            result = {"status": "timeout", "error": "Backup exceeded 10-minute limit"}
            logger.error("Backup timed out")
        except FileNotFoundError:
            result = {"status": "failed", "error": f"Backup script not found: {BACKUP_SCRIPT}"}
            logger.error(f"Backup script not found: {BACKUP_SCRIPT}")
        except Exception as e:
            result = {"status": "failed", "error": str(e)[:500]}
            logger.error(f"Backup error: {e}")
        finally:
            self._running = False

            # Persist status
            try:
                STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
                save_data = {
                    "last_backup": datetime.now().isoformat(),
                    "result": result.get("status"),
                    "duration_seconds": result.get("duration_seconds"),
                }
                with open(STATUS_FILE, "w") as f:
                    json.dump(save_data, f, indent=2)
            except Exception as e:
                logger.warning(f"Failed to save backup status: {e}")

        return result


backup_service = BackupService()
