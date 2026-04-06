"""
Signal Replay Tool — Phase 159-04
===================================
Replays historical case data (emails, bookings, occupancy events) through
all 3 bridge emitters, then runs correlation. Used to tune and validate
the correlation engine against known scenarios.

Main entry: ``replay_case("fairlands")``
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from app.services.signal_emitter_base import _reset_dedup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fixture data location
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "fixtures"


# ---------------------------------------------------------------------------
# Case data loader
# ---------------------------------------------------------------------------


async def _load_case_data(case_name: str) -> dict:
    """Load replay case data from JSON fixture.

    Raises:
        ValueError: If case_name is unknown or fixture file missing.
    """
    fixture_map = {
        "fairlands": "fairlands_replay.json",
    }

    filename = fixture_map.get(case_name)
    if filename is None:
        raise ValueError(f"Unknown replay case: '{case_name}'. Available cases: {list(fixture_map.keys())}")

    path = _FIXTURES_DIR / filename
    if not path.exists():
        raise ValueError(f"Fixture file not found: {path}")

    with open(path) as f:
        data = json.load(f)

    return data


# ---------------------------------------------------------------------------
# Per-bridge replay helpers
# ---------------------------------------------------------------------------


def _in_time_window(
    timestamp_str: str,
    time_window: dict | None,
) -> bool:
    """Check if a timestamp falls within the optional time window."""
    if time_window is None:
        return True

    if not timestamp_str:
        return True  # No timestamp → include by default

    try:
        ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return True

    start = time_window.get("start")
    end = time_window.get("end")

    if start and isinstance(start, str):
        start = datetime.fromisoformat(start.replace("Z", "+00:00"))
    if end and isinstance(end, str):
        end = datetime.fromisoformat(end.replace("Z", "+00:00"))

    if start and ts < start:
        return False
    if end and ts > end:
        return False

    return True


async def _replay_emails(
    emails: list,
    time_window: dict | None,
    verbose: bool,
) -> list[dict]:
    """Replay email data through the email signal emitter."""
    from app.services.signal_emitter import emit_email_signal

    results = []
    for i, email in enumerate(emails):
        ts = email.get("received_at", "")
        if not _in_time_window(ts, time_window):
            if verbose:
                logger.info("Replay: skipping email %d (outside time window)", i + 1)
            continue

        if verbose:
            logger.info(
                "Replay: emitting email %d/%d — %s",
                i + 1,
                len(emails),
                email.get("subject", ""),
            )

        try:
            result = await emit_email_signal(
                from_email=email.get("from_email", ""),
                from_name=email.get("from_name", ""),
                subject=email.get("subject", ""),
                body_plain=email.get("body_plain", ""),
                message_id=email.get("message_id", ""),
                in_reply_to=email.get("in_reply_to", ""),
                references=email.get("references", ""),
                to=email.get("to"),
                cc=email.get("cc"),
                received_at=email.get("received_at", ""),
            )
            if result and result.get("status") != "deduplicated":
                results.append(result)
        except Exception as exc:
            logger.warning("Replay: email %d failed: %s", i + 1, exc)

    return results


async def _replay_bookings(
    ghost_bookings: list,
    block_bookings: list,
    time_window: dict | None,
    verbose: bool,
) -> list[dict]:
    """Replay booking data through ghost and block booking emitters."""
    from app.services.booking_signal_emitter import (
        emit_block_booking_signal,
        emit_ghost_booking_signal,
    )

    results = []

    for i, finding in enumerate(ghost_bookings):
        ts = finding.get("start_time", "")
        if not _in_time_window(ts, time_window):
            continue

        if verbose:
            logger.info(
                "Replay: emitting ghost booking %d/%d — %s",
                i + 1,
                len(ghost_bookings),
                finding.get("room_code", ""),
            )

        try:
            result = await emit_ghost_booking_signal(finding)
            if result is not None:
                results.append(result)
        except Exception as exc:
            logger.warning("Replay: ghost booking %d failed: %s", i + 1, exc)

    for i, alert in enumerate(block_bookings):
        # Block bookings don't have a single timestamp; include all
        if verbose:
            logger.info(
                "Replay: emitting block booking %d/%d — %s by %s",
                i + 1,
                len(block_bookings),
                alert.get("room_code", ""),
                alert.get("booked_by", ""),
            )

        try:
            result = await emit_block_booking_signal(alert)
            if result is not None:
                results.append(result)
        except Exception as exc:
            logger.warning("Replay: block booking %d failed: %s", i + 1, exc)

    return results


async def _replay_occupancy(
    events: list,
    time_window: dict | None,
    verbose: bool,
) -> list[dict]:
    """Replay occupancy events through the occupancy mismatch emitter."""
    from app.services.occupancy_signal_emitter import emit_occupancy_mismatch_signal

    results = []
    for i, event in enumerate(events):
        ts = event.get("timestamp", "")
        if not _in_time_window(ts, time_window):
            continue

        if verbose:
            logger.info(
                "Replay: emitting occupancy event %d/%d — %s",
                i + 1,
                len(events),
                event.get("room_code", ""),
            )

        try:
            result = await emit_occupancy_mismatch_signal(event)
            if result is not None:
                results.append(result)
        except Exception as exc:
            logger.warning("Replay: occupancy event %d failed: %s", i + 1, exc)

    return results


# ---------------------------------------------------------------------------
# Correlation runner
# ---------------------------------------------------------------------------


async def _run_correlation(signal_ids: list[str]) -> dict:
    """Run correlation for each emitted signal.

    Uses psycopg2 connection to Supabase (same pattern as correlation tests).
    Returns summary of clusters formed, states, and cards generated.
    """
    import uuid

    import psycopg2

    from app.config.settings import settings
    from app.services.correlation.runner import run_correlation_for_signal

    summary = {
        "clusters_formed": 0,
        "cluster_states": [],
        "cards_generated": 0,
        "errors": [],
    }

    if not signal_ids:
        return summary

    db_url = settings.supabase_db_url
    if not db_url:
        summary["errors"].append("No Supabase DB URL configured — skipping correlation")
        return summary

    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
    except Exception as exc:
        summary["errors"].append(f"DB connection failed: {exc}")
        return summary

    seen_clusters: set[str] = set()

    try:
        for sid in signal_ids:
            try:
                result = run_correlation_for_signal(conn, uuid.UUID(sid))
                cid = result.get("cluster_id")
                if cid and cid not in seen_clusters:
                    seen_clusters.add(cid)
                    summary["clusters_formed"] += 1
                    if result.get("cluster_state"):
                        summary["cluster_states"].append(result["cluster_state"])
                summary["cards_generated"] += result.get("cards_generated", 0)
                if result.get("errors"):
                    summary["errors"].extend(result["errors"])
            except Exception as exc:
                summary["errors"].append(f"correlation({sid}): {exc}")
    finally:
        conn.close()

    return summary


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def replay_case(
    case_name: str,
    time_window: dict | None = None,
    verbose: bool = False,
) -> dict:
    """Replay a historical case through all 3 bridge emitters + correlation.

    Args:
        case_name: Case identifier, e.g. "fairlands".
        time_window: Optional ``{"start": iso_str, "end": iso_str}`` filter.
        verbose: If True, log progress for each item.

    Returns:
        Summary dict with keys:
        - signals_emitted: int
        - signals_deduped: int (from fixture count minus emitted)
        - clusters_formed: int
        - cluster_states: list[str]
        - cards_generated: int
        - errors: list[str]
    """
    # Reset dedup cache so replay is clean
    _reset_dedup()

    if verbose:
        logger.info("Replay: loading case '%s'", case_name)

    data = await _load_case_data(case_name)

    emails = data.get("emails", [])
    ghost_bookings = data.get("ghost_bookings", [])
    block_bookings = data.get("block_bookings", [])
    occupancy_events = data.get("occupancy_events", [])

    total_items = len(emails) + len(ghost_bookings) + len(block_bookings) + len(occupancy_events)

    if verbose:
        logger.info(
            "Replay: %d items (%d emails, %d ghost, %d block, %d occupancy)",
            total_items,
            len(emails),
            len(ghost_bookings),
            len(block_bookings),
            len(occupancy_events),
        )

    # Run all 3 bridges
    email_signals = await _replay_emails(emails, time_window, verbose)
    booking_signals = await _replay_bookings(ghost_bookings, block_bookings, time_window, verbose)
    occupancy_signals = await _replay_occupancy(occupancy_events, time_window, verbose)

    all_signals = email_signals + booking_signals + occupancy_signals
    signals_emitted = len(all_signals)
    signals_deduped = total_items - signals_emitted

    if verbose:
        logger.info(
            "Replay: %d signals emitted, %d deduped",
            signals_emitted,
            signals_deduped,
        )

    # Collect signal IDs for correlation
    signal_ids = []
    for sig in all_signals:
        sid = sig.get("signal_id") or sig.get("id")
        if sid:
            signal_ids.append(str(sid))

    # Run correlation
    correlation_summary = await _run_correlation(signal_ids)

    return {
        "case": case_name,
        "signals_emitted": signals_emitted,
        "signals_deduped": signals_deduped,
        "clusters_formed": correlation_summary["clusters_formed"],
        "cluster_states": correlation_summary["cluster_states"],
        "cards_generated": correlation_summary["cards_generated"],
        "errors": correlation_summary["errors"],
    }
