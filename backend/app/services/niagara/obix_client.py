"""
oBIX client for Tridium Niagara REST API integration.

Enables SENTINEL to retrieve historical data and alarm history from
Niagara Supervisor via oBIX XML protocol over HTTP.

Key design decisions:
- Uses requests.Session() for Niagara 4.9+ cookie-based authentication
- Parses oBIX XML using xml.etree.ElementTree (standard library)
- Automatic re-authentication on 401 responses
- Singleton pattern via get_obix_client() factory
"""

import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

# oBIX XML namespace
OBIX_NS = "http://obix.org/ns/schema/1.1"
OBIX_NS_MAP = {"obix": OBIX_NS}

# Common oBIX value types
OBIX_VALUE_TYPES = {"real", "int", "bool", "str", "enum", "abstime", "reltime", "uri"}


class OBIXAuthenticationError(Exception):
    """Raised when authentication with Niagara fails."""
    pass


class OBIXConnectionError(Exception):
    """Raised when connection to Niagara server fails."""
    pass


class OBIXPointNotFoundError(Exception):
    """Raised when a requested point path is not found."""
    pass


class OBIXParseError(Exception):
    """Raised when oBIX XML response cannot be parsed."""
    pass


class OBIXClient:
    """
    oBIX client for Tridium Niagara 4.9+ REST API.

    Uses requests.Session() for cookie-based authentication as required
    by Niagara 4.9+ (breaking change from older versions).

    Usage:
        client = OBIXClient("http://niagara-server", "admin", "password")
        client.authenticate()
        value = client.read_point("config/points/temperature1")
        history = client.read_history("histories/temperature1", start, end)
        alarms = client.read_alarms(start, end)
    """

    def __init__(
        self,
        base_url: str,
        username: str = "",
        password: str = "",
        timeout: int = 30,
        use_https: bool = False,
        verify_ssl: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.use_https = use_https
        self.verify_ssl = verify_ssl

        # Session for cookie handling (Niagara 4.9+ requirement)
        self.session = requests.Session()
        self.session.verify = verify_ssl

        # Authentication state
        self._authenticated = False
        self._last_auth_time: Optional[datetime] = None
        self._server_version: Optional[str] = None
        self._max_retries = 2

    @property
    def is_authenticated(self) -> bool:
        """Check if the client has an active session."""
        return self._authenticated

    @property
    def last_auth_time(self) -> Optional[datetime]:
        """Get the timestamp of the last successful authentication."""
        return self._last_auth_time

    @property
    def server_version(self) -> Optional[str]:
        """Get the Niagara server version if detected."""
        return self._server_version

    def configure(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_https: Optional[bool] = None,
        timeout: Optional[int] = None,
    ) -> None:
        """Reconfigure the client at runtime. Resets authentication."""
        if base_url is not None:
            self.base_url = base_url.rstrip("/")
        if username is not None:
            self.username = username
        if password is not None:
            self.password = password
        if use_https is not None:
            self.use_https = use_https
        if timeout is not None:
            self.timeout = timeout

        # Reset session on reconfiguration
        self._authenticated = False
        self._last_auth_time = None
        self.session = requests.Session()
        self.session.verify = self.verify_ssl

    def authenticate(self) -> bool:
        """
        Authenticate with Niagara 4.9+ via oBIX login endpoint.

        POST /obix/login with HTTPBasicAuth.
        Session cookie is stored in requests.Session() automatically.

        Returns:
            True if authentication successful.

        Raises:
            OBIXAuthenticationError: If login fails.
            OBIXConnectionError: If server is unreachable.
        """
        login_url = f"{self.base_url}/obix/login"
        logger.info("Authenticating with Niagara at %s", self.base_url)

        try:
            response = self.session.post(
                login_url,
                auth=HTTPBasicAuth(self.username, self.password),
                timeout=self.timeout,
            )

            if response.status_code == 200:
                self._authenticated = True
                self._last_auth_time = datetime.utcnow()

                # Try to detect server version from response headers
                server_header = response.headers.get("Server", "")
                if "Niagara" in server_header:
                    self._server_version = server_header

                logger.info(
                    "Authentication successful (server: %s)",
                    self._server_version or "unknown",
                )
                return True
            elif response.status_code == 401:
                self._authenticated = False
                raise OBIXAuthenticationError(
                    "Invalid credentials for Niagara server"
                )
            else:
                self._authenticated = False
                raise OBIXAuthenticationError(
                    f"Unexpected response from login: {response.status_code}"
                )

        except requests.exceptions.ConnectionError as e:
            self._authenticated = False
            raise OBIXConnectionError(
                f"Cannot connect to Niagara server at {self.base_url}: {e}"
            ) from e
        except requests.exceptions.Timeout as e:
            self._authenticated = False
            raise OBIXConnectionError(
                f"Connection timeout to {self.base_url}: {e}"
            ) from e

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """
        Make an authenticated request with auto-retry on 401.

        If a 401 is received, attempts re-authentication and retries once.
        """
        url = f"{self.base_url}{path}"
        kwargs.setdefault("timeout", self.timeout)

        for attempt in range(self._max_retries):
            try:
                response = self.session.request(method, url, **kwargs)

                if response.status_code == 401 and attempt < self._max_retries - 1:
                    logger.warning("Got 401, re-authenticating (attempt %d)", attempt + 1)
                    self.authenticate()
                    continue

                return response

            except requests.exceptions.ConnectionError as e:
                raise OBIXConnectionError(
                    f"Connection error: {e}"
                ) from e
            except requests.exceptions.Timeout as e:
                raise OBIXConnectionError(
                    f"Request timeout: {e}"
                ) from e

        # Should not reach here, but just in case
        raise OBIXConnectionError("Max retries exceeded")

    def read_point(self, point_path: str) -> Dict[str, Any]:
        """
        Read a single point value via oBIX.

        Args:
            point_path: Path to the point (e.g., "config/points/temperature1")

        Returns:
            Dict with keys: path, value, status, type, timestamp

        Raises:
            OBIXPointNotFoundError: If point does not exist.
            OBIXParseError: If XML response cannot be parsed.
        """
        obix_path = f"/obix/config/{point_path}"
        response = self._request("GET", obix_path)

        if response.status_code == 404:
            raise OBIXPointNotFoundError(f"Point not found: {point_path}")

        if response.status_code != 200:
            raise OBIXConnectionError(
                f"Unexpected status {response.status_code} reading {point_path}"
            )

        return self._parse_point_response(response.content, point_path)

    def read_history(
        self,
        history_path: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve historical data for a point via oBIX history service.

        Args:
            history_path: Path to the history (e.g., "histories/temperature1")
            start: Start datetime for the query range
            end: End datetime for the query range
            limit: Maximum number of records to return

        Returns:
            List of dicts with keys: timestamp, value, quality
        """
        obix_path = f"/obix/histories/{history_path}/~historyQuery"

        params = {}
        if start:
            params["start"] = start.isoformat()
        if end:
            params["end"] = end.isoformat()
        if limit:
            params["limit"] = str(limit)

        response = self._request("GET", obix_path, params=params)

        if response.status_code == 404:
            raise OBIXPointNotFoundError(f"History not found: {history_path}")

        if response.status_code != 200:
            raise OBIXConnectionError(
                f"Unexpected status {response.status_code} reading history {history_path}"
            )

        return self._parse_history_response(response.content)

    def read_alarms(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100,
        severity_filter: Optional[str] = None,
        priority_filter: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve alarm history via oBIX alarm service.

        Args:
            start: Start datetime filter
            end: End datetime filter
            limit: Maximum number of alarms to return (default 100)
            severity_filter: Filter by severity (e.g., "critical", "warning")
            priority_filter: Filter by priority level (1-5)

        Returns:
            List of dicts with keys: alarm_id, timestamp, severity, priority,
                                     source, message, ack_state
        """
        obix_path = "/obix/alarms/~alarmQuery"

        params = {"limit": str(limit)}
        if start:
            params["start"] = start.isoformat()
        if end:
            params["end"] = end.isoformat()

        response = self._request("GET", obix_path, params=params)

        if response.status_code != 200:
            raise OBIXConnectionError(
                f"Unexpected status {response.status_code} reading alarms"
            )

        alarms = self._parse_alarm_response(response.content)

        # Apply client-side filters
        if severity_filter:
            alarms = [
                a for a in alarms
                if a.get("severity", "").lower() == severity_filter.lower()
            ]
        if priority_filter is not None:
            alarms = [
                a for a in alarms
                if a.get("priority") == priority_filter
            ]

        return alarms

    def check_connection(self) -> Dict[str, Any]:
        """
        Check oBIX connection health.

        Returns:
            Dict with keys: connected, last_auth, server_version, base_url
        """
        if not self._authenticated:
            return {
                "connected": False,
                "last_auth": None,
                "server_version": None,
                "base_url": self.base_url,
                "message": "Not authenticated",
            }

        try:
            response = self._request("GET", "/obix/about")
            connected = response.status_code == 200

            return {
                "connected": connected,
                "last_auth": self._last_auth_time.isoformat() if self._last_auth_time else None,
                "server_version": self._server_version,
                "base_url": self.base_url,
                "message": "Connected" if connected else f"HTTP {response.status_code}",
            }
        except (OBIXConnectionError, Exception) as e:
            return {
                "connected": False,
                "last_auth": self._last_auth_time.isoformat() if self._last_auth_time else None,
                "server_version": self._server_version,
                "base_url": self.base_url,
                "message": str(e),
            }

    # -------------------------------------------------------------------------
    # XML Parsing helpers
    # -------------------------------------------------------------------------

    def _parse_point_response(self, xml_content: bytes, point_path: str) -> Dict[str, Any]:
        """
        Parse oBIX XML point response.

        oBIX returns XML like:
        <real name="temperature1" val="23.5" status="ok"
              href="/obix/config/points/temperature1"/>
        or nested:
        <obj href="...">
          <real name="out" val="23.5" status="ok"/>
        </obj>
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            raise OBIXParseError(f"Failed to parse XML for {point_path}: {e}") from e

        # Check for oBIX error response
        if root.tag.endswith("}err") or root.tag == "err":
            display = root.attrib.get("display", "Unknown error")
            raise OBIXPointNotFoundError(f"oBIX error for {point_path}: {display}")

        # Extract value from root element or first child
        result = self._extract_value_from_element(root)
        result["path"] = point_path
        result["timestamp"] = datetime.utcnow().isoformat()

        # If root is <obj>, look for value children
        tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
        if tag == "obj" and result.get("value") is None:
            for child in root:
                child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if child_tag in OBIX_VALUE_TYPES:
                    child_result = self._extract_value_from_element(child)
                    result.update(child_result)
                    break

        return result

    def _extract_value_from_element(self, elem: ET.Element) -> Dict[str, Any]:
        """Extract value, status, and type from an oBIX element."""
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        val = elem.attrib.get("val")
        status = elem.attrib.get("status", "ok")
        name = elem.attrib.get("name", "")

        # Type conversion
        value = self._convert_obix_value(tag, val)

        return {
            "value": value,
            "status": status,
            "type": tag,
            "name": name,
        }

    def _convert_obix_value(self, obix_type: str, raw_value: Optional[str]) -> Any:
        """Convert oBIX string value to Python type."""
        if raw_value is None:
            return None

        try:
            if obix_type == "real":
                return float(raw_value)
            elif obix_type == "int":
                return int(raw_value)
            elif obix_type == "bool":
                return raw_value.lower() in ("true", "1")
            elif obix_type == "abstime":
                return raw_value  # Keep as ISO string
            elif obix_type == "reltime":
                return raw_value
            elif obix_type in ("str", "enum", "uri"):
                return raw_value
            else:
                return raw_value
        except (ValueError, TypeError):
            return raw_value

    def _parse_history_response(self, xml_content: bytes) -> List[Dict[str, Any]]:
        """
        Parse oBIX history query response.

        oBIX history response structure:
        <obj is="obix:HistoryQueryOut">
          <int name="count" val="100"/>
          <abstime name="start" val="..."/>
          <abstime name="end" val="..."/>
          <list name="data" of="obix:HistoryRecord">
            <obj>
              <abstime name="timestamp" val="2025-01-01T00:00:00Z"/>
              <real name="value" val="23.5"/>
            </obj>
            ...
          </list>
        </obj>
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            raise OBIXParseError(f"Failed to parse history XML: {e}") from e

        records = []

        # Find the data list element
        data_list = self._find_element_by_name(root, "data")
        if data_list is None:
            # Try direct children
            for child in root:
                child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if child_tag == "list":
                    data_list = child
                    break

        if data_list is None:
            return records

        # Parse each record in the list
        for record_elem in data_list:
            record = self._parse_history_record(record_elem)
            if record:
                records.append(record)

        return records

    def _parse_history_record(self, elem: ET.Element) -> Optional[Dict[str, Any]]:
        """Parse a single history record element."""
        timestamp = None
        value = None
        quality = "good"

        for child in elem:
            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            name = child.attrib.get("name", "")

            if name == "timestamp" and child_tag == "abstime":
                timestamp = child.attrib.get("val")
            elif name == "value":
                value = self._convert_obix_value(child_tag, child.attrib.get("val"))
            elif name == "quality" or name == "status":
                quality = child.attrib.get("val", "good")

        if timestamp is not None:
            return {
                "timestamp": timestamp,
                "value": value,
                "quality": quality,
            }
        return None

    def _parse_alarm_response(self, xml_content: bytes) -> List[Dict[str, Any]]:
        """
        Parse oBIX alarm query response.

        oBIX alarm response structure:
        <obj is="obix:AlarmQueryOut">
          <list name="data" of="obix:Alarm">
            <obj>
              <str name="alarmId" val="..."/>
              <abstime name="timestamp" val="..."/>
              <str name="severity" val="critical"/>
              <int name="priority" val="1"/>
              <str name="source" val="..."/>
              <str name="message" val="..."/>
              <str name="ackState" val="unacked"/>
            </obj>
            ...
          </list>
        </obj>
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            raise OBIXParseError(f"Failed to parse alarm XML: {e}") from e

        alarms = []

        # Find the data list element
        data_list = self._find_element_by_name(root, "data")
        if data_list is None:
            for child in root:
                child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if child_tag == "list":
                    data_list = child
                    break

        if data_list is None:
            return alarms

        # Parse each alarm record
        for alarm_elem in data_list:
            alarm = self._parse_alarm_record(alarm_elem)
            if alarm:
                alarms.append(alarm)

        return alarms

    def _parse_alarm_record(self, elem: ET.Element) -> Optional[Dict[str, Any]]:
        """Parse a single alarm record element."""
        alarm = {
            "alarm_id": None,
            "timestamp": None,
            "severity": "unknown",
            "priority": 5,
            "source": "",
            "message": "",
            "ack_state": "unknown",
        }

        for child in elem:
            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            name = child.attrib.get("name", "")
            val = child.attrib.get("val", "")

            if name == "alarmId" or name == "alarm_id":
                alarm["alarm_id"] = val
            elif name == "timestamp" and child_tag == "abstime":
                alarm["timestamp"] = val
            elif name == "severity":
                alarm["severity"] = val
            elif name == "priority":
                alarm["priority"] = self._convert_obix_value(child_tag, val)
            elif name == "source":
                alarm["source"] = val
            elif name == "message" or name == "display":
                alarm["message"] = val
            elif name == "ackState" or name == "ack_state":
                alarm["ack_state"] = val

        if alarm["alarm_id"] or alarm["timestamp"]:
            return alarm
        return None

    def _find_element_by_name(self, root: ET.Element, name: str) -> Optional[ET.Element]:
        """Find a child element by its 'name' attribute."""
        for child in root:
            if child.attrib.get("name") == name:
                return child
        # Try with namespace
        for child in root.iter():
            if child.attrib.get("name") == name:
                return child
        return None


# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------

_obix_client: Optional[OBIXClient] = None


def get_obix_client() -> OBIXClient:
    """
    Get or create the singleton OBIXClient instance.

    Reads from environment variables directly so that runtime patches
    (and the wizard's configure endpoint) take effect immediately.
    Settings provides defaults when env vars are not set.

    Returns:
        Singleton OBIXClient instance.
    """
    global _obix_client

    if _obix_client is None:
        from app.config.settings import settings

        # Env vars take precedence (runtime-patchable), settings provide defaults
        host = os.environ.get("NIAGARA_OBIX_HOST") or settings.niagara_obix_host or "localhost"
        port = int(os.environ.get("NIAGARA_OBIX_PORT", "0")) or settings.niagara_obix_port or 80
        username = os.environ.get("NIAGARA_OBIX_USERNAME") or settings.niagara_obix_username or ""
        password = os.environ.get("NIAGARA_OBIX_PASSWORD") or settings.niagara_obix_password or ""
        use_https = os.environ.get("NIAGARA_OBIX_HTTPS", "").lower() in ("true", "1", "yes") or settings.niagara_obix_https
        timeout = int(os.environ.get("NIAGARA_OBIX_TIMEOUT", "0")) or settings.niagara_obix_timeout or 30
        verify_ssl = os.environ.get("NIAGARA_OBIX_VERIFY_SSL", "").lower() not in ("false", "0", "no") if os.environ.get("NIAGARA_OBIX_VERIFY_SSL") else settings.niagara_obix_verify_ssl

        protocol = "https" if use_https else "http"
        base_url = f"{protocol}://{host}:{port}"

        _obix_client = OBIXClient(
            base_url=base_url,
            username=username,
            password=password,
            timeout=timeout,
            use_https=use_https,
            verify_ssl=verify_ssl,
        )

        logger.info("OBIXClient singleton created for %s", base_url)

    return _obix_client


def reset_obix_client() -> None:
    """Reset the singleton (primarily for testing)."""
    global _obix_client
    _obix_client = None
