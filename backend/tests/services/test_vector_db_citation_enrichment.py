"""Tests for vector search grounding enrichment."""

from app.services.vector_db import VectorDBService


class _Result:
    def __init__(self, data):
        self.data = data


class _TableQuery:
    def __init__(self, rows):
        self._rows = rows

    def select(self, _fields):
        return self

    def in_(self, _field, _values):
        return self

    def execute(self):
        return _Result(self._rows)


class _Client:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return _TableQuery(self._rows)


def test_attach_grounding_metadata_enriches_results():
    rows = [
        {
            "id": "chunk-1",
            "document_id": "doc-1",
            "chunk_index": 0,
            "section_title": "Overview",
            "page_number": 2,
            "metadata": {
                "grounding": {
                    "document_title": "Generator Manual",
                    "source": "technician_notes",
                }
            },
        }
    ]
    svc = VectorDBService(_Client(rows))
    results = [{"chunk_id": "chunk-1", "content": "Generator restart procedure", "document_title": "Generator Manual"}]

    enriched = svc._attach_grounding_metadata(results)
    assert enriched[0]["document_id"] == "doc-1"
    assert enriched[0]["section_title"] == "Overview"
    assert enriched[0]["page_number"] == 2
    assert enriched[0]["grounding"]["chunk_id"] == "chunk-1"
    assert enriched[0]["grounding"]["document_id"] == "doc-1"
    assert enriched[0]["grounding"]["source"] == "technician_notes"
