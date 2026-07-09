"""Wizard acceptance gates for SENTINEL site onboarding.

Evaluates four pre-acceptance conditions before a site can have
``sentinel_processing_enabled`` set to ``true``:

1. **wizard_complete** — bridge-review committed, canonicalization done,
   hierarchy ingested (three independent side effects; no single flag).
2. **aggregation_fresh** — ``telemetry_hourly`` has rows within the
   freshness window (the canonical aggregation tier consumed by ML
   inference, pinned-signal detection, and cockpit dashboards).
3. **history_fresh** — raw telemetry exists and newest reading is within
   the freshness window (delegates to ``DataFreshnessMonitor``).
4. **operating_hours_set** — ``sites.operating_hours`` is non-null.

Gate evaluation is **fail-closed per gate** (AC-5): an unevaluable gate
returns ``check_error`` rather than passing open.  This is the opposite
of ``is_site_processing_enabled()`` which is intentionally fail-open
(legacy guard — if we cannot read DB state we assume processing should
continue).  The two functions serve different purposes and should NOT be
unified.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TELEMETRY_AGGREGATION_MAX_AGE: timedelta = timedelta(hours=48)
"""Max acceptable age of the newest ``telemetry_hourly`` row.

The Tier 1→Tier 2 aggregation runs nightly, so a gap up to ~24 h is
expected.  We allow 48 h to absorb an occasional missed run without
false-blocking the gate.
"""

_RAW_TELEMETRY_MAX_AGE: timedelta = timedelta(hours=4)
"""Max acceptable age of the newest raw sensor reading.

The bridge polls every ~60 s, so anything older than 4 h means the
bridge is likely disconnected.
"""

_GATE_TIMEOUT: float = 5.0
"""Per-gate timeout.  If a gate takes longer it fails closed with
``check_error``."""

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class GateResult:
    """Outcome of a single acceptance gate."""

    name: str
    passed: bool
    reason: str


@dataclass
class EvaluationResult:
    """Aggregate result of evaluating all four gates."""

    gates: list[GateResult] = field(default_factory=list)
    all_passed: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DB_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:55322/postgres",
)
"""Database URL used for direct SQL gate queries."""


async def _connect():
    """Open an asyncpg connection using the configured database URL."""
    import asyncpg

    return await asyncpg.connect(_DB_URL)


# ---------------------------------------------------------------------------
# Gate evaluation helpers
# ---------------------------------------------------------------------------


def _gate_error(name: str, exc: Exception) -> GateResult:
    """Fail-closed representation of a check that threw."""
    logger.warning("Gate %s failed with error: %s", name, exc, exc_info=True)
    return GateResult(name=name, passed=False, reason="check_error")


async def _check_wizard_complete(site_id: str) -> GateResult:
    """Infer wizard completion from three side effects.

    There is no single ``wizard_complete`` column.  The wizard is
    considered complete when:
      a) a bridge review has been committed (``bridge_discovered_equipment``
         rows exist with ``onboarding_status = 'onboarded'`` or
         ``site_discovery_sessions`` has a committed session),
      b) canonicalization is done (equipment rows where
         ``canonicalization_status != 'needs_review'``), and
      c) hierarchy has been ingested (wizard Step 5 ran).
    """

    conn = await _connect()
    try:
        # (a) Bridge review committed — at least one equipment row
        #     exists for this site (any canonicalization status proves
        #     the wizard bridge-review commit RPC ran).
        #     equipment.site_id is a UUID FK to sites.id, so JOIN.
        row = await conn.fetchrow(
            """SELECT count(*) AS cnt FROM equipment e
               JOIN sites s ON e.site_id = s.id
               WHERE s.code = $1""",
            site_id,
        )
        has_equipment = row and row["cnt"] > 0

        # (b) Canonicalization — at least one equipment row is
        #     past needs_review.
        row = await conn.fetchrow(
            """SELECT count(*) AS cnt FROM equipment e
               JOIN sites s ON e.site_id = s.id
               WHERE s.code = $1
                 AND (e.canonicalization_status IS NULL
                      OR e.canonicalization_status != 'needs_review')""",
            site_id,
        )
        has_canonicalization = row and row["cnt"] > 0

        # (c) Hierarchy ingestion — the wizard endpoint creates
        #     zone/hierarchy rows.  Check for zones or building tables.
        #     zones.site_id is also a UUID FK.
        row = await conn.fetchrow(
            """SELECT count(*) AS cnt FROM zones z
               JOIN sites s ON z.site_id = s.id
               WHERE s.code = $1""",
            site_id,
        )
        has_hierarchy = row and row["cnt"] > 0

        if has_equipment and has_canonicalization and has_hierarchy:
            return GateResult(
                name="wizard_complete",
                passed=True,
                reason=f"Equipment={has_equipment}, canonicalized={has_canonicalization}, hierarchy={has_hierarchy}",
            )
        else:
            return GateResult(
                name="wizard_complete",
                passed=False,
                reason=f"Equipment={has_equipment}, canonicalized={has_canonicalization}, hierarchy={has_hierarchy}",
            )
    finally:
        await conn.close()


async def _check_aggregation_fresh(site_id: str) -> GateResult:
    """Check that ``telemetry_hourly`` has recent rows.

    The authoritative aggregation source is ``telemetry_hourly`` (Tier 2
    of the three-tier aggregation pipeline).  It is consumed by ML
    inference, the pinned-signal detector, and cockpit dashboards.
    """

    cutoff = datetime.now(UTC) - _TELEMETRY_AGGREGATION_MAX_AGE

    conn = await _connect()
    try:
        row = await conn.fetchrow(
            """SELECT count(*)     AS cnt,
                      max(hour_bucket) AS newest
               FROM telemetry_hourly
               WHERE site_id = $1""",
            site_id,
        )
        await conn.close()

        cnt = row["cnt"] if row else 0
        newest = row["newest"] if row else None

        if cnt == 0:
            return GateResult(
                name="aggregation_fresh",
                passed=False,
                reason="No telemetry_hourly rows for site",
            )
        if newest and newest >= cutoff:
            return GateResult(
                name="aggregation_fresh",
                passed=True,
                reason=f"telemetry_hourly: {cnt} rows, newest {newest.isoformat()}",
            )
        return GateResult(
            name="aggregation_fresh",
            passed=False,
            reason=f"telemetry_hourly newest {newest.isoformat() if newest else 'never'} < cutoff {cutoff.isoformat()}",
        )
    except Exception as e:
        return _gate_error("aggregation_fresh", e)
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def _check_history_fresh(site_id: str) -> GateResult:
    """Check that raw telemetry exists and is current.

    Reads the ``data_freshness`` table (written every 5 min by
    ``DataFreshnessMonitor``) for the ``bms_telemetry`` source.
    Falls back to a direct query of ``equipment_sensor_readings`` if
    no cached row exists yet (first-run / new site).
    """

    raw_cutoff = datetime.now(UTC) - _RAW_TELEMETRY_MAX_AGE

    conn = await _connect()
    try:
        # Attempt cached freshness first
        row = await conn.fetchrow(
            """SELECT sli_pass, last_updated
               FROM data_freshness
               WHERE site_id = $1 AND data_source = 'bms_telemetry'
               ORDER BY last_updated DESC LIMIT 1""",
            site_id,
        )
        if row:
            sli_pass = row["sli_pass"]
            if sli_pass is True:
                return GateResult(
                    name="history_fresh",
                    passed=True,
                    reason=f"data_freshness bms_telemetry sli_pass=true, "
                    f"last_updated={row['last_updated'].isoformat()}",
                )

        # Fallback: direct query
        row = await conn.fetchrow(
            """SELECT count(*)     AS cnt,
                      max(recorded_at) AS newest
               FROM equipment_sensor_readings
               WHERE site_id = $1""",
            site_id,
        )
        cnt = row["cnt"] if row else 0
        newest = row["newest"] if row else None

        if cnt == 0:
            return GateResult(
                name="history_fresh",
                passed=False,
                reason="No raw readings for site",
            )
        if newest and newest >= raw_cutoff:
            return GateResult(
                name="history_fresh",
                passed=True,
                reason=f"Raw readings: {cnt} rows, newest {newest.isoformat()}",
            )
        return GateResult(
            name="history_fresh",
            passed=False,
            reason=f"Raw readings newest {newest.isoformat() if newest else 'never'} < cutoff {raw_cutoff.isoformat()}",
        )
    except Exception as e:
        return _gate_error("history_fresh", e)
    finally:
        try:
            await conn.close()
        except Exception:
            pass


async def _check_operating_hours_set(site_id: str) -> GateResult:
    """Check that ``sites.operating_hours`` is non-null."""
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            """SELECT operating_hours FROM sites WHERE code = $1""",
            site_id,
        )
        if row and row["operating_hours"] is not None:
            return GateResult(
                name="operating_hours_set",
                passed=True,
                reason="Site operating_hours is set",
            )
        return GateResult(
            name="operating_hours_set",
            passed=False,
            reason="Site operating_hours is null — must be set during wizard onboarding",
        )
    except Exception as e:
        return _gate_error("operating_hours_set", e)
    finally:
        try:
            await conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_GATES: dict[str, Callable] = {
    "wizard_complete": _check_wizard_complete,
    "aggregation_fresh": _check_aggregation_fresh,
    "history_fresh": _check_history_fresh,
    "operating_hours_set": _check_operating_hours_set,
}


async def evaluate(site_id: str) -> EvaluationResult:
    """Evaluate all four acceptance gates for ``site_id``.

    Each gate runs independently with a 5-second timeout.  A gate that
    throws or times out fails closed with ``check_error``.  The method
    returns ``EvaluationResult`` with per-gate breakdown and an
    ``all_passed`` shortcut.

    Fail-open vs fail-closed
    ------------------------
    This evaluator is deliberately **fail-closed**: if anything goes
    wrong the gate reports failure.  This is the correct behaviour for
    an acceptance gate that protects an unvalidated site from entering
    production processing.

    By contrast ``is_site_processing_enabled()`` in ``sites.py`` is
    intentionally **fail-open** (returns ``True`` on read failure).
    That function is a legacy safety guard read by background workers
    where a false negative (wrongly thinking the site is disabled)
    would silence all processing.  The two functions serve different
    purposes and should NOT be unified.
    """
    results: list[GateResult] = []
    for name, check in _GATES.items():
        try:
            r = await asyncio.wait_for(check(site_id), timeout=_GATE_TIMEOUT)
            results.append(r)
        except TimeoutError:
            logger.warning("Gate %s timed out after %ss", name, _GATE_TIMEOUT)
            results.append(GateResult(name=name, passed=False, reason="check_timeout"))
        except Exception as e:
            results.append(_gate_error(name, e))

    return EvaluationResult(
        gates=results,
        all_passed=all(r.passed for r in results),
    )
