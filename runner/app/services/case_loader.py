"""CaseLoader — loads and validates case evidence folders."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File type policy (spec Section 7.2)
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS: set[str] = {
    # Structured
    ".json", ".jsonl", ".csv", ".parquet",
    # Documents
    ".pdf", ".docx", ".txt", ".md",
    # Logs
    ".log", ".syslog",
    # Media
    ".png", ".jpg", ".jpeg", ".webp",
}

BLOCKED_EXTENSIONS: set[str] = {
    # Executables
    ".exe", ".dll", ".so",
    # Scripts
    ".sh", ".bat", ".ps1",
    # Archives
    ".zip", ".tar", ".gz", ".7z", ".rar", ".iso",
}

# Size limits (bytes)
SOFT_CAP_BYTES: int = 500 * 1024 * 1024  # 500 MB
HARD_CAP_BYTES: int = 750 * 1024 * 1024  # 750 MB


class CaseLoader:
    """Loads case folders from the filesystem with validation."""

    def __init__(self, cases_dir: str | None = None) -> None:
        self.cases_dir = Path(cases_dir or settings.cases_dir).resolve()

    def load_case(self, case_id: str) -> dict:
        """Load a case by ID.

        Returns dict with manifest data and enumerated evidence files.
        Raises FileNotFoundError if case directory or manifest is missing.
        Raises ValueError on path traversal attempts.
        """
        case_dir = self._resolve_case_dir(case_id)

        # Read manifest
        manifest_path = case_dir / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"manifest.json not found in case '{case_id}'")

        with open(manifest_path) as f:
            manifest = json.load(f)

        # Enumerate evidence files
        evidence_dir = case_dir / "evidence"
        evidence_files: list[Path] = []
        if evidence_dir.is_dir():
            for item in evidence_dir.rglob("*"):
                if item.is_file():
                    evidence_files.append(item)

        allowed, blocked = self.validate_file_types(evidence_files)

        return {
            "case_id": case_id,
            "manifest": manifest,
            "evidence_files": [str(f) for f in allowed],
            "blocked_files": [str(f) for f in blocked],
            "case_dir": str(case_dir),
        }

    def validate_file_types(self, files: list[Path]) -> tuple[list[Path], list[Path]]:
        """Split files into allowed and blocked based on extension policy.

        Returns (allowed, blocked) tuple.
        """
        allowed: list[Path] = []
        blocked: list[Path] = []

        for f in files:
            ext = f.suffix.lower()
            if ext in BLOCKED_EXTENSIONS:
                blocked.append(f)
                logger.warning("Blocked file type: %s", f)
            elif ext in ALLOWED_EXTENSIONS:
                allowed.append(f)
            else:
                # Unknown extension — treat as blocked for safety
                blocked.append(f)
                logger.warning("Unknown file type blocked: %s", f)

        return allowed, blocked

    def check_size_limits(self, case_dir: Path) -> dict:
        """Calculate total case size and check against caps.

        Returns dict with total_bytes, over_soft, over_hard.
        """
        total_bytes = 0
        resolved = case_dir.resolve()
        for item in resolved.rglob("*"):
            if item.is_file():
                total_bytes += item.stat().st_size

        return {
            "total_bytes": total_bytes,
            "over_soft": total_bytes > SOFT_CAP_BYTES,
            "over_hard": total_bytes > HARD_CAP_BYTES,
        }

    def _resolve_case_dir(self, case_id: str) -> Path:
        """Resolve case directory with path traversal protection.

        Raises ValueError if resolved path escapes cases_dir.
        Raises FileNotFoundError if case directory does not exist.
        """
        case_dir = (self.cases_dir / case_id).resolve()

        # Path traversal guard: resolved path MUST be under cases_dir
        if not str(case_dir).startswith(str(self.cases_dir)):
            raise ValueError(f"Path traversal detected: case_id '{case_id}' resolves outside cases_dir")

        if not case_dir.is_dir():
            raise FileNotFoundError(f"Case directory not found: {case_dir}")

        return case_dir
