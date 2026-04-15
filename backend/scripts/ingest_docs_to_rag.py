#!/usr/bin/env python3
"""Ingest markdown documentation files into RAG system.

This script indexes .md files from the project into Supabase pgvector
for semantic search by the AI chat system.

Usage:
    cd backend && source venv/bin/activate
    python scripts/ingest_docs_to_rag.py
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import List

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.supabase_client import get_supabase_client  # noqa: E402
from app.services.embedding_service import get_embedding_service  # noqa: E402
from app.services.vector_db import get_vector_db_service  # noqa: E402

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Directories to skip
SKIP_DIRS = {"node_modules", "venv", ".git", "__pycache__", "dist"}

# Specific .planning subdirs to include (everything else in .planning is skipped)
# Phase planning docs are NOT indexed to RAG — GSD master reads them directly from disk.
# Only approved security/governance docs (FSR gap analysis) are indexed.
PLANNING_INCLUDE_DIRS = {
    ".planning/phases/64-risk-governance-foundation",
}

# Priority documentation files (indexed first) - system docs only
PRIORITY_DOCS = [
    "docs/02-architecture/system-overview.md",
    "docs/04-features/demo-simulation-control.md",
    "docs/06-safety-compliance/safety-interlocks-engine.md",
    "docs/06-safety-compliance/audit-logging.md",
    "docs/03-api-reference/mcp-tools-reference.md",
    # Security & risk governance
    "docs/09-security/SECURITY-PRIVACY.md",
    "docs/09-security/information-security-framework.md",
    "docs/09-security/information-security-policy.md",
    "docs/09-security/data-privacy-policy.md",
    "docs/09-security/incident-response-policy.md",
    "docs/09-security/business-continuity-policy.md",
    "docs/09-security/information-security-risk-register.md",
    "docs/09-security/third-party-security-register.md",
    ".planning/phases/64-risk-governance-foundation/FSR-GAP-ANALYSIS.md",
    # Contract management
    "docs/04-features/48-contract-management.md",
    "docs/03-api-reference/contracts-api.md",
]


def find_md_files(root: Path, skip_dirs: set) -> List[Path]:
    """Find all .md files in project, excluding specified directories.

    System-documentation mode:
    - include files under docs/
    - include explicitly allowed .planning subdirs
    - exclude all other repository markdown (memories, local notes, backups, etc.)
    """
    md_files = []

    for path in root.rglob("*.md"):
        # Skip if any parent directory is in skip list
        if any(skip in path.parts for skip in skip_dirs):
            continue

        relative = str(path.relative_to(root))

        in_docs = relative.startswith("docs/")
        in_allowed_planning = any(relative.startswith(inc) for inc in PLANNING_INCLUDE_DIRS)
        if not (in_docs or in_allowed_planning):
            continue

        md_files.append(path)

    return md_files


def extract_title_from_md(content: str, filepath: Path) -> str:
    """Extract title from markdown content or use filename."""
    lines = content.split("\n")
    for line in lines[:10]:  # Check first 10 lines
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()

    # Fallback to filename
    return filepath.stem.replace("-", " ").replace("_", " ").title()


def get_doc_category(filepath: Path) -> str:
    """Determine document category from filepath."""
    path_str = str(filepath.relative_to(PROJECT_ROOT))

    if "docs/02-architecture" in path_str:
        return "architecture"
    elif "docs/03-api-reference" in path_str:
        return "api"
    elif "docs/04-features" in path_str:
        return "features"
    elif "docs/05-integrations" in path_str:
        return "integrations"
    elif "docs/06-safety" in path_str:
        return "safety"
    elif "docs/09-security" in path_str:
        return "security"
    elif "docs/10-operations" in path_str:
        return "operations"
    elif "docs/11-testing" in path_str:
        return "testing"
    elif "docs/14-regional" in path_str:
        return "regional"
    elif "docs/15-business-context" in path_str:
        return "business"
    elif ".planning/phases/64-risk-governance" in path_str:
        return "security"
    elif "SECURITY-PRIVACY" in path_str:
        return "security"
    elif "FEATURES.md" in path_str:
        return "features"
    elif "CLAUDE.md" in path_str:
        return "system"
    elif "README" in path_str:
        return "overview"
    else:
        return "general"


# Map category to valid document_type (matches 028_expand_document_types.sql constraint)
CATEGORY_TO_DOC_TYPE = {
    "api": "api_reference",
    "integrations": "integration_guide",
    "safety": "safety_procedure",
    "security": "system_documentation",
    "architecture": "system_documentation",
    "features": "system_documentation",
    "testing": "system_documentation",
    "operations": "system_documentation",
    "business": "system_documentation",
    "regional": "system_documentation",
    "system": "system_documentation",
    "overview": "system_documentation",
    "general": "system_documentation",
}


async def main():
    """Main ingestion function."""
    print("Documentation RAG Ingestion Script")
    print("=" * 50)

    # Initialize services
    client = get_supabase_client()
    embedding_service = get_embedding_service()
    vector_db = get_vector_db_service(client)

    print("\nEmbedding model: all-MiniLM-L6-v2")
    print(f"Vector dimensions: {embedding_service.get_embedding_dimension()}")

    # Find all .md files
    print("\n1. Scanning for documentation files...")
    all_files = find_md_files(PROJECT_ROOT, SKIP_DIRS)
    print(f"   Found {len(all_files)} markdown files")

    # Sort to process priority docs first
    priority_paths = [PROJECT_ROOT / p for p in PRIORITY_DOCS]
    priority_files = [f for f in all_files if f in priority_paths]
    other_files = [f for f in all_files if f not in priority_paths]
    sorted_files = priority_files + other_files

    print(f"   Priority documents: {len(priority_files)}")

    # Process each file
    print("\n2. Ingesting documentation...")
    total_docs = 0
    total_chunks = 0

    for filepath in sorted_files:
        try:
            relative_path = filepath.relative_to(PROJECT_ROOT)

            # Read content
            content = filepath.read_text(encoding="utf-8")
            if not content.strip():
                continue

            # Extract metadata
            title = extract_title_from_md(content, filepath)
            category = get_doc_category(filepath)
            code = f"DOC-{relative_path}".replace("/", "-").replace(".md", "")

            # Check if already exists
            existing = client.table("documents").select("id").eq("code", code).execute()
            if existing.data:
                print(f"   Skipping (exists): {relative_path}")
                continue

            # Map category to valid document_type
            doc_type = CATEGORY_TO_DOC_TYPE.get(category, "system_documentation")

            # Add document
            doc_result = vector_db.add_document(
                code=code,
                title=title,
                document_type=doc_type,
                equipment_type="system",  # General system documentation
                full_text=content,
                source="system_docs",
                summary=f"Documentation: {category} - {title}",
                keywords=[category, "sentinel", "bms", "documentation"],
            )

            if doc_result:
                doc_id = doc_result["id"]

                # Chunk and embed
                chunk_count = vector_db.chunk_and_embed_document(doc_id, chunk_size=800, chunk_overlap=100)

                print(f"   Indexed: {relative_path} ({chunk_count} chunks)")
                total_docs += 1
                total_chunks += chunk_count

        except Exception as e:
            print(f"   Error processing {filepath}: {e}")

    # Summary
    print("\n" + "=" * 50)
    print("Ingestion Complete!")
    print(f"\n  Documents indexed: {total_docs}")
    print(f"  Total chunks created: {total_chunks}")

    # Get counts
    try:
        doc_count = client.table("documents").select("id", count="exact").execute().count or 0
        chunk_count = client.table("document_chunks").select("id", count="exact").execute().count or 0

        print("\nDatabase totals:")
        print(f"  Documents: {doc_count}")
        print(f"  Chunks: {chunk_count}")
    except Exception as e:
        print(f"Error getting counts: {e}")

    # Test search
    print("\n" + "=" * 50)
    print("Testing documentation search...")

    test_queries = [
        "What features does SENTINEL have?",
        "How does the safety system work?",
        "What is the hybrid AI architecture?",
        "How do I control devices?",
        "What is the information security risk register?",
        "How does incident response work?",
        "What is the FirstRand security gap analysis?",
        "POPIA data privacy policy",
        "What is our SLA for the Sandton contract?",
        "How does contract management work?",
    ]

    for query in test_queries:
        print(f"\nQuery: '{query}'")
        results = vector_db.search(query, n_results=2, document_type="documentation", similarity_threshold=0.3)
        if results:
            for r in results:
                title = r.get("document_title", r.get("title", "Unknown"))
                sim = r.get("similarity", 0)
                print(f"  - {title} (similarity: {sim:.3f})")
        else:
            print("  No results found")


if __name__ == "__main__":
    asyncio.run(main())
