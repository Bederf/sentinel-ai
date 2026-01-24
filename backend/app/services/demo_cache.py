"""Demo cache service for pre-seeded AI responses.

This service provides instant, verified responses for key demo questions
when DEMO_MODE is enabled. Cached responses are streamed with SSE format
to match the live Claude API behavior.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DemoCache:
    """Cache for pre-seeded demo responses."""

    def __init__(self):
        """Initialize demo cache by loading responses from JSON file."""
        self.responses: list[dict] = []
        self._load_responses()

    def _load_responses(self) -> None:
        """Load demo responses from JSON file."""
        cache_file = Path(__file__).parent.parent / "data" / "demo_responses.json"

        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                    self.responses = data.get("responses", [])
                logger.info(f"Loaded {len(self.responses)} demo responses from cache")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse demo responses JSON: {e}")
                self.responses = []
            except Exception as e:
                logger.error(f"Failed to load demo responses: {e}")
                self.responses = []
        else:
            logger.warning(f"Demo responses file not found: {cache_file}")
            self.responses = []

    def get_cached_response(self, query: str) -> Optional[str]:
        """
        Check if query matches any demo patterns.

        Args:
            query: The user's query text

        Returns:
            Cached response text if pattern matches, None otherwise
        """
        if not self.responses:
            return None

        query_lower = query.lower()

        # Check each response pattern
        for response in self.responses:
            pattern = response.get("query_pattern", "").lower()
            if pattern and pattern in query_lower:
                logger.info(f"Demo cache hit for pattern: {pattern}")
                return response.get("response")

        return None

    def get_citations(self, query: str) -> list[str]:
        """
        Get citations for a cached response.

        Args:
            query: The user's query text

        Returns:
            List of citation strings if pattern matches, empty list otherwise
        """
        if not self.responses:
            return []

        query_lower = query.lower()

        for response in self.responses:
            pattern = response.get("query_pattern", "").lower()
            if pattern and pattern in query_lower:
                return response.get("citations", [])

        return []

    def is_demo_query(self, query: str) -> bool:
        """
        Check if a query matches any demo patterns.

        Args:
            query: The user's query text

        Returns:
            True if query matches a demo pattern, False otherwise
        """
        return self.get_cached_response(query) is not None

    def reload(self) -> None:
        """Reload demo responses from file (useful for development)."""
        self._load_responses()
