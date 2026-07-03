#!/usr/bin/env python3
"""Re-embed document intelligence corpus after an embedding dimension migration.

Dry-run by default. Use --execute only after the pgvector migration, Voyage
provider env, and corpus/source availability have been confirmed.
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.supabase_client import get_supabase_client
from app.services.concept_vector_db import get_concept_vector_db_service
from app.services.embedding_service import get_embedding_service
from app.services.vector_db import get_vector_db_service

DEFAULT_CHECKPOINT_FILE = "/tmp/sentinel-reembed-document-corpus-checkpoint.json"


def _fetch_rows(client, table: str, *, document_id: str | None, limit: int | None) -> list[dict]:
    query = (
        client.table(table)
        .select("id, title, document_type, indexing_status, full_text")
        .not_.is_("full_text", "null")
        .order("id")
    )
    if document_id:
        query = query.eq("id", document_id)
    if limit:
        query = query.limit(limit)
    result = query.execute()
    return result.data or []


def _estimate_tokens(text: str) -> int:
    """Rough planning estimate, not provider billing truth."""
    return max(1, len(text) // 4) if text else 0


def _load_checkpoint(path: Path) -> dict:
    if not path.exists():
        return {"completed": {}, "failed": {}}
    with path.open() as fh:
        data = json.load(fh)
    data.setdefault("completed", {})
    data.setdefault("failed", {})
    return data


def _write_checkpoint(path: Path, checkpoint: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w") as fh:
        json.dump(checkpoint, fh, indent=2, sort_keys=True)
        fh.write("\n")
    tmp_path.replace(path)


def _checkpoint_key(namespace: str, row_id: str) -> str:
    return f"{namespace}:{row_id}"


def _is_completed(checkpoint: dict, namespace: str, row_id: str) -> bool:
    return _checkpoint_key(namespace, row_id) in checkpoint["completed"]


def _doc_class_for_row(row: dict) -> str:
    return "system" if row.get("source") == "system_docs" else "site"


def _mark_completed(checkpoint: dict, namespace: str, row_id: str, detail: dict) -> None:
    key = _checkpoint_key(namespace, row_id)
    checkpoint["completed"][key] = {"completed_at": datetime.now(UTC).isoformat(), **detail}
    checkpoint["failed"].pop(key, None)


def _mark_failed(checkpoint: dict, namespace: str, row_id: str, exc: Exception) -> None:
    checkpoint["failed"][_checkpoint_key(namespace, row_id)] = {
        "failed_at": datetime.now(UTC).isoformat(),
        "error": repr(exc),
    }


def _print_dry_run(namespace: str, rows: list[dict]) -> None:
    total_tokens = 0
    for row in rows:
        estimated_tokens = _estimate_tokens(row.get("full_text") or "")
        total_tokens += estimated_tokens
        print(f"[dry-run] {namespace} {row['id']} {row.get('title', '')} estimated_tokens={estimated_tokens}")
    print(f"[dry-run] {namespace} rows={len(rows)} estimated_tokens={total_tokens}")


def _reembed_documents(
    client,
    *,
    document_id: str | None,
    limit: int | None,
    execute: bool,
    checkpoint: dict,
    checkpoint_file: Path,
) -> int:
    vector_db = get_vector_db_service(client)
    rows = _fetch_rows(client, "documents", document_id=document_id, limit=limit)
    if not execute:
        _print_dry_run("documents", rows)
        return len(rows)

    total_chunks = 0
    for row in rows:
        doc_id = row["id"]
        if _is_completed(checkpoint, "documents", doc_id):
            print(f"[skip] documents {doc_id}: already completed in checkpoint")
            continue
        try:
            client.table("document_chunks").delete().eq("document_id", doc_id).execute()
            chunk_count = vector_db.chunk_and_embed_markdown(
                document_id=doc_id,
                doc_class=_doc_class_for_row(row),
                doc_title=row.get("title", ""),
                doc_type=row.get("document_type", ""),
            )
        except Exception as exc:
            _mark_failed(checkpoint, "documents", doc_id, exc)
            _write_checkpoint(checkpoint_file, checkpoint)
            raise

        _mark_completed(checkpoint, "documents", doc_id, {"chunks": chunk_count})
        _write_checkpoint(checkpoint_file, checkpoint)
        total_chunks += chunk_count
        print(f"[embedded] documents {doc_id}: {chunk_count} chunks")
    return total_chunks


def _reembed_concept_documents(
    client,
    *,
    document_id: str | None,
    limit: int | None,
    execute: bool,
    checkpoint: dict,
    checkpoint_file: Path,
) -> int:
    vector_db = get_concept_vector_db_service(client)
    rows = _fetch_rows(client, "concept_documents", document_id=document_id, limit=limit)
    if not execute:
        _print_dry_run("concept_documents", rows)
        return len(rows)

    total_chunks = 0
    for row in rows:
        doc_id = row["id"]
        if _is_completed(checkpoint, "concept_documents", doc_id):
            print(f"[skip] concept_documents {doc_id}: already completed in checkpoint")
            continue
        try:
            client.table("concept_document_chunks").delete().eq("document_id", doc_id).execute()
            chunk_count = vector_db.chunk_and_embed_document(doc_id)
        except Exception as exc:
            _mark_failed(checkpoint, "concept_documents", doc_id, exc)
            _write_checkpoint(checkpoint_file, checkpoint)
            raise

        _mark_completed(checkpoint, "concept_documents", doc_id, {"chunks": chunk_count})
        _write_checkpoint(checkpoint_file, checkpoint)
        total_chunks += chunk_count
        print(f"[embedded] concept_documents {doc_id}: {chunk_count} chunks")
    return total_chunks


def _reembed_equipment_knowledge(
    client,
    *,
    limit: int | None,
    execute: bool,
    checkpoint: dict,
    checkpoint_file: Path,
) -> int:
    embedding_service = get_embedding_service()
    query = client.table("equipment_knowledge").select("id, title, description, symptoms, code")
    query = query.order("id")
    if limit:
        query = query.limit(limit)
    rows = query.execute().data or []
    if not execute:
        for row in rows:
            text = f"{row.get('title') or ''}. {row.get('description') or ''}"
            print(
                f"[dry-run] equipment_knowledge {row['id']} {row.get('title', '')} "
                f"estimated_tokens={_estimate_tokens(text)}"
            )
        return len(rows)

    for row in rows:
        row_id = row["id"]
        if _is_completed(checkpoint, "equipment_knowledge", row_id):
            print(f"[skip] equipment_knowledge {row_id}: already completed in checkpoint")
            continue
        text = f"{row.get('title') or ''}. {row.get('description') or ''}"
        if row.get("symptoms"):
            text += f" Symptoms: {', '.join(row['symptoms'])}"
        if row.get("code"):
            text += f" Fault code: {row['code']}"
        try:
            client.table("equipment_knowledge").update({"embedding": embedding_service.embed_document(text)}).eq(
                "id", row_id
            ).execute()
        except Exception as exc:
            _mark_failed(checkpoint, "equipment_knowledge", row_id, exc)
            _write_checkpoint(checkpoint_file, checkpoint)
            raise

        _mark_completed(checkpoint, "equipment_knowledge", row_id, {"chunks": 1})
        _write_checkpoint(checkpoint_file, checkpoint)
        print(f"[embedded] equipment_knowledge {row_id}")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="perform writes; default is dry-run")
    parser.add_argument("--document-id", help="limit document re-embed to one UUID")
    parser.add_argument("--limit", type=int, help="limit rows per table for staged runs")
    parser.add_argument("--skip-documents", action="store_true")
    parser.add_argument("--include-concept", action="store_true")
    parser.add_argument("--include-knowledge", action="store_true")
    parser.add_argument("--checkpoint-file", default=DEFAULT_CHECKPOINT_FILE)
    parser.add_argument("--reset-checkpoint", action="store_true")
    args = parser.parse_args()

    checkpoint_file = Path(args.checkpoint_file)
    if args.reset_checkpoint and checkpoint_file.exists():
        checkpoint_file.unlink()
    checkpoint = _load_checkpoint(checkpoint_file)

    client = get_supabase_client()
    embedding_service = get_embedding_service()
    provider_info = embedding_service.provider_info()
    print(
        "Embedding provider:",
        provider_info["provider"],
        provider_info["model"],
        provider_info["dimension"],
    )
    print("Mode:", "execute" if args.execute else "dry-run")
    print("Checkpoint:", checkpoint_file if args.execute else "disabled in dry-run")

    total = 0
    if not args.skip_documents:
        total += _reembed_documents(
            client,
            document_id=args.document_id,
            limit=args.limit,
            execute=args.execute,
            checkpoint=checkpoint,
            checkpoint_file=checkpoint_file,
        )
    if args.include_concept:
        total += _reembed_concept_documents(
            client,
            document_id=args.document_id,
            limit=args.limit,
            execute=args.execute,
            checkpoint=checkpoint,
            checkpoint_file=checkpoint_file,
        )
    if args.include_knowledge:
        total += _reembed_equipment_knowledge(
            client,
            limit=args.limit,
            execute=args.execute,
            checkpoint=checkpoint,
            checkpoint_file=checkpoint_file,
        )

    print("Processed:", total)
    if args.execute:
        print("Checkpoint completed:", len(checkpoint["completed"]))
        print("Checkpoint failed:", len(checkpoint["failed"]))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        try:
            from app.services.ai_usage_tracker import usage_tracker

            usage_tracker.flush()
        except Exception:
            pass
