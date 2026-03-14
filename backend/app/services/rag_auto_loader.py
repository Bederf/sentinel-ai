"""
RAG Auto-Loader
================
Automatically ingests system documentation and equipment knowledge into
the RAG vector store on startup. Skips if documents are already indexed.

Called from startup/events.py in a background thread to avoid blocking
the application startup.
"""

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent  # /opt/bms-intelligence
DOCS_DIR = PROJECT_ROOT / "docs"
BACKEND_DIR = PROJECT_ROOT / "backend"


def _count_indexed_docs() -> int:
    """Count documents already in the RAG store."""
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        if not client:
            return 0
        result = client.table("documents").select("id", count="exact").execute()
        return result.count if result.count is not None else len(result.data or [])
    except Exception:
        return 0


def _count_knowledge_entries() -> int:
    """Count equipment knowledge entries already indexed."""
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        if not client:
            return 0
        result = client.table("equipment_knowledge").select("id", count="exact").execute()
        return result.count if result.count is not None else len(result.data or [])
    except Exception:
        return 0


def auto_load_rag():
    """Run RAG ingestion if the vector store is empty or sparse.

    Designed to run in a background thread on startup.
    Safe to call multiple times — skips if already populated.
    """
    start = time.time()

    try:
        doc_count = _count_indexed_docs()
        knowledge_count = _count_knowledge_entries()

        logger.info(
            "RAG auto-loader: %d documents, %d knowledge entries in store",
            doc_count,
            knowledge_count,
        )

        needs_docs = doc_count < 10  # Less than 10 docs = needs ingestion
        needs_knowledge = knowledge_count < 5  # Less than 5 entries = needs ingestion

        if not needs_docs and not needs_knowledge:
            logger.info("RAG auto-loader: store already populated, skipping ingestion")
            return

        # Import ingestion functions — these are heavy (embedding model, etc.)

        if needs_knowledge:
            _ingest_equipment_knowledge()

        if needs_docs:
            _ingest_system_docs()

        elapsed = time.time() - start
        logger.info("RAG auto-loader: completed in %.1fs", elapsed)

    except Exception as e:
        logger.error("RAG auto-loader failed: %s", e, exc_info=True)


def _ingest_equipment_knowledge():
    """Ingest equipment fault codes and maintenance knowledge."""
    import asyncio

    try:
        logger.info("RAG auto-loader: ingesting equipment knowledge...")

        # Import the knowledge data and ingestion logic from the script
        import importlib.util

        script_path = BACKEND_DIR / "scripts" / "ingest_rag_knowledge.py"

        if not script_path.exists():
            logger.warning("RAG auto-loader: ingest_rag_knowledge.py not found at %s", script_path)
            return

        # Load the script as a module
        spec = importlib.util.spec_from_file_location("ingest_rag_knowledge", script_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Run its main function
        if hasattr(mod, "main"):
            asyncio.run(mod.main())
            logger.info("RAG auto-loader: equipment knowledge ingestion complete")
        else:
            logger.warning("RAG auto-loader: ingest_rag_knowledge.py has no main() function")

    except Exception as e:
        logger.error("RAG auto-loader: equipment knowledge ingestion failed: %s", e)


def _ingest_system_docs():
    """Ingest system documentation from docs/ directory."""
    import asyncio

    try:
        logger.info("RAG auto-loader: ingesting system documentation...")

        import importlib.util

        script_path = BACKEND_DIR / "scripts" / "ingest_system_docs.py"

        if not script_path.exists():
            logger.warning("RAG auto-loader: ingest_system_docs.py not found at %s", script_path)
            return

        spec = importlib.util.spec_from_file_location("ingest_system_docs", script_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if hasattr(mod, "main"):
            asyncio.run(mod.main())
            logger.info("RAG auto-loader: system docs ingestion complete")
        else:
            logger.warning("RAG auto-loader: ingest_system_docs.py has no main() function")

    except Exception as e:
        logger.error("RAG auto-loader: system docs ingestion failed: %s", e)
