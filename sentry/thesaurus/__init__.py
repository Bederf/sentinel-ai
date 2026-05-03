"""
Sentry Thesaurus — Facilities complaint classification service.

Exports:
    ThesaurusService  — main classifier
    classify_complaint — convenience function
    is_facilities      — bool check
    get_category_summary — for CLI
    TOTAL_PHRASES      — phrase count
    ComplaintCategory  — enum
"""

from complaint_thesaurus import (
    ComplaintCategory,
    TOTAL_PHRASES,
    get_category_summary,
)
from thesaurus_service import (
    MATCH_THRESHOLD,
    ThesaurusService,
    classify_complaint,
    get_thesaurus,
    is_facilities,
)

__all__ = [
    "MATCH_THRESHOLD",
    "TOTAL_PHRASES",
    "ComplaintCategory",
    "ThesaurusService",
    "classify_complaint",
    "get_category_summary",
    "get_thesaurus",
    "is_facilities",
]
