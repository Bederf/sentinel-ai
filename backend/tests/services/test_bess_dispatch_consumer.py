from app.services.bess_dispatch_consumer import _fetch_pending, _mark_recommendation


class _Cursor:
    def __init__(self) -> None:
        self.executed: tuple[str, tuple[object, ...]] | None = None
        self.description = [
            ("id",),
            ("site_id",),
            ("target_equipment",),
            ("action",),
            ("confidence_score",),
            ("reason",),
            ("timestamp",),
        ]

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.executed = (query, params)

    def fetchall(self) -> list[tuple[object, ...]]:
        return [
            (
                "rec-1",
                "site-002",
                "S002-BESS-B1-001",
                {"value": {"action": "charge", "power_kw": 50}},
                0.92,
                "Test dispatch",
                "2026-03-29T11:33:30+00:00",
            )
        ]

    def close(self) -> None:
        return None


class _Connection:
    def __init__(self) -> None:
        self.cursor_obj = _Cursor()

    def cursor(self) -> _Cursor:
        return self.cursor_obj


class _UpdateCursor:
    def __init__(self) -> None:
        self.executed: tuple[str, tuple[object, ...]] | None = None

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.executed = (query, params)

    def close(self) -> None:
        return None


class _UpdateConnection:
    def __init__(self) -> None:
        self.cursor_obj = _UpdateCursor()

    def cursor(self) -> _UpdateCursor:
        return self.cursor_obj


def test_fetch_pending_uses_timestamp_column_for_recommendations_ordering():
    conn = _Connection()

    rows = _fetch_pending("site-002", conn, limit=5)

    query, params = conn.cursor_obj.executed or ("", ())
    assert "timestamp" in query
    assert "created_at" not in query
    assert params == ("site-002", 5)
    assert rows == [
        {
            "id": "rec-1",
            "site_id": "site-002",
            "target_equipment": "S002-BESS-B1-001",
            "action": {"value": {"action": "charge", "power_kw": 50}},
            "confidence_score": 0.92,
            "reason": "Test dispatch",
            "timestamp": "2026-03-29T11:33:30+00:00",
        }
    ]


def test_mark_recommendation_remaps_unsupported_status_to_failed():
    conn = _UpdateConnection()

    _mark_recommendation("rec-1", "deferred", {"reason": "blocked"}, conn)

    query, params = conn.cursor_obj.executed or ("", ())
    assert "UPDATE recommendations" in query
    assert params[0] == "failed"
    assert params[1] == "failed"
    assert params[3] == "rec-1"
