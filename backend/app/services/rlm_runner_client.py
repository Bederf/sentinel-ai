"""RLM Runner HTTP client for Sentinel backend.

Proxies requests to the RLM runner service (port 8010) for long-context
evidence analysis. Feature-gated behind RLM_RUNNER_ENABLED.

See: docs/02-architecture/SENTINEL-RLM-ARCHITECTURE-SPEC-v1.0.md
Phase: 113-03
"""

import asyncio
import logging
import time
from typing import Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)


class RLMRunnerError(Exception):
    """Base exception for RLM runner client errors."""


class RLMRunnerDisabledError(RLMRunnerError):
    """Raised when RLM runner is not enabled."""


class RLMRunnerUnavailableError(RLMRunnerError):
    """Raised when the runner service cannot be reached."""


class RLMRunnerClient:
    """Async HTTP client for the RLM runner service.

    All methods check RLM_RUNNER_ENABLED before proceeding.
    Uses httpx.AsyncClient with configurable timeout.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        enabled: Optional[bool] = None,
        timeout: Optional[int] = None,
    ):
        self.base_url = (base_url or settings.rlm_runner_url).rstrip("/")
        self.enabled = enabled if enabled is not None else settings.rlm_runner_enabled
        self.timeout = timeout or settings.rlm_timeout_seconds

    def _check_enabled(self) -> None:
        """Raise if the runner feature flag is off."""
        if not self.enabled:
            raise RLMRunnerDisabledError("RLM Runner is not enabled")

    async def submit_run(
        self,
        case_id: str,
        question: str,
        model: Optional[str] = None,
    ) -> dict:
        """Submit an analysis run to the runner.

        POST {runner}/run with RunRequest body.

        Args:
            case_id: Case folder identifier.
            question: Analysis question / prompt.
            model: Optional model override (defaults to runner config).

        Returns:
            Dict with run_id and status (e.g. {"run_id": "...", "status": "queued"}).

        Raises:
            RLMRunnerDisabledError: If RLM_RUNNER_ENABLED is False.
            RLMRunnerUnavailableError: If runner cannot be reached.
            httpx.HTTPStatusError: On 4xx/5xx from runner.
        """
        self._check_enabled()
        body: dict = {"case_id": case_id, "question": question}
        if model:
            body["model"] = model

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/run", json=body)
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError as exc:
            logger.error("RLM Runner unavailable at %s: %s", self.base_url, exc)
            raise RLMRunnerUnavailableError(f"RLM Runner unavailable at {self.base_url}") from exc

    async def get_result(self, run_id: str) -> Optional[dict]:
        """Fetch result for a completed run.

        GET {runner}/runs/{run_id}.

        Returns:
            Result dict, or None if 404 (run not found).
        """
        self._check_enabled()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/runs/{run_id}")
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError as exc:
            logger.error("RLM Runner unavailable at %s: %s", self.base_url, exc)
            raise RLMRunnerUnavailableError(f"RLM Runner unavailable at {self.base_url}") from exc

    async def get_trace(self, run_id: str) -> Optional[list]:
        """Fetch trace log for a run.

        GET {runner}/runs/{run_id}/trace.

        Returns:
            List of trace step dicts, or None if 404.
        """
        self._check_enabled()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/runs/{run_id}/trace")
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
        except httpx.ConnectError as exc:
            logger.error("RLM Runner unavailable at %s: %s", self.base_url, exc)
            raise RLMRunnerUnavailableError(f"RLM Runner unavailable at {self.base_url}") from exc

    async def poll_until_complete(
        self,
        run_id: str,
        interval: float = 5.0,
        timeout: Optional[float] = None,
    ) -> dict:
        """Poll runner until the run reaches a terminal state.

        Loops GET /runs/{run_id} every *interval* seconds until
        status is one of: complete, error, timeout — or the polling
        timeout is exceeded.

        Args:
            run_id: Run identifier returned from submit_run.
            interval: Seconds between polls.
            timeout: Max seconds to poll. Defaults to self.timeout.

        Returns:
            Final result dict.

        Raises:
            TimeoutError: If polling exceeds timeout.
        """
        self._check_enabled()
        effective_timeout = timeout or float(self.timeout)
        terminal_states = {"complete", "error", "timeout"}
        start = time.monotonic()

        while True:
            result = await self.get_result(run_id)
            if result and result.get("status") in terminal_states:
                return result

            elapsed = time.monotonic() - start
            if elapsed >= effective_timeout:
                raise TimeoutError(f"Polling run {run_id} timed out after {elapsed:.1f}s")

            await asyncio.sleep(interval)

    async def is_available(self) -> bool:
        """Check if the runner service is reachable.

        GET {runner}/health — returns True if 200.
        Does NOT check RLM_RUNNER_ENABLED (used for diagnostics).
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except Exception as exc:
            logger.warning("RLM Runner health check failed: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_client: Optional[RLMRunnerClient] = None


def get_rlm_runner_client() -> RLMRunnerClient:
    """Return the singleton RLMRunnerClient instance."""
    global _client
    if _client is None:
        _client = RLMRunnerClient()
    return _client
