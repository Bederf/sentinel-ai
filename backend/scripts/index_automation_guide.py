#!/usr/bin/env python3
"""
Index the Automation Specialist Guide in the RAG system.

This script reads the AUTOMATION_SPECIALIST_GUIDE.md and adds it to the
RAG system so that the AI chat can retrieve and reference it when answering
automation specialist questions.

Usage:
    python backend/scripts/index_automation_guide.py
"""

import sys
import asyncio
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.supabase_client import get_supabase_client
from app.services.vector_db import get_vector_db_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def index_guide():
    """Index the Automation Specialist Integration Guide."""

    guide_path = Path(__file__).parent.parent.parent / "docs" / "05-integration" / "AUTOMATION_SPECIALIST_GUIDE.md"

    if not guide_path.exists():
        logger.error(f"Guide not found at {guide_path}")
        return False

    logger.info(f"Reading guide from {guide_path}")
    with open(guide_path, "r") as f:
        full_text = f.read()

    client = get_supabase_client()
    if not client:
        logger.error("Failed to connect to Supabase")
        return False

    vector_db = get_vector_db_service(client)

    # Add document to RAG system
    logger.info("Adding document to RAG system...")
    doc = vector_db.add_document(
        code="AUTOMATION_SPECIALIST_GUIDE",
        title="Automation Specialist Integration Guide",
        document_type="integration_guide",
        equipment_type="all",  # Applies to all equipment types
        full_text=full_text,
        source="internal_documentation",
        summary="Comprehensive guide for automation specialists integrating external systems with SENTINEL BMS. Covers device control APIs, safety interlocks, real-time streaming, work order automation, and common integration scenarios.",
        keywords=[
            "integration", "automation", "API", "device control", "real-time data",
            "work orders", "webhooks", "MQTT", "BACnet", "Modbus", "DALI",
            "safety interlocks", "REST API", "WebSocket", "alerts",
            "equipment control", "maintenance", "predictive", "workflow"
        ],
        failure_modes=None
    )

    if not doc:
        logger.error("Failed to add document")
        return False

    logger.info(f"Document added with ID: {doc['id']}")

    # Chunk and embed the document
    logger.info("Chunking and embedding document...")
    chunk_count = vector_db.chunk_and_embed_document(doc['id'])

    if chunk_count > 0:
        logger.info(f"✓ Successfully indexed guide with {chunk_count} chunks")
        logger.info("\nThe Automation Specialist Integration Guide is now available to the AI chat.")
        logger.info("Automation specialists can ask questions like:")
        logger.info("  - 'How do I control HVAC devices via the API?'")
        logger.info("  - 'What are the safety constraints for device control?'")
        logger.info("  - 'How do I integrate real-time data streaming?'")
        logger.info("  - 'How do I set up work order webhooks?'")
        return True
    else:
        logger.error("Failed to chunk and embed document")
        return False


if __name__ == "__main__":
    success = asyncio.run(index_guide())
    sys.exit(0 if success else 1)
