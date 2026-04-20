"""Tests for AEGIS tripwire alert functions.

Covers:
- _check_tripwire_gate_fail: fires on quality_gate_status=="fail", silent otherwise
- _check_tripwire_repeated_hash: fires at >= 3 unapproved same-hash in 1h
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.database.repositories.parasite_decision_repository import (
    ParasiteDecisionRepository,
)
from app.services.aegis_bridge import (
    _check_tripwire_gate_fail,
    _check_tripwire_repeated_hash,
)


def _now_iso(offset_minutes: int = 0) -> str:
    dt = datetime.now(UTC) + timedelta(minutes=offset_minutes)
    return dt.isoformat()


def _routing_result(decision_id: str = "dec-001"):
    return SimpleNamespace(decision_id=decision_id)


def _rec_dict(
    *,
    gate_status: str = "pass",
    command_hash: str = "abc123",
    approval_outcome: str = "pending",
    correlation_id: str = "corr-001",
) -> dict:
    return {
        "correlation_id": correlation_id,
        "contributing_factors": {
            "quality_gate_status": gate_status,
            "command_hash": command_hash,
            "approval_outcome": approval_outcome,
        },
    }


# -----------------------------------------------------------------------
# _check_tripwire_gate_fail
# -----------------------------------------------------------------------


class TestGateFailTripwire:
    def test_gate_fail_emits_event(self):
        """Should emit aegis.tripwire.gate_fail when gate_status is 'fail'."""
        with patch("app.services.aegis_bridge.emit_decision_event") as mock_emit:
            rd = _rec_dict(gate_status="fail")
            _check_tripwire_gate_fail(rd, _routing_result(), "site-002")

            mock_emit.assert_called_once()
            call_args = mock_emit.call_args
            assert call_args[0][0] == "aegis.tripwire.gate_fail"
            assert call_args[1]["site_id"] == "site-002"
            assert call_args[1]["status"] == "triggered"

    def test_gate_pass_no_event(self):
        """Should NOT emit when gate_status is 'pass'."""
        with patch("app.services.aegis_bridge.emit_decision_event") as mock_emit:
            _check_tripwire_gate_fail(_rec_dict(gate_status="pass"), _routing_result(), "site-002")
            mock_emit.assert_not_called()

    def test_gate_unknown_no_event(self):
        """Should NOT emit when gate_status is 'unknown'."""
        with patch("app.services.aegis_bridge.emit_decision_event") as mock_emit:
            _check_tripwire_gate_fail(_rec_dict(gate_status="unknown"), _routing_result(), "site-002")
            mock_emit.assert_not_called()


# -----------------------------------------------------------------------
# _check_tripwire_repeated_hash
# -----------------------------------------------------------------------


@pytest.fixture
def isolated_repo(tmp_path: Path) -> ParasiteDecisionRepository:
    r = ParasiteDecisionRepository(json_path=tmp_path / "tripwire_test.json")
    r._use_json = True
    return r


def _make_hash_decision(
    *,
    id: str,
    command_hash: str = "abc123",
    approval_outcome: str = "pending",
    created_at: str | None = None,
) -> dict:
    ts = created_at or _now_iso()
    return {
        "id": id,
        "site_id": "site-002",
        "write_status": "blocked",
        "created_at": ts,
        "updated_at": ts,
        "contributing_factors": {
            "command_hash": command_hash,
            "approval_outcome": approval_outcome,
            "proposal_source": "aegis",
        },
    }


class TestRepeatedHashTripwire:
    @pytest.mark.asyncio
    async def test_repeated_hash_fires_at_3(self, isolated_repo):
        """Should emit when 3 unapproved decisions share the same hash in 1h."""
        # Insert 2 prior decisions with same hash
        await isolated_repo.record_decision(_make_hash_decision(id="h1", created_at=_now_iso(-10)))
        await isolated_repo.record_decision(_make_hash_decision(id="h2", created_at=_now_iso(-5)))
        # The 3rd is the current one (already recorded by the pipeline)
        await isolated_repo.record_decision(_make_hash_decision(id="h3", created_at=_now_iso()))

        with (
            patch(
                "app.services.aegis_bridge.get_parasite_decision_repository",
                return_value=isolated_repo,
            ),
            patch("app.services.aegis_bridge.emit_decision_event") as mock_emit,
        ):
            await _check_tripwire_repeated_hash(_rec_dict(command_hash="abc123"), _routing_result(), "site-002")
            mock_emit.assert_called_once()
            assert mock_emit.call_args[0][0] == "aegis.tripwire.repeated_hash"
            assert mock_emit.call_args[1]["details"]["unapproved_count"] == 3

    @pytest.mark.asyncio
    async def test_repeated_hash_silent_below_3(self, isolated_repo):
        """Should NOT emit when fewer than 3 unapproved decisions share the hash."""
        await isolated_repo.record_decision(_make_hash_decision(id="h1", created_at=_now_iso(-5)))

        with (
            patch(
                "app.services.aegis_bridge.get_parasite_decision_repository",
                return_value=isolated_repo,
            ),
            patch("app.services.aegis_bridge.emit_decision_event") as mock_emit,
        ):
            await _check_tripwire_repeated_hash(_rec_dict(command_hash="abc123"), _routing_result(), "site-002")
            mock_emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_repeated_hash_ignores_approved(self, isolated_repo):
        """Approved decisions should not count toward the threshold."""
        await isolated_repo.record_decision(
            _make_hash_decision(id="h1", approval_outcome="approved", created_at=_now_iso(-10))
        )
        await isolated_repo.record_decision(
            _make_hash_decision(id="h2", approval_outcome="pending", created_at=_now_iso(-5))
        )
        await isolated_repo.record_decision(
            _make_hash_decision(id="h3", approval_outcome="pending", created_at=_now_iso())
        )

        with (
            patch(
                "app.services.aegis_bridge.get_parasite_decision_repository",
                return_value=isolated_repo,
            ),
            patch("app.services.aegis_bridge.emit_decision_event") as mock_emit,
        ):
            # Only 2 unapproved (h2 + h3), threshold is 3
            await _check_tripwire_repeated_hash(_rec_dict(command_hash="abc123"), _routing_result(), "site-002")
            mock_emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_repeated_hash_ignores_old(self, isolated_repo):
        """Decisions older than 1h should not count."""
        await isolated_repo.record_decision(
            _make_hash_decision(id="h1", created_at=_now_iso(-90))  # 90 min ago
        )
        await isolated_repo.record_decision(_make_hash_decision(id="h2", created_at=_now_iso(-5)))
        await isolated_repo.record_decision(_make_hash_decision(id="h3", created_at=_now_iso()))

        with (
            patch(
                "app.services.aegis_bridge.get_parasite_decision_repository",
                return_value=isolated_repo,
            ),
            patch("app.services.aegis_bridge.emit_decision_event") as mock_emit,
        ):
            # h1 is outside the 1h window, so only 2 in window
            await _check_tripwire_repeated_hash(_rec_dict(command_hash="abc123"), _routing_result(), "site-002")
            mock_emit.assert_not_called()
