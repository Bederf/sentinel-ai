"""
Prompt Injection Guard (enhanced).

Extends the existing prompt_injection_guard.py with:
    - Numeric scoring (0.0-1.0) instead of binary safe/unsafe
    - Per-source thresholds (direct chat vs webhook vs tool argument)
    - Rewrite mode for borderline inputs (score between REWRITE and BLOCK)
    - Unicode normalization and homoglyph detection

Wraps the existing PromptInjectionDetector from
app.services.prompt_injection_guard for backward compatibility.
"""
