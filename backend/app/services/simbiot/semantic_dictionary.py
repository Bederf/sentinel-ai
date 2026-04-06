"""Loader service for the canonical semantic dictionary.

Phase 162: Semantic Control Foundation — Plan 01.
Loads and serves the JSON semantic dictionary as validated Pydantic models.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.models.semantic_tag import SemanticDictionary, SemanticTag

_DEFAULT_DICTIONARY_PATH = Path(__file__).parent.parent.parent / "app" / "data" / "simbiot" / "semantic_dictionary.json"
# Fallback: relative path from cwd (e.g. when running from backend/)
_RELATIVE_FALLBACK = Path("app/data/simbiot/semantic_dictionary.json")


class SemanticDictionaryService:
    """Loads and serves the canonical semantic dictionary.

    Usage::

        service = SemanticDictionaryService()
        service.load()
        tag = service.get_tag("supply_air_temperature_sensor")
    """

    def __init__(self, dictionary_path: Path | None = None) -> None:
        if dictionary_path is not None:
            self.dictionary_path = Path(dictionary_path)
        elif _DEFAULT_DICTIONARY_PATH.exists():
            self.dictionary_path = _DEFAULT_DICTIONARY_PATH
        else:
            self.dictionary_path = _RELATIVE_FALLBACK
        self._dictionary: SemanticDictionary | None = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> SemanticDictionary:
        """Load and validate the dictionary from the JSON file.

        Raises:
            FileNotFoundError: If the dictionary file does not exist.
            ValidationError: If the JSON fails Pydantic validation.
        """
        with open(self.dictionary_path) as f:
            raw: dict = json.load(f)

        # Inject the tag name into each SemanticTag so callers can use tag.tag
        for tag_name, tag_data in raw.get("semantic_tags", {}).items():
            tag_data["tag"] = tag_name

        self._dictionary = SemanticDictionary(**raw)
        return self._dictionary

    def _ensure_loaded(self) -> None:
        if self._dictionary is None:
            self.load()

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_tag(self, tag: str) -> SemanticTag | None:
        """Return a semantic tag by name, or None if not found."""
        self._ensure_loaded()
        return self._dictionary.semantic_tags.get(tag)  # type: ignore[union-attr]

    def list_tags(self) -> list[str]:
        """Return all available semantic tag names."""
        self._ensure_loaded()
        return list(self._dictionary.semantic_tags.keys())  # type: ignore[union-attr]

    def find_by_equipment_type(self, equipment_type: str) -> list[SemanticTag]:
        """Return all tags applicable to a given equipment type."""
        self._ensure_loaded()
        eq_lower = equipment_type.lower()
        return [
            tag
            for tag in self._dictionary.semantic_tags.values()  # type: ignore[union-attr]
            if eq_lower in [t.lower() for t in tag.applies_to]
        ]

    def get_safety_class(self, tag: str) -> str | None:
        """Return the safety class string for a tag name."""
        semantic_tag = self.get_tag(tag)
        return semantic_tag.safety_class.value if semantic_tag else None

    def get_dictionary(self) -> SemanticDictionary | None:
        """Return the loaded dictionary model (None if not yet loaded)."""
        return self._dictionary
