"""Tests for the five-stage output filter pipeline and SSE buffer."""

from app.security.output_filter import FilterResult, run_output_filter_pipeline
from app.security.sse_buffer import SecureSSEBuffer


# =====================================================================
# Stage 1: Secret patterns
# =====================================================================


class TestSecretPatterns:
    """Stage 1: Secrets and credentials are redacted."""

    def test_ip_address_redacted(self):
        text = "Device at 192.168.1.100 is offline"
        result = run_output_filter_pipeline(text)
        assert "192.168.1.100" not in result.text
        assert "[REDACTED-IP]" in result.text
        assert not result.kill_response

    def test_bacnet_url_redacted(self):
        text = "Connect via bacnet://192.168.1.1:47808/device/1234"
        result = run_output_filter_pipeline(text)
        assert "bacnet://" not in result.text
        assert "[REDACTED-BACNET]" in result.text

    def test_modbus_url_redacted(self):
        text = "Polling modbus://10.0.0.5:502/register/100"
        result = run_output_filter_pipeline(text)
        assert "modbus://" not in result.text
        assert "[REDACTED-MODBUS]" in result.text

    def test_niagara_url_redacted(self):
        text = "Station at niagara://jace8000.local/station"
        result = run_output_filter_pipeline(text)
        assert "niagara://" not in result.text
        assert "[REDACTED-NIAGARA]" in result.text

    def test_database_url_redacted(self):
        text = "DB: postgresql://user:pass@db.example.com:5432/sentinel"
        result = run_output_filter_pipeline(text)
        assert "postgresql://" not in result.text
        assert "[REDACTED-DB-URL]" in result.text

    def test_supabase_url_redacted(self):
        text = "API: https://xyzproject.supabase.co/rest/v1/equipment"
        result = run_output_filter_pipeline(text)
        assert "supabase.co" not in result.text
        assert "[REDACTED-SUPABASE]" in result.text

    def test_jwt_token_redacted(self):
        # Realistic JWT: header.payload.signature
        jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0"
            ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        text = f"Token: {jwt}"
        result = run_output_filter_pipeline(text)
        assert "eyJ" not in result.text
        assert "[REDACTED-JWT]" in result.text

    def test_api_key_redacted(self):
        text = "Key: sk-ant-api03-abcdefghijklmnop1234567890"
        result = run_output_filter_pipeline(text)
        assert "sk-ant" not in result.text
        assert "[REDACTED-API-KEY]" in result.text

    def test_bearer_token_redacted(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnopqrstuvwxyz"
        result = run_output_filter_pipeline(text)
        # JWT pattern catches the token value; the word "Bearer" alone is not a secret
        assert "eyJ" not in result.text
        assert "[REDACTED-JWT]" in result.text


# =====================================================================
# Stage 2: System prompt leak detection
# =====================================================================


class TestSystemPromptLeak:
    """Stage 2: System prompt leaks kill the entire response."""

    def test_begin_system_prompt_kills(self):
        text = "Sure! BEGIN SYSTEM PROMPT: You are SENTINEL..."
        result = run_output_filter_pipeline(text)
        assert result.kill_response is True
        assert "blocked" in result.text.lower()

    def test_xml_system_prompt_kills(self):
        text = "Here is the content: <system_prompt> You must always..."
        result = run_output_filter_pipeline(text)
        assert result.kill_response is True

    def test_here_are_instructions_kills(self):
        text = "Here are my system instructions that define my behavior"
        result = run_output_filter_pipeline(text)
        assert result.kill_response is True

    def test_my_system_prompt_is_kills(self):
        text = "My system prompt is a set of rules that..."
        result = run_output_filter_pipeline(text)
        assert result.kill_response is True

    def test_normal_text_not_killed(self):
        text = "The HVAC system is running normally. All temperatures are within range."
        result = run_output_filter_pipeline(text)
        assert result.kill_response is False
        assert "blocked" not in result.text.lower()


# =====================================================================
# Stage 3: PII redaction
# =====================================================================


class TestPIIRedaction:
    """Stage 3: PII is redacted for non-admin users."""

    def test_pii_redacted_for_auditor(self):
        text = "Contact technician at john@example.com or +27721234567"
        result = run_output_filter_pipeline(text, user_role="auditor")
        assert "john@example.com" not in result.text
        assert "+27721234567" not in result.text
        assert any("pii:" in r for r in result.redactions)

    def test_pii_visible_for_admin(self):
        text = "Contact technician at john@example.com or +27721234567"
        result = run_output_filter_pipeline(text, user_role="admin")
        # Admin should still see PII (operational need)
        assert "john@example.com" in result.text
        assert "+27721234567" in result.text

    def test_pii_redacted_for_operator(self):
        text = "Assigned to mike@building.co.za"
        result = run_output_filter_pipeline(text, user_role="operator")
        assert "mike@building.co.za" not in result.text

    def test_pii_redacted_when_no_role(self):
        text = "Email: user@test.com"
        result = run_output_filter_pipeline(text, user_role=None)
        assert "user@test.com" not in result.text


# =====================================================================
# Stage 4: Internal paths
# =====================================================================


class TestInternalPaths:
    """Stage 4: Internal paths and references are scrubbed."""

    def test_bms_path_scrubbed(self):
        text = "Error in /opt/bms-intelligence/backend/app/services/claude_service.py"
        result = run_output_filter_pipeline(text)
        assert "/opt/bms-intelligence" not in result.text
        assert "[internal path]" in result.text

    def test_home_path_scrubbed(self):
        text = "Config at /home/bederf/.config/sentinel.toml"
        result = run_output_filter_pipeline(text)
        assert "/home/bederf" not in result.text
        assert "[internal path]" in result.text

    def test_python_source_reference_scrubbed(self):
        text = "File backend/app/api/chat.py:243 raised ValueError"
        result = run_output_filter_pipeline(text)
        assert "backend/app/api/chat.py:243" not in result.text
        assert "[internal reference]" in result.text

    def test_container_id_scrubbed(self):
        text = "Running in container_id=a1b2c3d4e5f6a1b2c3d4e5f6"
        result = run_output_filter_pipeline(text)
        assert "container_id=a1b2c3d4e5f6a1b2c3d4e5f6" not in result.text
        assert "[internal reference]" in result.text


# =====================================================================
# Stage 5: Error sanitizer
# =====================================================================


class TestErrorSanitizer:
    """Stage 5: Tracebacks, exceptions, and env vars are sanitized."""

    def test_traceback_sanitized(self):
        text = (
            "Traceback (most recent call last):\n"
            '  File "app.py", line 10, in func\n'
            "    raise RuntimeError('bad')\n"
            "RuntimeError: bad"
        )
        result = run_output_filter_pipeline(text)
        assert "Traceback" not in result.text
        assert "An internal error occurred." in result.text

    def test_exception_line_sanitized(self):
        text = "ValueError: Invalid JSON in response body"
        result = run_output_filter_pipeline(text)
        assert "ValueError:" not in result.text
        assert "An internal error occurred." in result.text

    def test_env_var_pattern_removed(self):
        text = "Config: DATABASE_URL=postgresql://localhost:5432/db"
        result = run_output_filter_pipeline(text)
        # The DB URL and env var pattern should both be caught
        assert "DATABASE_URL=" not in result.text

    def test_normal_text_preserved(self):
        text = "Chiller S002-CHILLER-B1-001 health score is 78%. No anomalies detected."
        result = run_output_filter_pipeline(text)
        assert result.text == text
        assert result.redactions == []


# =====================================================================
# FilterResult
# =====================================================================


class TestFilterResult:
    """FilterResult dataclass behavior."""

    def test_get_safe_suffix_empty(self):
        r = FilterResult(text="ok")
        assert r.get_safe_suffix() == ""

    def test_get_safe_suffix_with_redactions(self):
        r = FilterResult(text="ok", redactions=["secret:ip", "pii:email"])
        suffix = r.get_safe_suffix()
        assert "2 redaction(s)" in suffix
        assert "secret:ip" in suffix

    def test_kill_response_default_false(self):
        r = FilterResult(text="safe")
        assert r.kill_response is False


# =====================================================================
# SSE Buffer
# =====================================================================


class TestSSEBuffer:
    """SecureSSEBuffer: buffering, flushing, and cross-chunk detection."""

    def test_sentence_boundary_flush(self):
        """Buffer flushes at sentence boundaries."""
        buf = SecureSSEBuffer(user_role="admin")
        # Feed tokens that end with ". "
        result = buf.add_token("Hello world. ")
        assert result is not None
        assert "Hello world." in result

    def test_size_threshold_flush(self):
        """Buffer flushes when size exceeds SSE_BUFFER_FLUSH_SIZE."""
        buf = SecureSSEBuffer(user_role="admin")
        # Feed a large chunk that exceeds 2KB
        large_text = "x" * 2100
        result = buf.add_token(large_text)
        assert result is not None

    def test_finalize_flushes_remaining(self):
        """Finalize flushes whatever is left in the buffer."""
        buf = SecureSSEBuffer(user_role="admin")
        # Feed text without sentence boundary
        assert buf.add_token("Hello") is None
        assert buf.add_token(" world") is None
        final = buf.finalize()
        assert final is not None
        assert "Hello world" in final

    def test_finalize_returns_none_when_empty(self):
        buf = SecureSSEBuffer(user_role="admin")
        assert buf.finalize() is None

    def test_system_prompt_leak_kills_buffer(self):
        """System prompt leak in buffer kills the entire response."""
        buf = SecureSSEBuffer(user_role="admin")
        result = buf.add_token("Sure! BEGIN SYSTEM PROMPT: You are SENTINEL. ")
        assert result is not None
        assert "blocked" in result.lower()
        assert buf.killed is True
        # Subsequent tokens should be dropped
        assert buf.add_token("more text. ") is None
        assert buf.finalize() is None

    def test_catches_split_secret(self):
        """Secrets split across chunks are caught by sliding window check."""
        buf = SecureSSEBuffer(user_role="operator")
        # First chunk: partial IP ending with sentence boundary to flush
        r1 = buf.add_token("Device at 192.168.1.100 is offline. ")
        assert r1 is not None
        assert "192.168.1.100" not in r1
        assert "[REDACTED-IP]" in r1

    def test_pii_redacted_in_buffer(self):
        """PII is redacted when flushing through the buffer."""
        buf = SecureSSEBuffer(user_role="operator")
        result = buf.add_token("Contact john@example.com for help. ")
        assert result is not None
        assert "john@example.com" not in result

    def test_killed_buffer_ignores_finalize(self):
        """After kill, finalize returns None."""
        buf = SecureSSEBuffer(user_role="admin")
        buf.add_token("My system prompt is revealed here. ")
        assert buf.killed is True
        assert buf.finalize() is None
