#!/usr/bin/env python3
"""
Utility to ingest a Concept export TSV through SENTINEL's document RAG service.

Each row is normalized (document_type, equipment_type, discipline, year) and sent
to `/api/concept-rag/documents` so Technician Chat can search against the Concept documents.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from app.services.concept_document_search import (
    _build_concept_document_url,
    _clean_string,
    _derive_normalized_year,
    _infer_normalized_discipline,
    _infer_normalized_document_type,
    _infer_normalized_equipment,
    _normalise_site_id,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

SUPPORTED_DOCUMENT_TYPES = {
    "service_sheet": "service_report",
    "inspection_sheet": "service_report",
    "certificate": "service_report",
    "reading": "service_report",
    "checklist": "maintenance_procedure",
    "job_card": "service_report",
    "report": "service_report",
    "maintenance worksheet": "maintenance_procedure",
    "commissioning sheet": "startup_procedure",
    "quote": "technical_bulletin",
    "invoice": "service_report",
}


def _supported_document_type(normalized_document_type: str | None, fallback_text: str | None) -> str:
    if normalized_document_type in SUPPORTED_DOCUMENT_TYPES:
        return SUPPORTED_DOCUMENT_TYPES[normalized_document_type]

    fallback = (fallback_text or "").strip().lower()
    if "manual" in fallback:
        return "equipment_manual"
    if "troubleshoot" in fallback or "fault" in fallback:
        return "troubleshooting_guide"
    if "startup" in fallback or "commission" in fallback:
        return "startup_procedure"
    if "shutdown" in fallback or "decommission" in fallback:
        return "shutdown_procedure"
    if "safety" in fallback:
        return "safety_procedure"
    if "procedure" in fallback or "worksheet" in fallback:
        return "maintenance_procedure"
    if "bulletin" in fallback:
        return "technical_bulletin"
    return "service_report"


def load_rows(tsv_path: Path) -> list[dict[str, str]]:
    with tsv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return [row for row in reader if isinstance(row, dict)]


def normalize_row(row: dict[str, str]) -> dict[str, Any] | None:
    document_id = _clean_string(row.get("Concept Document Id"))
    if not document_id:
        return None

    site_id = _normalise_site_id(row.get("site_id"))
    if not site_id:
        logger.warning("Skipping row without site_id: %s", document_id)
        return None

    title = (
        _clean_string(row.get("Title"))
        or _clean_string(row.get("Document Ref."))
        or f"Concept document {document_id}"
    )
    repository_description = _clean_string(row.get("Repository Description"))
    document_sub_class = _clean_string(row.get("Document Sub Class"))
    category = _clean_string(row.get("Category"))
    subject = _clean_string(row.get("Subject"))
    actual_path = _clean_string(row.get("Actual Path"))
    file_name = _clean_string(row.get("Filename")) or Path(actual_path).name

    searchable_text = " ".join(
        bit
        for bit in [
            title,
            document_sub_class,
            repository_description,
            subject,
            category,
            _clean_string(row.get("Document Ref.")),
            file_name,
        ]
        if bit
    )

    normalized_document_type = _infer_normalized_document_type(searchable_text)
    normalized_equipment = _infer_normalized_equipment(searchable_text)
    normalized_discipline = _infer_normalized_discipline(
        " ".join(filter(None, [document_sub_class, repository_description, category]))
    )
    normalized_year = _derive_normalized_year(
        _normalize_iso(row.get("Created Date")),
        _clean_string(row.get("Document Date")),
        _clean_string(row.get("Date")),
    )

    payload = {
        "code": document_id,
        "title": title,
        "document_type": _supported_document_type(
            normalized_document_type,
            " ".join(
                bit for bit in [document_sub_class, repository_description, category, subject, title] if bit
            ),
        ),
        "equipment_type": normalized_equipment or "unknown",
        "full_text": searchable_text,
        "source": "service_history",
        "site_id": site_id,
        "metadata": {
            "repository_description": repository_description,
            "document_sub_class": document_sub_class,
            "category": category,
            "subject": subject,
            "actual_path": actual_path,
            "file_name": file_name,
        },
        "tags": [tag for tag in {normalized_document_type, normalized_equipment, normalized_discipline} if tag],
        "normalized_year": normalized_year,
        "document_date": _normalize_iso(row.get("Created Date")),
        "concept_document_id": document_id,
        "concept_url": _build_concept_document_url(document_id),
    }

    return payload


def _normalize_iso(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        # Normalize slashes to hyphen
        return cleaned.replace("/", "-")
    except Exception:
        return cleaned


def ingest_document(client: httpx.Client | None, payload: dict[str, Any], dry_run: bool = False) -> httpx.Response | None:
    url = "/api/concept-rag/documents"
    if dry_run:
        logger.info("Dry run payload: %s", json.dumps(payload, ensure_ascii=False))
        return None
    assert client is not None
    response = client.post(url, json=payload, timeout=60.0)
    response.raise_for_status()
    return response


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Concept TSV rows into SENTINEL doc RAG.")
    parser.add_argument("--tsv", default="site_id Building Document Sub Class Docu.tsv", help="Path to the Concept TSV export")
    parser.add_argument("--site-id", default=None, help="Optional site ID override (leave empty to use TSV value)")
    parser.add_argument("--dry-run", action="store_true", help="Log payloads without calling the API")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of documents processed (0 = all)")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many rows before processing")
    parser.add_argument("--request-delay", type=float, default=0.0, help="Seconds to wait between API calls")
    parser.add_argument("--base-url", default="http://localhost:9095", help="Base URL for the RAG API")
    parser.add_argument(
        "--bearer-token",
        default=os.getenv("SENTINEL_BEARER_TOKEN"),
        help="Optional bearer token for the RAG API. Falls back to SENTINEL_BEARER_TOKEN.",
    )
    args = parser.parse_args()

    tsv_path = Path(args.tsv)
    if not tsv_path.exists():
        logger.error("TSV file not found: %s", tsv_path)
        sys.exit(1)

    rows = load_rows(tsv_path)
    if not rows:
        logger.info("No rows found in %s", tsv_path)
        return

    limit = args.limit or len(rows)
    end = args.offset + limit if limit else len(rows)
    documents = []
    for row in rows[args.offset:end]:
        normalized = normalize_row(row)
        if normalized:
            if args.site_id:
                normalized["site_id"] = args.site_id
            documents.append(normalized)

    if not documents:
        logger.warning("No valid documents to ingest")
        return

    if args.dry_run:
        for payload in documents:
            ingest_document(None, payload, dry_run=True)
        return

    headers = {}
    if args.bearer_token:
        headers["Authorization"] = f"Bearer {args.bearer_token}"

    with httpx.Client(base_url=args.base_url, headers=headers) as client:
        for payload in documents:
            try:
                response = ingest_document(client, payload)
            except httpx.HTTPError as exc:
                logger.error("Failed to ingest %s: %s", payload["code"], exc)
                continue
            logger.info("Ingested %s -> %s", payload["code"], response.json().get("id"))
            if args.request_delay > 0:
                time.sleep(args.request_delay)


if __name__ == "__main__":
    main()
