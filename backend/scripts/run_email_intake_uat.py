#!/usr/bin/env python3
"""Run Phase 131 Email Intake UAT cases against SENTINEL backend.

Usage:
  python backend/scripts/run_email_intake_uat.py \
    --base-url http://localhost:9095 \
    --api-key "$SENTRY_BOT_API_KEY" \
    --secret "$SENTRY_WEBHOOK_SECRET"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib import error, request

DEFAULT_FIXTURE = Path("backend/tests/fixtures/email_intake_uat_cases.json")
INTAKE_PATH = "/api/sentry/email/intake"


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=30) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8")
            return status, json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return exc.code, parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run email intake UAT payloads.")
    parser.add_argument("--base-url", default="http://localhost:9095", help="Backend base URL")
    parser.add_argument("--api-key", required=True, help="X-Sentry-API-Key value")
    parser.add_argument("--secret", required=True, help="X-Sentry-Secret value")
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE), help="Path to UAT JSON fixture")
    args = parser.parse_args()

    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        print(f"[ERROR] Fixture not found: {fixture_path}")
        return 2

    cases = json.loads(fixture_path.read_text(encoding="utf-8"))
    headers = {
        "Content-Type": "application/json",
        "X-Sentry-API-Key": args.api_key,
        "X-Sentry-Secret": args.secret,
    }
    url = f"{args.base_url.rstrip('/')}{INTAKE_PATH}"

    failures = 0
    print(f"Running {len(cases)} UAT cases from {fixture_path} against {url}")

    for case in cases:
        name = case.get("name", "Unnamed case")
        case_type = case.get("type", "backend")
        print(f"\n=== {name} ===")

        if case_type != "backend":
            print("SKIP (n8n-only):")
            print(f"- Expected: {case.get('expected', 'N/A')}")
            n8n_payload = case.get("n8n_webhook_payload")
            if n8n_payload:
                print("- Payload for n8n webhook:")
                print(json.dumps(n8n_payload, indent=2))
            continue

        payload = case.get("payload")
        if not isinstance(payload, dict):
            print("[FAIL] Missing backend payload")
            failures += 1
            continue

        status, resp = _post_json(url, payload, headers)
        expected_action = case.get("expected_action_taken")
        expected_urgency = case.get("expected_urgency")

        got_action = resp.get("action_taken")
        got_urgency = resp.get("urgency")

        print(f"HTTP {status}")
        print(f"action_taken={got_action!r} urgency={got_urgency!r} intake_id={resp.get('intake_id')!r}")

        case_failed = False
        if status != 200:
            case_failed = True
            print(f"[FAIL] Expected HTTP 200, got {status}")
        if expected_action and got_action != expected_action:
            case_failed = True
            print(f"[FAIL] Expected action_taken={expected_action!r}, got {got_action!r}")
        if expected_urgency and got_urgency != expected_urgency:
            case_failed = True
            print(f"[FAIL] Expected urgency={expected_urgency!r}, got {got_urgency!r}")

        if case_failed:
            failures += 1
            print("[DETAIL] Response:")
            print(json.dumps(resp, indent=2))
        else:
            print("[PASS]")

    print("\n=== UAT Summary ===")
    if failures:
        print(f"FAILED: {failures} case(s)")
        return 1

    print("PASSED: all backend cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
