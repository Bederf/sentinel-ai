#!/usr/bin/env python3
"""
Grant module access to a user at a specific site.

Usage:
    python grant_user_modules.py \
        --email grant@grantdemo.co.za \
        --site-code site-002 \
        --modules lighting \
        --granted-by admin@sentinel.bms

Example - Grant DALI (lighting) module to Grant Demo:
    python grant_user_modules.py \
        --email grant@grantdemo.co.za \
        --site-code site-002 \
        --modules lighting \
        --granted-by system
"""

import sys
import argparse
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.repositories.module_access_repository import get_module_access_repository


def main():
    parser = argparse.ArgumentParser(description="Grant module access to a user at a specific site")
    parser.add_argument(
        "--email",
        required=True,
        help="User email address",
    )
    parser.add_argument(
        "--site-code",
        required=True,
        help="Site code (e.g., site-002)",
    )
    parser.add_argument(
        "--modules",
        required=True,
        nargs="+",
        help="Module types to grant (e.g., lighting dali security)",
    )
    parser.add_argument(
        "--granted-by",
        default="system",
        help="Admin email or system identifier",
    )

    args = parser.parse_args()

    # Get repository
    repo = get_module_access_repository()

    # Grant modules
    print(f"Granting modules to {args.email} at {args.site_code}:")
    print(f"  Modules: {', '.join(args.modules)}")
    print(f"  Granted by: {args.granted_by}")

    success = repo.set_user_modules(
        user_email=args.email,
        site_code=args.site_code,
        module_types=args.modules,
        granted_by=args.granted_by,
        replace_existing=True,
    )

    if success:
        # Verify what the user has access to
        effective_modules = repo.get_effective_modules(
            user_email=args.email,
            user_role=None,  # Will include base modules
            site_code=args.site_code,
        )
        print("\n✓ Successfully granted modules!")
        print(f"\nUser {args.email} now has access to at site {args.site_code}:")
        base_mods = ["control", "assets", "simbiot", "integrations", "notifications", "hvac", "energy"]
        print(f"  - Base modules (automatic): {', '.join(sorted(base_mods))}")
        print(f"  - Granted modules: {', '.join(sorted(args.modules))}")
        print(f"  - Total effective: {', '.join(sorted(effective_modules))}")
        return 0
    else:
        print("✗ Failed to grant modules!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
