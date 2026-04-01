"""Visit Policy Engine — enforces all visit access rules.

Reception endpoints delegate TO this engine; never call C-CURE or repository directly.

Policy rules:
- check_scan_policy:      8 rules (token/pin lookup, expiry, time window, status)
- check_registration_policy: 4 rules (expired/cancelled/already-active)
- check_access_issue_policy: 4 rules (must be registered, not denied/expired)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from app.database.repositories.visit_repository import VisitRepository
from app.models.visit import Visit, VisitStatus


@dataclass
class PolicyResult:
    """Result of a policy check."""

    allowed: bool
    reason: str
    status_code: int
    visit: Optional[Visit] = None


class VisitPolicyEngine:
    """Enforces visit access policy rules.

    All reception endpoints must use this engine rather than calling
    C-CURE or the repository directly.
    """

    def __init__(self, repo: Optional[VisitRepository] = None) -> None:
        self._repo = repo or VisitRepository()

    # -------------------------------------------------------------------------
    # Scan policy — 8 rules
    # -------------------------------------------------------------------------

    def check_scan_policy(
        self,
        token: Optional[UUID] = None,
        pin: Optional[str] = None,
    ) -> PolicyResult:
        """Check whether a scan (QR token or PIN) grants entry.

        Rules:
        1. MUST have either token or pin — else REJECT "no credentials"
        2. Token path: look up by token UUID; Pin path: look up by pin string
        3. If not found → REJECT "visit not found" (404)
        4. If found but expired (past meeting_end + 60min) → REJECT "visit expired" (410)
        5. If found but meeting hasn't started (now < meeting_start - 30min) → REJECT "too early" (403)
        6. If status == CANCELLED → REJECT "visit cancelled" (410)
        7. If status == DENIED → REJECT "host denied access" (403)
        8. VALID → ALLOW
        """
        # Rule 1: credentials required
        if not token and not pin:
            return PolicyResult(
                allowed=False,
                reason="no credentials",
                status_code=401,
                visit=None,
            )

        # Rule 2/3: lookup
        visit: Optional[Visit] = None
        if token:
            visit = self._repo.get_visit_by_token(token)
        else:
            visit = self._repo.get_visit_by_pin(pin)

        if visit is None:
            return PolicyResult(
                allowed=False,
                reason="visit not found",
                status_code=404,
                visit=None,
            )

        # Rule 4: expired (past meeting_end + 60 min)
        now = datetime.now(timezone.utc)
        meeting_end = visit.meeting_end
        if meeting_end.tzinfo is None:
            meeting_end = meeting_end.replace(tzinfo=timezone.utc)
        expiry_threshold = meeting_end + timedelta(minutes=60)
        if now > expiry_threshold:
            return PolicyResult(
                allowed=False,
                reason="visit expired",
                status_code=410,
                visit=visit,
            )

        # Rule 5: too early (now < meeting_start - 30 min)
        meeting_start = visit.meeting_start
        if meeting_start.tzinfo is None:
            meeting_start = meeting_start.replace(tzinfo=timezone.utc)
        window_start = meeting_start - timedelta(minutes=30)
        if now < window_start:
            return PolicyResult(
                allowed=False,
                reason="too early",
                status_code=403,
                visit=visit,
            )

        # Rule 6: cancelled
        if visit.status == VisitStatus.CANCELLED:
            return PolicyResult(
                allowed=False,
                reason="visit cancelled",
                status_code=410,
                visit=visit,
            )

        # Rule 7: denied
        if visit.status == VisitStatus.DENIED:
            return PolicyResult(
                allowed=False,
                reason="host denied access",
                status_code=403,
                visit=visit,
            )

        # Rule 8: valid
        return PolicyResult(
            allowed=True,
            reason="allowed",
            status_code=200,
            visit=visit,
        )

    # -------------------------------------------------------------------------
    # Registration policy
    # -------------------------------------------------------------------------

    def check_registration_policy(self, visit: Visit) -> PolicyResult:
        """Check whether a visitor can be registered at reception.

        Rules:
        1. If status == EXPIRED → REJECT "visit expired"
        2. If status == CANCELLED → REJECT "visit cancelled"
        3. If status == ACTIVE → REJECT "already active" (409)
        4. ALLOW
        """
        if visit.status == VisitStatus.EXPIRED:
            return PolicyResult(
                allowed=False,
                reason="visit expired",
                status_code=410,
                visit=visit,
            )

        if visit.status == VisitStatus.CANCELLED:
            return PolicyResult(
                allowed=False,
                reason="visit cancelled",
                status_code=410,
                visit=visit,
            )

        if visit.status == VisitStatus.ACTIVE:
            return PolicyResult(
                allowed=False,
                reason="already active",
                status_code=409,
                visit=visit,
            )

        return PolicyResult(
            allowed=True,
            reason="allowed",
            status_code=200,
            visit=visit,
        )

    # -------------------------------------------------------------------------
    # Access issue policy
    # -------------------------------------------------------------------------

    def check_access_issue_policy(self, visit: Visit) -> PolicyResult:
        """Check whether reception can issue an access card to a visitor.

        Rules:
        1. If status != REGISTERED → REJECT "visitor not registered" (400)
        2. If status == DENIED → REJECT "host denied" (403)
        3. If status == EXPIRED → REJECT "visit expired" (410)
        4. ALLOW
        """
        if visit.status != VisitStatus.REGISTERED:
            return PolicyResult(
                allowed=False,
                reason="visitor not registered",
                status_code=400,
                visit=visit,
            )

        if visit.status == VisitStatus.DENIED:
            return PolicyResult(
                allowed=False,
                reason="host denied",
                status_code=403,
                visit=visit,
            )

        if visit.status == VisitStatus.EXPIRED:
            return PolicyResult(
                allowed=False,
                reason="visit expired",
                status_code=410,
                visit=visit,
            )

        return PolicyResult(
            allowed=True,
            reason="allowed",
            status_code=200,
            visit=visit,
        )
