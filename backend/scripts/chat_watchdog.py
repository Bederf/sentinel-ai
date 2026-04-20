#!/usr/bin/env python3
"""Chat query watchdog - discovers feature requests from chat queries.

Reads backend/app/data/chat_queries.json, filters trivial queries,
deduplicates via hash, and appends new items to TODO-auto.md.
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path


def load_chat_queries() -> list[dict[str, str]]:
    """Load chat queries from JSON file."""
    queries_path = Path(__file__).parent.parent / "app" / "data" / "chat_queries.json"
    if not queries_path.exists():
        print(f"Warning: {queries_path} not found")
        return []

    with open(queries_path) as f:
        return json.load(f)


def normalize_query(query: str) -> str:
    """Normalize query text for deduplication."""
    # Lowercase and strip whitespace
    normalized = query.strip().lower()

    # Remove extra whitespace
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized


def should_skip_query(query: str) -> bool:
    """Return True if query should be skipped (trivial/status queries)."""
    normalized = normalize_query(query)

    # Skip short queries
    if len(normalized) < 5:
        return True

    # Skip test queries
    if normalized == "test":
        return True

    # Skip common status queries
    skip_patterns = [
        r"^what is the system status\??$",
        r"^summarize equipment status",
        r"^hi$",
        r"^hello$",
        r"^good day",
        r"^good day\. give me a quick overview",
    ]

    for pattern in skip_patterns:
        if re.match(pattern, normalized):
            return True

    return False


def hash_query(query: str) -> str:
    """Generate SHA256 hash for normalized query deduplication."""
    normalized = normalize_query(query)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]  # 16 chars for readability


def load_existing_hashes(todo_path: Path) -> set[str]:
    """Extract hashes from existing TODO-auto.md entries."""
    if not todo_path.exists():
        return set()

    existing_hashes = set()
    hash_pattern = re.compile(r"hash:\s*([a-f0-9]{16})")

    try:
        with open(todo_path) as f:
            content = f.read()
            for match in hash_pattern.finditer(content):
                existing_hashes.add(match.group(1))
    except Exception as e:
        print(f"Warning: Could not read existing TODO-auto.md: {e}")

    return existing_hashes


def format_todo_entry(query: str, query_hash: str, timestamp: str) -> str:
    """Format a TODO entry with proper timestamp and hash."""
    # Clean up query for display (escape brackets if needed)
    display_query = query.strip()
    if "[" in display_query or "]" in display_query:
        # Replace brackets to avoid Markdown issues
        display_query = display_query.replace("[", "(").replace("]", ")")

    # Parse and format timestamp
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        date_str = dt.strftime("%Y-%m-%d")
    except Exception:
        date_str = timestamp[:10] if len(timestamp) >= 10 else "unknown"

    return f"- [ ] **[INVESTIGATE][P2]** {display_query} (first seen: {date_str}, hash: {query_hash})\n"


def main():
    """Main watchdog execution."""
    print("Chat query watchdog starting...")

    # Load chat queries
    queries = load_chat_queries()
    print(f"Loaded {len(queries)} chat queries")

    # Filter and process
    new_items = []
    seen_hashes = set()

    for entry in queries:
        query = entry.get("query", "")
        timestamp = entry.get("timestamp", "")

        if not query or not timestamp:
            continue

        # Skip trivial queries
        if should_skip_query(query):
            continue

        # Generate hash for deduplication
        query_hash = hash_query(query)

        # Skip if already seen in this batch (duplicate queries in log)
        if query_hash in seen_hashes:
            continue
        seen_hashes.add(query_hash)

        new_items.append({"query": query, "hash": query_hash, "timestamp": timestamp})

    print(f"Found {len(new_items)} non-trivial unique queries after filtering")

    if not new_items:
        print("No new items to process")
        return

    # Load existing TODO-auto.md
    todo_path = Path("/home/bederf/sentinel-vault/99-Tasks/TODO-auto.md")
    existing_hashes = load_existing_hashes(todo_path)

    # Filter out items already in TODO-auto.md
    truly_new_items = [item for item in new_items if item["hash"] not in existing_hashes]

    print(f"Found {len(truly_new_items)} new items not in TODO-auto.md")

    if not truly_new_items:
        print("All items already in TODO-auto.md")
        return

    # Prepare new entries
    entries_text = ""
    for item in truly_new_items:
        entries_text += format_todo_entry(item["query"], item["hash"], item["timestamp"])

    # Write to TODO-auto.md
    try:
        # Ensure directory exists
        todo_path.parent.mkdir(parents=True, exist_ok=True)

        # Append or create file
        if todo_path.exists():
            with open(todo_path, "a") as f:
                f.write("\n" + entries_text)
            print(f"Appended {len(truly_new_items)} items to {todo_path}")
        else:
            # Create with header
            header = "# Auto-Generated TODO Items from Chat Queries\n\n"
            header += "## P2 - Auto-Discovered Feature Requests\n\n"
            header += "*Generated by chat_watchdog.py*\n\n"

            with open(todo_path, "w") as f:
                f.write(header + entries_text)
            print(f"Created new {todo_path} with {len(truly_new_items)} items")

        # Print summary of added items
        for i, item in enumerate(truly_new_items[:5], 1):
            query_preview = item["query"][:50] + "..." if len(item["query"]) > 50 else item["query"]
            print(f"  {i}. {query_preview}")

        if len(truly_new_items) > 5:
            print(f"  ... and {len(truly_new_items) - 5} more")

    except Exception as e:
        print(f"Error writing to TODO-auto.md: {e}")


if __name__ == "__main__":
    main()
