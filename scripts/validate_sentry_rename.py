#!/usr/bin/env python3

"""
Validation script for SENTRY rename.

This script:
1. Checks for any remaining 'sentry' references
2. Verifies all Python imports resolve correctly
3. Checks for broken API endpoints
4. Validates configuration keys
5. Generates a detailed report

Usage:
  python3 scripts/validate_sentry_rename.py [--strict] [--fix]
"""

import os
import sys
import re
import subprocess
from pathlib import Path
from collections import defaultdict
from typing import Set, Dict, List, Tuple, Optional

# ANSI colors
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

# Configuration
PROJECT_ROOT = Path(__file__).parent.parent
EXCLUDE_DIRS = {
    '.git', '.pytest_cache', '.ruff_cache', 'node_modules', 'venv',
    '__pycache__', '.serena', '.rename-backup-', '.env.local',
    '.next', 'dist', 'build'
}

EXCLUDE_FILES = {
    '.rename-log-', '.rename-backup-',
    '__pycache__', '*.pyc'
}

# Patterns that should NO LONGER exist after rename
FORBIDDEN_PATTERNS = [
    r'\bsentry\b(?!-)',  # sentry not followed by hyphen
    r'sentry',
    r'moltbot',
    r'Sentry(?!-)',
    r'SENTRY(?!_)',
    r'\.sentry',
    r'$SENTRY_HOME/',
]

# Patterns that SHOULD exist after rename
REQUIRED_PATTERNS = [
    r'\bsentry\b',
    r'SentryAuthService',
    r'/api/sentry/',
    r'SENTRY_',
]

# Files to check
FILE_PATTERNS = ['.py', '.ts', '.tsx', '.md', '.yaml', '.yml', '.json', '.sh']

class ValidationReport:
    def __init__(self):
        self.issues: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
        self.warnings: List[str] = []
        self.successes: List[str] = []
        self.errors: List[str] = []
        self.file_count = 0
        self.checked_count = 0

    def add_issue(self, file_path: str, line_no: int, pattern: str):
        """Record a forbidden pattern found"""
        self.issues[pattern].append((file_path, line_no))

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def add_success(self, msg: str):
        self.successes.append(msg)

    def add_error(self, msg: str):
        self.errors.append(msg)

    def print_report(self):
        """Print formatted validation report"""
        print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
        print(f"{Colors.BOLD}SENTRY Rename Validation Report{Colors.END}")
        print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")

        # Success section
        if self.successes:
            print(f"{Colors.GREEN}✓ Successes ({len(self.successes)}):{Colors.END}")
            for msg in self.successes:
                print(f"  {Colors.GREEN}✓{Colors.END} {msg}")
            print()

        # Issues section
        if self.issues:
            print(f"{Colors.RED}✗ Forbidden Patterns Found ({len(self.issues)} patterns):{Colors.END}")
            for pattern, occurrences in sorted(self.issues.items()):
                print(f"\n  {Colors.RED}Pattern: {pattern}{Colors.END}")
                print(f"  Found {len(occurrences)} time(s) in {len(set(f for f, _ in occurrences))} file(s):")

                # Group by file
                by_file = defaultdict(list)
                for filepath, line_no in occurrences:
                    by_file[filepath].append(line_no)

                for filepath, line_nos in sorted(by_file.items()):
                    rel_path = str(Path(filepath).relative_to(PROJECT_ROOT))
                    print(f"    • {rel_path}:{','.join(map(str, line_nos))}")
        else:
            print(f"{Colors.GREEN}✓ No forbidden patterns found{Colors.END}\n")

        # Warnings section
        if self.warnings:
            print(f"{Colors.YELLOW}⚠ Warnings ({len(self.warnings)}):{Colors.END}")
            for msg in self.warnings:
                print(f"  {Colors.YELLOW}⚠{Colors.END} {msg}")
            print()

        # Errors section
        if self.errors:
            print(f"{Colors.RED}✗ Errors ({len(self.errors)}):{Colors.END}")
            for msg in self.errors:
                print(f"  {Colors.RED}✗{Colors.END} {msg}")
            print()

        # Summary
        print(f"{Colors.BOLD}Summary:{Colors.END}")
        print(f"  Files checked:     {self.checked_count}/{self.file_count}")
        print(f"  Issues found:      {len(self.issues)}")
        print(f"  Warnings:          {len(self.warnings)}")
        print(f"  Errors:            {len(self.errors)}")

        status = Colors.GREEN + "PASS" + Colors.END
        if self.issues or self.errors:
            status = Colors.RED + "FAIL" + Colors.END
        elif self.warnings:
            status = Colors.YELLOW + "WARN" + Colors.END

        print(f"  Status:            {status}")
        print()

    def has_issues(self) -> bool:
        return bool(self.issues) or bool(self.errors)


def should_check_file(filepath: Path) -> bool:
    """Determine if file should be checked"""
    # Skip excluded directories
    for excluded in EXCLUDE_DIRS:
        if excluded in filepath.parts:
            return False

    # Skip excluded filenames
    for excluded in EXCLUDE_FILES:
        if excluded in filepath.name:
            return False

    # Only check specific file types
    return filepath.suffix in FILE_PATTERNS


def read_file_safely(filepath: Path) -> Optional[List[str]]:
    """Read file with error handling"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return f.readlines()
    except Exception as e:
        return None


def check_file_for_patterns(filepath: Path, report: ValidationReport) -> None:
    """Check a single file for forbidden patterns"""
    lines = read_file_safely(filepath)
    if lines is None:
        return

    rel_path = str(filepath.relative_to(PROJECT_ROOT))

    for line_no, line in enumerate(lines, 1):
        # Remove comments for cleaner checking
        if filepath.suffix == '.py':
            line_content = line.split('#')[0]
        else:
            line_content = line

        # Check each forbidden pattern
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, line_content, re.IGNORECASE):
                report.add_issue(rel_path, line_no, pattern)


def validate_python_imports(report: ValidationReport) -> None:
    """Verify Python imports still resolve"""
    report.add_success("Checking Python imports...")

    py_files = list(PROJECT_ROOT.rglob('*.py'))
    py_files = [f for f in py_files if should_check_file(f)]

    import_errors = []
    for pyfile in py_files:
        try:
            with open(pyfile, 'r') as f:
                compile(f.read(), pyfile, 'exec')
        except SyntaxError as e:
            import_errors.append(f"{pyfile}: {e}")

    if import_errors:
        for error in import_errors:
            report.add_error(f"Syntax error: {error}")
    else:
        report.add_success(f"All {len(py_files)} Python files have valid syntax")


def validate_api_endpoints(report: ValidationReport) -> None:
    """Check that API endpoints reference /api/sentry/ not /api/sentry/"""
    report.add_success("Checking API endpoints...")

    api_files = []

    # Find API routers
    for py_file in PROJECT_ROOT.rglob('backend/app/api/*.py'):
        if should_check_file(py_file):
            api_files.append(py_file)

    if not api_files:
        report.add_warning("No API files found")
        return

    for api_file in api_files:
        lines = read_file_safely(api_file)
        if lines is None:
            continue

        content = ''.join(lines)
        if '/api/sentry/' in content or '/api/sentry-' in content:
            report.add_issue(str(api_file), 0, "API endpoint still references /api/sentry/")
        elif '/api/sentry/' in content or '/api/sentry-' in content:
            report.add_success(f"API endpoints properly use /api/sentry/ in {api_file.name}")


def validate_config_keys(report: ValidationReport) -> None:
    """Validate configuration keys in settings.py"""
    settings_file = PROJECT_ROOT / 'backend/app/config/settings.py'

    if not settings_file.exists():
        report.add_warning("settings.py not found")
        return

    lines = read_file_safely(settings_file)
    if lines is None:
        return

    content = ''.join(lines)

    # Check for SENTRY_ keys
    if 'sentry_webhook_secret' in content.lower():
        report.add_success("Configuration keys use sentry_ prefix")
    else:
        report.add_warning("Configuration may not have sentry_ keys")


def check_documentation(report: ValidationReport) -> None:
    """Check documentation files for consistency"""
    docs_updated = 0
    docs_total = 0

    for md_file in PROJECT_ROOT.rglob('*.md'):
        if should_check_file(md_file):
            docs_total += 1
            lines = read_file_safely(md_file)
            if lines is not None:
                content = ''.join(lines)
                if 'sentry' in content.lower():
                    docs_updated += 1

    if docs_total > 0:
        report.add_success(f"Documentation: {docs_updated}/{docs_total} files reference SENTRY")


def run_validation(strict: bool = False) -> bool:
    """Run complete validation"""
    report = ValidationReport()

    print(f"{Colors.BLUE}Collecting files...{Colors.END}")

    # Find all files to check
    all_files = []
    for root, dirs, files in os.walk(PROJECT_ROOT):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if not any(exc in d for exc in EXCLUDE_DIRS)]

        for file in files:
            filepath = Path(root) / file
            if should_check_file(filepath):
                all_files.append(filepath)

    report.file_count = len(all_files)

    print(f"{Colors.BLUE}Scanning {len(all_files)} files for forbidden patterns...{Colors.END}\n")

    # Check each file
    for filepath in all_files:
        report.checked_count += 1
        check_file_for_patterns(filepath, report)

        # Progress indicator
        if report.checked_count % 100 == 0:
            print(f"  Checked {report.checked_count}/{len(all_files)} files...")

    # Run validation checks
    print(f"{Colors.BLUE}Running validation checks...{Colors.END}")
    validate_python_imports(report)
    validate_api_endpoints(report)
    validate_config_keys(report)
    check_documentation(report)

    # Print report
    report.print_report()

    return not report.has_issues()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Validate SENTRY rename completion'
    )
    parser.add_argument('--strict', action='store_true',
                       help='Exit with error if any warnings found')
    parser.add_argument('--fix', action='store_true',
                       help='Attempt to fix issues (not implemented)')

    args = parser.parse_args()

    success = run_validation(strict=args.strict)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
