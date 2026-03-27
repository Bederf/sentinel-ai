from datetime import datetime, timedelta

from app.api import events


def test_dashboard_sse_ticket_is_single_use() -> None:
    ticket = events._create_ticket("test-user")

    assert events._validate_ticket(ticket) == "test-user"
    assert events._validate_ticket(ticket) is None


def test_dashboard_sse_ticket_rejects_expired_ticket() -> None:
    ticket = events._create_ticket("test-user")
    events._SSE_TICKETS[ticket] = (datetime.utcnow() - timedelta(seconds=1), "test-user")

    assert events._validate_ticket(ticket) is None
