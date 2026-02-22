"""Simple logger for chat queries that may contain feature requests.

Logs all doc-mode queries to a JSON file so they can be reviewed
and added to TODO.md when they represent unimplemented features.
"""

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

FEATURE_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "chat_queries.json"
)


def log_chat_query(query: str) -> None:
    """Append a chat query to the log file."""
    try:
        entries = []
        if os.path.exists(FEATURE_LOG_PATH):
            with open(FEATURE_LOG_PATH, "r") as f:
                entries = json.load(f)

        entries.append(
            {
                "query": query,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Keep last 500 entries
        entries = entries[-500:]

        with open(FEATURE_LOG_PATH, "w") as f:
            json.dump(entries, f, indent=2)

    except Exception as e:
        logger.warning(f"Failed to log chat query: {e}")
