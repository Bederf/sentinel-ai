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
    Search indexed documentation for relevant content.

    Args:
        query: User's question or search query
        n_results: Maximum number of results to return
        similarity_threshold: Minimum similarity score (0-1)

    Returns:
        List of matching document chunks with content and metadata
    """
    try:
        client = get_supabase_client()
        vector_db = get_vector_db_service(client)

        # Search for documentation type documents
        results = vector_db.search(
            query=query,
            n_results=n_results,
            document_type="documentation",
            similarity_threshold=similarity_threshold
        )

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
            similarity = doc.get('similarity', 0)

            section_header = f"**{title}**"
            if section:
                section_header += f" > {section}"

            doc_sections.append(f"{section_header} (relevance: {similarity:.0%})\n{content}")

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
4. **Acknowledge gaps**: If the documentation doesn't cover the question, say so clearly
5. **No device control**: In documentation mode, you explain features but don't execute device commands
6. **Use citations**: Reference document titles when citing information

Example response format:
"According to the **Safety Interlocks** documentation, SENTINEL validates all control actions through the SafetyEngine before execution. For example, temperature setpoints outside 16-28°C are blocked. In your current building (Sandton City), this applies to the 15 FCU units across all floors."

If the user asks about something not in the documentation, you can provide general information but note that it's not from official docs."""

    return prompt
