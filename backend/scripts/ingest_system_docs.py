#!/usr/bin/env python3
"""Ingest SENTINEL system documentation into Supabase RAG.

Reads all markdown files from docs/, chunks them, generates embeddings,
and stores them in the documents + document_chunks tables for semantic search.

Usage:
    cd backend && source venv/bin/activate
    python scripts/ingest_system_docs.py
    python scripts/ingest_system_docs.py --force  # Re-ingest all (deletes existing)
"""

import asyncio
import sys
import os
import re
import hashlib
from pathlib import Path
from typing import Optional

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.supabase_client import get_supabase_client
from app.services.embedding_service import get_embedding_service
from app.services.vector_db import get_vector_db_service

# Project root
PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DOCS_DIR = PROJECT_ROOT / "docs"

# Map doc directories to equipment types and document types
DOC_CATEGORY_MAP = {
    "01-getting-started": ("general", "system_documentation"),
    "02-architecture": ("general", "system_documentation"),
    "03-api-reference": ("general", "api_reference"),
    "04-features": ("general", "system_documentation"),
    "05-bms-concepts": ("general", "system_documentation"),
    "05-integrations": ("general", "integration_guide"),
    "06-safety-compliance": ("general", "safety_procedure"),
    "07-integrations": ("general", "integration_guide"),
    "08-ai-ml": ("general", "system_documentation"),
    "11-testing": ("general", "system_documentation"),
    "12-development": ("general", "system_documentation"),
    "13-modules": ("general", "system_documentation"),
    "14-south-africa-context": ("general", "system_documentation"),
    "16-glossary": ("general", "system_documentation"),
}

# Override equipment_type for specific files
EQUIPMENT_TYPE_OVERRIDES = {
    "tridium-niagara-integration.md": "niagara",
    "dali-hvac-integration.md": "dali",
    "energy-centre.md": "generator",
    "cafm-schema.md": "general",
    "hvac-systems.md": "hvac",
    "safety-interlocks-engine.md": "general",
    "mcp-tools-reference.md": "general",
    "load-shedding-optimization.md": "general",
}


def extract_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from markdown."""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not match:
        return {}

    frontmatter = {}
    for line in match.group(1).split('\n'):
        if ':' in line:
            key, _, value = line.partition(':')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if value.startswith('[') and value.endswith(']'):
                # Parse simple arrays
                value = [v.strip().strip('"').strip("'") for v in value[1:-1].split(',')]
            frontmatter[key] = value
    return frontmatter


def strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from markdown content."""
    return re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, count=1, flags=re.DOTALL)


def extract_title(content: str) -> str:
    """Extract title from first H1 heading."""
    match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "Untitled"


def extract_summary(content: str, max_length: int = 500) -> str:
    """Extract first paragraph as summary."""
    stripped = strip_frontmatter(content)
    # Skip the title line
    lines = stripped.strip().split('\n')
    summary_lines = []
    started = False
    for line in lines:
        stripped_line = line.strip()
        if not started:
            if stripped_line and not stripped_line.startswith('#'):
                started = True
                summary_lines.append(stripped_line)
        elif stripped_line == '' and summary_lines:
            break
        elif stripped_line.startswith('#'):
            break
        else:
            summary_lines.append(stripped_line)

    summary = ' '.join(summary_lines)
    if len(summary) > max_length:
        summary = summary[:max_length] + "..."
    return summary


def extract_keywords(content: str, frontmatter: dict) -> list:
    """Extract keywords from frontmatter tags and content."""
    keywords = []
    if isinstance(frontmatter.get('tags'), list):
        keywords.extend(frontmatter['tags'])

    # Add domain if present
    if frontmatter.get('domain'):
        keywords.append(frontmatter['domain'])

    return list(set(keywords))


def get_doc_code(filepath: Path) -> str:
    """Generate unique code for document from its path."""
    relative = filepath.relative_to(DOCS_DIR)
    return f"DOC-{str(relative).replace('/', '-').replace('.md', '').upper()}"


def get_doc_category(filepath: Path) -> tuple:
    """Get equipment_type and document_type for a file based on its directory."""
    relative = filepath.relative_to(DOCS_DIR)
    parts = relative.parts

    # Check directory mapping
    if parts[0] in DOC_CATEGORY_MAP:
        equipment_type, document_type = DOC_CATEGORY_MAP[parts[0]]
    else:
        equipment_type, document_type = "general", "system_documentation"

    # Check filename overrides
    filename = filepath.name
    if filename in EQUIPMENT_TYPE_OVERRIDES:
        equipment_type = EQUIPMENT_TYPE_OVERRIDES[filename]

    return equipment_type, document_type


def content_hash(content: str) -> str:
    """Generate hash for content change detection."""
    return hashlib.md5(content.encode()).hexdigest()


async def main():
    """Main ingestion function."""
    force = '--force' in sys.argv

    print("SENTINEL System Documentation RAG Ingestion")
    print("=" * 55)

    # Initialize services
    client = get_supabase_client()
    embedding_service = get_embedding_service()
    vector_db = get_vector_db_service(client)

    print(f"Embedding model: all-MiniLM-L6-v2")
    print(f"Vector dimensions: {embedding_service.get_embedding_dimension()}")
    print(f"Docs directory: {DOCS_DIR}")
    print(f"Force re-ingest: {force}")

    # Collect all markdown files
    md_files = sorted(DOCS_DIR.rglob("*.md"))
    # Exclude templates directory
    md_files = [f for f in md_files if '/_templates/' not in str(f)]

    print(f"\nFound {len(md_files)} markdown files")

    if force:
        print("\n[FORCE] Deleting existing system documentation entries...")
        try:
            # Delete chunks first (FK constraint)
            existing_docs = client.table('documents').select('id').eq('source', 'system_docs').execute()
            if existing_docs.data:
                doc_ids = [d['id'] for d in existing_docs.data]
                for doc_id in doc_ids:
                    client.table('document_chunks').delete().eq('document_id', doc_id).execute()
                client.table('documents').delete().eq('source', 'system_docs').execute()
                print(f"   Deleted {len(doc_ids)} existing documents and their chunks")
        except Exception as e:
            print(f"   Error cleaning up: {e}")

    # Process each file
    added = 0
    updated = 0
    skipped = 0
    errors = 0

    print(f"\nProcessing documents...")

    for filepath in md_files:
        relative = filepath.relative_to(DOCS_DIR)
        code = get_doc_code(filepath)
        equipment_type, document_type = get_doc_category(filepath)

        try:
            content = filepath.read_text(encoding='utf-8')
        except Exception as e:
            print(f"  ERROR reading {relative}: {e}")
            errors += 1
            continue

        # Skip very short files
        text_content = strip_frontmatter(content)
        if len(text_content.strip()) < 100:
            print(f"  SKIP (too short): {relative}")
            skipped += 1
            continue

        frontmatter = extract_frontmatter(content)
        title = frontmatter.get('title') or extract_title(text_content)
        summary = extract_summary(content)
        keywords = extract_keywords(content, frontmatter)
        file_hash = content_hash(content)

        # Check if document already exists
        if not force:
            try:
                existing = client.table('documents').select('id, summary').eq('code', code).execute()
                if existing.data:
                    # Check if content changed (use summary as proxy for simple hash)
                    print(f"  SKIP (exists): {relative}")
                    skipped += 1
                    continue
            except Exception:
                pass

        # Add document
        try:
            doc_data = {
                'code': code,
                'title': title,
                'document_type': document_type,
                'equipment_type': equipment_type,
                'full_text': text_content,
                'source': 'system_docs',
                'summary': summary,
                'keywords': keywords,
                'indexing_status': 'pending'
            }

            result = client.table('documents').insert(doc_data).execute()
            if result.data:
                doc_id = result.data[0]['id']

                # Chunk and embed with section-aware markdown chunking
                # + context-enhanced embeddings (title/heading/type prepended)
                chunk_count = vector_db.chunk_and_embed_markdown(
                    doc_id,
                    doc_title=title,
                    doc_type=document_type,
                )
                print(f"  ADD: {relative} ({chunk_count} chunks, type={document_type})")
                added += 1
            else:
                print(f"  ERROR (no data): {relative}")
                errors += 1

        except Exception as e:
            error_msg = str(e)
            if 'duplicate key' in error_msg:
                print(f"  SKIP (duplicate): {relative}")
                skipped += 1
            else:
                print(f"  ERROR: {relative}: {error_msg[:100]}")
                errors += 1

    # Summary
    print(f"\n{'=' * 55}")
    print(f"Ingestion Complete!")
    print(f"  Added:   {added}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors:  {errors}")

    # Get counts
    try:
        doc_count = client.table('documents').select('id', count='exact').execute().count or 0
        chunk_count = client.table('document_chunks').select('id', count='exact').execute().count or 0
        knowledge_count = client.table('equipment_knowledge').select('id', count='exact').execute().count or 0

        print(f"\nTotal RAG content:")
        print(f"  Documents:       {doc_count}")
        print(f"  Document chunks: {chunk_count}")
        print(f"  Knowledge base:  {knowledge_count}")
    except Exception as e:
        print(f"Error getting counts: {e}")

    # Test search with system docs
    print(f"\n{'=' * 55}")
    print("Testing system documentation search...")

    test_queries = [
        ("niagara bacnet integration", None),
        ("point discovery classification", None),
        ("safety interlocks engine", None),
        ("remote operations dispatch", None),
        ("obix historical data alarms", None),
    ]

    for query, eq_type in test_queries:
        print(f"\nQuery: '{query}'")
        results = vector_db.search(query, n_results=3, similarity_threshold=0.2)
        if results:
            for r in results:
                title = r.get('section_title') or r.get('document_type', 'unknown')
                sim = r.get('similarity', 0)
                content_preview = r.get('content', '')[:80]
                print(f"  [{sim:.3f}] {title}: {content_preview}...")
        else:
            print("  No results found")


if __name__ == "__main__":
    asyncio.run(main())
