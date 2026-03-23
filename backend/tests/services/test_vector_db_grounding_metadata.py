"""Tests for citation grounding metadata in document chunks."""

from app.services.vector_db import VectorDBService


class _DummyClient:
    pass


def _document_payload() -> dict:
    return {
        "id": "doc-123",
        "title": "Generator Service Manual",
        "source": "user_upload",
        "equipment_type": "generator",
        "document_type": "manual",
        "site_id": "site-002",
        "manufacturer": "Acme",
        "model": "G-9000",
        "keywords": ["service", "generator"],
        "failure_modes": ["overheat"],
    }


def test_build_chunk_record_contains_grounding_fields():
    svc = VectorDBService(_DummyClient())
    document = _document_payload()
    chunk = {
        "content": "Section 1: Safety checks for weekly start.",
        "section": "Safety checks",
        "page_number": 3,
    }

    record = svc._build_chunk_record(
        document=document,
        document_id=document["id"],
        chunk_index=0,
        chunk=chunk,
        embedding=[0.1, 0.2, 0.3],
    )

    assert record["document_id"] == "doc-123"
    assert record["chunk_index"] == 0
    assert record["section_title"] == "Safety checks"
    assert record["page_number"] == 3
    assert isinstance(record["id"], str) and len(record["id"]) > 10
    grounding = record["metadata"]["grounding"]
    assert grounding["document_id"] == "doc-123"
    assert grounding["chunk_id"] == record["id"]
    assert grounding["chunk_index"] == 0
    assert grounding["section_title"] == "Safety checks"
    assert grounding["page_number"] == 3


def test_build_grounding_metadata_preserves_existing_metadata():
    svc = VectorDBService(_DummyClient())
    metadata = svc._build_grounding_metadata(
        document=_document_payload(),
        document_id="doc-123",
        chunk_id="chunk-001",
        chunk_index=5,
        section_title="Troubleshooting",
        page_number=None,
        existing_metadata={"heading_path": ["Chapter 2", "Troubleshooting"]},
    )

    assert metadata["heading_path"] == ["Chapter 2", "Troubleshooting"]
    assert metadata["grounding"]["chunk_id"] == "chunk-001"
    assert metadata["grounding"]["chunk_index"] == 5
    assert metadata["grounding"]["section_title"] == "Troubleshooting"
    assert metadata["grounding"]["page_number"] is None
