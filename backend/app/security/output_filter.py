"""
Output Filter.

Scans AI-generated output before it reaches the client:
    - Secret/credential detection (extends schema_validator.scan_output_for_secrets)
    - PII redaction (integrates pii_guard.py)
    - Citation verification (ensures [Source: ...] references are valid)
    - Tool result size enforcement

Applied both to batch responses and streaming (via sse_buffer.py).
"""
