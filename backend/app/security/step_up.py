"""
Step-Up Authentication.

Requires re-authentication for sensitive operations:
    - Device control commands
    - Configuration changes
    - User management

Issues short-lived step-up tokens (STEP_UP_VALIDITY_SECONDS)
that are validated alongside the primary JWT.
"""
