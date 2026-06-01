"""Unit tests for AdaptiveChunker — calibrated against S002 contractor report corpus."""

from app.services.chunker import (
    BALANCED_THRESHOLD,
    DENSE_THRESHOLD,
    SENT_WEIGHT,
    AdaptiveChunk,
    AdaptiveChunker,
    SectionDensity,
)


class TestClassifyDensity:
    """Tests for the semantic density scorer. Calibrated 2026-05-08 against real contractor report."""

    def test_table_element_is_dense(self):
        c = AdaptiveChunker()
        density, _ = c.classify_density("System | Impact | Duration", "table")
        assert density == SectionDensity.DENSE

    def test_signoff_is_light(self):
        c = AdaptiveChunker()
        text = "Report Prepared By: J. van der Merwe, Senior HVAC Engineer, CoolTech Services. Reviewed By: P. Naidoo, Technical Director."
        density, _ = c.classify_density(text, "paragraph")
        assert density == SectionDensity.LIGHT

    def test_timeline_bullet_is_dense(self):
        c = AdaptiveChunker()
        text = "00:00-06:00: Night setback mode. Chiller-001 running as lead, CWT supply at 7.2C (setpoint 6.5C). COP measured at 3.8 (design: 5.2). Condenser approach temperature elevated at 8.5C vs design 3.0C."
        density, _ = c.classify_density(text, "paragraph")
        assert density == SectionDensity.DENSE

    def test_conclusion_is_light(self):
        c = AdaptiveChunker()
        text = "This cascading failure was preventable. Each individual system had warning signs that were either missed, deferred, or inadequately addressed. The combination of a hot February, load shedding, and deferred maintenance created a perfect storm."
        density, _ = c.classify_density(text, "paragraph")
        assert density == SectionDensity.LIGHT

    def test_recommendations_is_dense_or_balanced(self):
        c = AdaptiveChunker()
        text = "1. Chiller-001: Full mechanical tube cleaning complete. 2. Chiller-003: Schedule compressor bearing replacement before failure. Oil iron levels 3x threshold."
        density, _ = c.classify_density(text, "paragraph")
        # Either DENSE or BALANCED is acceptable — both are correct per grid search
        assert density in (SectionDensity.DENSE, SectionDensity.BALANCED)

    def test_heading_element_is_balanced(self):
        c = AdaptiveChunker()
        density, _ = c.classify_density("Root Cause Analysis", "heading")
        assert density == SectionDensity.BALANCED

    def test_formula_element_is_dense(self):
        c = AdaptiveChunker()
        density, _ = c.classify_density("COP = (Q / W)", "formula")
        assert density == SectionDensity.DENSE

    def test_calibration_constants_are_locked(self):
        """Verify the thresholds are the ones confirmed in calibration."""
        assert DENSE_THRESHOLD == 0.15
        assert BALANCED_THRESHOLD == 0.06
        assert SENT_WEIGHT == 0.05


class TestChunkElement:
    def test_empty_text_returns_empty_list(self):
        c = AdaptiveChunker()
        result = c.chunk_element({"type": "paragraph", "content": ""})
        assert result == []

    def test_table_element_returns_per_row_chunks(self):
        c = AdaptiveChunker()
        element = {
            "type": "table",
            "content": "System | Impact\nChiller Plant | 35% capacity reduction\nAHU System | Supply air temp elevated",
            "page_number": 2,
        }
        chunks = c.chunk_element(element, asset_id="site-002-chiller", document_id="doc-123")
        assert len(chunks) == 2
        # Each row has header context prepended
        assert all("System | Impact" in ch.text for ch in chunks)
        assert all(ch.density == SectionDensity.DENSE for ch in chunks)
        assert all(ch.element_type == "table_row" for ch in chunks)

    def test_paragraph_chunks_by_density(self):
        c = AdaptiveChunker()
        # No digits, no technical markers → LIGHT (800 words/chunk)
        words = " ".join(["aaa"] * 500)
        element = {"type": "paragraph", "content": words}
        chunks = c.chunk_element(element)
        assert len(chunks) == 1
        assert chunks[0].chunk_size_used == 800
        assert chunks[0].density == SectionDensity.LIGHT

    def test_technical_content_classifies_dense(self):
        c = AdaptiveChunker()
        element = {
            "type": "paragraph",
            "content": "Chiller-001 compressor trip count: 12 in 48 hours. Oil iron levels 3x threshold. COP measured at 2.8.",
        }
        density, _ = c.classify_density(element["content"], element["type"])
        assert density == SectionDensity.DENSE


class TestChunkDocument:
    def test_mixed_elements_all_chunked(self):
        c = AdaptiveChunker()
        elements = [
            {"type": "heading", "content": "Executive Summary", "page_number": 1},
            {"type": "paragraph", "content": "Site S003 experienced a cascading failure.", "page_number": 1},
            {
                "type": "table",
                "content": "System | Impact\nChiller Plant | 35% reduction",
                "page_number": 2,
            },
        ]
        chunks = c.chunk_document(elements, asset_id="site-002", document_id="doc-456")
        assert len(chunks) == 3  # heading + paragraph + 1 table row


class TestAdaptiveChunkDataclass:
    def test_to_dict_includes_all_fields(self):
        chunk = AdaptiveChunk(
            text="Chiller-001 fault: low oil pressure",
            chunk_size_used=200,
            density=SectionDensity.DENSE,
            element_type="paragraph",
            page_number=3,
            asset_id="site-002-chiller-001",
            document_id="doc-789",
            heading_path=["Root Cause Analysis", "Primary Finding"],
        )
        d = chunk.to_dict()
        assert d["text"] == "Chiller-001 fault: low oil pressure"
        assert d["density"] == "dense"
        assert d["element_type"] == "paragraph"
        assert d["page_number"] == 3
        assert d["heading_path"] == ["Root Cause Analysis", "Primary Finding"]
