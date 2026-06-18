#!/usr/bin/env python3
"""
clean_migrations.py — make supabase/migrations fresh-install friendly.

Runs inside a git checkout. It:
  1. Flattens subdirectories and removes non-.sql junk.
  2. Sorts .sql files by the author date of their first commit.
  3. Renames them into a clean, gap-free 001..NNN sequence.

This is meant for the sentinel-ai deployment mirror, where historical
migration numbers are allowed to diverge from the internal working repo.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path


def git_first_author_date(path: Path) -> str:
    """Return ISO-8601 author date of the first commit that added ``path``."""
    result = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%aI", "--", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else "9999-12-31T23:59:59+00:00"


def clean_description(stem: str) -> str:
    """Strip leading numbering and collapse punctuation into underscores."""
    desc = re.sub(r"^(\d+[-_])+", "", stem)
    desc = re.sub(r"[^a-zA-Z0-9]+", "_", desc)
    desc = re.sub(r"_+", "_", desc).strip("_").lower()
    return desc or "migration"


def file_hash(path: Path) -> str:
    """MD5 of file contents for reconciliation."""
    return hashlib.md5(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean and renumber Supabase migrations.")
    parser.add_argument("migrations_dir", type=Path, help="Path to supabase/migrations")
    args = parser.parse_args()

    migrations_dir: Path = args.migrations_dir.resolve()
    if not migrations_dir.is_dir():
        print(f"ERROR: {migrations_dir} is not a directory", file=sys.stderr)
        return 1

    repo_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=migrations_dir,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if not repo_root:
        print("ERROR: migrations_dir must be inside a git repository", file=sys.stderr)
        return 1

    # 1. Discover every .sql file recursively and record its authorship date.
    original_sql = sorted(migrations_dir.rglob("*.sql"))
    if not original_sql:
        print("No migration files found.")
        return 0

    original_hashes = {p: file_hash(p) for p in original_sql}
    meta = {p: git_first_author_date(p) for p in original_sql}

    # 2. Flatten all .sql files into migrations_dir.
    flattened: dict[Path, Path] = {}  # new_path -> original_path
    for original in original_sql:
        target = migrations_dir / original.name
        if target.exists() and target != original:
            slug = re.sub(r"[^a-zA-Z0-9]+", "_", original.parent.name).strip("_").lower()
            target = migrations_dir / f"{slug}_{original.name}"
        shutil.move(str(original), str(target))
        flattened[target] = original

    # 3. Remove everything else under migrations_dir.
    removed = 0
    for entry in list(migrations_dir.iterdir()):
        if entry in flattened:
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
            removed += 1
            print(f"removed dir:  {entry.name}")
        elif entry.suffix != ".sql":
            entry.unlink()
            removed += 1
            print(f"removed file: {entry.name}")

    # 4. Verify no .sql content was lost.
    final_sql = sorted(migrations_dir.glob("*.sql"))
    final_hashes = {flattened[p]: file_hash(p) for p in final_sql}

    if len(final_sql) != len(original_sql):
        print(
            f"ERROR: migration count mismatch: {len(original_sql)} source -> {len(final_sql)} final",
            file=sys.stderr,
        )
        return 1

    missing = [p for p in original_sql if original_hashes[p] != final_hashes.get(p)]
    if missing:
        print(
            f"ERROR: {len(missing)} source migration(s) lost or altered during flattening",
            file=sys.stderr,
        )
        for p in missing:
            print(f"  - {p}", file=sys.stderr)
        return 1

    # 5. Sort by true authorship order and renumber.
    #    Use temporary names first so final targets never collide with source paths.
    ordered = sorted(
        final_sql,
        key=lambda p: (meta[flattened[p]], flattened[p].name),
    )

    width = max(3, len(str(len(ordered))))
    staged: list[tuple[int, Path, Path]] = []
    for idx, old_path in enumerate(ordered, start=1):
        tmp_path = migrations_dir / f".clean_stage_{idx:0{width}d}.sql"
        old_path.rename(tmp_path)
        staged.append((idx, tmp_path, flattened[old_path]))

    for idx, tmp_path, original_path in staged:
        desc = clean_description(original_path.stem)
        new_name = f"{idx:0{width}d}_{desc}.sql"
        new_path = migrations_dir / new_name
        tmp_path.rename(new_path)
        print(f"{idx:0{width}d} <- {original_path.name}")

    print(f"\nCleaned {removed} non-migration entries and renumbered {len(ordered)} migrations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
