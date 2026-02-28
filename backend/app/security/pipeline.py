"""
Security Pipeline Orchestrator.

Coordinates the full security pipeline for AI chat requests:
    1. Input validation (prompt guard, trust level, size limits)
    2. Tool policy enforcement (per-tool auth, argument scanning)
    3. Output filtering (secrets, PII, citation verification)
    4. Audit event emission

Future implementation will replace the current ad-hoc security checks
scattered across chat.py, claude_service.py, and schema_validator.py
with a single, composable pipeline.
"""
