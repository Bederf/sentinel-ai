"""
Pytest configuration and fixtures for BMS Intelligence backend tests.
"""

import os
import warnings

# Universal Engine: Tests run in production mode without TESTING/DEMO_MODE bypasses.
# All test requests must include valid JWT tokens from the fixtures below.
# This ensures tests validate the actual authentication code path.
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")
warnings.filterwarnings(
    "ignore",
    message="Please use `import python_multipart` instead.",
    category=PendingDeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message="on_event is deprecated.*",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module="typing_extensions",
)
warnings.filterwarnings(
    "ignore",
    message="on_event is deprecated.*",
    category=DeprecationWarning,
    module="app.api.devices",
)
warnings.filterwarnings(
    "ignore",
    message=".*enablePackrat.*",
)
warnings.filterwarnings(
    "ignore",
    message=".*escChar.*",
)
warnings.filterwarnings(
    "ignore",
    message=".*unquoteResults.*",
)
try:
    import pyparsing

    warnings.filterwarnings(
        "ignore",
        category=pyparsing.warnings.PyparsingDeprecationWarning,
    )
except Exception:
    pass

import asyncio  # noqa: E402
import json  # noqa: E402
from collections.abc import AsyncGenerator, Generator  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import Mock, patch  # noqa: E402

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

if os.getenv("LIGHTWEIGHT_APP", "").lower() == "true":
    from app.api import audit as audit_api
    from app.api import devices as devices_api
    from app.api import health as health_api
    from app.api import safety as safety_api
    from app.api import sites as sites_api
    from app.api import stats as stats_api
    from app.api import workflow as workflow_api

    app = FastAPI()
    app.router.redirect_slashes = False
    app.include_router(devices_api.router, prefix="/api", tags=["devices"])
    app.include_router(health_api.router, prefix="/api", tags=["health"])
    app.include_router(sites_api.router, prefix="/api", tags=["sites"])
    app.include_router(stats_api.router, prefix="/api", tags=["stats"])
    app.include_router(safety_api.router, tags=["safety"])
    app.include_router(audit_api.router, tags=["audit"])
    app.include_router(workflow_api.router, tags=["workflow"])

    @app.get("/")
    async def _root():
        return {"status": "ok"}

    @app.post("/api/chat")
    async def _chat_stub(payload: dict):
        return {"status": "ok", "message": payload.get("message", "")}

    @app.post("/api/hybrid-chat")
    async def _hybrid_chat_stub(payload: dict):
        return {"status": "ok", "message": payload.get("message", "")}
else:
    from app.main import app

# Speed up API tests by skipping app startup/shutdown hooks in testing mode.
if os.getenv("TESTING", "").lower() == "true":
    app.router.on_startup.clear()
    app.router.on_shutdown.clear()
from datetime import UTC

from app.services.audit_logger import AuditLogger  # noqa: E402
from app.services.device_abstraction import DeviceManager  # noqa: E402
from app.services.safety_interlocks import SafetyEngine  # noqa: E402

# Test data directory
TEST_DATA_DIR = Path(__file__).parent.parent / "app" / "data"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class _SyncASGIClient:
    """Sync wrapper around AsyncClient for tests where TestClient hangs."""

    def __init__(self, app: FastAPI):
        self._app = app

    def request(self, method: str, url: str, **kwargs):
        async def _do_request():
            transport = ASGITransport(app=self._app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(_do_request())

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def options(self, url: str, **kwargs):
        return self.request("OPTIONS", url, **kwargs)


@pytest.fixture
def test_client() -> Generator[TestClient, None, None]:
    """FastAPI test client for synchronous tests."""
    yield _SyncASGIClient(app)


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for tests that use ``client`` fixture name."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for async tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_devices_data() -> list[dict]:
    """Load reference devices data from JSON file."""
    ref_devices_file = (
        Path(__file__).parent.parent / "app" / "services" / "bms_simulator" / "data" / "reference_devices.json"
    )
    if ref_devices_file.exists():
        with open(ref_devices_file) as f:
            return json.load(f)
    return []


@pytest.fixture
def mock_safety_rules_data() -> list[dict]:
    """Load safety rules data from JSON file."""
    safety_rules_file = TEST_DATA_DIR / "safety_rules.json"
    if safety_rules_file.exists():
        with open(safety_rules_file) as f:
            return json.load(f)
    return []


@pytest.fixture
async def device_manager(mock_devices_data: list[dict]) -> DeviceManager:
    """Device manager fixture with test devices."""
    manager = DeviceManager()
    await manager.initialize(mock_devices_data)
    yield manager
    # Cleanup if needed
    await manager.shutdown()


@pytest.fixture
async def safety_engine(mock_safety_rules_data: list[dict]) -> SafetyEngine:
    """Safety engine fixture with test rules."""
    engine = SafetyEngine()
    await engine.initialize(mock_safety_rules_data)
    yield engine
    # Reset engine state
    engine.rules = {}
    engine._initialized = False


@pytest.fixture
def audit_logger() -> AuditLogger:
    """Audit logger fixture."""
    logger = AuditLogger()
    yield logger
    # Cleanup audit logs if needed
    logger.logs.clear()


@pytest.fixture
def sample_device() -> dict:
    """Sample device data for testing."""
    return {
        "id": "test-device-001",
        "name": "Test Chiller",
        "device_type": "hvac",
        "protocol": "mock",
        "location": "Test Location",
        "site_id": "test-site-001",
        "description": "Test device for unit tests",
        "points": {
            "setpoint": {
                "name": "setpoint",
                "point_type": "analog_output",
                "description": "Temperature setpoint",
                "unit": "°C",
                "min_value": 16.0,
                "max_value": 28.0,
                "default_value": 22.0,
                "writable": True,
                "priority": 8,
            },
            "status": {
                "name": "status",
                "point_type": "binary_output",
                "description": "Device status",
                "unit": "",
                "default_value": True,
                "writable": True,
                "priority": 8,
            },
        },
        "metadata": {
            "manufacturer": "Test Manufacturer",
            "model": "Test Model",
        },
    }


@pytest.fixture
def sample_safety_rule() -> dict:
    """Sample safety rule data for testing."""
    return {
        "id": "test-rule-001",
        "name": "Test Temperature Range",
        "type": "temperature_range",
        "device_type": "hvac",
        "device_id": None,
        "point_name": "setpoint",
        "severity": "block",
        "enabled": True,
        "min_value": 16.0,
        "max_value": 28.0,
        "description": "Test temperature range rule",
    }


@pytest.fixture
def sample_site() -> dict:
    """Sample site data for testing."""
    return {
        "id": "test-site-001",
        "name": "Test Site",
        "location": "Test Location",
        "region": "Gauteng",
        "type": "office",
        "equipment_count": 5,
        "alert_count": 2,
        "status": "normal",
    }


@pytest.fixture
def sample_equipment() -> dict:
    """Sample equipment data for testing."""
    return {
        "id": "test-equipment-001",
        "name": "Test Chiller",
        "type": "chiller",
        "site_id": "test-site-001",
        "site_name": "Test Site",
        "status": "online",
        "last_reading": {
            "timestamp": "2025-01-28T10:00:00Z",
            "value": 22.5,
            "unit": "°C",
        },
    }


@pytest.fixture
def sample_audit_log() -> dict:
    """Sample audit log entry for testing."""
    return {
        "id": "test-audit-001",
        "timestamp": "2025-01-28T10:00:00Z",
        "action": "DEVICE_CONTROL",
        "user": "test-operator",
        "device_id": "test-device-001",
        "point_name": "setpoint",
        "old_value": 21.5,
        "new_value": 22.0,
        "result": "SUCCESS",
        "safety_validation": {
            "rules_checked": ["temperature_range"],
            "passed_rules": ["temperature_range"],
            "failed_rules": [],
        },
        "metadata": {},
    }


@pytest.fixture
def mock_claude_api():
    """Mock Claude API responses."""
    with patch("app.services.claude_service.anthropic.Anthropic") as mock:
        mock_instance = Mock()
        mock.return_value = mock_instance

        # Mock streaming response
        async def mock_stream(*args, **kwargs):
            class MockMessage:
                delta = Mock()
                delta.text = "Test AI response"
                type = "content_block_delta"

            yield MockMessage()

        mock_instance.messages.stream.return_value = mock_stream()
        yield mock_instance


@pytest.fixture(autouse=True)
def reset_services():
    """Reset service state before each test."""
    # This runs before each test
    yield
    # Cleanup after each test if needed


@pytest.fixture(autouse=True)
def _reset_node_room_mapping_cache():
    """Reset the module-level node_room_mapping cache to prevent test pollution.

    space_mqtt_listener caches the mapping at module level; if one test loads
    real data (e.g. node_001 -> FA2-1Q4-MR28), subsequent tests that patch
    get_node_room_mapping() still see the stale cache via the global variable.
    """
    import app.services.space_mqtt_listener as mqtt_mod

    mqtt_mod._node_room_mapping = None
    yield
    mqtt_mod._node_room_mapping = None


class _Mocker:
    """Lightweight pytest-mock compatible mocker fixture.

    Provides ``patch()`` and ``patch.object()`` that auto-cleanup after each test,
    mirroring the ``mocker`` fixture from the ``pytest-mock`` package.
    """

    def __init__(self):
        self._patchers = []

    def patch(self, target: str, *args, **kwargs):
        """Wrapper around ``unittest.mock.patch`` with automatic cleanup."""
        patcher = patch(target, *args, **kwargs)
        mock_obj = patcher.start()
        self._patchers.append(patcher)
        return mock_obj

    def patch_object(self, target, attribute: str, *args, **kwargs):
        """Wrapper around ``unittest.mock.patch.object`` with automatic cleanup."""
        patcher = patch.object(target, attribute, *args, **kwargs)
        mock_obj = patcher.start()
        self._patchers.append(patcher)
        return mock_obj

    def stopall(self):
        """Stop all active patchers."""
        for patcher in reversed(self._patchers):
            patcher.stop()
        self._patchers.clear()


# Make patch.object accessible as mocker.patch.object via a wrapper
class _PatchProxy:
    """Proxy so ``mocker.patch(...)`` and ``mocker.patch.object(...)`` both work."""

    def __init__(self, mocker: _Mocker):
        self._mocker = mocker

    def __call__(self, target: str, *args, **kwargs):
        return self._mocker.patch(target, *args, **kwargs)

    def object(self, target, attribute: str, *args, **kwargs):
        return self._mocker.patch_object(target, attribute, *args, **kwargs)


class MockerFixture:
    """Public mocker fixture exposing ``mocker.patch(...)`` and ``mocker.patch.object(...)``."""

    def __init__(self):
        self._mocker = _Mocker()
        self.patch = _PatchProxy(self._mocker)

    def stopall(self):
        self._mocker.stopall()


@pytest.fixture
def mocker():
    """Lightweight mocker fixture compatible with pytest-mock's API.

    Supports:
        mocker.patch("some.module.path", return_value=...)
        mocker.patch.object(obj, "attr", return_value=...)
    """
    m = MockerFixture()
    yield m
    m.stopall()


@pytest.fixture
def disable_background_scheduler():
    """Disable background scheduler during tests."""
    with patch("app.services.background_scheduler.scheduler_service.start") as mock_start:
        with patch("app.services.background_scheduler.scheduler_service.stop") as mock_stop:
            yield mock_start, mock_stop


# ============================================================================
# Universal Engine: JWT Token Fixtures (replaces TESTING bypass)
# ============================================================================


@pytest.fixture
def jwt_token_admin() -> str:
    """Generate a valid JWT token for ADMIN role."""
    from datetime import datetime, timedelta

    import jwt

    secret = os.environ.get("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")
    import uuid

    payload = {
        "sub": "admin-test-user",
        "email": "admin@test.sentinel.local",
        "role": "admin",
        "iss": "sentinel.bms",
        "aud": "sentinel.bms",
        "token_type": "access",
        "jti": str(uuid.uuid4()),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
def jwt_token_operator() -> str:
    """Generate a valid JWT token for OPERATOR role."""
    from datetime import datetime, timedelta

    import jwt

    secret = os.environ.get("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")
    import uuid

    payload = {
        "sub": "operator-test-user",
        "email": "operator@test.sentinel.local",
        "role": "operator",
        "iss": "sentinel.bms",
        "aud": "sentinel.bms",
        "token_type": "access",
        "jti": str(uuid.uuid4()),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
def jwt_token_auditor() -> str:
    """Generate a valid JWT token for AUDITOR role."""
    from datetime import datetime, timedelta

    import jwt

    secret = os.environ.get("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")
    import uuid

    payload = {
        "sub": "auditor-test-user",
        "email": "auditor@test.sentinel.local",
        "role": "auditor",
        "iss": "sentinel.bms",
        "aud": "sentinel.bms",
        "token_type": "access",
        "jti": str(uuid.uuid4()),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
def jwt_token_engineer() -> str:
    """Generate a valid JWT token for ENGINEER role."""
    from datetime import datetime, timedelta

    import jwt

    secret = os.environ.get("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")
    import uuid

    payload = {
        "sub": "engineer-test-user",
        "email": "engineer@test.sentinel.local",
        "role": "engineer",
        "iss": "sentinel.bms",
        "aud": "sentinel.bms",
        "token_type": "access",
        "jti": str(uuid.uuid4()),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
def auth_headers_admin(jwt_token_admin: str) -> dict:
    """HTTP headers with ADMIN JWT token."""
    return {"Authorization": f"Bearer {jwt_token_admin}"}


@pytest.fixture
def auth_headers_operator(jwt_token_operator: str) -> dict:
    """HTTP headers with OPERATOR JWT token."""
    return {"Authorization": f"Bearer {jwt_token_operator}"}


@pytest.fixture
def auth_headers_auditor(jwt_token_auditor: str) -> dict:
    """HTTP headers with AUDITOR JWT token."""
    return {"Authorization": f"Bearer {jwt_token_auditor}"}


@pytest.fixture
def auth_headers_engineer(jwt_token_engineer: str) -> dict:
    """HTTP headers with ENGINEER JWT token."""
    return {"Authorization": f"Bearer {jwt_token_engineer}"}


@pytest.fixture
def jwt_token_bot_agent() -> str:
    """Generate a valid JWT token for BOT_AGENT role (Phase 184)."""
    import uuid
    from datetime import datetime, timedelta

    import jwt

    secret = os.environ.get("JWT_SECRET_KEY", "test-only-jwt-secret-for-ci-at-least-32-chars")
    payload = {
        "sub": "bot-agent-test",
        "email": "bot@sentinel.local",
        "role": "bot_agent",
        "iss": "sentinel.bms",
        "aud": "sentinel.bms",
        "token_type": "access",
        "jti": str(uuid.uuid4()),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
def auth_headers(jwt_token_bot_agent: str) -> dict:
    """HTTP headers with BOT_AGENT JWT token (default for block booking tests)."""
    return {"Authorization": f"Bearer {jwt_token_bot_agent}"}
