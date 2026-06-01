"""Adaptive chunking for SENTINEL document processing pipeline.

Plugs between DoclingExtractionService output and pgvector upsert.
Content-aware: uses semantic density scoring to decide chunk size per section.

Chunk sizes (words):
    DENSE    → 200  (tables, fault codes, technical specs)
    BALANCED → 512  (section anchors, procedure steps)
    LIGHT    → 800  (narrative, descriptions)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SectionDensity(str, Enum):
    DENSE = "dense"
    BALANCED = "balanced"
    LIGHT = "light"


@dataclass
class AdaptiveChunk:
    """A single chunk produced by AdaptiveChunker."""

    text: str
    chunk_size_used: int
    density: SectionDensity
    element_type: str
    page_number: int = 0
    bounding_box: list | None = None
    asset_id: str = ""
    document_id: str = ""
    heading_path: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "chunk_size_used": self.chunk_size_used,
            "density": self.density.value,
            "element_type": self.element_type,
            "page_number": self.page_number,
            "bounding_box": self.bounding_box,
            "asset_id": self.asset_id,
            "document_id": self.document_id,
            "heading_path": self.heading_path,
        }


# Tuned thresholds — confirmed against S002 real corpus (contractor report scoring, 2026-05-08)
DENSE_THRESHOLD = 0.15
BALANCED_THRESHOLD = 0.06
SENT_WEIGHT = 0.05

CHUNK_SIZES = {
    SectionDensity.DENSE: 200,
    SectionDensity.BALANCED: 512,
    SectionDensity.LIGHT: 800,
}

# Confirmed from S002 real document scoring + SA building services corpus
TECHNICAL_MARKERS: set[str] = {
    # Core technical terms
    "fault",
    "error",
    "failed",
    "replaced",
    "measured",
    "reading",
    "pressure",
    "temperature",
    "voltage",
    "current",
    "flow",
    "rpm",
    "hz",
    "kpa",
    "bar",
    "amps",
    "kw",
    "kwh",
    "setpoint",
    "alarm",
    "trip",
    "hours",
    "litres",
    "oil",
    "filter",
    "belt",
    "bearing",
    # SA building services
    "kva",
    "rcd",
    "mcb",
    "isolator",
    "reticulation",
    "earthing",
    "db",
    "board",
    "lpg",
    "borehole",
    # HVAC / refrigeration
    "evaporator",
    "condenser",
    "compressor",
    "refrigerant",
    "chiller",
    "ahu",
    "msb",
    "ats",
    "ups",
    "cop",
    "cwt",
    "louvre",
    "retorque",
    "fretting",
    # Confirmed from real contractor corpus
    "thermographic",
    "ir",
    "rod-out",
    "biological",
    "legionella",
    "capex",
    "oem",
}


class AdaptiveChunker:
    """Content-aware chunker using semantic density scoring."""

    ELEMENT_DENSITY_MAP: dict[str, SectionDensity] = {
        "table": SectionDensity.DENSE,
        "list": SectionDensity.DENSE,
        "formula": SectionDensity.DENSE,
        "heading": SectionDensity.BALANCED,
        "caption": SectionDensity.DENSE,
    }

    def classify_density(
        self,
        text: str,
        element_type: str,
    ) -> tuple[SectionDensity, float]:
        """Classify a text element's density band.

        Returns (density, raw_score) — raw_score is useful for auditing
        and for tuning thresholds against real corpus.
        """
        mapped = self.ELEMENT_DENSITY_MAP.get(element_type)
        if mapped is not None:
            return mapped, -1.0

        words = text.split()
        if not words:
            return SectionDensity.LIGHT, 0.0

        numeric_ratio = sum(1 for w in words if any(c.isdigit() for c in w)) / len(words)
        lower_words = [w.lower() for w in words]
        technical_ratio = sum(1 for w in lower_words if w in TECHNICAL_MARKERS) / len(words)

        dot_count = max(text.count("."), 1)
        avg_sentence_len = len(words) / dot_count

        density_score = (numeric_ratio * 0.4) + (technical_ratio * 0.4) + (min(avg_sentence_len, 30) / 30 * SENT_WEIGHT)

        if density_score > DENSE_THRESHOLD:
            return SectionDensity.DENSE, density_score
        elif density_score > BALANCED_THRESHOLD:
            return SectionDensity.BALANCED, density_score
        else:
            return SectionDensity.LIGHT, density_score

    def chunk_element(
        self,
        element: dict[str, Any],
        asset_id: str = "",
        document_id: str = "",
    ) -> list[AdaptiveChunk]:
        """Chunk a single OpenDataLoader element.

        Args:
            element: Dict with keys: type, content, page_number, bounding_box
            asset_id: Equipment asset identifier
            document_id: Source document UUID

        Returns:
            List of AdaptiveChunk objects
        """
        element_type = element.get("type", "paragraph")
        text = element.get("content", "")
        page = element.get("page_number", 0)
        bbox = element.get("bounding_box")
        heading_path = element.get("heading_path", [])

        if not text.strip():
            return []

        if element_type == "table":
            return self._chunk_table(element, asset_id, document_id, heading_path)

        density, _ = self.classify_density(text, element_type)
        chunk_size = CHUNK_SIZES[density]

        words = text.split()
        chunks = []
        for i in range(0, len(words), chunk_size):
            chunk_text = " ".join(words[i : i + chunk_size])
            chunks.append(
                AdaptiveChunk(
                    text=chunk_text,
                    chunk_size_used=chunk_size,
                    density=density,
                    element_type=element_type,
                    page_number=page,
                    bounding_box=bbox,
                    asset_id=asset_id,
                    document_id=document_id,
                    heading_path=heading_path,
                )
            )
        return chunks

    def _chunk_table(
        self,
        element: dict[str, Any],
        asset_id: str,
        document_id: str,
        heading_path: list[str],
    ) -> list[AdaptiveChunk]:
        """Each table row becomes its own chunk.

        Preserves table headers as context prefix — critical for retrieval
        since a row like "35% | capacity reduction" is meaningless without
        the column headers.
        """
        raw_content = element.get("content", "")
        lines = raw_content.split("\n")
        if not lines:
            return []

        # Find header row (first non-empty, non-separator line)
        header = ""
        data_start = 0
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("|---"):
                header = stripped
                data_start = idx + 1
                break

        page = element.get("page_number", 0)
        bbox = element.get("bounding_box")

        chunks = []
        for line in lines[data_start:]:
            stripped = line.strip()
            if not stripped or stripped.startswith("|---"):
                continue
            # Prepend header for context
            chunk_text = f"{header}\n{stripped}" if header else stripped
            chunks.append(
                AdaptiveChunk(
                    text=chunk_text,
                    chunk_size_used=200,
                    density=SectionDensity.DENSE,
                    element_type="table_row",
                    page_number=page,
                    bounding_box=bbox,
                    asset_id=asset_id,
                    document_id=document_id,
                    heading_path=heading_path,
                )
            )
        return chunks

    def chunk_document(
        self,
        elements: list[dict[str, Any]],
        asset_id: str = "",
        document_id: str = "",
    ) -> list[AdaptiveChunk]:
        """Chunk a full document from OpenDataLoader JSON elements.

        Args:
            elements: List of OpenDataLoader element dicts
            asset_id: Equipment asset identifier
            document_id: Source document UUID

        Returns:
            Flat list of all AdaptiveChunk objects for the document
        """
        chunks = []
        for element in elements:
            chunks.extend(self.chunk_element(element, asset_id, document_id))
        return chunks
