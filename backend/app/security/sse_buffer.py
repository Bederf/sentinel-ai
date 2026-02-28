"""
SSE Streaming Buffer.

Buffers Server-Sent Event chunks so output_filter can scan
complete tokens before flushing to the client.

Features:
    - Configurable flush threshold (SSE_BUFFER_FLUSH_SIZE)
    - Sliding window for cross-chunk pattern detection
    - Guaranteed flush on stream end
    - Zero-copy passthrough when filtering is disabled
"""
