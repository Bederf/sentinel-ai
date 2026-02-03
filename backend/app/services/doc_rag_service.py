"""Documentation RAG service for searching indexed .md files.

This service searches the pgvector database for documentation chunks
and provides context for the AI chat when documentation mode is enabled.
"""

import logging
from typing import Any

from app.database.supabase_client import get_supabase_client
from app.services.vector_db import get_vector_db_service
from app.services.fm_context import fm_context_service

logger = logging.getLogger(__name__)


async def search_documentation(
    query: str,
    n_results: int = 5,
    similarity_threshold: float = 0.3
) -> list[dict[str, Any]]:
    """
    Search indexed documentation for relevant content using hybrid search.

    Uses both keyword matching and semantic search to find relevant content.
    This ensures custom terms like "SIMBIOT" are found even when the embedding
    model doesn't recognize them semantically.

    Args:
        query: User's question or search query
        n_results: Maximum number of results to return
        similarity_threshold: Minimum similarity score (0-1) - not used in hybrid

    Returns:
        List of matching document chunks with content and metadata
    """
    try:
        client = get_supabase_client()
        vector_db = get_vector_db_service(client)

        # Use hybrid search to combine keyword + semantic matching
        # This ensures custom terms like "SIMBIOT" are found via keyword matching
        # even if the semantic embedding doesn't recognize them
        results = vector_db.hybrid_search(
            query=query,
            n_results=n_results,
            equipment_type=None,  # Search all documentation
            keyword_weight=0.4,   # Give keyword matching significant weight
            semantic_weight=0.6   # Still favor semantic for natural language queries
        )

        # Filter to only documentation type if needed
        # Note: hybrid_search doesn't filter by document_type, so we include all results

        logger.info(f"Documentation search for '{query[:50]}...' returned {len(results)} results")
        return results

    except Exception as e:
        logger.error(f"Error searching documentation: {e}")
        return []


def get_doc_rag_system_prompt(doc_results: list[dict[str, Any]]) -> str:
    """
    Build a system prompt that includes retrieved documentation context.

    Args:
        doc_results: Results from search_documentation()

    Returns:
        System prompt with documentation context for Claude
    """
    # Get building context for reference
    building_context = fm_context_service.get_full_context()

    # Format documentation results
    if doc_results:
        doc_sections = []
        for i, doc in enumerate(doc_results, 1):
            title = doc.get('document_title', doc.get('title', 'Documentation'))
            section = doc.get('section_title', '')
            content = doc.get('content', '')
            # Handle both hybrid_score (from hybrid search) and similarity (from semantic search)
            score = doc.get('hybrid_score') or doc.get('similarity', 0)
            # Handle case where score might be a string
            if isinstance(score, str):
                try:
                    score = float(score)
                except (ValueError, TypeError):
                    score = 0

            section_header = f"**{title}**"
            if section:
                section_header += f" > {section}"

            doc_sections.append(f"{section_header} (relevance: {score:.0%})\n{content}")

        documentation_context = "\n\n---\n\n".join(doc_sections)
    else:
        documentation_context = "No specific documentation found for this query. Answer based on your knowledge of SENTINEL and the building context below."

    prompt = f"""You are SENTINEL's documentation assistant. Your role is to answer questions about the SENTINEL BMS Intelligence Platform based on the official documentation.

## Retrieved Documentation

The following documentation sections are relevant to the user's question:

{documentation_context}

---

## Current Building Context

For reference, here is the current building data that SENTINEL is monitoring:

{building_context}

---

## Response Guidelines

1. **Answer from documentation first**: Base your answer primarily on the retrieved documentation above
2. **Reference building data**: When relevant, cite specific examples from the current building (equipment, zones, sensors)
3. **Be specific**: Quote documentation sections when explaining features or capabilities
4. **Be honest about limitations**: If asked about weaknesses, gaps, or areas for improvement, answer truthfully based on documentation. Clients respect transparency
5. **Discuss future plans openly**: The documentation includes planned features and roadmap items. Distinguish clearly between what is built today vs what is planned
6. **No device control**: In documentation mode, you explain features but don't execute device commands
7. **Use citations**: Reference document titles when citing information

When answering difficult questions (weaknesses, comparisons, future plans):
- Be direct and honest - do not oversell or hide limitations
- If a feature is planned but not built, say "This is on our roadmap" not "We do this"
- If asked about weaknesses, acknowledge them and explain our mitigation or plans
- Treat the client as a technical peer who values substance over sales pitch

Example response format:
"According to the **Safety Interlocks** documentation, SENTINEL validates all control actions through the SafetyEngine before execution. For example, temperature setpoints outside 16-28°C are blocked. In your current building (Sandton City), this applies to the 15 FCU units across all floors."

If the user asks about something not in the documentation, you can provide general information but note that it's not from official docs.

**Feature Requests:** If a user asks about functionality that doesn't exist and isn't on the roadmap, acknowledge it honestly and say: "That's not currently in SENTINEL or on our roadmap, but it's a great suggestion. I've noted it as a feature request." This feedback is valuable for product development."""

    return prompt
