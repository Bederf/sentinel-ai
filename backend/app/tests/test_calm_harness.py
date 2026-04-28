from app.utils.calm_harness import ErrorCategory, calm_error, calm_tool_result


def test_connection_error_maps_correctly():
    result = calm_error(ConnectionError("refused"), "test_tool")
    assert result["status"] == "error"
    assert result["error_category"] == ErrorCategory.UNREACHABLE.value
    assert "str(e)" not in result["message"]
    assert "refused" not in result["message"]


def test_timeout_maps_correctly():
    result = calm_error(TimeoutError("timed out after 30s"), "test_tool")
    assert result["error_category"] == ErrorCategory.TIMEOUT.value


def test_unknown_exception_is_safe():
    class WeirdError(Exception):
        pass

    result = calm_error(WeirdError("internal detail"), "test_tool")
    assert result["status"] == "error"
    assert "internal detail" not in result["message"]


def test_success_result_shape():
    result = calm_tool_result({"reading": 42}, "sensor_tool")
    assert result["status"] == "success"
    assert result["data"]["reading"] == 42


def test_calm_error_never_exposes_exc_message():
    """Paranoid check — no exception detail in any field."""
    secret = "supersecret_internal_error_detail_12345"
    result = calm_error(ValueError(secret), "test_tool")
    result_str = str(result)
    assert secret not in result_str


# ---------------------------------------------------------------------------
# Scratchpad constant tests
# ---------------------------------------------------------------------------


def test_scratchpad_injected_when_site_context_true():
    """Scratchpad constant must contain the key constraint phrases."""
    from app.utils.calm_harness import SCRATCHPAD_PREFIX

    assert "phase constraints" in SCRATCHPAD_PREFIX
    assert "do not infer" in SCRATCHPAD_PREFIX
    assert "confidence levels" in SCRATCHPAD_PREFIX


def test_scratchpad_not_empty():
    from app.utils.calm_harness import SCRATCHPAD_PREFIX

    assert len(SCRATCHPAD_PREFIX.strip()) > 50
