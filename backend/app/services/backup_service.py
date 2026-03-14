"""
Backup Service
===============
Wraps the existing backup_supabase_to_json.py script with status tracking
and async execution for the Settings UI manual trigger.
"""

import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)

BACKUP_DIR = Path(__file__).parent.parent / "data" / "supabase_backup"
BACKUP_SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "backup_supabase_to_json.py"
STATUS_FILE = BACKUP_DIR / "_backup_status.json"


class BackupService:
    """Manages Supabase-to-JSON backup with status tracking."""

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
            files = [f for f in BACKUP_DIR.iterdir() if f.suffix == ".json" and f.name != "_backup_status.json"]
            status["file_count"] = len(files)
            status["total_size_mb"] = round(sum(f.stat().st_size for f in files) / (1024 * 1024), 2)

            # Get most recent file modification time
            if files:
                newest = max(f.stat().st_mtime for f in files)
                last_dt = datetime.fromtimestamp(newest)
                status["last_backup"] = last_dt.isoformat()
                age_hours = (datetime.now() - last_dt).total_seconds() / 3600
                status["last_backup_age_hours"] = round(age_hours, 1)

        return status

    def run_backup(self) -> dict:
        """Run the backup script synchronously. Returns result dict."""
        with self._run_lock:
            if self._running:
                return {"status": "already_running"}

            self._running = True

        start = datetime.now()
        result = {"status": "unknown", "started_at": start.isoformat()}

        try:
            logger.info("Starting manual Supabase backup...")

            # Run the existing backup script as a subprocess
            proc = subprocess.run(
                [sys.executable, str(BACKUP_SCRIPT)],
                capture_output=True,
                text=True,
                timeout=300,  # 5 min max
                cwd=str(BACKUP_SCRIPT.parent.parent),  # backend/
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
            result = {"status": "timeout", "error": "Backup exceeded 5-minute limit"}
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
                BACKUP_DIR.mkdir(parents=True, exist_ok=True)
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
