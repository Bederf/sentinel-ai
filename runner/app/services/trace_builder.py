"""TraceBuilder — typed helpers for audit trace entries.

Wraps RunManager.append_trace() with semantic methods for file access,
model calls, state changes, and recursive steps.

Spec Section 9.2: NO raw prompts or responses in trace — only hashes.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.services.run_manager import run_manager

logger = logging.getLogger(__name__)


class TraceBuilder:
    """Builds typed trace entries and appends them via RunManager."""

    def capture_file_access(
        self,
        run_id: str,
        file_path: Path,
        sha256: str,
        size_bytes: int,
    ) -> None:
        """Log a file read event in the trace."""
        entry = self._make_entry(
            event_type="file_access",
            details={
                "file_path": str(file_path),
                "sha256": sha256,
                "size_bytes": size_bytes,
            },
        )
        run_manager.append_trace(run_id, entry)

    def capture_model_call(
        self,
        run_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        prompt_hash: str,
        response_hash: str,
        elapsed_ms: float,
    ) -> None:
        """Log an LLM call in the trace.

        NO raw prompts or responses stored — only SHA256 hashes (spec Section 9.2).
        """
        entry = self._make_entry(
            event_type="model_call",
            details={
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "prompt_hash": prompt_hash,
                "response_hash": response_hash,
                "elapsed_ms": round(elapsed_ms, 2),
            },
        )
        run_manager.append_trace(run_id, entry)

    def capture_state_change(
        self,
        run_id: str,
        from_state: str,
        to_state: str,
    ) -> None:
        """Log a run state transition in the trace."""
        entry = self._make_entry(
            event_type="state_change",
            details={
                "from_state": from_state,
                "to_state": to_state,
            },
        )
        run_manager.append_trace(run_id, entry)

    def capture_step(
        self,
        run_id: str,
        step_number: int,
        action: str,
        result_summary: str,
    ) -> None:
        """Log a recursive analysis pass step in the trace."""
        entry = self._make_entry(
            event_type="analysis_step",
            details={
                "step_number": step_number,
                "action": action,
                "result_summary": result_summary,
            },
        )
        run_manager.append_trace(run_id, entry)

    @staticmethod
    def compute_sha256(file_path: Path) -> str:
        """Compute SHA256 hash of a file using chunked reading (8KB chunks).

        Works efficiently for large files without loading entirely into memory.
        """
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def hash_text(text: str) -> str:
        """SHA256 hash of text content (for prompt/response hashing).

        Never stores raw text — only the hash.
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _make_entry(event_type: str, details: dict) -> dict:
        """Create a trace entry dict with UTC timestamp."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "details": details,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

trace_builder = TraceBuilder()
