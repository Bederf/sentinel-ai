"""
Code Search Helpers

Provides functions for searching the codebase by file patterns, content, and symbols.
"""

import fnmatch
import re
from pathlib import Path
from typing import Any

# Root of the BMS intelligence codebase
CODEBASE_ROOT = Path("/opt/bms-intelligence")

# Directories to always exclude
EXCLUDE_DIRS = {
    "__pycache__",
    ".git",
    ".pytest_cache",
    "node_modules",
    ".venv",
    "venv",
    ".next",
    "build",
    "dist",
    ".env",
    ".idea",
    ".vscode",
    "*.egg-info",
}

# File extensions to search
SEARCHABLE_EXTENSIONS = {
    ".py",
    ".tsx",
    ".ts",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".sql",
    ".yaml",
    ".yml",
    ".txt",
    ".html",
    ".css",
    ".scss",
}


def _should_exclude_path(path: Path) -> bool:
    """Check if path should be excluded from search."""
    for exclude in EXCLUDE_DIRS:
        if fnmatch.fnmatch(path.name, exclude) or exclude in str(path):
            return True
    return False


def _should_include_file(path: Path) -> bool:
    """Check if file should be included in search."""
    if path.is_dir():
        return False
    if _should_exclude_path(path):
        return False
    return path.suffix.lower() in SEARCHABLE_EXTENSIONS


def search_files_by_pattern(pattern: str, base_path: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """
    Search for files matching glob pattern.

    Args:
        pattern: Glob pattern (e.g., "*.tsx", "components/**/*.tsx", "backend/app/api/*.py")
        base_path: Optional subdirectory to search in (e.g., "frontend/src")
        limit: Maximum results to return

    Returns:
        List of dicts with keys: path, name, size, type (file/dir)
    """
    root = CODEBASE_ROOT
    if base_path:
        root = root / base_path
        if not root.exists():
            return []

    matches = []
    try:
        # Use rglob for ** patterns, glob for others
        if "**" in pattern:
            for path in root.rglob("*"):
                if fnmatch.fnmatch(str(path.relative_to(root)), pattern):
                    if _should_include_file(path) and len(matches) < limit:
                        matches.append(
                            {
                                "path": str(path.relative_to(CODEBASE_ROOT)),
                                "name": path.name,
                                "type": "directory" if path.is_dir() else "file",
                                "size": path.stat().st_size if path.is_file() else 0,
                            }
                        )
        else:
            for path in root.glob(pattern):
                if _should_include_file(path) and len(matches) < limit:
                    matches.append(
                        {
                            "path": str(path.relative_to(CODEBASE_ROOT)),
                            "name": path.name,
                            "type": "directory" if path.is_dir() else "file",
                            "size": path.stat().st_size if path.is_file() else 0,
                        }
                    )
    except Exception as e:
        return [{"error": f"Search failed: {e!s}"}]

    return sorted(matches, key=lambda x: x["path"])


def search_file_contents(
    query: str, base_path: str | None = None, is_regex: bool = False, limit: int = 20
) -> list[dict[str, Any]]:
    """
    Search file contents for keyword or regex pattern.

    Args:
        query: Keyword or regex pattern to search
        base_path: Optional subdirectory to search in
        is_regex: If True, treat query as regex pattern
        limit: Maximum files to return

    Returns:
        List of dicts with keys: path, matches (list of {line_no, line, context})
    """
    root = CODEBASE_ROOT
    if base_path:
        root = root / base_path
        if not root.exists():
            return []

    matches = []
    try:
        if is_regex:
            pattern = re.compile(query, re.IGNORECASE | re.MULTILINE)
        else:
            query_lower = query.lower()
            pattern = None

        for path in root.rglob("*"):
            if not _should_include_file(path) or len(matches) >= limit:
                continue

            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()

                file_matches = []
                for line_no, line in enumerate(lines, 1):
                    if is_regex:
                        if pattern.search(line):
                            file_matches.append(
                                {
                                    "line_no": line_no,
                                    "line": line.rstrip(),
                                    "context": "".join(lines[max(0, line_no - 2) : min(len(lines), line_no + 1)]),
                                }
                            )
                    else:
                        if query_lower in line.lower():
                            file_matches.append(
                                {
                                    "line_no": line_no,
                                    "line": line.rstrip(),
                                    "context": "".join(lines[max(0, line_no - 2) : min(len(lines), line_no + 1)]),
                                }
                            )

                if file_matches and len(matches) < limit:
                    matches.append(
                        {
                            "path": str(path.relative_to(CODEBASE_ROOT)),
                            "match_count": len(file_matches),
                            "matches": file_matches[:5],  # Limit matches per file
                        }
                    )
            except Exception:
                pass  # Skip files we can't read

    except Exception as e:
        return [{"error": f"Content search failed: {e!s}"}]

    return matches


def search_symbols(
    symbol_name: str,
    base_path: str | None = None,
) -> list[dict[str, Any]]:
    """
    Search for function/class definitions by name.

    Args:
        symbol_name: Name of symbol to search (function or class)
        base_path: Optional subdirectory to search in

    Returns:
        List of dicts with keys: path, type (class/function), name, line_no
    """
    root = CODEBASE_ROOT
    if base_path:
        root = root / base_path
        if not root.exists():
            return []

    # Patterns for function/class definitions
    # Build patterns using string concatenation to avoid f-string issues with special chars
    escaped_name = re.escape(symbol_name)

    py_func_pattern = re.compile(r"^\s*(async\s+)?def\s+" + escaped_name + r"\s*\(")
    py_class_pattern = re.compile(r"^\s*class\s+" + escaped_name + r"[\(:\s]")

    ts_func_pattern = re.compile(r"(function|const|export|async)\s+" + escaped_name + r"\s*[\(:|=]")
    ts_class_pattern = re.compile(r"(class|interface|type)\s+" + escaped_name + r"\s*[{:\|<]")

    matches = []
    try:
        for path in root.rglob("*"):
            if not _should_include_file(path):
                continue

            try:
                with open(path, encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()

                for line_no, line in enumerate(lines, 1):
                    is_py = path.suffix == ".py"
                    is_ts = path.suffix in {".ts", ".tsx", ".js", ".jsx"}

                    symbol_type = None
                    if is_py:
                        if py_func_pattern.search(line):
                            symbol_type = "function"
                        elif py_class_pattern.search(line):
                            symbol_type = "class"
                    elif is_ts:
                        if ts_class_pattern.search(line):
                            symbol_type = "class" if "class" in line else "type"
                        elif ts_func_pattern.search(line):
                            symbol_type = "function"

                    if symbol_type:
                        matches.append(
                            {
                                "path": str(path.relative_to(CODEBASE_ROOT)),
                                "type": symbol_type,
                                "name": symbol_name,
                                "line_no": line_no,
                                "line": line.rstrip(),
                            }
                        )

            except Exception:
                pass  # Skip files we can't read

    except Exception as e:
        return [{"error": f"Symbol search failed: {e!s}"}]

    return matches[:20]  # Limit results


def build_directory_tree(
    base_path: str | None = None, depth: int = 2, exclude_patterns: list[str] | None = None
) -> dict[str, Any]:
    """
    Build directory tree structure.

    Args:
        base_path: Optional subdirectory to start from
        depth: Maximum depth to traverse
        exclude_patterns: List of glob patterns to exclude

    Returns:
        Dict with keys: tree (string), summary (dict with counts)
    """
    root = CODEBASE_ROOT
    if base_path:
        root = root / base_path
        if not root.exists():
            return {"tree": "Path not found", "summary": {}}

    exclude_set = set(exclude_patterns or [])
    lines = []
    file_count = 0
    dir_count = 0

    def _build_tree(path: Path, prefix: str = "", current_depth: int = 0):
        nonlocal file_count, dir_count

        if current_depth >= depth:
            return

        try:
            entries = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
            for i, entry in enumerate(entries):
                if _should_exclude_path(entry):
                    continue

                is_last = i == len(entries) - 1
                current_prefix = "└── " if is_last else "├── "
                next_prefix = "    " if is_last else "│   "

                if entry.is_dir():
                    dir_count += 1
                    lines.append(f"{prefix}{current_prefix}{entry.name}/")
                    _build_tree(entry, prefix + next_prefix, current_depth + 1)
                else:
                    file_count += 1
                    lines.append(f"{prefix}{current_prefix}{entry.name}")
        except PermissionError:
            pass

    lines.append(f"{root.name}/")
    _build_tree(root)

    return {
        "tree": "\n".join(lines),
        "summary": {
            "total_files": file_count,
            "total_directories": dir_count,
            "max_depth": depth,
            "root_path": str(root.relative_to(CODEBASE_ROOT)) if base_path else "/",
        },
    }


def fetch_file_content(file_path: str) -> dict[str, Any]:
    """
    Fetch full content of a file.

    Args:
        file_path: Relative path to file from codebase root

    Returns:
        Dict with keys: content, path, language, lines, size
    """
    full_path = CODEBASE_ROOT / file_path
    full_path = full_path.resolve()

    # Security: Ensure path is within codebase
    try:
        full_path.relative_to(CODEBASE_ROOT.resolve())
    except ValueError:
        return {"error": "Path outside codebase root"}

    if not full_path.exists():
        return {"error": f"File not found: {file_path}"}

    if not full_path.is_file():
        return {"error": f"Not a file: {file_path}"}

    try:
        with open(full_path, encoding="utf-8") as f:
            content = f.read()

        # Detect language from extension
        ext = full_path.suffix.lower()
        lang_map = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".json": "json",
            ".md": "markdown",
            ".sql": "sql",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".html": "html",
            ".css": "css",
            ".scss": "scss",
        }
        language = lang_map.get(ext, "text")

        return {
            "path": file_path,
            "content": content,
            "language": language,
            "lines": len(content.splitlines()),
            "size": len(content),
            "extension": ext,
        }
    except Exception as e:
        return {"error": f"Failed to read file: {e!s}"}
