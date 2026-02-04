"""Tests for the Niagara oBIX client service."""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET

import pytest

from app.services.niagara.obix_client import (
    OBIXClient,
    OBIXAuthenticationError,
    OBIXConnectionError,
    OBIXPointNotFoundError,
    OBIXParseError,
    get_obix_client,
    reset_obix_client,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Create a fresh OBIXClient for testing."""
    return OBIXClient(
        base_url="http://niagara-test:80",
        username="testuser",
        password="testpass",
        timeout=10,
    )


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the singleton between tests."""
    reset_obix_client()
    yield
    reset_obix_client()


# ---------------------------------------------------------------------------
# Sample oBIX XML responses
# ---------------------------------------------------------------------------

POINT_REAL_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<real name="temperature1" val="23.5" status="ok"
      href="/obix/config/points/temperature1"/>
"""

POINT_OBJ_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<obj href="/obix/config/points/temperature1">
  <real name="out" val="23.5" status="ok"/>
</obj>
"""

POINT_BOOL_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<bool name="fan_status" val="true" status="ok"/>
"""

POINT_INT_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<int name="floor_count" val="3" status="ok"/>
"""

POINT_ENUM_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<enum name="mode" val="cooling" status="ok"/>
"""

ERROR_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<err display="Not Found: /obix/config/points/nonexistent"/>
"""

HISTORY_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<obj is="obix:HistoryQueryOut">
  <int name="count" val="3"/>
  <abstime name="start" val="2025-01-01T00:00:00Z"/>
  <abstime name="end" val="2025-01-01T03:00:00Z"/>
  <list name="data" of="obix:HistoryRecord">
    <obj>
      <abstime name="timestamp" val="2025-01-01T00:00:00Z"/>
      <real name="value" val="22.1"/>
    </obj>
    <obj>
      <abstime name="timestamp" val="2025-01-01T01:00:00Z"/>
      <real name="value" val="22.5"/>
    </obj>
    <obj>
      <abstime name="timestamp" val="2025-01-01T02:00:00Z"/>
      <real name="value" val="23.0"/>
    </obj>
  </list>
</obj>
"""

ALARM_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<obj is="obix:AlarmQueryOut">
  <list name="data" of="obix:Alarm">
    <obj>
      <str name="alarmId" val="ALM-001"/>
      <abstime name="timestamp" val="2025-01-01T10:30:00Z"/>
      <str name="severity" val="critical"/>
      <int name="priority" val="1"/>
      <str name="source" val="Chiller-1/CompressorFault"/>
      <str name="message" val="Compressor high pressure shutdown"/>
      <str name="ackState" val="unacked"/>
    </obj>
    <obj>
      <str name="alarmId" val="ALM-002"/>
      <abstime name="timestamp" val="2025-01-01T11:00:00Z"/>
      <str name="severity" val="warning"/>
      <int name="priority" val="3"/>
      <str name="source" val="AHU-2/FilterDirty"/>
      <str name="message" val="Filter differential pressure high"/>
      <str name="ackState" val="acked"/>
    </obj>
  </list>
</obj>
"""


# ---------------------------------------------------------------------------
# Test: Initialization
# ---------------------------------------------------------------------------

class TestOBIXClientInit:
    """Tests for OBIXClient initialization."""

    def test_init_defaults(self, client):
        assert client.base_url == "http://niagara-test:80"
        assert client.username == "testuser"
        assert client.password == "testpass"
        assert client.timeout == 10
        assert client.is_authenticated is False
        assert client.last_auth_time is None
        assert client.server_version is None

    def test_init_strips_trailing_slash(self):
        c = OBIXClient("http://server/", "u", "p")
        assert c.base_url == "http://server"

    def test_configure_resets_auth(self, client):
        client._authenticated = True
        client._last_auth_time = datetime.utcnow()

        client.configure(base_url="http://new-server:8080")

        assert client.base_url == "http://new-server:8080"
        assert client.is_authenticated is False
        assert client.last_auth_time is None


# ---------------------------------------------------------------------------
# Test: Authentication
# ---------------------------------------------------------------------------

class TestOBIXAuthentication:
    """Tests for Niagara 4.9+ authentication."""

    @patch("app.services.niagara.obix_client.requests.Session")
    def test_authenticate_success(self, mock_session_cls, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Server": "Niagara/4.13"}
        client.session.post = MagicMock(return_value=mock_response)

        result = client.authenticate()

        assert result is True
        assert client.is_authenticated is True
        assert client.last_auth_time is not None
        assert "Niagara/4.13" in client.server_version

    def test_authenticate_invalid_credentials(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 401
        client.session.post = MagicMock(return_value=mock_response)

        with pytest.raises(OBIXAuthenticationError, match="Invalid credentials"):
            client.authenticate()

        assert client.is_authenticated is False

    def test_authenticate_connection_error(self, client):
        import requests as req
        client.session.post = MagicMock(
            side_effect=req.exceptions.ConnectionError("Connection refused")
        )

        with pytest.raises(OBIXConnectionError, match="Cannot connect"):
            client.authenticate()


# ---------------------------------------------------------------------------
# Test: Point Reading
# ---------------------------------------------------------------------------

class TestPointReading:
    """Tests for reading oBIX point values."""

    def test_read_real_point(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = POINT_REAL_XML
        client.session.request = MagicMock(return_value=mock_response)
        client._authenticated = True

        result = client.read_point("config/points/temperature1")

        assert result["value"] == 23.5
        assert result["status"] == "ok"
        assert result["type"] == "real"
        assert result["path"] == "config/points/temperature1"

    def test_read_obj_nested_point(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = POINT_OBJ_XML
        client.session.request = MagicMock(return_value=mock_response)
        client._authenticated = True

        result = client.read_point("config/points/temperature1")

        assert result["value"] == 23.5
        assert result["type"] == "real"

    def test_read_bool_point(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = POINT_BOOL_XML
        client.session.request = MagicMock(return_value=mock_response)
        client._authenticated = True

        result = client.read_point("config/points/fan_status")
        assert result["value"] is True
        assert result["type"] == "bool"

    def test_read_int_point(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = POINT_INT_XML
        client.session.request = MagicMock(return_value=mock_response)
        client._authenticated = True

        result = client.read_point("config/points/floor_count")
        assert result["value"] == 3
        assert result["type"] == "int"

    def test_read_enum_point(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = POINT_ENUM_XML
        client.session.request = MagicMock(return_value=mock_response)
        client._authenticated = True

        result = client.read_point("config/points/mode")
        assert result["value"] == "cooling"
        assert result["type"] == "enum"

    def test_read_point_not_found(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 404
        client.session.request = MagicMock(return_value=mock_response)
        client._authenticated = True

        with pytest.raises(OBIXPointNotFoundError):
            client.read_point("config/points/nonexistent")

    def test_read_point_obix_error(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = ERROR_XML
        client.session.request = MagicMock(return_value=mock_response)
        client._authenticated = True

        with pytest.raises(OBIXPointNotFoundError, match="oBIX error"):
            client.read_point("config/points/nonexistent")


# ---------------------------------------------------------------------------
# Test: History Reading
# ---------------------------------------------------------------------------

class TestHistoryReading:
    """Tests for reading oBIX historical data."""

    def test_read_history_basic(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = HISTORY_XML
        client.session.request = MagicMock(return_value=mock_response)
        client._authenticated = True

        start = datetime(2025, 1, 1)
        end = datetime(2025, 1, 1, 3, 0, 0)

        records = client.read_history("histories/temperature1", start, end)

        assert len(records) == 3
        assert records[0]["timestamp"] == "2025-01-01T00:00:00Z"
        assert records[0]["value"] == 22.1
        assert records[1]["value"] == 22.5
        assert records[2]["value"] == 23.0

    def test_read_history_quality_field(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = HISTORY_XML
        client.session.request = MagicMock(return_value=mock_response)
        client._authenticated = True

        records = client.read_history("histories/temperature1")

        # Default quality is "good"
        assert records[0]["quality"] == "good"

    def test_read_history_not_found(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 404
        client.session.request = MagicMock(return_value=mock_response)
        client._authenticated = True

        with pytest.raises(OBIXPointNotFoundError):
            client.read_history("histories/nonexistent")


# ---------------------------------------------------------------------------
# Test: Alarm Reading
# ---------------------------------------------------------------------------

class TestAlarmReading:
    """Tests for reading oBIX alarm history."""

    def test_read_alarms_basic(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = ALARM_XML
        client.session.request = MagicMock(return_value=mock_response)
        client._authenticated = True

        alarms = client.read_alarms()

        assert len(alarms) == 2
        assert alarms[0]["alarm_id"] == "ALM-001"
        assert alarms[0]["severity"] == "critical"
        assert alarms[0]["priority"] == 1
        assert alarms[0]["source"] == "Chiller-1/CompressorFault"
        assert alarms[0]["message"] == "Compressor high pressure shutdown"
        assert alarms[0]["ack_state"] == "unacked"

    def test_read_alarms_severity_filter(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = ALARM_XML
        client.session.request = MagicMock(return_value=mock_response)
        client._authenticated = True

        alarms = client.read_alarms(severity_filter="critical")

        assert len(alarms) == 1
        assert alarms[0]["severity"] == "critical"

    def test_read_alarms_priority_filter(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = ALARM_XML
        client.session.request = MagicMock(return_value=mock_response)
        client._authenticated = True

        alarms = client.read_alarms(priority_filter=3)

        assert len(alarms) == 1
        assert alarms[0]["alarm_id"] == "ALM-002"


# ---------------------------------------------------------------------------
# Test: Connection Health Check
# ---------------------------------------------------------------------------

class TestConnectionHealthCheck:
    """Tests for connection health checking."""

    def test_health_check_not_authenticated(self, client):
        status = client.check_connection()

        assert status["connected"] is False
        assert "Not authenticated" in status["message"]

    def test_health_check_connected(self, client):
        client._authenticated = True
        client._last_auth_time = datetime(2025, 1, 1, 12, 0, 0)
        client._server_version = "Niagara/4.13"

        mock_response = MagicMock()
        mock_response.status_code = 200
        client.session.request = MagicMock(return_value=mock_response)

        status = client.check_connection()

        assert status["connected"] is True
        assert status["server_version"] == "Niagara/4.13"
        assert status["base_url"] == "http://niagara-test:80"


# ---------------------------------------------------------------------------
# Test: Auto-retry on 401
# ---------------------------------------------------------------------------

class TestAutoRetry:
    """Tests for automatic re-authentication on 401 responses."""

    def test_auto_retry_on_401(self, client):
        """Verify the client re-authenticates and retries on 401."""
        # First request returns 401, second succeeds
        response_401 = MagicMock()
        response_401.status_code = 401

        response_200 = MagicMock()
        response_200.status_code = 200
        response_200.content = POINT_REAL_XML

        client.session.request = MagicMock(side_effect=[response_401, response_200])

        # Mock authenticate to succeed
        auth_response = MagicMock()
        auth_response.status_code = 200
        auth_response.headers = {}
        client.session.post = MagicMock(return_value=auth_response)
        client._authenticated = True

        result = client.read_point("config/points/temperature1")

        assert result["value"] == 23.5
        # Verify authenticate was called
        assert client.session.post.called


# ---------------------------------------------------------------------------
# Test: Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    """Tests for the singleton factory function."""

    def test_get_obix_client_returns_singleton(self):
        client1 = get_obix_client()
        client2 = get_obix_client()
        assert client1 is client2

    def test_get_obix_client_default_config(self):
        client = get_obix_client()
        assert "localhost" in client.base_url
        assert client.username == ""

    def test_get_obix_client_env_config(self):
        with patch.dict(os.environ, {
            "NIAGARA_OBIX_HOST": "192.168.1.100",
            "NIAGARA_OBIX_PORT": "443",
            "NIAGARA_OBIX_USERNAME": "admin",
            "NIAGARA_OBIX_PASSWORD": "secret",
            "NIAGARA_OBIX_HTTPS": "true",
            "NIAGARA_OBIX_TIMEOUT": "60",
        }):
            reset_obix_client()
            client = get_obix_client()

            assert client.base_url == "https://192.168.1.100:443"
            assert client.username == "admin"
            assert client.timeout == 60

    def test_reset_obix_client(self):
        client1 = get_obix_client()
        reset_obix_client()
        client2 = get_obix_client()
        assert client1 is not client2
