"""
Concept MRI legacy document search — Site-002 ONLY.

PURPOSE
-------
Locate raw files in the Concept MRI DMS for site-002 (Fairlands).
Returns the UNC path (Actual Path) so the user can open the file
in their browser directly from the tech chat.

SCOPE — READ THIS BEFORE MODIFYING
------------------------------------
This service exists solely because site-002 data was loaded into
Concept MRI before controlled upload fields (F1-F8) were enforced.
The data is unstructured: free-text titles, inconsistent naming,
missing discipline tags. This service compensates for that in code.

Sites onboarded with F1-F8 enforced use the ADVANCED RAG PIPELINE —
a completely separate system. Do NOT merge these two pipelines.
This service must also never be confused with or connected to the
SYSTEM DOCUMENT RAG, which indexes SENTINEL's own internal knowledge.

The three pipelines are distinct and must remain so:
  1. System Document RAG    — SENTINEL internal docs (manuals, policies)
  2. Advanced RAG Pipeline  — properly onboarded client sites (pgvector)
  3. This file              — site-002 legacy TSV keyword search only

Remove this file when site-002 retrospective data capture (action A3)
is complete and all records are re-ingested via the advanced RAG pipeline.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INDEX_PATH = DATA_DIR / "concept_documents.json"
DEFAULT_TSV_INDEX_PATH = PROJECT_ROOT / "site_id Building Document Sub Class Docu.tsv"

MONTH_MAP: dict[str, int] = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

STOP_WORDS: set[str] = {
    "a", "an", "and", "at", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "the", "to", "with", "all",
}


class ConceptDocumentSearchUnavailable(RuntimeError):
    """Raised when the site-002 legacy index is unavailable."""


@dataclass(slots=True)
class ConceptDocument:
    site_id: str
    title: str
    document_ref: str
    subject: str
    discipline: str
    filename: str
    actual_path: str
    concept_document_id: str
    created_date: str
    expiry_date: str


class ConceptDocumentSearchService:
    """
    Locate raw Concept MRI documents for site-002 by keyword query.

    Matches against: Title, Document Ref, Subject, Discipline, Filename.
    Returns: title, filename, actual_path (UNC), concept_document_id.

    This is a keyword search against a flat TSV/JSON export.
    It is NOT a vector search and NOT connected to any RAG pipeline.
    """

    def __init__(self, index_path: Path | str = DEFAULT_INDEX_PATH) -> None:
        self.index_path = Path(index_path)
        self._documents: list[ConceptDocument] | None = None

    def search(
        self,
        *,
        site_id: str,
        query: str,
        top_k: int = 10,
    ) -> dict[str, Any]:
        documents = self._get_documents()
        normalised_site = _normalise_site_id(site_id)

        site_docs = [
            doc for doc in documents
            if _normalise_site_id(doc.site_id) == normalised_site
        ]

        if not site_docs:
            return _empty_result(query, site_id)

        tokens, query_month, query_year = _parse_query(query)

        if not tokens and query_month is None and query_year is None:
            return _empty_result(query, site_id)

        results = []
        for doc in site_docs:
            if _matches(doc, tokens, query_month, query_year):
                results.append(_to_result(doc))

        # Docs with a valid UNC path first, then alphabetical by title
        results.sort(key=lambda r: (0 if r["actual_path"] else 1, r["title"].lower()))

        return {
            "query": query,
            "site_id": site_id,
            "total": len(results),
            "results": results[:top_k],
        }

    def _get_documents(self) -> list[ConceptDocument]:
        if self._documents is None:
            self._documents = self._load_documents()
        return self._documents

    def _load_documents(self) -> list[ConceptDocument]:
        index_path = self.index_path
        if not index_path.exists():
            if DEFAULT_TSV_INDEX_PATH.exists():
                index_path = DEFAULT_TSV_INDEX_PATH
            else:
                raise ConceptDocumentSearchUnavailable(
                    f"Site-002 legacy index not found at {self.index_path}"
                )

        if index_path.suffix.lower() == ".tsv":
            return _load_from_tsv(index_path)

        with index_path.open(encoding="utf-8") as f:
            payload = json.load(f)

        rows = payload.get("documents", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ConceptDocumentSearchUnavailable("Site-002 legacy index is malformed")

        return [_row_to_doc(row) for row in rows if isinstance(row, dict)]


# ---------------------------------------------------------------------------
# Query parsing
# ---------------------------------------------------------------------------

def _parse_query(query: str) -> tuple[set[str], int | None, int | None]:
    """Extract keyword tokens, optional month, optional year from query."""
    lowered = query.lower()

    query_month = next(
        (v for k, v in MONTH_MAP.items() if re.search(rf"\b{k}\b", lowered)),
        None,
    )
    year_match = re.search(r"\b(20\d{2})\b", lowered)
    query_year = int(year_match.group(1)) if year_match else None

    # Strip month words and year from tokens
    cleaned = re.sub(r"\b(20\d{2})\b", "", lowered)
    for month_word in MONTH_MAP:
        cleaned = re.sub(rf"\b{month_word}\b", "", cleaned)

    tokens = {
        t for t in re.findall(r"[a-z0-9]+", cleaned)
        if t not in STOP_WORDS and len(t) > 1
    }
    return tokens, query_month, query_year


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _matches(
    doc: ConceptDocument,
    tokens: set[str],
    query_month: int | None,
    query_year: int | None,
) -> bool:
    searchable = " ".join([
        doc.title,
        doc.document_ref,
        doc.subject,
        doc.discipline,
        doc.filename,
    ]).lower()

    # At least one keyword token must appear
    if tokens and not any(t in searchable for t in tokens):
        return False

    # Month filter — month word must appear in title/subject/ref text
    if query_month is not None:
        doc_month = next(
            (v for k, v in MONTH_MAP.items() if re.search(rf"\b{k}\b", searchable)),
            None,
        )
        if doc_month != query_month:
            return False

    # Year filter
    if query_year is not None and str(query_year) not in searchable:
        return False

    return True


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _to_result(doc: ConceptDocument) -> dict[str, Any]:
    return {
        "title": doc.title.strip(),
        "filename": doc.filename.strip(),
        "actual_path": doc.actual_path.strip() if doc.actual_path else None,
        "concept_document_id": doc.concept_document_id,
        "discipline": doc.discipline.strip() if doc.discipline else None,
        "created_date": doc.created_date,
        "expiry_date": doc.expiry_date,
    }


def _empty_result(query: str, site_id: str) -> dict[str, Any]:
    return {"query": query, "site_id": site_id, "total": 0, "results": []}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _load_from_tsv(path: Path) -> list[ConceptDocument]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return [
            doc
            for row in reader
            if isinstance(row, dict)
            for doc in [_row_to_doc(row)]
            if doc.concept_document_id and doc.site_id
        ]


def _row_to_doc(row: dict[str, Any]) -> ConceptDocument:
    return ConceptDocument(
        site_id=_clean(row.get("site_id")),
        title=_clean(row.get("Title") or row.get("Document Ref.") or ""),
        document_ref=_clean(row.get("Document Ref.", "")),
        subject=_clean(row.get("Subject", "")),
        discipline=_clean(row.get("Document Sub Class", "")),
        filename=_clean(row.get("Filename", "")),
        actual_path=_clean(row.get("Actual Path", "")),
        concept_document_id=_clean(str(row.get("Concept Document Id", ""))),
        created_date=_clean(row.get("Created Date", "")),
        expiry_date=_clean(row.get("Expiry Date", "")),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(value: Any) -> str:
    s = str(value or "").strip()
    return "" if s.lower() in {"nan", "none", "null"} else s


def _normalise_site_id(value: str) -> str:
    """Normalise site-002, site-2, 2 → site-002."""
    raw = _clean(value).lower()
    if raw.startswith("site-"):
        num = raw[5:]
        return f"site-{num.zfill(3)}" if num.isdigit() else raw
    if raw.isdigit():
        return f"site-{raw.zfill(3)}"
    return raw


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_service: ConceptDocumentSearchService | None = None


def get_concept_document_search_service() -> ConceptDocumentSearchService:
    global _service
    if _service is None:
        _service = ConceptDocumentSearchService()
    return _service
