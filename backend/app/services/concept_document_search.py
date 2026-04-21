"""Site-scoped Concept document search service."""

from __future__ import annotations

import csv
import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INDEX_PATH = DATA_DIR / "concept_documents.json"
DEFAULT_TSV_INDEX_PATH = PROJECT_ROOT / "site_id Building Document Sub Class Docu.tsv"
CONCEPT_BASE_URL = "https://remsconcept.fnb.co.za"
CONCEPT_DOCUMENT_ITEMS_REFERRER_PATH = "/Evolution/!System/Documents/ConceptDocument/ViewConceptDocumentItems.aspx"
CONCEPT_DOCUMENT_ITEM_URL_TEMPLATE = (
    CONCEPT_BASE_URL
    + "/Evolution/!System/Documents/ConceptDocument/ViewConceptDocumentItem.aspx"
    + "?__referrer={referrer}&id={concept_document_id}&PrimaryEntity=&PrimaryKeyId=-1"
)
CONCEPT_DOCUMENT_RAW_URL_TEMPLATE = (
    CONCEPT_BASE_URL
    + "/Evolution/!System/Documents/ViewDocument.aspx"
    + "?__referrer={referrer}&docId={concept_document_id}"
)

STOP_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "last",
    "latest",
    "me",
    "of",
    "on",
    "or",
    "recent",
    "the",
    "to",
    "with",
}

# Query-side typo corrections for high-frequency technician misspellings.
# Applied to user input only (not indexed document text).
QUERY_TYPO_CORRECTIONS = {
    "generagor": "generator",
    "genrator": "generator",
    "genreator": "generator",
    "inspecion": "inspection",
    "sertificate": "certificate",
}

DOCUMENT_TYPE_SYNONYMS = {
    "service sheet": {"service", "sheet", "service sheet", "service sheets"},
    "job card": {"job", "card", "job card", "job cards"},
    "inspection sheet": {
        "inspection",
        "sheet",
        "inspection sheet",
        "inspection sheets",
        "inspection record",
        "inspection records",
    },
    "certificate": {
        "certificate",
        "cert",
        "certificates",
        "lift cert",
        "annual inspection cert",
        "elevator certificate",
    },
    "report": {"report", "reports", "maintenance report", "maintenance reports"},
    "maintenance worksheet": {"maintenance worksheet", "maintenance worksheets", "worksheet"},
    "commissioning sheet": {"commissioning", "commissioning sheet", "commissioning sheets"},
    "statutory inspection": {"statutory inspection", "compliance inspection"},
    "quote": {"quote", "quotation", "quotations"},
    "invoice": {"invoice", "invoices"},
}

QUERY_DOCUMENT_TYPE_SYNONYMS = {
    "service sheet": {
        "service sheet",
        "service sheets",
        "maintenance sheet",
        "maintenance sheets",
    },
    "job card": {"job card", "job cards"},
    "inspection sheet": {
        "inspection sheet",
        "inspection sheets",
        "inspection record",
        "inspection records",
        "inspection",
        "inspections",
    },
    "certificate": {
        "certificate",
        "cert",
        "certificates",
        "lift cert",
        "annual inspection cert",
        "elevator certificate",
    },
    "report": {"report", "reports", "maintenance report", "maintenance reports"},
    "maintenance worksheet": {"maintenance worksheet", "maintenance worksheets", "worksheet"},
    "commissioning sheet": {"commissioning sheet", "commissioning sheets"},
    "statutory inspection": {"statutory inspection", "compliance inspection"},
    "quote": {"quote", "quotation", "quotations"},
    "invoice": {"invoice", "invoices"},
}

EQUIPMENT_SYNONYMS = {
    "elevator": {"elevator", "lift", "vertical transport", "lifts"},
    "generator": {"generator", "genset", "gen"},
    "fire pump": {"fire pump", "firepump", "fire-pump"},
    "chiller": {"chiller", "chillers", "cooling plant"},
    "pump": {"pump", "pumps"},
}

DISCIPLINE_SYNONYMS = {
    "vertical transport": {"vertical transport", "elevator", "lift"},
    "electrical": {"electrical", "generator", "ups"},
    "mechanical": {"mechanical", "hvac", "chiller", "pump"},
    "fire": {"fire", "fire pump", "sprinkler"},
}

DOCUMENT_TYPE_CLASSIFIER = [
    (
        "service_sheet",
        {"service sheet", "service sheets", "maintenance service", "maintenance sheets", "maintenance report"},
    ),
    (
        "inspection_sheet",
        {
            "inspection",
            "inspections",
            "inspection sheet",
            "inspection sheets",
            "weekly inspection",
            "quarterly inspection",
        },
    ),
    (
        "certificate",
        {"certificate", "cert", "certificates", "annual inspection cert", "lift cert", "elevator certificate"},
    ),
    ("reading", {"reading", "readings", "meter reading", "diesel reading"}),
    ("checklist", {"check list", "checklist", "check-lists"}),
    ("job_card", {"job card", "job cards"}),
    ("report", {"report", "reports"}),
    ("unknown", set()),
]

EQUIPMENT_CLASSIFIER = [
    ("generator", {"generator", "generators", "genset", "gen", "gen set"}),
    ("lift", {"lift", "lifts", "elevator", "elevators", "vertical transport"}),
    ("hvac", {"hvac", "air conditioning", "air-con", "kitchen extraction", "extraction"}),
    ("plumbing", {"plumbing", "pipe", "pipes"}),
    ("fire_system", {"fire", "suppression", "foam", "fire pump"}),
    ("pressure_vessel", {"pressure vessel", "pressure vessels"}),
    ("electrical", {"electrical", "switchgear", "power", "distribution"}),
    ("structural", {"structural", "roof", "beam", "column"}),
    ("water_meter", {"meter reading", "water meter", "meter"}),
    ("oil_spill_kit", {"oil spill kit"}),
    ("pv", {"pv", "solar", "photovoltaic"}),
    ("unknown", set()),
]

DISCIPLINE_CLASSIFIER = [
    ("electrical", {"electrical", "generator", "switchgear", "power"}),
    ("plumbing", {"plumbing", "pipe", "drain"}),
    ("fire", {"fire", "suppression", "sprinkler"}),
    ("structural", {"structural", "building", "roof"}),
    ("hvac", {"hvac", "air conditioning", "chiller"}),
    ("operational", {"operations", "operational", "service"}),
    ("unknown", set()),
]

RECENCY_TERMS = {"latest", "last", "current", "recent", "newest"}
ANNUAL_TERMS = {"annual", "yearly"}
MONTH_WORDS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
FREQUENCY_KEYWORDS = {
    "daily": "daily",
    "weekly": "weekly",
    "monthly": "monthly",
    "quarterly": "quarterly",
    "annual": "annual",
    "yearly": "annual",
}

INTENT_DOCUMENT_TYPE_KEYWORDS = {
    "service_sheet": {"service sheet", "service sheets", "service"},
    "certificate": {"certificate", "cert", "certificates", "inspection certificate", "annual inspection certificate"},
    "inspection_sheet": {"inspection sheet", "inspection sheets", "inspection", "inspection report", "inspections"},
    "reading": {"reading", "readings"},
    "checklist": {"checklist", "check list"},
}

INTENT_DISCIPLINE_KEYWORDS = {
    "plumbing": {"plumbing", "plumber", "pipes", "pipe"},
    "electrical": {"electrical", "electric", "electrics"},
    "fire": {"fire", "fire system", "fire pump", "sprinkler"},
    "structural": {"structural", "building", "structure"},
    "hvac": {"hvac", "heating", "cooling", "air conditioning", "air-con"},
}

INTENT_EQUIPMENT_KEYWORDS = {
    "generator": {"generator", "genset", "gen", "generator room"},
    "pressure_vessel": {"pressure vessel", "pressure vessels"},
    "pv": {"pv", "solar", "photovoltaic"},
    "diesel": {"diesel", "diesel engine", "diesel generator"},
    "lift": {"lift", "elevator"},
}


class ConceptDocumentSearchUnavailable(RuntimeError):
    """Raised when the Concept document index is unavailable."""


@dataclass(slots=True)
class QueryHints:
    raw_query: str
    tokens: set[str]
    years: set[int]
    document_types: set[str]
    equipment_categories: set[str]
    disciplines: set[str]
    prefers_recent: bool
    annual_intent: bool


def parse_query_intent(query: str) -> dict[str, Any]:
    lowered = _normalise_query_typos(query.lower())
    tokens = _token_list(lowered)
    token_set = set(tokens)
    year = _extract_year_from_text(lowered)
    month = _extract_month_from_text(lowered)
    frequency = _extract_frequency(lowered)
    document_type, doc_type_alias = _detect_intent_value(lowered, token_set, INTENT_DOCUMENT_TYPE_KEYWORDS)
    equipment, equipment_alias = _detect_intent_value(lowered, token_set, INTENT_EQUIPMENT_KEYWORDS)
    discipline, discipline_alias = _detect_intent_value(lowered, token_set, INTENT_DISCIPLINE_KEYWORDS)
    recognized_tokens: set[str] = set()
    for alias in (doc_type_alias, equipment_alias, discipline_alias):
        if alias:
            recognized_tokens.update(_token_list(alias))
    if frequency:
        recognized_tokens.add(frequency)
    if month:
        month_name = next((name for name, number in MONTH_WORDS.items() if number == month), None)
        if month_name:
            recognized_tokens.update(_token_list(month_name))
    if year:
        recognized_tokens.add(str(year))
    keywords = [token for token in tokens if token not in recognized_tokens]
    return {
        "year": year,
        "month": month,
        "equipment": equipment,
        "discipline": discipline,
        "document_type": document_type,
        "frequency": frequency,
        "keywords": keywords,
    }


def _normalise_query_typos(text: str) -> str:
    normalized = text
    for typo, corrected in QUERY_TYPO_CORRECTIONS.items():
        normalized = re.sub(rf"\b{re.escape(typo)}\b", corrected, normalized)
    return normalized


def _extract_building(text: str) -> str | None:
    if "fairlands" in text:
        return "Fairlands"
    return None


def _extract_site(text: str) -> str | None:
    return _extract_building(text)


def _extract_year_from_text(text: str) -> int | None:
    match = re.search(r"\b(20\d{2})\b", text)
    return int(match.group(1)) if match else None


def _extract_month_from_text(text: str) -> int | None:
    for name, num in MONTH_WORDS.items():
        if name in text:
            return num
    return None


def _extract_frequency(text: str) -> str | None:
    for keyword, freq in FREQUENCY_KEYWORDS.items():
        if keyword in text:
            return freq
    return None


def _detect_intent_value(text: str, token_set: set[str], mapping: dict[str, set[str]]) -> tuple[str | None, str | None]:
    for canonical, aliases in mapping.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if _alias_matches_text(alias, text, token_set):
                return canonical, alias
    return None, None


@dataclass(slots=True)
class IndexedConceptDocument:
    document_id: str
    concept_document_id: str
    source_system: str
    file_name: str
    file_extension: str
    file_path: str
    open_url: str
    download_url: str | None
    upload_date: str | None
    checksum: str | None
    site_id: str
    site_name: str | None
    building_id: str | None
    building_name: str | None
    floor: str | None
    discipline: str | None
    equipment_category: str | None
    equipment_id: str | None
    equipment_name: str | None
    document_type: str | None
    subtype: str | None
    document_date: str | None
    issue_date: str | None
    expiry_date: str | None
    vendor: str | None
    tags: list[str]
    extracted_text: str
    cleaned_text: str
    ocr_confidence: float | None
    filename_tokens: list[str]
    path_tokens: list[str]
    metadata_text: str
    indexing_status: str | None
    extraction_status: str | None
    classification_confidence: float | None
    last_indexed_at: str | None
    title: str
    path: str
    snippet: str | None
    normalized_year: int | None
    normalized_document_type: str | None
    normalized_equipment: str | None
    normalized_discipline: str | None
    concept_url: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> IndexedConceptDocument:
        file_name = str(payload.get("file_name") or payload.get("title") or "")
        title = str(payload.get("title") or file_name or payload.get("concept_document_id") or "Untitled document")
        file_path = str(payload.get("file_path") or payload.get("path") or "")
        path = str(payload.get("path") or file_path)
        document_type = _normalise_document_type(payload.get("document_type"))
        equipment_category = _normalise_equipment_category(payload.get("equipment_category"))
        tags = [str(tag) for tag in payload.get("tags", []) if str(tag).strip()]
        filename_tokens = payload.get("filename_tokens") or _token_list(file_name)
        path_tokens = payload.get("path_tokens") or _token_list(file_path)

        metadata_bits = [
            payload.get("building_name"),
            payload.get("site_name"),
            payload.get("discipline"),
            equipment_category,
            payload.get("equipment_name"),
            document_type,
            payload.get("subtype"),
            " ".join(tags),
        ]
        metadata_text = str(payload.get("metadata_text") or " ".join(bit for bit in metadata_bits if bit))
        searchable_text = str(payload.get("searchable_text") or metadata_text or title)

        concept_document_id = str(payload.get("concept_document_id") or payload.get("document_id") or "")
        open_url = str(payload.get("open_url") or "") or (
            _build_concept_item_url(concept_document_id) if concept_document_id else ""
        )
        download_url = payload.get("download_url") or (
            _build_concept_raw_document_url(concept_document_id) if concept_document_id else None
        )
        return cls(
            document_id=str(payload.get("document_id") or payload.get("id") or ""),
            concept_document_id=concept_document_id,
            source_system=str(payload.get("source_system") or "concept"),
            file_name=file_name,
            file_extension=str(payload.get("file_extension") or Path(file_name).suffix.lstrip(".")),
            file_path=file_path,
            open_url=open_url,
            download_url=download_url,
            upload_date=payload.get("upload_date"),
            checksum=payload.get("checksum"),
            site_id=str(payload.get("site_id") or payload.get("building_id") or ""),
            site_name=payload.get("site_name"),
            building_id=payload.get("building_id"),
            building_name=payload.get("building_name") or payload.get("site_name"),
            floor=payload.get("floor"),
            discipline=_normalise_discipline(payload.get("discipline")),
            equipment_category=equipment_category,
            equipment_id=payload.get("equipment_id"),
            equipment_name=payload.get("equipment_name"),
            document_type=document_type,
            subtype=payload.get("subtype"),
            document_date=payload.get("document_date"),
            issue_date=payload.get("issue_date"),
            expiry_date=payload.get("expiry_date"),
            vendor=payload.get("vendor"),
            tags=tags,
            extracted_text=str(payload.get("extracted_text") or ""),
            cleaned_text=str(payload.get("cleaned_text") or payload.get("extracted_text") or ""),
            ocr_confidence=_coerce_float(payload.get("ocr_confidence")),
            filename_tokens=[str(token) for token in filename_tokens],
            path_tokens=[str(token) for token in path_tokens],
            metadata_text=metadata_text,
            indexing_status=payload.get("indexing_status"),
            extraction_status=payload.get("extraction_status"),
            classification_confidence=_coerce_float(payload.get("classification_confidence")),
            last_indexed_at=payload.get("last_indexed_at"),
            title=title,
            path=path,
            snippet=payload.get("snippet"),
            normalized_year=_coerce_int(payload.get("normalized_year"))
            or _derive_normalized_year(
                payload.get("document_date"), payload.get("issue_date"), payload.get("upload_date")
            ),
            normalized_document_type=payload.get("normalized_document_type")
            or _infer_normalized_document_type(searchable_text),
            normalized_equipment=payload.get("normalized_equipment") or _infer_normalized_equipment(searchable_text),
            normalized_discipline=payload.get("normalized_discipline")
            or _infer_normalized_discipline(
                " ".join(
                    filter(None, [payload.get("document_sub_class"), payload.get("path"), payload.get("category")])
                )
            ),
            concept_url=str(payload.get("concept_url") or open_url),
        )


class ConceptDocumentSearchService:
    """Search Concept-indexed document metadata and OCR text for a single site."""

    def __init__(self, index_path: Path | str = DEFAULT_INDEX_PATH) -> None:
        self.index_path = Path(index_path)

    def search(
        self,
        *,
        site_id: str,
        query: str,
        top_k: int = 10,
        building_id: str | None = None,
    ) -> dict[str, Any]:
        intent = parse_query_intent(query)
        hints = self._parse_query(query)
        documents = self._load_documents()

        scoped_documents = [
            document
            for document in documents
            if document.site_id == site_id
            and (not building_id or not document.building_id or document.building_id == building_id)
        ]

        if not scoped_documents:
            return {
                "mode": "concept_document_search",
                "query": query,
                "building_id": building_id or site_id,
                "results": [],
                "total_matched": 0,
                "total_results": 0,
                "weak_results": False,
            }

        filtered_documents = self._filter_documents(scoped_documents, intent)
        if not filtered_documents:
            filtered_documents = scoped_documents

        freshed_pool = [
            _parse_best_date(document.document_date, document.issue_date, document.upload_date)
            for document in filtered_documents
        ]
        dated_pool = [value for value in freshed_pool if value is not None]
        newest = max(dated_pool) if dated_pool else None
        oldest = min(dated_pool) if dated_pool else None

        ranked_results: list[dict[str, Any]] = []
        for document in filtered_documents:
            candidate = self._score_document(
                document=document,
                hints=hints,
                intent=intent,
                newest_date=newest,
                oldest_date=oldest,
                query=query,
            )
            if candidate is not None:
                ranked_results.append(candidate)

        ranked_results.sort(key=lambda item: item["rank_key"], reverse=True)
        total_matched = len(ranked_results)
        trimmed = ranked_results[:top_k]
        trimmed = self._rerank_with_ai(query, trimmed)

        weak_results = not trimmed or trimmed[0]["score"] < 0.45

        return {
            "mode": "concept_document_search",
            "query": query,
            "building_id": building_id or site_id,
            "results": [item["payload"] for item in trimmed],
            "total_results": total_matched,
            "weak_results": weak_results,
        }

    def _load_documents(self) -> list[IndexedConceptDocument]:
        index_path = self.index_path
        if not index_path.exists():
            if index_path == DEFAULT_INDEX_PATH and DEFAULT_TSV_INDEX_PATH.exists():
                index_path = DEFAULT_TSV_INDEX_PATH
            else:
                raise ConceptDocumentSearchUnavailable(f"Concept document index not found at {self.index_path}")

        if index_path.suffix.lower() == ".tsv":
            return self._load_documents_from_tsv(index_path)

        with index_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)

        rows = payload.get("documents", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ConceptDocumentSearchUnavailable("Concept document index is malformed")

        return self._load_documents_from_rows(rows)

    def _load_documents_from_tsv(self, index_path: Path) -> list[IndexedConceptDocument]:
        with index_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            rows = [_normalise_tsv_row(row) for row in reader if isinstance(row, dict)]

        return self._load_documents_from_rows(rows)

    def _load_documents_from_rows(self, rows: Iterable[dict[str, Any] | None]) -> list[IndexedConceptDocument]:
        documents: list[IndexedConceptDocument] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            document = IndexedConceptDocument.from_dict(row)
            if not document.document_id or not document.open_url or not document.site_id:
                continue
            documents.append(document)
        return documents

    def _parse_query(self, query: str) -> QueryHints:
        lowered = _normalise_query_typos(query.lower())
        tokens = set(_token_list(lowered))
        years = {int(year) for year in re.findall(r"\b(20\d{2})\b", lowered)}
        document_types = {
            doc_type
            for doc_type, aliases in QUERY_DOCUMENT_TYPE_SYNONYMS.items()
            if _matches_any_alias(lowered, tokens, aliases)
        }
        equipment_categories = {
            category for category, aliases in EQUIPMENT_SYNONYMS.items() if _matches_any_alias(lowered, tokens, aliases)
        }
        disciplines = {
            discipline
            for discipline, aliases in DISCIPLINE_SYNONYMS.items()
            if _matches_any_alias(lowered, tokens, aliases)
        }
        prefers_recent = any(term in tokens or term in lowered for term in RECENCY_TERMS)
        annual_intent = any(term in tokens or term in lowered for term in ANNUAL_TERMS)

        return QueryHints(
            raw_query=query,
            tokens=tokens,
            years=years,
            document_types=document_types,
            equipment_categories=equipment_categories,
            disciplines=disciplines,
            prefers_recent=prefers_recent,
            annual_intent=annual_intent,
        )

    def _filter_documents(
        self, documents: Iterable[IndexedConceptDocument], intent: dict[str, Any]
    ) -> list[IndexedConceptDocument]:
        candidates = list(documents)
        if intent.get("year"):
            year_matches = [doc for doc in candidates if _document_matches_year(doc, intent["year"])]
            if year_matches:
                candidates = year_matches
        if intent.get("month"):
            month_matches = [doc for doc in candidates if _document_matches_month(doc, intent["month"])]
            if month_matches:
                candidates = month_matches
        if intent.get("discipline"):
            discipline_matches = [doc for doc in candidates if _matches_discipline(doc, intent["discipline"])]
            if discipline_matches:
                candidates = discipline_matches
        if intent.get("document_type"):
            doc_type_matches = [doc for doc in candidates if _matches_document_type(doc, intent["document_type"])]
            if not doc_type_matches and intent["document_type"] == "service_sheet":
                doc_type_matches = [doc for doc in candidates if _matches_document_type(doc, "inspection_sheet")]
            elif not doc_type_matches and intent["document_type"] == "inspection_sheet":
                doc_type_matches = [doc for doc in candidates if _matches_document_type(doc, "service_sheet")]
            if doc_type_matches:
                candidates = doc_type_matches
        if intent.get("equipment"):
            equipment_matches = [doc for doc in candidates if _matches_equipment(doc, intent["equipment"])]
            if equipment_matches:
                candidates = equipment_matches
        return candidates

    def _rerank_with_ai(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not candidates or not _openai_available():
            return candidates

        payload_candidates = []
        for item in candidates[:10]:
            doc = item["payload"]
            payload_candidates.append(
                {
                    "id": doc["document_id"],
                    "title": doc["title"],
                    "type": doc.get("document_type") or "unknown",
                    "equipment": doc.get("equipment_category") or doc.get("equipment_name") or "unknown",
                    "date": doc.get("document_date"),
                    "path": doc.get("path"),
                }
            )

        prompt = (
            "You are a document search re-ranker for SENTINEL. "
            "Given the user's query and the top candidate documents (id, title, type, "
            "equipment, date, path), return a JSON array of document IDs sorted by relevance "
            "from most relevant to least. Do not add any explanation. "
            f"Query: {query.strip()!r}\nCandidates: {json.dumps(payload_candidates)}"
        )
        body = _post_openai_chat([{"role": "user", "content": prompt}], settings.openai_model_heavy)
        if not body:
            return candidates

        text = _extract_message_content(body)
        ordered_ids = _extract_json_array(text)
        if not ordered_ids:
            return candidates

        id_to_item = {item["payload"]["document_id"]: item for item in candidates}
        reordered: list[dict[str, Any]] = []
        for doc_id in ordered_ids:
            if doc_id in id_to_item:
                reordered.append(id_to_item.pop(doc_id))
        reordered.extend(id_to_item.values())
        return reordered

    def _score_document(
        self,
        *,
        document: IndexedConceptDocument,
        hints: QueryHints,
        intent: dict[str, Any],
        newest_date: date | None,
        oldest_date: date | None,
        query: str,
    ) -> dict[str, Any] | None:
        document_date = _parse_best_date(document.document_date, document.issue_date, document.upload_date)
        title_tokens = set(_token_list(f"{document.title} {document.file_name}"))
        path_tokens = set(_token_list(f"{document.path} {document.file_path}"))
        content_tokens = set(
            _token_list(
                " ".join(
                    [
                        document.metadata_text,
                        document.cleaned_text[:2000],
                        document.extracted_text[:2000],
                        " ".join(document.tags),
                    ]
                )
            )
        )
        combined_tokens = title_tokens | path_tokens | content_tokens
        lexical_title = _overlap_score(hints.tokens, title_tokens)
        lexical_path = _overlap_score(hints.tokens, path_tokens)
        lexical_content = _overlap_score(hints.tokens, content_tokens)
        lexical_score = min(1.0, (lexical_title * 0.45) + (lexical_path * 0.2) + (lexical_content * 0.35))

        normalized_doc_type = document.normalized_document_type or _normalise_document_type(document.document_type)
        normalized_equipment = document.normalized_equipment or _normalise_equipment_category(
            document.equipment_category
        )
        doc_type_match = (
            1.0 if intent.get("document_type") and normalized_doc_type == intent.get("document_type") else 0.0
        )
        equipment_match = 1.0 if intent.get("equipment") and normalized_equipment == intent.get("equipment") else 0.0
        discipline_match = (
            1.0 if intent.get("discipline") and _matches_discipline(document, intent.get("discipline")) else 0.0
        )

        filename_tokens = set(_token_list(document.file_name))
        title_score = _overlap_score(hints.tokens, title_tokens)
        filename_score = _overlap_score(hints.tokens, filename_tokens)
        subject_tokens = set(_token_list(document.metadata_text))
        subject_score = _overlap_score(hints.tokens, subject_tokens)

        recency_score = _compute_recency_score(
            document_date=document_date,
            prefers_recent=hints.prefers_recent or hints.annual_intent,
            newest=newest_date,
            oldest=oldest_date,
        )
        semantic_score = self._semantic_score(hints=hints, document=document, combined_tokens=combined_tokens)

        query_phrase = query.lower().strip()
        exact_phrase_match = (
            1.0
            if query_phrase and (query_phrase in document.title.lower() or query_phrase in document.file_name.lower())
            else 0.0
        )

        final_score = (
            exact_phrase_match * 0.35
            + lexical_score * 0.2
            + doc_type_match * 0.15
            + equipment_match * 0.1
            + discipline_match * 0.05
            + subject_score * 0.05
            + recency_score * 0.05
            + semantic_score * 0.05
        )

        rank_key = (
            exact_phrase_match,
            doc_type_match,
            equipment_match,
            filename_score,
            title_score,
            subject_score,
            final_score,
        )

        match_reasons = _match_reasons(hints, document, combined_tokens)
        if not match_reasons and lexical_score < 0.05 and semantic_score < 0.05:
            return None

        return {
            "score": round(final_score, 4),
            "payload": {
                "document_id": document.document_id,
                "concept_document_id": document.concept_document_id,
                "title": document.title,
                "document_type": document.document_type,
                "document_date": document.document_date or document.issue_date,
                "building_name": document.building_name or document.site_name,
                "equipment_category": document.equipment_category,
                "equipment_name": document.equipment_name,
                "path": document.path,
                "open_url": document.open_url,
                "download_url": document.download_url,
                "normalized_year": document.normalized_year,
                "normalized_document_type": document.normalized_document_type,
                "normalized_equipment": document.normalized_equipment,
                "normalized_discipline": document.normalized_discipline,
                "concept_url": document.concept_url,
                "match_reasons": match_reasons,
                "snippet": _build_snippet(document, hints),
            },
            "rank_key": rank_key,
        }

    def _semantic_score(
        self,
        *,
        hints: QueryHints,
        document: IndexedConceptDocument,
        combined_tokens: set[str],
    ) -> float:
        semantic_terms = set(hints.document_types) | set(hints.equipment_categories) | set(hints.disciplines)
        if hints.annual_intent:
            semantic_terms.add("annual")
        if hints.prefers_recent:
            semantic_terms.add("recent")

        if not semantic_terms:
            return _overlap_score(hints.tokens, combined_tokens)

        document_terms = {
            term
            for term in semantic_terms
            if term
            in {
                document.document_type,
                document.equipment_category,
                document.discipline,
                "annual" if "annual" in combined_tokens else None,
                "recent" if document.document_date or document.upload_date else None,
            }
        }

        alias_matches = 0
        for category, aliases in {**DOCUMENT_TYPE_SYNONYMS, **EQUIPMENT_SYNONYMS, **DISCIPLINE_SYNONYMS}.items():
            if category in semantic_terms and any(alias in combined_tokens for alias in _tokenise_aliases(aliases)):
                alias_matches += 1

        base_score = len(document_terms) / max(len(semantic_terms), 1)
        alias_score = alias_matches / max(len(semantic_terms), 1)
        return min(1.0, max(base_score, alias_score))


def _token_list(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", value.lower()) if token not in STOP_WORDS]


def _tokenise_aliases(aliases: Iterable[str]) -> set[str]:
    tokens: set[str] = set()
    for alias in aliases:
        tokens.update(_token_list(alias))
    return tokens


def _normalise_document_type(value: Any) -> str | None:
    if not value:
        return None
    lowered = str(value).strip().lower()
    for canonical, aliases in DOCUMENT_TYPE_SYNONYMS.items():
        if lowered == canonical or lowered in aliases:
            return canonical
    return lowered


def _normalise_equipment_category(value: Any) -> str | None:
    if not value:
        return None
    lowered = str(value).strip().lower()
    for canonical, aliases in EQUIPMENT_SYNONYMS.items():
        if lowered == canonical or lowered in aliases:
            return canonical
    return lowered


def _normalise_discipline(value: Any) -> str | None:
    if not value:
        return None
    lowered = str(value).strip().lower()
    for canonical, aliases in DISCIPLINE_SYNONYMS.items():
        if lowered == canonical or lowered in aliases:
            return canonical
    return lowered


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _overlap_score(query_tokens: set[str], field_tokens: set[str]) -> float:
    if not query_tokens or not field_tokens:
        return 0.0
    return len(query_tokens & field_tokens) / max(len(query_tokens), 1)


def _parse_best_date(*values: str | None) -> date | None:
    for value in values:
        if not value:
            continue
        parsed = _parse_datetime_value(value)
        if parsed is not None:
            return parsed.date()
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            continue
    return None


def _compute_recency_score(
    *,
    document_date: date | None,
    prefers_recent: bool,
    newest: date | None,
    oldest: date | None,
) -> float:
    if not prefers_recent:
        return 0.5
    if document_date is None or newest is None or oldest is None:
        return 0.0
    span = max((newest - oldest).days, 1)
    return max(0.0, min(1.0, 1 - ((newest - document_date).days / span)))


def _match_reasons(
    hints: QueryHints,
    document: IndexedConceptDocument,
    combined_tokens: set[str],
) -> list[str]:
    reasons: list[str] = []
    reasons.extend(sorted(hints.tokens & combined_tokens)[:4])

    if hints.document_types and document.document_type in hints.document_types:
        reasons.append(document.document_type)
    if hints.equipment_categories and document.equipment_category in hints.equipment_categories:
        reasons.append(document.equipment_category)
    if hints.annual_intent and "annual" not in reasons and (
        "annual" in combined_tokens
        or "annual" in document.title.lower()
        or "annual" in document.cleaned_text.lower()
    ):
        reasons.append("annual")

    deduped: list[str] = []
    for reason in reasons:
        if reason and reason not in deduped:
            deduped.append(reason)
    return deduped[:4]


def _build_snippet(document: IndexedConceptDocument, hints: QueryHints) -> str:
    if document.snippet:
        return document.snippet

    source_text = document.cleaned_text or document.extracted_text or document.metadata_text
    if not source_text:
        return document.path

    lowered = source_text.lower()
    positions = [lowered.find(token) for token in hints.tokens if lowered.find(token) >= 0]
    if positions:
        start = max(min(positions) - 50, 0)
        end = min(start + 180, len(source_text))
        snippet = source_text[start:end].strip()
    else:
        snippet = source_text[:180].strip()

    if len(snippet) < len(source_text):
        snippet = snippet.rstrip(". ") + "..."
    return snippet


def _openai_available() -> bool:
    return bool(settings.openai_api_key and not settings.local_ai_only)


def _post_openai_chat(messages: list[dict[str, str]], model: str | None) -> dict[str, Any] | None:
    if not model:
        model = settings.openai_model
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": "You are a concise metadata assistant."}, *messages],
        "temperature": 0.2,
    }
    try:
        response = httpx.post(
            f"{settings.openai_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        body = response.json()
        usage = body.get("usage", {})
        try:
            from app.services.ai_usage_tracker import usage_tracker

            usage_tracker.record(
                provider="openai",
                model=model,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                source="concept_search",
            )
        except Exception:
            pass
        return body
    except Exception as exc:
        logger.warning("OpenAI call failed: %s", exc)
        return None


def _extract_message_content(body: dict[str, Any]) -> str:
    choices = body.get("choices", [])
    if not choices:
        return ""
    message = choices[0].get("message") or choices[0].get("delta", {})
    return _build_text_from_message(message)


def _build_text_from_message(message: dict[str, Any]) -> str:
    if not message:
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    parts: list[str] = []
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text", "")))
            elif isinstance(part, str):
                parts.append(part)
    return "".join(parts)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None


def _extract_json_array(text: str) -> list[str] | None:
    cleaned = text.strip()
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1:
        return None
    try:
        array = json.loads(cleaned[start : end + 1])
        return [str(item) for item in array if isinstance(item, str)]
    except json.JSONDecodeError:
        return None


def _normalise_tsv_row(row: dict[str, str]) -> dict[str, Any] | None:
    concept_document_id = _clean_string(row.get("Concept Document Id"))
    site_id = _normalise_site_id(row.get("site_id"))
    actual_path = _clean_string(row.get("Actual Path"))
    file_name = _clean_string(row.get("Filename")) or _file_name_from_path(actual_path)

    if not concept_document_id or not site_id or not file_name:
        return None

    building_name = _clean_string(row.get("Building"))
    title = (
        _clean_string(row.get("Title"))
        or file_name
        or _clean_string(row.get("Document Ref."))
        or f"Concept document {concept_document_id}"
    )
    repository_description = _clean_string(row.get("Repository Description"))
    document_sub_class = _clean_string(row.get("Document Sub Class"))
    subject = _clean_string(row.get("Subject"))
    category = _clean_string(row.get("Category"))
    author = _clean_string(row.get("Author"))
    document_ref = _clean_string(row.get("Document Ref."))

    searchable_text = " ".join(
        bit
        for bit in [
            building_name,
            document_sub_class,
            document_ref,
            title,
            author,
            category,
            subject,
            repository_description,
            file_name,
        ]
        if bit
    )
    display_path = _build_display_path(repository_description, actual_path)
    document_type = _infer_canonical_value(searchable_text, DOCUMENT_TYPE_SYNONYMS)
    equipment_category = _infer_canonical_value(searchable_text, EQUIPMENT_SYNONYMS)
    discipline = _infer_canonical_value(searchable_text, DISCIPLINE_SYNONYMS)
    created_date = _normalise_datetime_string(row.get("Created Date"))
    expiry_date = _normalise_datetime_string(row.get("Expiry Date"))
    file_extension = Path(file_name).suffix.lstrip(".").lower()
    repository_location = _extract_repository_location_path(repository_description)
    open_url = _build_concept_document_url(concept_document_id)
    download_url = _build_concept_raw_document_url(concept_document_id)
    normalized_document_type = _infer_normalized_document_type(searchable_text)
    normalized_equipment = _infer_normalized_equipment(searchable_text)
    normalized_discipline = _infer_normalized_discipline(
        " ".join(filter(None, [document_sub_class, repository_description, category]))
    )
    normalized_year = _derive_normalized_year(
        created_date, _clean_string(row.get("Date")), _clean_string(row.get("Document Date"))
    )
    concept_url = open_url

    return {
        "document_id": concept_document_id,
        "concept_document_id": concept_document_id,
        "source_system": "concept",
        "title": title,
        "file_name": file_name,
        "file_extension": file_extension,
        "file_path": actual_path or repository_location or display_path,
        "path": display_path,
        "open_url": open_url,
        "download_url": download_url,
        "upload_date": created_date,
        "site_id": site_id,
        "site_name": building_name,
        "building_id": site_id,
        "building_name": building_name,
        "discipline": discipline,
        "equipment_category": equipment_category,
        "document_type": document_type,
        "subtype": document_sub_class,
        "document_date": created_date,
        "expiry_date": expiry_date,
        "tags": [token for token in [document_type, equipment_category, discipline] if token],
        "extracted_text": searchable_text,
        "cleaned_text": searchable_text,
        "filename_tokens": _token_list(file_name),
        "path_tokens": _token_list(f"{display_path} {actual_path}"),
        "metadata_text": searchable_text,
        "indexing_status": "indexed",
        "extraction_status": "metadata_only",
        "title_source": "tsv_export",
        "snippet": subject or document_ref or repository_description or display_path,
        "normalized_year": normalized_year,
        "normalized_document_type": normalized_document_type,
        "normalized_equipment": normalized_equipment,
        "normalized_discipline": normalized_discipline,
        "concept_url": concept_url,
    }


def _clean_string(value: Any) -> str:
    cleaned = str(value or "").strip()
    return "" if cleaned.lower() in {"nan", "none", "null"} else cleaned


def _normalise_site_id(value: Any) -> str | None:
    raw = _clean_string(value).lower()
    if not raw or raw == "ok":
        return None
    if raw.startswith("site-"):
        suffix = raw.split("site-", 1)[1]
        if suffix.isdigit():
            return f"site-{suffix.zfill(3)}"
        return raw
    if raw.isdigit():
        return f"site-{raw.zfill(3)}"
    return raw


def _file_name_from_path(value: str) -> str:
    if not value:
        return ""
    return Path(value.replace("\\", "/")).name


def _build_display_path(repository_description: str, actual_path: str) -> str:
    if repository_description:
        label, separator, _raw_path = repository_description.partition(":")
        if separator and label.strip():
            return label.strip()
        if repository_description.strip():
            return repository_description.strip()

    if actual_path:
        parts = [part for part in actual_path.split("\\") if part]
        if len(parts) > 4:
            return " / ".join(parts[-4:-1])
        if parts:
            return " / ".join(parts[:-1]) or parts[-1]

    return "Concept document"


def _extract_repository_location_path(repository_description: str) -> str:
    if not repository_description:
        return ""
    _, separator, raw_path = repository_description.partition(":")
    if separator:
        cleaned = raw_path.strip()
        return "" if cleaned in {"", "."} else cleaned
    return ""


def _infer_canonical_value(searchable_text: str, synonyms: dict[str, set[str]]) -> str | None:
    lowered = searchable_text.lower()
    tokens = set(_token_list(searchable_text))
    exact_matches = [canonical for canonical, aliases in synonyms.items() if lowered == canonical or lowered in aliases]
    if exact_matches:
        return exact_matches[0]

    ranked_alias_matches: list[tuple[int, str]] = []
    for canonical, aliases in synonyms.items():
        matching_aliases = [
            alias
            for alias in aliases
            if _matches_requested_canonical(canonical, lowered, tokens, synonyms)
            and _alias_matches_text(alias, lowered, tokens)
        ]
        if matching_aliases:
            ranked_alias_matches.append((max(len(alias) for alias in matching_aliases), canonical))

    if not ranked_alias_matches:
        return None

    ranked_alias_matches.sort(reverse=True)
    return ranked_alias_matches[0][1]


def _parse_datetime_value(value: str | None) -> datetime | None:
    cleaned = _clean_string(value)
    if not cleaned:
        return None

    formats = (
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
    )
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def _normalise_datetime_string(value: str | None) -> str | None:
    parsed = _parse_datetime_value(value)
    return parsed.isoformat() if parsed is not None else None


def _build_concept_document_url(concept_document_id: str) -> str:
    # Backwards-compatible alias for older call sites.
    return _build_concept_item_url(concept_document_id)


def _build_concept_item_url(concept_document_id: str) -> str:
    """Link to the Concept "item" page (metadata + actions)."""
    # Concept appears to expect "!System" unescaped in this referrer value
    # (matches observed URLs like "...__referrer=%2fEvolution%2f!System%2fDocuments...").
    referrer = quote(CONCEPT_DOCUMENT_ITEMS_REFERRER_PATH, safe="!")
    return CONCEPT_DOCUMENT_ITEM_URL_TEMPLATE.format(
        referrer=referrer,
        concept_document_id=quote(concept_document_id, safe=""),
    )


def _build_concept_raw_document_url(concept_document_id: str) -> str:
    """Link to the raw document viewer/download page."""
    item_relative = (
        "/Evolution/!System/Documents/ConceptDocument/ViewConceptDocumentItem.aspx"
        f"?__referrer={quote(CONCEPT_DOCUMENT_ITEMS_REFERRER_PATH, safe='')}"
        f"&id={quote(concept_document_id, safe='')}&PrimaryEntity=&PrimaryKeyId=-1"
    )
    referrer = quote(item_relative, safe="")
    return CONCEPT_DOCUMENT_RAW_URL_TEMPLATE.format(
        referrer=referrer,
        concept_document_id=quote(concept_document_id, safe=""),
    )


def _infer_normalized_document_type(text: str) -> str | None:
    lowered = text.lower()
    for canonical, keywords in DOCUMENT_TYPE_CLASSIFIER:
        if not keywords:
            continue
        if any(keyword in lowered for keyword in keywords):
            return canonical
    return None


def _infer_normalized_equipment(text: str) -> str | None:
    lowered = text.lower()
    for canonical, keywords in EQUIPMENT_CLASSIFIER:
        if not keywords:
            continue
        if any(keyword in lowered for keyword in keywords):
            return canonical
    return None


def _infer_normalized_discipline(text: str) -> str | None:
    lowered = text.lower()
    for canonical, keywords in DISCIPLINE_CLASSIFIER:
        if not keywords:
            continue
        if any(keyword in lowered for keyword in keywords):
            return canonical
    return None


def _derive_normalized_year(*date_strings: str | None) -> int | None:
    parsed = _parse_best_date(*date_strings)
    return parsed.year if parsed else None


def _matches_any_alias(lowered_text: str, token_set: set[str], aliases: Iterable[str]) -> bool:
    return any(_alias_matches_text(alias, lowered_text, token_set) for alias in aliases)


def _matches_requested_canonical(
    canonical: str,
    lowered_text: str,
    token_set: set[str],
    synonyms: dict[str, set[str]],
) -> bool:
    aliases = synonyms.get(canonical, {canonical})
    matched = _matches_any_alias(lowered_text, token_set, aliases)
    if not matched:
        return False

    if canonical == "generator" and "generator room" in lowered_text:
        generator_signals = {
            "generator service",
            "generator inspection",
            "generator weekly",
            "generator monthly",
            "generator annual",
            "generator test",
            "generator report",
            "genset",
        }
        if not any(signal in lowered_text for signal in generator_signals):
            return False

    return True


def _document_matches_year(document: IndexedConceptDocument, year: int) -> bool:
    if document.normalized_year == year:
        return True
    if document_date := _parse_best_date(document.document_date, document.issue_date, document.upload_date):
        return document_date.year == year
    return False


def _document_matches_month(document: IndexedConceptDocument, month: int) -> bool:
    if not (document_date := _parse_best_date(document.document_date, document.issue_date, document.upload_date)):
        return False
    if document_date.month == month:
        return True
    try:
        start = date(document_date.year, month, 1)
    except ValueError:
        return False
    return abs((document_date - start).days) <= 7


def _matches_document_type(document: IndexedConceptDocument, canonical: str) -> bool:
    normalized = document.normalized_document_type or _normalise_document_type(document.document_type)
    return normalized == canonical


def _matches_equipment(document: IndexedConceptDocument, canonical: str) -> bool:
    normalized = document.normalized_equipment or _normalise_equipment_category(document.equipment_category)
    return normalized == canonical


def _matches_discipline(document: IndexedConceptDocument, canonical: str) -> bool:
    normalized = document.normalized_discipline or _normalise_discipline(document.discipline)
    return normalized == canonical


def _alias_matches_text(alias: str, lowered_text: str, token_set: set[str]) -> bool:
    alias_tokens = _token_list(alias)
    if not alias_tokens:
        return False
    if len(alias_tokens) == 1:
        return alias_tokens[0] in token_set
    alias_phrase = " ".join(alias_tokens)
    return alias_phrase in lowered_text or all(token in token_set for token in alias_tokens)


_concept_search_service: ConceptDocumentSearchService | None = None


def get_concept_document_search_service() -> ConceptDocumentSearchService:
    global _concept_search_service
    if _concept_search_service is None:
        _concept_search_service = ConceptDocumentSearchService()
    return _concept_search_service
