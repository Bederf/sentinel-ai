#!/usr/bin/env python3
"""Send an email via SENTINEL's configured SMTP transport.

This command bootstraps the backend runtime so it always uses the existing
`backend/.env` SMTP configuration, regardless of the caller's working
directory.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
DEFAULT_RECIPIENT = "bederf@gmail.com"


def _bootstrap_backend() -> None:
    """Ensure backend imports and `.env` loading resolve correctly."""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    os.chdir(BACKEND_DIR)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send an email with SENTINEL's existing SMTP configuration."
    )
    parser.add_argument(
        "--to",
        default=DEFAULT_RECIPIENT,
        help=f"Recipient email address (default: {DEFAULT_RECIPIENT})",
    )
    parser.add_argument("--to-name", help="Optional recipient display name")
    parser.add_argument("--subject", required=True, help="Email subject")
    parser.add_argument("--body", help="Plain-text body")
    parser.add_argument(
        "--body-file",
        type=Path,
        help="Read plain-text body from a file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and print the send summary without sending",
    )
    return parser


def _load_body(args: argparse.Namespace) -> str:
    if args.body:
        return args.body

    if args.body_file:
        return args.body_file.read_text(encoding="utf-8")

    if not sys.stdin.isatty():
        return sys.stdin.read()

    raise ValueError("Provide --body, --body-file, or pipe the body via stdin.")


async def _run(args: argparse.Namespace) -> int:
    _bootstrap_backend()

    from app.config.settings import settings
    from app.services.email_reply_service import get_email_reply_service

    body_plain = _load_body(args).strip()
    if not body_plain:
        raise ValueError("Email body is empty.")

    service = get_email_reply_service()
    if not service.is_configured():
        print("SENTINEL SMTP is not configured.", file=sys.stderr)
        return 1

    if args.dry_run:
        print("dry_run=True")
        print(f"to={args.to}")
        print(f"to_name={args.to_name or ''}")
        print(f"subject={args.subject}")
        print(f"from={settings.email_reply_from_name} <{settings.email_reply_from_address}>")
        print(f"body_chars={len(body_plain)}")
        return 0

    result = await service.send_reply(
        to_email=args.to,
        to_name=args.to_name,
        subject=args.subject,
        body_plain=body_plain,
        body_html=None,
    )

    if not result.sent:
        print(f"sent=False\nerror={result.error or 'unknown error'}", file=sys.stderr)
        return 1

    print("sent=True")
    print(f"message_id={result.message_id or ''}")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
