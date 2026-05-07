#!/usr/bin/env python3
"""
RAG Ingestion Script — Phase 192 Equipment Manuals
Loads docs/_equipment-manuals/*.md into Supabase document_chunks table.
Generates embeddings via all-MiniLM-L6-v2 (384d) matching the schema.
Source: 'equipment_manual'
"""

import logging
import os
import sys
import uuid
from pathlib import Path

from app.services.embedding_service import get_embedding_service
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    logger.error("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    sys.exit(1)

MANUALS_DIR = Path(__file__).parent.parent.parent / "docs/_equipment-manuals"
if not MANUALS_DIR.exists():
    logger.error(f"Equipment manuals directory not found at {MANUALS_DIR}")
    sys.exit(1)

logger.info(f"Connecting to Supabase: {SUPABASE_URL}")
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

try:
    logger.info("Loading embedding model (all-MiniLM-L6-v2, 384d)...")
    es = get_embedding_service()
    _ = es.model
    logger.info("Embedding model ready")
except Exception as e:
    logger.warning(f"Embedding model not available ({e}) — skipping vector embedding generation")
    es = None


def parse_frontmatter(content: str) -> dict:
    """Parse markdown frontmatter into key-value pairs."""
    frontmatter = {}
    if content.startswith("---"):
        end = content.find("\n---\n", 4)
        if end != -1:
            block = content[4:end]
            for line in block.split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    frontmatter[key.strip().lower()] = val.strip()
    return frontmatter


def split_into_chunks(content: str, chunk_size: int = 800) -> list[dict]:
    """Split markdown content into semantic chunks."""
    chunks = []
    lines = content.split("\n")
    current_section = ""
    current_body: list[str] = []
    chunk_index = 0

    def save_chunk():
        nonlocal chunk_index, current_section, current_body
        if current_body:
            text = "\n".join(current_body).strip()
            if text:
                chunks.append(
                    {
                        "chunk_id": f"chunk_{chunk_index:04d}",
                        "section": current_section,
                        "content": text,
                    }
                )
            chunk_index += 1
            current_body = []

    for line in lines:
        if line.startswith("## ") or line.startswith("### "):
            save_chunk()
            current_section = line.lstrip("#").strip()
            current_body.append(line)
        else:
            current_body.append(line)

    save_chunk()
    return chunks


def get_equipment_type(code: str) -> str:
    """Extract equipment type from site code like S002-CHILLER-B1-001."""
    parts = code.split("-")
    if len(parts) >= 2:
        return parts[1].lower()
    return "unknown"


inserted_docs: dict[str, str] = {}
chunk_count = 0
batch_size = 50

md_files = sorted(MANUALS_DIR.glob("*.md"))
logger.info(f"Found {len(md_files)} equipment manual files")

for md_file in md_files:
    content = md_file.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(content)

    code = frontmatter.get("code", md_file.stem.upper().replace("-", "_"))
    title = frontmatter.get("title", md_file.stem)
    manufacturer = frontmatter.get("manufacturer", "")
    model = frontmatter.get("model", "")

    doc_type = "technical_bulletin"

    doc_record = {
        "code": code,
        "title": title,
        "document_type": doc_type,
        "equipment_type": get_equipment_type(code),
        "manufacturer": manufacturer,
        "model": model,
        "source": "system_docs",
        "indexing_status": "pending",
    }

    logger.info(f"  Inserting document: {code}")
    try:
        result = supabase.table("documents").upsert(doc_record, on_conflict="code").execute()
        if result.data:
            inserted_docs[code] = result.data[0]["id"]
        else:
            logger.warning(f"  Failed to insert document {code}: {result.error}")
            continue
    except Exception as e:
        logger.error(f"  Document upsert failed for {code}: {e}")
        continue

    chunks = split_into_chunks(content)
    logger.info(f"  {len(chunks)} chunks extracted from {md_file.name}")

    for chunk in chunks:
        embedding = None
        if es is not None:
            try:
                embedding = es.embed_text(chunk["content"])
            except Exception as e:
                logger.warning(f"  Embedding failed for {chunk['chunk_id']}: {e}")

        rec = {
            "id": str(uuid.uuid4()),
            "document_id": inserted_docs[code],
            "chunk_index": int(chunk["chunk_id"].split("_")[-1]),
            "content": chunk["content"],
            "content_length": len(chunk["content"]),
            "section_title": chunk.get("section", ""),
            "equipment_type": get_equipment_type(code),
            "document_type": doc_type,
            "keywords": [],
            "embedding": embedding,
        }

        try:
            supabase.table("document_chunks").insert(rec).execute()
            chunk_count += 1
        except Exception as e:
            logger.error(f"  Chunk insert failed: {e}")

    logger.info(f"  Inserted {len(chunks)} chunks for {code}")

logger.info(f"Total documents: {len(inserted_docs)}")
logger.info(f"Total chunks inserted: {chunk_count}")
logger.info("Equipment manual RAG ingestion complete.")
