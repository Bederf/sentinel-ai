"""Semantic Priority Classifier — Phase 207-03.

Two-stage consumables classifier that corrects misclassified priorities
(e.g. soap dispensers flagged as CRITICAL when they are LOW priority).

Stage 1 — Keyword match: fast path against consumables taxonomy.
Stage 2 — Embedding similarity: only if Stage 1 misses.
No LLM fallback — deterministic, sub-100ms.

Architecture:
- Does NOT replace issue_classifier.py (keyword-only, 47 categories)
- Extends it by correcting the priority for consumables before recommendation creation
- Loaded once at init (not per-call)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from app.models.priority_classification import PriorityClassification

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Taxonomy cache — loaded once
# ---------------------------------------------------------------------------

_CONSUMABLES_TAXONOMY: dict[str, Any] | None = None


def _load_taxonomy() -> dict[str, Any]:
    """Load consumables taxonomy from JSON (cached)."""
    global _CONSUMABLES_TAXONOMY
    if _CONSUMABLES_TAXONOMY is not None:
        return _CONSUMABLES_TAXONOMY

    taxonomy_path = Path(__file__).parent.parent / "data" / "consumables_taxonomy.json"
    # Support absolute path override via env var
    if os.environ.get("CONSUMABLES_TAXONOMY_PATH"):
        taxonomy_path = Path(os.environ["CONSUMABLES_TAXONOMY_PATH"])

    if not taxonomy_path.exists():
        logger.error("Consumables taxonomy not found at %s", taxonomy_path)
        return {"consumables": {}}

    with open(taxonomy_path, encoding="utf-8") as f:
        _CONSUMABLES_TAXONOMY = json.load(f)

    logger.info("Loaded consumables taxonomy from %s", taxonomy_path)
    return _CONSUMABLES_TAXONOMY


# ---------------------------------------------------------------------------
# Consumables keyword index — built at load time
# ---------------------------------------------------------------------------

# Maps lowercase item string -> (category, priority)
_ITEM_INDEX: dict[str, tuple[str, str]] = {}


def _build_item_index() -> None:
    """Build lowercase item → (category, priority) index from taxonomy."""
    taxonomy = _load_taxonomy()
    _ITEM_INDEX.clear()
    for category, info in taxonomy.get("consumables", {}).items():
        priority = info.get("priority", "LOW")
        for item in info.get("items", []):
            _ITEM_INDEX[item.lower()] = (category, priority)


_build_item_index()


# ---------------------------------------------------------------------------
# SemanticPriorityClassifier
# ---------------------------------------------------------------------------


class SemanticPriorityClassifier:
    """Corrects misclassified consumable priorities using two-stage classification.

    Stage 1 — Keyword match: Check if title/description contains known
               consumable items. Fast path, no embeddings required.

    Stage 2 — Embedding similarity (only if Stage 1 misses):
               Encode issue text and compare against known consumable
               patterns via EmbeddingService. Handles paraphrased issues
               like "restroom supplies need replenishing" where no keyword matches.

    No LLM fallback — if Stage 2 also misses, returns original_priority
    with is_consumable=False.
    """

    def __init__(self) -> None:
        """Initialize classifier (loads taxonomy once, not per call)."""
        _load_taxonomy()
        _build_item_index()
        self._embedding_service = None  # lazy-load

    @property
    def _embed(self):
        """Lazy-load embedding service only when Stage 2 is needed."""
        if self._embedding_service is None:
            from app.services.embedding_service import get_embedding_service

            self._embedding_service = get_embedding_service()
        return self._embedding_service

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def classify_issue(
        self,
        title: str,
        description: str,
        current_priority: str,
    ) -> PriorityClassification:
        """Classify issue, correcting consumable priorities.

        Args:
            title: Issue title (e.g. "replace soap dispenser")
            description: Issue description text
            current_priority: Priority assigned by keyword classifier

        Returns:
            PriorityClassification with is_consumable and corrected_priority
        """
        # Guard against empty input
        if not title and not description:
            return self._make_result(
                is_consumable=False,
                original_priority=current_priority,
                corrected_priority=current_priority,
                reason="empty input",
                confidence=0.0,
                method="keyword",
            )

        combined = f"{title or ''} {description or ''}".strip()

        # Stage 1: Keyword match
        result = self._keyword_match(combined, current_priority)
        if result is not None:
            return result

        # Stage 2: Embedding similarity (only if Stage 1 misses)
        try:
            result = self._embedding_match(combined, current_priority)
            if result is not None:
                return result
        except Exception as e:
            logger.warning("Embedding classification failed, falling through: %s", e)

        # No match — return original priority
        return self._make_result(
            is_consumable=False,
            original_priority=current_priority,
            corrected_priority=current_priority,
            reason="no consumable match",
            confidence=0.0,
            method="none",
        )

    # -----------------------------------------------------------------------
    # Stage 1 — Keyword
    # -----------------------------------------------------------------------

    def _keyword_match(self, text: str, current_priority: str) -> PriorityClassification | None:
        """Check if text matches a known consumable item.

        Longest-match wins (more specific consumable item beats shorter).
        """
        text_lower = text.lower()
        best_match = None
        best_len = 0

        for item, (category, priority) in _ITEM_INDEX.items():
            if item in text_lower:
                if len(item) > best_len:
                    best_len = len(item)
                    best_match = (item, category, priority)

        if best_match is None:
            return None

        item, category, corrected_priority = best_match
        is_consumable = True
        reason = f"matched consumable item '{item}' in category '{category}'"

        # Priority stays the same if already LOW or if original was lower than corrected
        if corrected_priority == current_priority:
            reason += f"; priority already {corrected_priority}"
        else:
            reason += f"; priority corrected {current_priority} → {corrected_priority}"

        return self._make_result(
            is_consumable=is_consumable,
            original_priority=current_priority,
            corrected_priority=corrected_priority,
            reason=reason,
            confidence=1.0,  # Keyword match = high confidence
            method="keyword",
        )

    # -----------------------------------------------------------------------
    # Stage 2 — Embedding similarity
    # -----------------------------------------------------------------------

    # Known consumable pattern embeddings (cached as list of embedding vectors)
    _consumable_embeddings: list[tuple[str, list[float]]] | None = None

    def _embedding_match(self, text: str, current_priority: str) -> PriorityClassification | None:
        """Use embedding similarity to detect paraphrased consumables.

        Only runs when Stage 1 keyword match misses.
        Encodes text and compares against pre-cached consumable embeddings.
        """
        if not self._consumable_embeddings:
            self._consumable_embeddings = self._build_consumable_embeddings()

        if not self._consumable_embeddings:
            return None

        # Encode the issue text
        query_embedding = self._embed.embed_text(text)

        # Cosine similarity against all consumable patterns
        best_score = 0.0
        best_item = None

        for consumable_text, embedding in self._consumable_embeddings:
            score = self._cosine_similarity(query_embedding, embedding)
            if score > best_score:
                best_score = score
                best_item = consumable_text

        # Threshold: similarity must be high enough to be confident
        SIMILARITY_THRESHOLD = 0.65

        if best_score >= SIMILARITY_THRESHOLD:
            # Find the corrected priority from the item index
            item_lower = best_item.lower()
            if item_lower in _ITEM_INDEX:
                category, corrected_priority = _ITEM_INDEX[item_lower]
            else:
                corrected_priority = "LOW"  # default for embedding matches

            reason = f"embedding match '{best_item}' (score={best_score:.2f})"
            if corrected_priority != current_priority:
                reason += f"; priority corrected {current_priority} → {corrected_priority}"

            return self._make_result(
                is_consumable=True,
                original_priority=current_priority,
                corrected_priority=corrected_priority,
                reason=reason,
                confidence=best_score,  # Use similarity as confidence
                method="embedding",
            )

        return None

    def _build_consumable_embeddings(self) -> list[tuple[str, list[float]]]:
        """Pre-compute embeddings for all consumable items (once at startup)."""
        taxonomy = _load_taxonomy()
        items = []
        for category, info in taxonomy.get("consumables", {}).items():
            for item in info.get("items", []):
                items.append(item)

        if not items:
            return []

        embeddings = self._embed.embed_batch(items)
        return list(zip(items, embeddings))

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _make_result(
        is_consumable: bool,
        original_priority: str,
        corrected_priority: str,
        reason: str,
        confidence: float,
        method: str,
    ) -> PriorityClassification:
        """Construct PriorityClassification result."""
        return PriorityClassification(
            is_consumable=is_consumable,
            original_priority=original_priority,
            corrected_priority=corrected_priority,
            reason=reason,
            confidence=confidence,
            classification_method=method,
        )


# Singleton
_classifier: SemanticPriorityClassifier | None = None


def get_semantic_priority_classifier() -> SemanticPriorityClassifier:
    """Get singleton SemanticPriorityClassifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = SemanticPriorityClassifier()
    return _classifier
