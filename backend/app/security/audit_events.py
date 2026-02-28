"""
Security Audit Events.

Structured event logging for security-relevant actions:
    - Prompt injection attempts (blocked and borderline)
    - Secret leakage detections
    - Step-up auth challenges
    - Rate limit violations
    - Document scan results
    - Trust level transitions

Events are emitted to the existing audit_log.json and
optionally to Supabase for long-term retention.
"""
