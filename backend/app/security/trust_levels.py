"""
Trust Level Management.

Assigns trust levels to input sources that determine which
security checks are applied and how strictly:

    VERIFIED    - Authenticated user with step-up auth
    STANDARD    - Authenticated user (JWT/API key)
    UNTRUSTED   - Unauthenticated or demo-mode user
    QUARANTINED - Input that failed a security check

Trust level flows downstream through the security pipeline
and influences prompt guard thresholds, tool access, and
output filtering strictness.
"""
