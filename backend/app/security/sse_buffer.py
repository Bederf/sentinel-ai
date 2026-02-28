"""
Secure SSE Streaming Buffer.

Buffers Server-Sent Event tokens so the output filter pipeline can scan
complete sentences before flushing to the client. Uses a sliding window
of the last SSE_SLIDING_WINDOW_SIZE bytes to catch patterns that span
chunk boundaries.

Features:
    - Configurable flush threshold (SSE_BUFFER_FLUSH_SIZE)
    - Sliding window for cross-chunk pattern detection
    - Guaranteed flush on stream end (finalize)
    - Kills entire response on system prompt leak detection
"""

import logging

from app.security.constants import SSE_BUFFER_FLUSH_SIZE, SSE_SLIDING_WINDOW_SIZE
from app.security.output_filter import run_output_filter_pipeline

logger = logging.getLogger(__name__)

# Sentence boundary markers that are good flush points
_SENTENCE_BOUNDARIES = (". ", ".\n", "? ", "!\n", "! ", "?\n", "\n\n")


class SecureSSEBuffer:
    """Buffer SSE tokens and run the output filter before flushing.

    Usage::

        buffer = SecureSSEBuffer(user_role="operator")
        async for token in llm_stream:
            safe = buffer.add_token(token)
            if safe is not None:
                yield sse_format(safe)
        final = buffer.finalize()
        if final:
            yield sse_format(final)

    Args:
        user_role: The role of the current user (passed to PII stage).
    """

    def __init__(self, user_role: str | None = None) -> None:
        self._user_role = user_role
        self._buffer: str = ""
        self._sliding_window: str = ""
        self._killed: bool = False

    @property
    def killed(self) -> bool:
        """True if the response was killed by the filter (system prompt leak)."""
        return self._killed

    def add_token(self, token: str) -> str | None:
        """Add a token to the buffer.

        Returns:
            Filtered text to flush, or None if still buffering.
            If the response was killed, returns the kill message once.
        """
        if self._killed:
            return None

        self._buffer += token

        # Check if we should flush: sentence boundary or size threshold
        if self._should_flush():
            return self._flush()

        return None

    def finalize(self) -> str | None:
        """Flush any remaining buffer content at end of stream.

        Returns:
            Remaining filtered text, or None if empty/killed.
        """
        if self._killed or not self._buffer:
            return None

        return self._flush()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _should_flush(self) -> bool:
        """Determine if the buffer should be flushed now."""
        # Always flush if buffer exceeds size threshold
        if len(self._buffer.encode("utf-8")) >= SSE_BUFFER_FLUSH_SIZE:
            return True

        # Flush at sentence boundaries for natural reading experience
        for boundary in _SENTENCE_BOUNDARIES:
            if self._buffer.endswith(boundary):
                return True

        return False

    def _flush(self) -> str | None:
        """Run the filter on sliding_window + buffer, return safe text."""
        # Combine sliding window with current buffer for cross-chunk detection
        combined = self._sliding_window + self._buffer

        result = run_output_filter_pipeline(combined, user_role=self._user_role)

        if result.kill_response:
            self._killed = True
            self._buffer = ""
            logger.warning("SSE_BUFFER: Response killed by output filter")
            return "[Response blocked by security filter]"

        # The filtered combined text includes the already-flushed window portion.
        # We only want to emit the NEW text (the buffer portion, post-filter).
        # Strategy: the sliding window was already filtered and emitted previously,
        # so we filter the buffer alone but check combined for cross-chunk patterns.
        #
        # Since the filter already ran on `combined`, and the window portion was
        # already emitted, we need to extract just the new portion.
        # However, redactions may have changed the window text. Instead, filter
        # the buffer alone for the actual output, and use the combined check
        # only for kill detection (already done above).
        buffer_result = run_output_filter_pipeline(self._buffer, user_role=self._user_role)

        if buffer_result.kill_response:
            self._killed = True
            self._buffer = ""
            return "[Response blocked by security filter]"

        safe_text = buffer_result.text

        # Update sliding window: append the raw buffer, trim to window size
        self._sliding_window += self._buffer
        if len(self._sliding_window) > SSE_SLIDING_WINDOW_SIZE:
            self._sliding_window = self._sliding_window[-SSE_SLIDING_WINDOW_SIZE:]

        self._buffer = ""
        return safe_text
