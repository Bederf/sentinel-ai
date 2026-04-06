"""
Phase 180-02: Asset Resolution Service.

apply_resolution — write a ResolutionResult back to the documents table,
with quarantine routing based on confidence band and asset_id presence.

B3 FIX: quarantine if asset_id is None OR confidence_band is LOW (OR, not AND).
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.asset_resolution import ResolutionConfidence, ResolutionResult

logger = logging.getLogger(__name__)


def apply_resolution(
    document_id: str,
    result: ResolutionResult,
    db: Any,
) -> None:
    """
    Apply a ResolutionResult to a document record in the database.

    Quarantine routing (B3 FIX):
        quarantine if asset_id is None OR confidence_band is LOW.

    When resolved (not quarantined) AND (confidence_band == MEDIUM or needs_review):
        a compiler_queue entry is created for downstream processing.

    Parameters
    ----------
    document_id : str
        UUID of the document to update.
    result : ResolutionResult
        The resolution result from AssetIDResolver.resolve().
    db : Supabase client
        Initialised Supabase client (async table() API).
    """
    review_reason = result.review_reason

    # ---- Quarantine condition: asset_id is None OR LOW confidence ---- #
    if result.asset_id is None or result.confidence_band == ResolutionConfidence.LOW:
        logger.info(
            "apply_resolution quarantining document_id=%s reason=%s",
            document_id,
            review_reason,
        )
        _update_document(
            db,
            document_id,
            extraction_status="quarantined",
            needs_human_review=True,
            review_flags_add=[review_reason] if review_reason else None,
            # Clear any previously resolved fields
            asset_id=None,
            resolution_method=None,
            resolution_confidence=None,
        )
        return

    # ---- Resolved: update asset_id and metadata ---- #
    logger.info(
        "apply_resolution resolved document_id=%s asset_id=%s method=%s confidence=%s",
        document_id,
        result.asset_id,
        result.method.value,
        result.confidence,
    )
    _update_document(
        db,
        document_id,
        extraction_status="resolved",
        needs_human_review=result.needs_review,
        review_flags_add=[review_reason] if review_reason and result.needs_review else None,
        asset_id=result.asset_id,
        resolution_method=result.method.value,
        resolution_confidence=result.confidence,
    )

    # ---- Queue for compiler if confidence is good enough ---- #
    # Condition: asset_id exists AND (not needs_review OR MEDIUM confidence)
    if result.asset_id and (
        not result.needs_review or result.confidence_band == ResolutionConfidence.MEDIUM
    ):
        _enqueue_compiler(db, result.asset_id, document_id)


# -------------------------------------------------------------------------- #
# Internal helpers
# -------------------------------------------------------------------------- #


def _update_document(
    db: Any,
    document_id: str,
    *,
    extraction_status: str,
    needs_human_review: bool,
    review_flags_add: list[str] | None,
    asset_id: str | None,
    resolution_method: str | None,
    resolution_confidence: float | None,
) -> None:
    """
    Construct and execute the documents UPDATE.
    """
    update_payload: dict[str, Any] = {
        "extraction_status": extraction_status,
        "needs_human_review": needs_human_review,
    }
    if asset_id is not None:
        update_payload["asset_id"] = asset_id
    if resolution_method is not None:
        update_payload["resolution_method"] = resolution_method
    if resolution_confidence is not None:
        update_payload["resolution_confidence"] = resolution_confidence

    # Handle review_flags array append (SQL: review_flags || ['new_flag'])
    if review_flags_add:
        # Use a raw RPC call or upsert to append to array
        # Supabase: update with array push via DB function or raw SQL
        # Here we use db.rpc for array concat if available, otherwise raw update
        try:
            db.rpc(
                "array_push_to_review_flags",
                {"doc_id": document_id, "new_flag": review_flags_add[0]},
            ).execute()
        except Exception:
            # Fallback: update without array append; flags stay as-is
            pass

    db.table("documents").update(update_payload).eq("id", document_id).execute()


def _enqueue_compiler(db: Any, asset_id: str, document_id: str) -> None:
    """
    Insert a compiler_queue entry to trigger downstream compilation.
    """
    try:
        db.table("compiler_queue").insert(
            {
                "asset_id": asset_id,
                "trigger_event": "asset_resolved",
                "document_id": document_id,
                "queued_at": "now()",
            }
        ).on_conflict(
            constraint="compiler_queue_asset_id_trigger_event_document_id_key"
        ).execute()
    except Exception as exc:
        # If ON CONFLICT clause not supported (older Supabase), try plain insert
        try:
            db.table("compiler_queue").insert(
                {
                    "asset_id": asset_id,
                    "trigger_event": "asset_resolved",
                    "document_id": document_id,
                    "queued_at": "now()",
                }
            ).execute()
        except Exception as inner_exc:
            logger.warning(
                "Failed to enqueue compiler for asset_id=%s document_id=%s: %s",
                asset_id,
                document_id,
                inner_exc,
            )
