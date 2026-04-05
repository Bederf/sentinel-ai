"""
MRI Evolution → SENTINEL P1-P4 priority translation.
Rev 4 SLA targets from SLA_Concept_20260319_Rev_4:
P1 Very Critical: Respond 1hr, Attend 4hr, Temp Fix 8hr, Resolve TBD
P2 Critical:      Respond 2hr, Attend 6hr, Temp Fix 12hr, Resolve 3 work days
P3 Non-Critical:  Respond 3hr, Attend 8hr, Temp Fix 16hr, Resolve 6 work days
P4 Routine:       Respond 4hr, Attend 24hr, Temp Fix 48hr, Resolve 15 work days
"""

from __future__ import annotations

PRIORITY_MAP = {
    "Very Critical": {"tier": "P1", "respond_hours": 1,  "attend_hours": 4,  "temp_fix_hours": 8,  "resolve_work_days": None},
    "URGENT":        {"tier": "P1", "respond_hours": 1,  "attend_hours": 4,  "temp_fix_hours": 8,  "resolve_work_days": None},
    "High":          {"tier": "P1", "respond_hours": 1,  "attend_hours": 4,  "temp_fix_hours": 8,  "resolve_work_days": None},
    "Critical":      {"tier": "P2", "respond_hours": 2,  "attend_hours": 6,  "temp_fix_hours": 12, "resolve_work_days": 3},
    "Non Critical":  {"tier": "P3", "respond_hours": 3,  "attend_hours": 8,  "temp_fix_hours": 16, "resolve_work_days": 6},
    "Low":           {"tier": "P3", "respond_hours": 3,  "attend_hours": 8,  "temp_fix_hours": 16, "resolve_work_days": 6},
    "Medium":        {"tier": "P3", "respond_hours": 3,  "attend_hours": 8,  "temp_fix_hours": 16, "resolve_work_days": 6},
    "Routine":       {"tier": "P4", "respond_hours": 4,  "attend_hours": 24, "temp_fix_hours": 48, "resolve_work_days": 15},
    "Planned":       {"tier": "P4", "respond_hours": 4,  "attend_hours": 24, "temp_fix_hours": 48, "resolve_work_days": 15},
}

# Fallback for unknown priorities
_DEFAULT = {"tier": "P4", "respond_hours": 4, "attend_hours": 24, "temp_fix_hours": 48, "resolve_work_days": 15}


def normalise_priority(raw: str | None) -> dict:
    """Translate MRI raw priority string to SENTINEL P1-P4 tier + SLA hours."""
    if not raw:
        return _DEFAULT
    stripped = raw.strip()
    return PRIORITY_MAP.get(stripped, _DEFAULT)
