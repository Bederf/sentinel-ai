#!/usr/bin/env python3
"""
Validate frontmatter metadata in all markdown documentation files.

Checks:
- Frontmatter exists (--- ... ---)
- YAML is valid
- Required fields are present
- Field values match expected types/enums
- Date format is YYYY-MM-DD
- Version is semver compliant
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

# Required frontmatter fields
REQUIRED_FIELDS = [
    'title',
    'type',
    'status',
    'version',
    'created',
    'updated',
    'tags',
    'domain',
    'audience',
    'complexity',
    'estimated_read_time',
]

# Optional fields
OPTIONAL_FIELDS = [
    'author',
    'reviewer',
    'related',
]

# Enum field validators
TYPE_VALUES = ['architecture', 'guide', 'reference', 'spec', 'tutorial', 'audit', 'policy']
STATUS_VALUES = ['draft', 'review', 'approved', 'deprecated']
DOMAIN_VALUES = ['bms', 'hvac', 'lighting', 'security', 'water', 'solar', 'compliance', 'general']
AUDIENCE_VALUES = ['developers', 'operators', 'product-managers', 'safety-engineers', 'all']
COMPLEXITY_VALUES = ['beginner', 'intermediate', 'advanced']


def validate_date(date_str: str) -> Tuple[bool, str]:
    """Validate date format YYYY-MM-DD."""
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True, ""
    except ValueError:
        return False, f"Invalid date format: {date_str} (expected YYYY-MM-DD)"


def validate_version(version_str: str) -> Tuple[bool, str]:
    """Validate semantic version."""
    pattern = r'^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$'
    if not re.match(pattern, version_str):
        return False, f"Invalid version: {version_str} (expected semver like 1.0.0)"
    return True, ""


def validate_frontmatter(file_path: Path) -> List[Tuple[str, str]]:
    """
    Validate frontmatter in a markdown file.

    Returns:
        List of (error_type, message) tuples. Empty if valid.
    """
    errors = []

    # Read file
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return [('FATAL', f'Cannot read file: {e}')]

    # Extract frontmatter
    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not match:
        errors.append(('FRONTMATTER', 'No frontmatter found (expected --- ... ---)'))
        return errors

    # Parse YAML
    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        errors.append(('YAML', f'Invalid YAML: {e}'))
        return errors

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in frontmatter:
            errors.append(('REQUIRED', f"Missing required field: '{field}'"))

    # Validate field types and enums
    if 'title' in frontmatter:
        if not isinstance(frontmatter['title'], str):
            errors.append(('TYPE', "Field 'title' must be a string"))

    if 'type' in frontmatter:
        if frontmatter['type'] not in TYPE_VALUES:
            errors.append(('ENUM', f"Field 'type' must be one of {TYPE_VALUES}"))

    if 'status' in frontmatter:
        if frontmatter['status'] not in STATUS_VALUES:
            errors.append(('ENUM', f"Field 'status' must be one of {STATUS_VALUES}"))

    if 'version' in frontmatter:
        valid, msg = validate_version(frontmatter['version'])
        if not valid:
            errors.append(('FORMAT', msg))

    if 'created' in frontmatter:
        valid, msg = validate_date(frontmatter['created'])
        if not valid:
            errors.append(('FORMAT', msg))

    if 'updated' in frontmatter:
        valid, msg = validate_date(frontmatter['updated'])
        if not valid:
            errors.append(('FORMAT', msg))

    if 'tags' in frontmatter:
        if not isinstance(frontmatter['tags'], list):
            errors.append(('TYPE', "Field 'tags' must be a list"))
        elif not all(isinstance(tag, str) for tag in frontmatter['tags']):
            errors.append(('TYPE', "All tags must be strings"))

    if 'related' in frontmatter:
        if not isinstance(frontmatter['related'], list):
            errors.append(('TYPE', "Field 'related' must be a list"))
        elif not all(isinstance(link, str) for link in frontmatter['related']):
            errors.append(('TYPE', "All related links must be strings"))

    if 'domain' in frontmatter:
        if frontmatter['domain'] not in DOMAIN_VALUES:
            errors.append(('ENUM', f"Field 'domain' must be one of {DOMAIN_VALUES}"))

    if 'audience' in frontmatter:
        if frontmatter['audience'] not in AUDIENCE_VALUES:
            errors.append(('ENUM', f"Field 'audience' must be one of {AUDIENCE_VALUES}"))

    if 'complexity' in frontmatter:
        if frontmatter['complexity'] not in COMPLEXITY_VALUES:
            errors.append(('ENUM', f"Field 'complexity' must be one of {COMPLEXITY_VALUES}"))

    if 'estimated_read_time' in frontmatter:
        if not isinstance(frontmatter['estimated_read_time'], (int, float)):
            errors.append(('TYPE', "Field 'estimated_read_time' must be a number"))
        elif frontmatter['estimated_read_time'] <= 0:
            errors.append(('VALUE', "Field 'estimated_read_time' must be positive"))

    return errors


def main():
    parser = argparse.ArgumentParser(description='Validate frontmatter in documentation files')
    parser.add_argument('path', nargs='?', default='docs', help='Path to docs directory (default: docs)')
    parser.add_argument('--strict', action='store_true', help='Exit with error code on validation failures')
    args = parser.parse_args()

    docs_path = Path(args.path)

    if not docs_path.exists():
        print(f"❌ Error: Path does not exist: {docs_path}")
        sys.exit(1)

    # Find all markdown files
    md_files = list(docs_path.rglob('*.md'))

    if not md_files:
        print(f"⚠️  No markdown files found in {docs_path}")
        sys.exit(0)

    print(f"Validating {len(md_files)} markdown files in {docs_path}...\n")

    total_errors = 0
    valid_count = 0

    for md_file in md_files:
        errors = validate_frontmatter(md_file)
        rel_path = md_file.relative_to(docs_path.parent)

        if errors:
            total_errors += len(errors)
            print(f"❌ {rel_path}")
            for error_type, message in errors:
                print(f"   [{error_type}] {message}")
        else:
            valid_count += total_errors
            print(f"✅ {rel_path}")

    # Summary
    print(f"\n{'='*60}")
    print(f"Validated {len(md_files)} files")
    print(f"✅ Valid: {valid_count}")
    print(f"❌ Errors: {total_errors}")
    print(f"{'='*60}")

    if args.strict and total_errors > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
