"""
OCR Correction Handler for Sentry Bot (Phase 41-02)

When OCR returns needs_review status, prompts technician to verify/correct
extracted values one at a time via Telegram.

Flow:
1. OCR processes service sheet photo -> returns needs_review
2. CorrectionHandler starts correction flow
3. Prompts technician for each field needing correction
4. Technician replies with corrected value
5. Handler stores correction with audit trail
6. After all corrections, applies to final data
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class OCRCorrectionHandler:
    """Handles technician corrections for OCR-extracted data via Sentry."""

    def __init__(self):
        # service_record_id -> correction state
        self.pending_corrections: Dict[str, Dict] = {}

    async def start_correction_flow(
        self, service_record_id: str, pipeline_result: Dict[str, Any], telegram_user_id: str
    ) -> Dict[str, Any]:
        """
        Start correction flow for a service record that needs review.

        Args:
            service_record_id: The service record being corrected
            pipeline_result: Result from OCR pipeline with issues
            telegram_user_id: Telegram user ID of technician

        Returns:
            First field that needs correction, or complete status
        """
        corrections_needed = pipeline_result.get("pipeline_info", {}).get("issues", [])

        # Filter to only error-level issues
        error_issues = [i for i in corrections_needed if i.get("severity") == "error"]

        if not error_issues:
            return {"complete": True, "message": "No corrections needed"}

        # Store correction state
        self.pending_corrections[service_record_id] = {
            "telegram_user_id": telegram_user_id,
            "validated_data": pipeline_result.get("validated_data", {}),
            "extracted_data": pipeline_result.get("extracted_data", {}),
            "issues": error_issues,
            "current_index": 0,
            "corrections": {},
            "started_at": datetime.now().isoformat(),
        }

        logger.info(f"Started correction flow for {service_record_id} with {len(error_issues)} issues")

        # Return first field to correct
        return self._get_next_correction_prompt(service_record_id)

    def _get_next_correction_prompt(self, service_record_id: str) -> Dict[str, Any]:
        """Get the next field that needs correction."""
        state = self.pending_corrections.get(service_record_id)
        if not state:
            return {"complete": True, "error": "No pending correction session"}

        issues = state["issues"]
        idx = state["current_index"]

        if idx >= len(issues):
            # All corrections complete
            return {
                "complete": True,
                "final_data": self._apply_corrections(service_record_id),
                "corrections_made": len(state["corrections"]),
                "message": "All corrections complete!",
            }

        issue = issues[idx]
        current_value = issue.get("raw_value", "not detected")

        # Format user-friendly prompt
        prompt = self._format_correction_prompt(issue, current_value, idx + 1, len(issues))

        return {
            "complete": False,
            "field": issue["field"],
            "message": issue["message"],
            "current_value": current_value,
            "prompt": prompt,
            "progress": f"{idx + 1}/{len(issues)}",
        }

    def _format_correction_prompt(self, issue: Dict, current_value: Any, current_num: int, total: int) -> str:
        """Format a user-friendly correction prompt."""
        field_name = issue["field"].replace("_", " ").title()

        prompt_lines = [
            f"Correction needed ({current_num}/{total}):",
            f"Field: {field_name}",
            f"Issue: {issue['message']}",
        ]

        if current_value and current_value != "not detected":
            prompt_lines.append(f"OCR detected: {current_value}")

        prompt_lines.append("\nPlease type the correct value:")

        return "\n".join(prompt_lines)

    async def process_correction_response(self, service_record_id: str, response: str) -> Dict[str, Any]:
        """
        Process technician's correction response.

        Args:
            service_record_id: The service record being corrected
            response: Technician's response with corrected value

        Returns:
            Next correction prompt or completion status
        """
        state = self.pending_corrections.get(service_record_id)
        if not state:
            return {"error": "No pending correction session", "complete": True}

        issues = state["issues"]
        idx = state["current_index"]

        if idx >= len(issues):
            return {"complete": True}

        # Store correction
        field = issues[idx]["field"]
        original_value = issues[idx].get("raw_value")

        state["corrections"][field] = {
            "original": original_value,
            "corrected": response.strip(),
            "corrected_at": datetime.now().isoformat(),
            "corrected_by": state["telegram_user_id"],
        }

        logger.info(f"Correction for {field}: '{original_value}' -> '{response.strip()}'")

        # Move to next
        state["current_index"] += 1

        return self._get_next_correction_prompt(service_record_id)

    def _apply_corrections(self, service_record_id: str) -> Dict[str, Any]:
        """Apply all corrections and return final data."""
        state = self.pending_corrections.get(service_record_id)
        if not state:
            return {}

        # Start with validated data from OCR pipeline
        final_data = state["validated_data"].copy()

        # Apply each correction
        for field, correction in state["corrections"].items():
            final_data[field] = {
                "value": correction["corrected"],
                "confidence": 1.0,  # Human-verified = full confidence
                "was_corrected": True,
                "corrected_from": correction["original"],
                "corrected_at": correction["corrected_at"],
                "corrected_by": correction["corrected_by"],
            }

        # Clean up pending state
        self.pending_corrections.pop(service_record_id)

        logger.info(f"Applied {len(state['corrections'])} corrections to {service_record_id}")

        return final_data

    def get_correction_status(self, service_record_id: str) -> Dict[str, Any]:
        """Get current correction status for a service record."""
        state = self.pending_corrections.get(service_record_id)
        if not state:
            return {"in_progress": False, "message": "No active correction session"}

        return {
            "in_progress": True,
            "current_index": state["current_index"],
            "total_issues": len(state["issues"]),
            "corrections_made": len(state["corrections"]),
            "started_at": state["started_at"],
        }

    def cancel_correction_flow(self, service_record_id: str) -> bool:
        """Cancel an active correction flow."""
        if service_record_id in self.pending_corrections:
            del self.pending_corrections[service_record_id]
            logger.info(f"Cancelled correction flow for {service_record_id}")
            return True
        return False

    def has_pending_correction(self, service_record_id: str) -> bool:
        """Check if a service record has pending corrections."""
        return service_record_id in self.pending_corrections


# Singleton instance
_correction_handler: Optional[OCRCorrectionHandler] = None


def get_ocr_correction_handler() -> OCRCorrectionHandler:
    """Get singleton OCR correction handler instance."""
    global _correction_handler
    if _correction_handler is None:
        _correction_handler = OCRCorrectionHandler()
    return _correction_handler
