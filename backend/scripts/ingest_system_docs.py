#!/usr/bin/env python3
"""Ingest SENTINEL system documentation into Supabase RAG.

Reads all markdown files from docs/, chunks them, generates embeddings,
and stores them in the documents + document_chunks tables for semantic search.

Usage:
    cd backend && source venv/bin/activate
    python scripts/ingest_system_docs.py                    # Incremental: skip unchanged
    python scripts/ingest_system_docs.py --force             # Full re-ingest (deletes + re-embeds all)
    python scripts/ingest_system_docs.py --file=docs/09-security/control-matrix.md  # Single doc
"""

import asyncio
import hashlib
import os
import re
import sys
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.supabase_client import get_supabase_client
from app.services.embedding_service import get_embedding_service
from app.services.vector_db import get_vector_db_service

# Project root
PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DOCS_DIR = PROJECT_ROOT / "docs"

# Extra directories outside docs/ to scan for RAG ingestion
EXTRA_SCAN_DIRS = [
    PROJECT_ROOT / ".planning" / "phases" / "64-risk-governance-foundation",
]

# Map doc directories to equipment types and document types
DOC_CATEGORY_MAP = {
    "01-getting-started": ("general", "system_documentation"),
    "02-architecture": ("general", "system_documentation"),
    "03-api-reference": ("general", "api_reference"),
    "04-features": ("general", "system_documentation"),
    "05-integrations": ("general", "integration_guide"),
    "06-safety-compliance": ("general", "safety_procedure"),
    "08-ai-ml": ("general", "system_documentation"),
    "09-security": ("security", "security_policy"),
    "10-operations": ("general", "system_documentation"),
    "11-testing": ("general", "system_documentation"),
    "12-development": ("general", "system_documentation"),
    "13-modules": ("general", "system_documentation"),
    "14-regional": ("general", "system_documentation"),
    "15-business-context": ("general", "system_documentation"),
    "16-glossary": ("general", "system_documentation"),
    "_archive": ("general", "system_documentation"),
}

# Map extra scan dirs to categories (for files outside docs/)
EXTRA_DIR_CATEGORY_MAP = {
    "64-risk-governance-foundation": ("security", "security_policy"),
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
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return {}

    frontmatter = {}
    for line in match.group(1).split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if value.startswith("[") and value.endswith("]"):
                # Parse simple arrays
                value = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",")]
            frontmatter[key] = value
    return frontmatter


def strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from markdown content."""
    return re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, count=1, flags=re.DOTALL)


def extract_title(content: str) -> str:
    """Extract title from first H1 heading."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "Untitled"


def extract_summary(content: str, max_length: int = 500) -> str:
    """Extract first paragraph as summary."""
    stripped = strip_frontmatter(content)
    # Skip the title line
    lines = stripped.strip().split("\n")
    summary_lines = []
    started = False
    for line in lines:
        stripped_line = line.strip()
        if not started:
            if stripped_line and not stripped_line.startswith("#"):
                started = True
                summary_lines.append(stripped_line)
        elif (stripped_line == "" and summary_lines) or stripped_line.startswith("#"):
            break
        else:
            summary_lines.append(stripped_line)

    summary = " ".join(summary_lines)
    if len(summary) > max_length:
        summary = summary[:max_length] + "..."
    return summary


def extract_keywords(content: str, frontmatter: dict) -> list:
    """Extract keywords from frontmatter tags and content."""
    keywords = []
    if isinstance(frontmatter.get("tags"), list):
        keywords.extend(frontmatter["tags"])

    # Add domain if present
    if frontmatter.get("domain"):
        keywords.append(frontmatter["domain"])

    return list(set(keywords))


def get_doc_code(filepath: Path) -> str:
    """Generate unique code for document from its path."""
    try:
        relative = filepath.relative_to(DOCS_DIR)
        return f"DOC-{str(relative).replace('/', '-').replace('.md', '').upper()}"
    except ValueError:
        # File is outside docs/ (e.g. .planning/)
        relative = filepath.relative_to(PROJECT_ROOT)
        return f"DOC-{str(relative).replace('/', '-').replace('.md', '').upper()}"


def get_doc_category(filepath: Path) -> tuple:
    """Get equipment_type and document_type for a file based on its directory."""
    # Check if file is inside docs/
    try:
        relative = filepath.relative_to(DOCS_DIR)
        parts = relative.parts

        # Check directory mapping
        equipment_type, document_type = DOC_CATEGORY_MAP.get(parts[0], ("general", "system_documentation"))
    except ValueError:
        # File is outside docs/ — check extra dir mappings
        equipment_type, document_type = "general", "system_documentation"
        for dir_name, category in EXTRA_DIR_CATEGORY_MAP.items():
            if dir_name in filepath.parts:
                equipment_type, document_type = category
                break

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
    force = "--force" in sys.argv
    single_file = None
    for arg in sys.argv:
        if arg.startswith("--file="):
            single_file = arg[7:]

    print("SENTINEL System Documentation RAG Ingestion")
    print("=" * 55)

    # Initialize services
    client = get_supabase_client()
    embedding_service = get_embedding_service()
    vector_db = get_vector_db_service(client)

    print("Embedding model: all-MiniLM-L6-v2")
    print(f"Vector dimensions: {embedding_service.get_embedding_dimension()}")
    print(f"Docs directory: {DOCS_DIR}")
    print(f"Force re-ingest: {force}")

    # Collect all markdown files from docs/
    if single_file:
        # Target a specific file
        target = Path(single_file)
        if not target.is_absolute():
            target = PROJECT_ROOT / target
        if target.exists():
            md_files = [target]
            print(f"\nTargeting single file: {target}")
        else:
            print(f"\nFile not found: {target}")
            return
    else:
        md_files = sorted(DOCS_DIR.rglob("*.md"))
        # Exclude templates directory
        md_files = [f for f in md_files if "/_templates/" not in str(f)]

        # Also collect from extra scan directories
        extra_count = 0
        for extra_dir in EXTRA_SCAN_DIRS:
            if extra_dir.exists():
                extra_files = sorted(extra_dir.rglob("*.md"))
                md_files.extend(extra_files)
                extra_count += len(extra_files)

        print(f"\nFound {len(md_files)} markdown files ({extra_count} from extra scan dirs)")

    if force:
        print("\n[FORCE] Deleting existing system documentation entries...")
        try:
            # Delete chunks first (FK constraint)
            existing_docs = client.table("documents").select("id").eq("source", "system_docs").execute()
            if existing_docs.data:
                doc_ids = [d["id"] for d in existing_docs.data]
                for doc_id in doc_ids:
                    client.table("document_chunks").delete().eq("document_id", doc_id).execute()
                client.table("documents").delete().eq("source", "system_docs").execute()
                print(f"   Deleted {len(doc_ids)} existing documents and their chunks")
        except Exception as e:
            print(f"   Error cleaning up: {e}")

    # Process each file
    added = 0
    skipped = 0
    errors = 0

    print("\nProcessing documents...")

    for i, filepath in enumerate(md_files):
        # Display path relative to project root (works for any file location)
        try:
            relative = filepath.relative_to(DOCS_DIR)
        except ValueError:
            relative = filepath.relative_to(PROJECT_ROOT)

        code = get_doc_code(filepath)
        equipment_type, document_type = get_doc_category(filepath)

        try:
            content = filepath.read_text(encoding="utf-8")
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
        title = frontmatter.get("title") or extract_title(text_content)
        summary = extract_summary(content)
        keywords = extract_keywords(content, frontmatter)
        _file_hash = content_hash(content)

        # Check if document already exists — incremental update logic
        do_insert = True
        doc_id = None
        if not force:
            try:
                existing = client.table("documents").select("id, full_text").eq("code", code).execute()
                if existing.data:
                    existing_text = existing.data[0].get("full_text", "")
                    if existing_text == text_content:
                        print(f"  SKIP (unchanged): {relative}")
                        skipped += 1
                        continue
                    else:
                        # Content changed — update existing record and re-embed
                        doc_id = existing.data[0]["id"]
                        client.table("documents").update(
                            {
                                "title": title,
                                "document_type": document_type,
                                "equipment_type": equipment_type,
                                "full_text": text_content,
                                "summary": summary,
                                "keywords": keywords,
                                "indexing_status": "pending",
                            }
                        ).eq("id", doc_id).execute()
                        client.table("document_chunks").delete().eq("document_id", doc_id).execute()
                        print(f"  UPDATE: {relative} (content changed)")
                        added += 1
                        do_insert = False
            except Exception:
                do_insert = True

        # Insert new document if not found
        if do_insert:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    doc_data = {
                        "code": code,
                        "title": title,
                        "document_type": document_type,
                        "equipment_type": equipment_type,
                        "full_text": text_content,
                        "source": "system_docs",
                        "summary": summary,
                        "keywords": keywords,
                        "indexing_status": "pending",
                    }

                    result = client.table("documents").insert(doc_data).execute()
                    if result.data:
                        doc_id = result.data[0]["id"]
                    else:
                        print(f"  ERROR (no data): {relative}")
                        errors += 1
                        continue
                    break  # Success, exit retry loop

                except Exception as e:
                    error_msg = str(e)
                    if "duplicate key" in error_msg:
                        print(f"  SKIP (duplicate): {relative}")
                        skipped += 1
                        break
                    elif attempt < max_retries - 1:
                        wait = (attempt + 1) * 2
                        print(f"  RETRY ({attempt + 1}/{max_retries}): {relative} — waiting {wait}s...")
                        time.sleep(wait)
                    else:
                        print(f"  ERROR: {relative}: {error_msg[:100]}")
                        errors += 1
                        continue

        # Chunk and embed — runs for both new inserts and content updates
        if doc_id:
            try:
                chunk_count = vector_db.chunk_and_embed_markdown(
                    doc_id,
                    doc_title=title,
                    doc_type=document_type,
                )
                if do_insert:
                    print(f"  ADD: {relative} ({chunk_count} chunks, type={document_type})")
            except Exception as e:
                print(f"  ERROR (chunking): {relative}: {e}")
                errors += 1

        # Throttle to avoid overwhelming Supabase connection pool
        if (i + 1) % 5 == 0:
            time.sleep(0.5)

    # Summary
    print(f"\n{'=' * 55}")
    print("Ingestion Complete!")
    print(f"  Added:   {added}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors:  {errors}")

    # Get counts
    try:
        doc_count = client.table("documents").select("id", count="exact").execute().count or 0
        chunk_count = client.table("document_chunks").select("id", count="exact").execute().count or 0
        knowledge_count = client.table("equipment_knowledge").select("id", count="exact").execute().count or 0

        print("\nTotal RAG content:")
        print(f"  Documents:       {doc_count}")
        print(f"  Document chunks: {chunk_count}")
        print(f"  Knowledge base:  {knowledge_count}")
    except Exception as e:
        print(f"Error getting counts: {e}")

    # ---------------------------------------------------------------
    # Phase 2: Ingest inspection checklist templates as documents
    # ---------------------------------------------------------------
    print(f"\n{'=' * 55}")
    print("Phase 2: Ingesting inspection checklist templates...")

    checklist_path = Path(__file__).parent.parent / "app" / "data" / "inspection_checklist_templates.json"
    if checklist_path.exists():
        import json

        with open(checklist_path, encoding="utf-8") as f:
            checklist_data = json.load(f)

        templates = checklist_data.get("templates", checklist_data)
        if not isinstance(templates, dict):
            print("  WARN: unexpected checklist structure, skipping")
        else:
            for template_key, template in templates.items():
                code = f"DOC-CHECKLIST-{template_key.upper()}"
                equipment_type = template.get("equipment_type", "general")
                template_name = template.get("template_name", template_key)
                items = template.get("checklist_items", [])

                if not items:
                    continue

                # Check if already exists
                if not force:
                    try:
                        existing = client.table("documents").select("id").eq("code", code).execute()
                        if existing.data:
                            print(f"  SKIP (exists): {template_key}")
                            skipped += 1
                            continue
                    except Exception:
                        pass

                # Convert checklist to markdown prose for RAG
                md_lines = [
                    f"# {template_name}",
                    "",
                    f"Equipment type: {equipment_type}",
                    f"Items: {len(items)}",
                    "",
                    "## Checklist Items",
                    "",
                ]
                for item in items:
                    question = item.get("question", item.get("item_id", ""))
                    category = item.get("category", "")
                    item_type = item.get("item_type", "checklist")
                    unit = item.get("unit", "")
                    tol_min = item.get("tolerance_min")
                    tol_max = item.get("tolerance_max")

                    line = f"- **{question}**"
                    if category:
                        line += f" (Category: {category})"
                    if item_type == "measurement" and unit:
                        line += f" — Measurement in {unit}"
                        if tol_min is not None and tol_max is not None:
                            line += f", acceptable range {tol_min}–{tol_max} {unit}"
                    if item.get("options"):
                        opts = ", ".join(o.get("label", "") for o in item["options"])
                        line += f" — Options: {opts}"
                    md_lines.append(line)

                full_text = "\n".join(md_lines)
                summary = f"Inspection checklist for {equipment_type}: {template_name} ({len(items)} items)"
                keywords = [equipment_type, "inspection", "checklist", "maintenance", template_key]

                try:
                    doc_data = {
                        "code": code,
                        "title": template_name,
                        "document_type": "maintenance_procedure",
                        "equipment_type": equipment_type,
                        "full_text": full_text,
                        "source": "system_docs",
                        "summary": summary,
                        "keywords": keywords,
                        "indexing_status": "pending",
                    }

                    result = client.table("documents").insert(doc_data).execute()
                    if result.data:
                        doc_id = result.data[0]["id"]
                        chunk_count = vector_db.chunk_and_embed_markdown(
                            doc_id,
                            doc_title=template_name,
                            doc_type="maintenance_procedure",
                        )
                        print(f"  ADD: {template_key} ({chunk_count} chunks, type={equipment_type})")
                        added += 1
                    else:
                        print(f"  ERROR (no data): {template_key}")
                        errors += 1
                except Exception as e:
                    error_msg = str(e)
                    if "duplicate key" in error_msg:
                        print(f"  SKIP (duplicate): {template_key}")
                        skipped += 1
                    else:
                        print(f"  ERROR: {template_key}: {error_msg[:100]}")
                        errors += 1
    else:
        print(f"  WARN: checklist file not found at {checklist_path}")

    # Updated totals
    try:
        doc_count = client.table("documents").select("id", count="exact").execute().count or 0
        chunk_count_total = client.table("document_chunks").select("id", count="exact").execute().count or 0
        print(f"\nUpdated RAG totals: {doc_count} documents, {chunk_count_total} chunks")
    except Exception as e:
        print(f"Error getting updated counts: {e}")

    # Test search with system docs
    print(f"\n{'=' * 55}")
    print("Testing system documentation search...")

    test_queries = [
        ("niagara bacnet integration", None),
        ("point discovery classification", None),
        ("safety interlocks engine", None),
        ("remote operations dispatch", None),
        ("obix historical data alarms", None),
        ("information security risk register", None),
        ("incident response policy", None),
        ("data privacy POPIA compliance", None),
        ("FirstRand supplier security assessment", None),
        ("business continuity disaster recovery", None),
        # Checklist-specific queries
        ("chiller inspection vibration compressor", None),
        ("generator weekly maintenance checklist", None),
        ("UPS battery inspection Eaton", None),
    ]

    for query, _eq_type in test_queries:
        print(f"\nQuery: '{query}'")
        results = vector_db.search(query, n_results=3, similarity_threshold=0.2)
        if results:
            for r in results:
                title = r.get("section_title") or r.get("document_type", "unknown")
                sim = r.get("similarity", 0)
                content_preview = r.get("content", "")[:80]
                print(f"  [{sim:.3f}] {title}: {content_preview}...")
        else:
            print("  No results found")


if __name__ == "__main__":
    asyncio.run(main())
